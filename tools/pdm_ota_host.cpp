// Host fixture for the real Olimex OTA transport and boot-selection path.
#include <algorithm>
#include <cassert>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

using std::min;
class String {
 public:
  String(const char* value = "") : value_(value) {}
  String(int value) : value_(std::to_string(value)) {}
  String(std::string value) : value_(std::move(value)) {}
  size_t length() const { return value_.size(); }
  char operator[](size_t index) const { return value_[index]; }
  const char* c_str() const { return value_.c_str(); }
  void trim() {
    const auto start = value_.find_first_not_of(" \r\n\t");
    value_ = start == std::string::npos ? "" : value_.substr(start, value_.find_last_not_of(" \r\n\t") - start + 1);
  }
  void toLowerCase() { for (char& c : value_) c = std::tolower(static_cast<unsigned char>(c)); }
  void remove(size_t start, size_t count) { value_.erase(start, count); }
  bool startsWith(const char* prefix) const { return value_.rfind(prefix, 0) == 0; }
  int indexOf(char value, size_t start = 0) const { return position(value_.find(value, start)); }
  int indexOf(const String& value) const { return position(value_.find(value.value_)); }
  String substring(size_t start, size_t end = std::string::npos) const {
    return value_.substr(start, end == std::string::npos ? end : end - start);
  }
  void operator+=(char c) { value_ += c; }
  friend bool operator==(const String& lhs, const String& rhs) { return lhs.value_ == rhs.value_; }
  friend bool operator!=(const String& lhs, const String& rhs) { return !(lhs == rhs); }
  friend String operator+(const String& lhs, const String& rhs) { return lhs.value_ + rhs.value_; }

 private:
  static int position(size_t index) { return index == std::string::npos ? -1 : static_cast<int>(index); }
  std::string value_;
};

bool isDigit(char c) { return std::isdigit(static_cast<unsigned char>(c)); }
uint32_t nowMs = 0;
struct WorkerWait {};
struct WorkerRestart {};
bool stopAfterWorkerWait = false;
uint32_t millis() { return nowMs; }
uint64_t uptimeMs() { return nowMs; }
void delay(uint32_t ms) {
  nowMs += ms;
  if (stopAfterWorkerWait && ms >= 5000) throw WorkerWait{};
}
void yield() {}

class IPAddress {
 public:
  IPAddress() = default;
  explicit IPAddress(uint32_t value) : value_(value) {}
  explicit IPAddress(const uint8_t* address) : IPAddress(address[0], address[1], address[2], address[3]) {}
  IPAddress(uint8_t a, uint8_t b, uint8_t c, uint8_t d)
      : value_(uint32_t(a) | (uint32_t(b) << 8) | (uint32_t(c) << 16) | (uint32_t(d) << 24)) {}
  uint8_t operator[](size_t index) const { return value_ >> (8 * index); }
  explicit operator uint32_t() const { return value_; }
  bool fromString(const char* input) {
    unsigned a, b, c, d;
    char extra;
    if (sscanf(input, "%u.%u.%u.%u%c", &a, &b, &c, &d, &extra) != 4 || std::max({a, b, c, d}) > 255) return false;
    *this = IPAddress(a, b, c, d);
    return true;
  }
  String toString() const {
    char buffer[16];
    snprintf(buffer, sizeof buffer, "%u.%u.%u.%u",
             unsigned((*this)[0]), unsigned((*this)[1]), unsigned((*this)[2]), unsigned((*this)[3]));
    return buffer;
  }
  bool operator==(const IPAddress& other) const { return value_ == other.value_; }
  bool operator!=(const IPAddress& other) const { return !(*this == other); }

 private:
  uint32_t value_ = 0;
};

const IPAddress ethernet{172, 20, 1, 110}, wifi{192, 168, 1, 1}, srvr{172, 20, 1, 100};
const IPAddress alternateSrvr{172, 20, 1, 104}, offSubnet{192, 168, 50, 10};
constexpr int HTTP_CODE_OK = 200;
std::vector<uint8_t> reply, canonical, wrongBoard, runningImage;
IPAddress source = ethernet;
int contentLength = 0;
bool stall = false;
String manifestJson;
String permitReply;
int permitCode = HTTP_CODE_OK;
int imageCode = HTTP_CODE_OK;
uint32_t permitDelayMs = 0;
int configuredManifestCode = HTTP_CODE_OK;
int alternateManifestCode = HTTP_CODE_OK;
bool servedAlternateImage = false;

