#include "pdm_ota.h"
#include "pdm_log.h"
#include "HV_P2P_SRVR_Authority_OTA.h"

#include <ETH.h>
#include <Preferences.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <atomic>
#include <cstring>

namespace {
using namespace HVP2PAuthorityOTA;
constexpr char ROLE[] = "PDM";
constexpr char TARGET[] = "OLIMEX_ESP32_POE_ISO";
constexpr char TOKEN[] = "HV_P2P_FW_ROLE=PDM;HV_P2P_FW_TARGET=OLIMEX_ESP32_POE_ISO;HV_P2P_FW_VERSION="
                         HV_PDM_FIRMWARE_VERSION ";";
constexpr size_t APP_SLOT_BYTES = 0x1e0000;
const IPAddress DEFAULT_AUTHORITY(172, 20, 1, 100);
enum class Phase : uint8_t {
  Searching, Current, Downloading, Verifying, Restarting, Failed, PermitRetry, StorageBusy, Bootstrap, Newer
};
std::atomic<Phase> phase{Phase::Searching};
std::atomic<unsigned> percent{0};
std::atomic<uint32_t> authority{0};
portMUX_TYPE offerLock = portMUX_INITIALIZER_UNLOCKED;
uint32_t offeredAuthority = 0;
uint64_t offerExpiresAt = 0;
TaskHandle_t otaTask = nullptr;
bool pinAuthority = false;

bool validAuthorityIp(const IPAddress& ip) {
  return ip[0] != 0 && ip[0] != 127 && ip[0] < 224;
}

uint32_t currentOffer() {
  const uint64_t now = uptimeMs();
  portENTER_CRITICAL(&offerLock);
  const uint32_t peer = now < offerExpiresAt ? offeredAuthority : 0;
  portEXIT_CRITICAL(&offerLock);
  return peer;
}

void setOffer(uint32_t peer) {
  const uint64_t expires = peer ? uptimeMs() + 60000 : 0;
  portENTER_CRITICAL(&offerLock);
  offeredAuthority = peer;
  offerExpiresAt = expires;
  portEXIT_CRITICAL(&offerLock);
}

void progress(size_t received, size_t total, const char* stage) {
  percent.store(total ? 100ULL * received / total : 0);
  phase.store(!strcmp(stage, "Downloading") ? Phase::Downloading : Phase::Verifying);
}

bool hasOtaSlots() {
  const esp_partition_t* next = esp_ota_get_next_update_partition(nullptr);
  const auto* boot = esp_ota_get_running_partition();
  const auto* data = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_OTA, nullptr);
  return data && boot && next && boot->address != next->address &&
         boot->size >= APP_SLOT_BYTES && next->size >= APP_SLOT_BYTES;
}

bool verifyPermit(const IPAddress& peer, const Manifest& manifest, String& error) {
  const auto accepted = (uint32_t)peer;
  if (!ETH.linkUp() || !ETH.hasIP() || (accepted != authority.load() && accepted != currentOffer())) {
    error = "permit_ethernet_or_authority_changed";
    return false;
  }
  const IPAddress local = ETH.localIP();
  if (!fetchUpdatePermit(peer, manifest, local, error)) return false;
  if (!ETH.linkUp() || !ETH.hasIP() || ETH.localIP() != local ||
      (accepted != authority.load() && accepted != currentOffer())) {
    error = "permit_ethernet_or_authority_changed";
    return false;
  }
  return true;
}

bool canCommit(const IPAddress& peer, const Manifest& manifest, String& error) {
  // Pause at the SD worker's record boundary and confirm the selected
  // authority and image again after the flush, before activating the slot.
  if (!verifyPermit(peer, manifest, error)) return false;
  if (!pauseLogForUpdate(1500)) {
    error = "sd_writer_pause_timeout";
    return false;
  }
  return verifyPermit(peer, manifest, error);
}

void reportFailure(Phase next, const IPAddress& peer, const String& error) {
  static String lastError;
  static IPAddress lastPeer;
  if (phase.exchange(next) != next || error != lastError || peer != lastPeer) {
    Serial.printf("PDM OTA: SRVR %s:%u %s\n", peer.toString().c_str(), (unsigned)AUTHORITY_PORT, error.c_str());
    lastError = error;
    lastPeer = peer;
  }
}

bool checkManifest(const IPAddress& peer, const IPAddress& local, Manifest& manifest, String& error) {
  if (!fetchManifest(peer, ROLE, manifest, error, local)) return false;
  uint32_t versionParts[4];
  if (manifest.release == manifest.version && manifest.role == ROLE && manifest.target == TARGET &&
      parseVersion(manifest.version, versionParts) && isSha256Hex(manifest.bundleId) && manifest.size <= APP_SLOT_BYTES) {
    return true;
  }
  error = "manifest_release_target_or_size";
  return false;
}

void waitForFirmwareCheck(uint32_t ms) {
  ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(ms));
}