class NetworkClient {
 public:
  IPAddress localIP() const { return source; }
  int available() const { return stall ? 0 : reply.size() - offset_; }
  int read(uint8_t* output, size_t count) {
    count = min(count, min(size_t(509), reply.size() - offset_));
    memcpy(output, reply.data() + offset_, count);
    offset_ += count;
    return count;
  }

 private:
  size_t offset_ = 0;
};

class HTTPClient {
 public:
  void setConnectTimeout(unsigned) {}
  void setTimeout(unsigned) {}
  bool begin(NetworkClient& client, const String& url) {
    manifest_ = strstr(url.c_str(), "/manifest") != nullptr;
    permit_ = strstr(url.c_str(), "/permit") != nullptr;
    alternate_ = strstr(url.c_str(), "http://172.20.1.104:5760/firmware/pdm/") != nullptr;
    assert(alternate_ || strstr(url.c_str(), "http://172.20.1.100:5760/firmware/pdm/"));
    client_ = &client;
    return true;
  }
  int GET() const {
    if (manifest_) return alternate_ ? alternateManifestCode : configuredManifestCode;
    if (!permit_) {
      servedAlternateImage = alternate_;
      return imageCode;
    }
    nowMs += permitDelayMs;
    return permitCode;
  }
  int getSize() const {
    if (permit_) return permitReply.length();
    return manifest_ ? manifestJson.length() : contentLength;
  }
  String getString() const { return permit_ ? permitReply : manifestJson; }
  NetworkClient* getStreamPtr() const { return client_; }
  bool connected() const { return stall || client_->available() > 0; }
  void end() {}

 private:
  NetworkClient* client_ = nullptr;
  bool manifest_ = false;
  bool permit_ = false;
  bool alternate_ = false;
};

constexpr int ESP_OK = 0, U_FLASH = 0, ESP_PARTITION_TYPE_DATA = 1, ESP_PARTITION_SUBTYPE_DATA_OTA = 0;
struct esp_partition_t { size_t size; uint32_t address; };
esp_partition_t slot{0x1e0000, 0x1f0000}, activeSlot{0x1e0000, 0x10000}, otaData{0x2000, 0xe000};
const esp_partition_t* esp_ota_get_next_update_partition(void*) { return &slot; }
const esp_partition_t* esp_ota_get_running_partition() { return &activeSlot; }
const esp_partition_t* esp_partition_find_first(int type, int subtype, const char*) {
  assert(type == ESP_PARTITION_TYPE_DATA && subtype == ESP_PARTITION_SUBTYPE_DATA_OTA);
  return &otaData;
}
int esp_partition_read(const esp_partition_t*, size_t offset, void* output, size_t size) {
  if (offset + size > runningImage.size()) return -1;
  memcpy(output, runningImage.data() + offset, size);
  return ESP_OK;
}

struct UpdateFixture {
  std::vector<uint8_t> staging;
  size_t expected = 0;
  int writes = 0, aborts = 0, activations = 0;
  bool begin(size_t bytes, int kind) {
    assert(kind == U_FLASH);
    expected = bytes;
    staging.clear();
    return true;
  }
  size_t write(uint8_t* data, size_t bytes) {
    ++writes;
    staging.insert(staging.end(), data, data + bytes);
    return bytes;
  }
  void abort() { ++aborts; staging.clear(); }
  bool end(bool partial) {
    assert(!partial && staging.size() == expected);
    ++activations;
    return true;
  }
  bool hasError() const { return false; }
} Update;

// The native SDK provides SHA-256. These fixture digests differ unless the
// exact expected stream reaches the real helper's hash comparison.
struct mbedtls_sha256_context { std::vector<uint8_t> bytes; };
void mbedtls_sha256_init(mbedtls_sha256_context*) {}
void mbedtls_sha256_free(mbedtls_sha256_context*) {}
int mbedtls_sha256_starts(mbedtls_sha256_context*, int) { return 0; }
int mbedtls_sha256_update(mbedtls_sha256_context* ctx, const uint8_t* data, size_t len) {
  ctx->bytes.insert(ctx->bytes.end(), data, data + len);
  return 0;
}
int mbedtls_sha256_finish(mbedtls_sha256_context* ctx, uint8_t digest[32]) {
  memset(digest, ctx->bytes == canonical ? 0x11 : ctx->bytes == wrongBoard ? 0x22 : 0x33, 32);
  return 0;
}

#include "HV_P2P_SRVR_Authority_OTA.h"

using namespace HVP2PAuthorityOTA;
bool permitCommit = false;
bool storageBusy = false;
bool denyAfterPause = false;
bool writerPaused = false;
int commitChecks = 0;
bool mayActivate(const IPAddress& peer, const Manifest& manifest, String& error) {
  ++commitChecks;
  assert(peer == srvr && manifest.role == "PDM");
  if (!permitCommit) error = "permit_denied";
  else if (storageBusy) error = "sd_writer_pause_timeout";
  return permitCommit && !storageBusy;
}

struct EthernetFixture {
  bool selected = false;
  bool linkUp() const { return true; }
  bool hasIP() const { return true; }
  IPAddress localIP() const { return ethernet; }
  IPAddress subnetMask() const { return {255, 255, 0, 0}; }
  bool isDefault() const { return selected; }
  bool setDefault() { return selected = true; }
} ETH;

struct SerialFixture {
  std::string input;
  size_t consumed = 0;
  template<typename... Args> void printf(const char*, Args...) {}
  void println(const char*) {}
  int available() const { return input.size() - consumed; }
  int read() { return input[consumed++]; }
} Serial;

struct Preferences {
  static inline uint32_t savedAuthority = 0;
  bool begin(const char*, bool) { return true; }
  bool isKey(const char*) { return savedAuthority != 0; }
  uint32_t getUInt(const char*, uint32_t fallback) { return savedAuthority ? savedAuthority : fallback; }
  size_t putUInt(const char*, uint32_t value) {
    savedAuthority = value;
    return sizeof(uint32_t);
  }
};

constexpr int pdPASS = 1, pdTRUE = 1;
using portMUX_TYPE = int;
constexpr int portMUX_INITIALIZER_UNLOCKED = 0;
void portENTER_CRITICAL(portMUX_TYPE*) {}
void portEXIT_CRITICAL(portMUX_TYPE*) {}
using TaskHandle_t = void*;
int taskId;
int wakeNotifications = 0;
int xTaskCreate(void (*)(void*), const char*, unsigned, void*, unsigned, TaskHandle_t* task) {
  *task = &taskId;
  return pdPASS;
}
void xTaskNotifyGive(TaskHandle_t task) {
  assert(task == &taskId);
  ++wakeNotifications;
}
uint32_t pdMS_TO_TICKS(uint32_t ms) { return ms; }
uint32_t ulTaskNotifyTake(int, uint32_t ticks) {
  delay(ticks);
  return 0;
}
struct {
  void restart() {
    runningImage = Update.staging;
    throw WorkerRestart{};
  }
} ESP;

bool pauseLogForUpdate(uint32_t timeout) {
  assert(timeout == 1500);
  if (storageBusy) return false;
  writerPaused = true;
  if (denyAfterPause) permitCode = 403;
  return true;
}
void resumeLogAfterUpdate() { writerPaused = false; }

#include "pdm_ota.cpp"