void otaWorker(void*) {
  String checkedDigest;
  bool exactImage = false;
  for (;;) {
    percent.store(0);
    IPAddress peer(authority.load());
    const IPAddress offered(currentOffer());
    if (!ETH.linkUp() || !ETH.hasIP()) {
      reportFailure(Phase::Searching, peer, "ethernet_unavailable");
      waitForFirmwareCheck(5000);
      continue;
    }
    // The HTTP dashboard can be busy when the link is restored. Select the
    // OTA route here as well as in the dashboard loop.
    if (!ETH.isDefault()) ETH.setDefault();
    const IPAddress local = ETH.localIP();
    // An SRVR that can reach this PDM can ask it to check its own release.
    // Keep the saved address for normal polling and as a fallback.
    if ((uint32_t)offered) peer = offered;
    Manifest manifest;
    String error;
    bool found = checkManifest(peer, local, manifest, error);
    const IPAddress configured(authority.load());
    if (!found && configured != peer) {
      peer = configured;
      found = checkManifest(peer, local, manifest, error);
    }
    if (!found) {
      reportFailure(error == "manifest_release_target_or_size" ? Phase::Failed : Phase::Searching, peer, error);
    } else {
      bool versionValid = false;
      const int relation = compareVersions(HV_PDM_FIRMWARE_VERSION, manifest.version, versionValid);
      if (!versionValid) {
        reportFailure(Phase::Failed, peer, "manifest_release_target_or_size");
      } else if (relation > 0) {
        phase.store(Phase::Newer);
      } else {
        if (relation == 0 && checkedDigest != manifest.sha256) {
          String running;
          if (!hashRunningPrefix(manifest.size, running, error)) {
            reportFailure(Phase::Failed, peer, error);
            waitForFirmwareCheck(5000);
            continue;
          }
          exactImage = running == manifest.sha256;
          checkedDigest = manifest.sha256;
        }
        if (relation == 0 && exactImage) {
          phase.store(Phase::Current);
        } else if (!verifyPermit(peer, manifest, error)) {
          reportFailure(Phase::PermitRetry, peer, error);
        } else {
          if (downloadAndStage(peer, manifest, ROLE, TARGET, local, error, progress, canCommit)) {
            phase.store(Phase::Restarting);
            ESP.restart();
          }
          resumeLogAfterUpdate();
          const bool imageDenied = error == "image_http_403" || error == "image_http_409";
          Phase next = Phase::Failed;
          if (imageDenied || error.startsWith("permit_")) next = Phase::PermitRetry;
          else if (error == "sd_writer_pause_timeout") next = Phase::StorageBusy;
          reportFailure(next, peer, error);
          if (!imageDenied) waitForFirmwareCheck(15000);
        }
      }
    }
    waitForFirmwareCheck(5000);
  }
}
}  // namespace

void startPdmOta() {
  Preferences prefs;
  uint32_t ip = (uint32_t)DEFAULT_AUTHORITY;
  if (prefs.begin("pdm_ota", true)) {
    ip = prefs.getUInt("srvr_ip", ip);
    pinAuthority = prefs.isKey("srvr_ip");
  }
  authority.store(ip);
  Serial.printf("%s, authority %s\n", TOKEN, IPAddress(ip).toString().c_str());
  if (!hasOtaSlots()) {
    phase.store(Phase::Bootstrap);
    return;
  }
  if (xTaskCreate(otaWorker, "pdm-ota", 9216, nullptr, 1, &otaTask) != pdPASS) {
    reportFailure(Phase::Failed, IPAddress(ip), "ota_worker_start_failed");
  }
}

bool requestPdmOta(const IPAddress& peer, const IPAddress& local) {
  if (!otaTask || !validAuthorityIp(peer) || !ETH.linkUp() || !ETH.hasIP() || ETH.localIP() != local || peer == local) {
    return false;
  }
  const uint32_t mask = (uint32_t)ETH.subnetMask();
  if ((uint32_t)peer != authority.load()) {
    if (pinAuthority || !mask || ((uint32_t)peer & mask) != ((uint32_t)local & mask)) return false;
  }
  setOffer((uint32_t)peer);
  xTaskNotifyGive(otaTask);
  return true;
}

bool pdmOtaCheckSupported() { return otaTask != nullptr; }

void servicePdmOtaConsole() {
  static char line[40];
  static size_t used = 0;
  static bool overflow = false;
  for (int remaining = 48; remaining > 0 && Serial.available(); --remaining) {
    const char c = Serial.read();
    if (c == '\r') continue;
    if (c != '\n') {
      if (used + 1 < sizeof line) line[used++] = c;
      else overflow = true;
      continue;
    }
    line[used] = '\0';
    used = 0;
    const bool valid = !overflow;
    overflow = false;
    if (!valid || strncmp(line, "SRVR_IP ", 8)) continue;
    IPAddress ip;
    if (!ip.fromString(line + 8) || !validAuthorityIp(ip)) {
      Serial.println("PDM OTA: use SRVR_IP followed by a LAN IPv4 address");
      continue;
    }
    Preferences prefs;
    if (prefs.begin("pdm_ota", false) && prefs.putUInt("srvr_ip", (uint32_t)ip) == sizeof(uint32_t)) {
      pinAuthority = true;
      authority.store((uint32_t)ip);
      setOffer(0);
      if (otaTask) xTaskNotifyGive(otaTask);
      Serial.printf("PDM OTA authority saved: %s\n", ip.toString().c_str());
    } else Serial.println("PDM OTA: could not save SRVR address");
  }
}

const char* pdmOtaPhase() {
  switch (phase.load()) {
    case Phase::Current: return "Current";
    case Phase::Downloading: return "Downloading";
    case Phase::Verifying: return "Verifying";
    case Phase::Restarting: return "Restarting";
    case Phase::Failed: return "Retry pending";
    case Phase::PermitRetry: return "Firmware permit retry";
    case Phase::StorageBusy: return "Waiting for SD writer";
    case Phase::Bootstrap: return "USB bootstrap required";
    case Phase::Newer: return "PDM is newer than SRVR";
    default: return "Looking for SRVR";
  }
}

unsigned pdmOtaPercent() { return percent.load(); }

IPAddress pdmOtaAuthorityIp() { return IPAddress(authority.load()); }

uint16_t pdmOtaAuthorityPort() { return HVP2PAuthorityOTA::AUTHORITY_PORT; }