namespace ApFixture {
#include "pdm_ap_config.h"
LanConfig lan;
WifiConfig wifi;
bool ethConfigOk, apStarted, apConfigOk, naptActive;
const char* routingState = "starting";
uint64_t routingCheckAt;
constexpr int WIFI_AP = 1, WIFI_OFF = 0;

struct Ethernet {
  IPAddress ip, mask, dns;
  bool selected = false;
  bool begin() { return true; }
  bool config(IPAddress address, IPAddress, IPAddress subnet, IPAddress resolver) {
    ip = address;
    mask = subnet;
    dns = resolver;
    return true;
  }
  bool linkUp() const { return true; }
  bool hasIP() const { return (uint32_t)ip != 0; }
  bool isDefault() const { return selected; }
  bool setDefault() { return selected = true; }
  IPAddress localIP() const { return ip; }
  IPAddress subnetMask() const { return mask; }
  IPAddress dnsIP() const { return dns; }
} ETH;

struct WifiDriver {
  struct AccessPoint {
    IPAddress ip, mask;
    bool nat = false;
    IPAddress subnetMask() const { return mask; }
    IPAddress localIP() const { return ip; }
    bool enableNAPT(bool enable) { nat = enable; return true; }
  } AP;
  bool enabled = false;
  bool configurationFails = false;
  int starts = 0;
  int stops = 0;
  std::string ssid, pass;
  bool mode(int selected) {
    enabled = selected == WIFI_AP;
    if (!enabled) {
      ++stops;
      AP = {};
    }
    return true;
  }
  void setSleep(bool) {}
  bool softAPConfig(IPAddress ip, IPAddress, IPAddress mask, IPAddress lease, IPAddress) {
    assert(enabled && (uint32_t)lease);
    AP.ip = ip;
    AP.mask = mask;
    return !configurationFails;
  }
  bool softAP(const char* name, const char* password, int, int) {
    assert(enabled);
    ssid = name;
    pass = password ? password : "";
    ++starts;
    return true;
  }
  IPAddress softAPIP() const { return AP.ip; }
} WiFi;

#include "pdm_ap_startup.h"

void reset() {
  lan = {};
  wifi = {};
  ETH = {};
  WiFi = {};
  ethConfigOk = apStarted = apConfigOk = naptActive = false;
  routingCheckAt = 0;
  routingState = "starting";
}

void checkRouting() {
  reset();
  const IPAddress oldAp(172, 20, 1, 1);
  wifi.ip = wifi.gateway = (uint32_t)oldAp;
  strcpy(wifi.ssid, "Saved equipment AP");
  strcpy(wifi.pass, "saved password");
  startNetwork();
  assert(apStarted && apConfigOk && ETH.localIP() == ethernet && WiFi.softAPIP() == DEFAULT_AP);
  assert(wifi.ip == (uint32_t)oldAp && WiFi.ssid == wifi.ssid && WiFi.pass == wifi.pass);
  serviceRouting();
  assert(ETH.isDefault() && WiFi.AP.nat && naptActive);

  reset();
  lan.ip = (uint32_t)IPAddress(192, 168, 1, 110);
  lan.mask = (uint32_t)DEFAULT_AP_MASK;
  lan.gateway = (uint32_t)IPAddress(192, 168, 1, 254);
  startNetwork();
  assert(apStarted && WiFi.softAPIP() == IPAddress(192, 168, 4, 1) && wifi.ip == (uint32_t)DEFAULT_AP);

  reset();
  WiFi.configurationFails = true;
  startNetwork();
  assert(ethConfigOk && !apStarted && !apConfigOk && !WiFi.enabled && !WiFi.starts && WiFi.stops == 1);

  reset();
  lan.dhcp = 1;
  wifi.ip = wifi.gateway = (uint32_t)oldAp;
  wifi.bridge = 0;
  startNetwork();
  assert(apStarted && WiFi.softAPIP() == oldAp && !ETH.hasIP());
  ETH.ip = ethernet;
  ETH.mask = DEFAULT_MASK;
  serviceRouting();
  assert(apStarted && WiFi.softAPIP() == DEFAULT_AP && WiFi.stops == 1);
  assert(ETH.isDefault() && !WiFi.AP.nat && wifi.ip == (uint32_t)oldAp);
  assert(strcmp(routingState, "disabled") == 0);

  reset();
  const IPAddress distinctAp(192, 168, 50, 1);
  wifi.ip = wifi.gateway = (uint32_t)distinctAp;
  startNetwork();
  assert(apStarted && WiFi.softAPIP() == distinctAp && !WiFi.stops);

  reset();
  wifi.enabled = 0;
  startNetwork();
  assert(ethConfigOk && !apStarted && !WiFi.enabled && !WiFi.starts);
  puts("PDM_AP_STARTUP_AND_ETHERNET_ROUTE_PASS");
}
}  // namespace ApFixture

bool runWorkerCycle() {
  stopAfterWorkerWait = true;
  bool restarted = false;
  try {
    otaWorker(nullptr);
  } catch (const WorkerWait&) {
  } catch (const WorkerRestart&) {
    restarted = true;
  }
  stopAfterWorkerWait = false;
  return restarted;
}

int main(int argc, char** argv) {
  assert(argc == 2);
  const String version = argv[1];
  const String target = "OLIMEX_ESP32_POE_ISO";
  const String goodDigest = std::string(64, '1');
  const auto serveRelease = [&](const String& release) {
    canonical.assign(35000, 0);
    canonical[0] = 0xe9;
    const String identity = String("HV_P2P_FW_ROLE=PDM;HV_P2P_FW_TARGET=") + target +
                            ";HV_P2P_FW_VERSION=" + release + ";";
    memcpy(canonical.data() + 500, identity.c_str(), identity.length()); // Spans a network read boundary.
    manifestJson = String("{\"schema\":\"hv-p2p-firmware-manifest-v1\",\"authority\":\"HV_P2P_SRVR\",") +
        "\"bundle_id\":\"" + std::string(64, 'b') + "\",\"release\":\"" + release +
        "\",\"role\":\"PDM\",\"target\":\"" + target + "\",\"version\":\"" + release +
        "\",\"size\":35000,\"sha256\":\"" + goodDigest + "\"}";
    permitReply = release + " " + goodDigest + "\n";
    reply = canonical;
  };
  serveRelease(version);
  wrongBoard = canonical;
  wrongBoard[500 + strlen("HV_P2P_FW_ROLE=PDM;HV_P2P_FW_TARGET=")] = 'X';
  String error;
  Manifest manifest;
  source = wifi;
  assert(!fetchManifest(srvr, "PDM", manifest, error, ethernet) && error == "manifest_wrong_interface");
  source = ethernet;
  assert(fetchManifest(srvr, "PDM", manifest, error, ethernet));
  assert(manifest.version == version && manifest.size == canonical.size());
  bool validVersion = false;
  assert(compareVersions("v26.11.12.07", version, validVersion) < 0 && validVersion);
  permitReply = manifest.release + " " + manifest.sha256 + "\n";
  permitCode = 403;
  assert(!fetchUpdatePermit(srvr, manifest, ethernet, error) && error == "permit_http_403");
  permitCode = -1;
  assert(!fetchUpdatePermit(srvr, manifest, ethernet, error) && error == "permit_http_-1");
  permitCode = HTTP_CODE_OK;
  source = wifi;
  assert(!fetchUpdatePermit(srvr, manifest, ethernet, error) && error == "permit_wrong_interface");
  source = ethernet;
  permitReply = manifest.release + " " + std::string(64, '3') + "\n";
  assert(!fetchUpdatePermit(srvr, manifest, ethernet, error) && error == "permit_image_identity_mismatch");
  permitReply = manifest.release + " " + manifest.sha256 + "\n";
  permitDelayMs = PERMIT_MAX_RTT_MS + 1;
  assert(!fetchUpdatePermit(srvr, manifest, ethernet, error) && error == "permit_expired");
  permitDelayMs = 0;
  assert(fetchUpdatePermit(srvr, manifest, ethernet, error) && !error.length());
  const auto stage = [&] { return downloadAndStage(srvr, manifest, "PDM", target.c_str(),
                                                  ethernet, error, nullptr, mayActivate); };
  contentLength = manifest.size;
  reply = canonical;
  manifest.target = "EDGEBOX_ESP100";
  assert(!stage() && error == "manifest_target_mismatch" && Update.writes == 0);
  manifest.target = target;
  source = wifi;
  assert(!stage() && error == "image_interface_or_length" && Update.writes == 0);
  source = ethernet;
  reply.resize(15000);
  assert(!stage() && error == "image_stream_closed" && Update.aborts == 1);
  stall = true;
  assert(!stage() && error == "image_stream_stall" && Update.aborts == 2);
  stall = false;
  reply = wrongBoard;
  assert(!stage() && error == "image_sha256_mismatch" && Update.aborts == 3);
  manifest.sha256 = std::string(64, '2');
  assert(!stage() && error == "image_embedded_identity_mismatch" && Update.aborts == 4);
  reply = canonical;
  manifest.sha256 = goodDigest;
  assert(!stage() && error == "permit_denied" && Update.aborts == 5);
  assert(Update.activations == 0 && commitChecks == 1 && Update.staging.empty());
  permitCommit = true;
  storageBusy = true;
  assert(!stage() && error == "sd_writer_pause_timeout" && Update.aborts == 6);
  assert(Update.activations == 0 && commitChecks == 2 && Update.staging.empty());
  storageBusy = false;
  assert(stage() && Update.activations == 1 && commitChecks == 3 && Update.staging == canonical);
  runningImage = Update.staging; // Simulated reboot into the selected application.
  String activeDigest;
  assert(hashRunningPrefix(canonical.size(), activeDigest, error) && activeDigest == goodDigest);

  // Run the device's worker, including the installed-image hash, fresh permit
  // after the writer pause, and selection/reboot only after a successful stage.
  assert(!pdmOtaCheckSupported());
  startPdmOta();
  assert(pdmOtaCheckSupported());
  runningImage = wrongBoard;
  permitCode = -1;
  const int writesBeforeRejection = Update.writes;
  assert(!runWorkerCycle() && ETH.isDefault() && phase.load() == Phase::PermitRetry);
  assert(Update.writes == writesBeforeRejection && Update.activations == 1);
  permitCode = HTTP_CODE_OK;
  imageCode = 403;
  const uint32_t retryStarted = millis();
  assert(!runWorkerCycle() && ETH.isDefault());
  assert(phase.load() == Phase::PermitRetry && millis() - retryStarted == 5000);
  assert(Update.writes == writesBeforeRejection && Update.activations == 1);
  imageCode = HTTP_CODE_OK;
  denyAfterPause = true;
  assert(!runWorkerCycle() && phase.load() == Phase::PermitRetry && !writerPaused);
  assert(Update.activations == 1);
  denyAfterPause = false;
  permitCode = HTTP_CODE_OK;
  storageBusy = true;
  assert(!runWorkerCycle() && phase.load() == Phase::StorageBusy && !writerPaused);
  assert(Update.activations == 1);
  storageBusy = false;
  assert(runWorkerCycle() && phase.load() == Phase::Restarting);
  assert(Update.activations == 2 && runningImage == canonical);

  // An unconfigured PDM can check a connected SRVR when the factory
  // destination is unavailable. Configured destinations stay pinned.
  runningImage = wrongBoard;
  assert(!requestPdmOta(alternateSrvr, wifi));
  assert(!requestPdmOta(ethernet, ethernet));
  assert(!requestPdmOta(offSubnet, ethernet));
  assert(requestPdmOta(alternateSrvr, ethernet) && wakeNotifications == 1);
  alternateManifestCode = 404;
  assert(runWorkerCycle() && !servedAlternateImage);
  runningImage = wrongBoard;
  configuredManifestCode = 404;
  alternateManifestCode = HTTP_CODE_OK;
  permitCode = 403;
  assert(!runWorkerCycle() && phase.load() == Phase::PermitRetry);
  permitCode = HTTP_CODE_OK;
  assert(runWorkerCycle() && servedAlternateImage && runningImage == canonical);
  assert(pdmOtaAuthorityIp() == srvr && Preferences::savedAuthority == 0);
  const int exactImageWrites = Update.writes;
  assert(!runWorkerCycle() && phase.load() == Phase::Current && Update.writes == exactImageWrites);
  nowMs += 60000;
  runningImage = wrongBoard;
  assert(!runWorkerCycle() && phase.load() == Phase::Searching);
  assert(Update.activations == 4);

  // Exercise a different release through the request and actual OTA worker.
  runningImage = canonical;
  serveRelease("v99.12.31.99");
  assert(requestPdmOta(alternateSrvr, ethernet));
  permitCode = 403;
  assert(!runWorkerCycle() && phase.load() == Phase::PermitRetry && Update.writes == exactImageWrites);
  permitCode = HTTP_CODE_OK;
  assert(runWorkerCycle() && phase.load() == Phase::Restarting);
  assert(Update.activations == 5 && runningImage == canonical);
  serveRelease("v00.01.01.01");
  const int newerWrites = Update.writes;
  assert(!runWorkerCycle() && phase.load() == Phase::Newer && Update.writes == newerWrites);

  Serial.input = "SRVR_IP 172.20.1.100\n";
  servicePdmOtaConsole();
  assert(Preferences::savedAuthority == (uint32_t)srvr && currentOffer() == 0);
  assert(!requestPdmOta(alternateSrvr, ethernet));
  startPdmOta();
  assert(!requestPdmOta(alternateSrvr, ethernet));
  assert(requestPdmOta(srvr, ethernet));
  ApFixture::checkRouting();
  puts("PDM_OTA_HOST_PASS");
}
