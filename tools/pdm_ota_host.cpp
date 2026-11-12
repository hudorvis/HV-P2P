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
void delay(uint32_t ms) {
  nowMs += ms;
  if (stopAfterWorkerWait && ms >= 5000) throw WorkerWait{};
}
void yield() {}

class IPAddress {
 public:
  IPAddress() = default;
  explicit IPAddress(uint32_t value) : value_(value) {}
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
    assert(strstr(url.c_str(), "http://172.20.1.100:5760/firmware/pdm/"));
    client_ = &client;
    return true;
  }
  int GET() const {
    if (!permit_) return manifest_ ? HTTP_CODE_OK : imageCode;
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
bool lease = false;
bool storageBusy = false;
bool dropIdleAfterPause = false;
bool writerPaused = false;
int commitChecks = 0;
bool mayActivate(const IPAddress& peer, const Manifest& manifest, String& error) {
  ++commitChecks;
  assert(peer == srvr && manifest.role == "PDM");
  if (!lease) error = "idle_window_closed";
  else if (storageBusy) error = "sd_writer_pause_timeout";
  return lease && !storageBusy;
}

struct EthernetFixture {
  bool selected = false;
  bool linkUp() const { return true; }
  bool hasIP() const { return true; }
  IPAddress localIP() const { return ethernet; }
  bool isDefault() const { return selected; }
  bool setDefault() { return selected = true; }
} ETH;

struct SerialFixture {
  template<typename... Args> void printf(const char*, Args...) {}
  void println(const char*) {}
  int available() const { return 0; }
  int read() const { return -1; }
} Serial;

struct Preferences {
  bool begin(const char*, bool) { return true; }
  uint32_t getUInt(const char*, uint32_t fallback) { return fallback; }
  size_t putUInt(const char*, uint32_t) { return sizeof(uint32_t); }
};

constexpr int pdPASS = 1;
int xTaskCreate(void (*)(void*), const char*, unsigned, void*, unsigned, void*) { return pdPASS; }
void vTaskDelete(void*) { assert(false); }
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
  if (dropIdleAfterPause) permitCode = 409;
  return true;
}
void resumeLogAfterUpdate() { writerPaused = false; }

#include "pdm_ota.cpp"

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
  canonical.assign(35000, 0);
  canonical[0] = 0xe9;
  const String identity = String("HV_P2P_FW_ROLE=PDM;HV_P2P_FW_TARGET=") + target + ";HV_P2P_FW_VERSION=" + version + ";";
  memcpy(canonical.data() + 500, identity.c_str(), identity.length()); // Spans a network read boundary.
  wrongBoard = canonical;
  wrongBoard[500 + strlen("HV_P2P_FW_ROLE=PDM;HV_P2P_FW_TARGET=")] = 'X';
  const String goodDigest = std::string(64, '1');
  manifestJson = String("{\"schema\":\"hv-p2p-firmware-manifest-v1\",\"authority\":\"HV_P2P_SRVR\",") +
      "\"bundle_id\":\"" + std::string(64, 'b') + "\",\"release\":\"" + version +
      "\",\"role\":\"PDM\",\"target\":\"" + target + "\",\"version\":\"" + version +
      "\",\"size\":35000,\"sha256\":\"" + goodDigest + "\"}";
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
  permitCode = 409;
  assert(!fetchIdlePermit(srvr, manifest, ethernet, error) && error == "idle_window_closed");
  permitCode = -1;
  assert(!fetchIdlePermit(srvr, manifest, ethernet, error) && error == "permit_http_-1");
  permitCode = HTTP_CODE_OK;
  source = wifi;
  assert(!fetchIdlePermit(srvr, manifest, ethernet, error) && error == "permit_wrong_interface");
  source = ethernet;
  permitReply = manifest.release + " " + std::string(64, '3') + "\n";
  assert(!fetchIdlePermit(srvr, manifest, ethernet, error) && error == "permit_image_identity_mismatch");
  permitReply = manifest.release + " " + manifest.sha256 + "\n";
  permitDelayMs = PERMIT_MAX_RTT_MS + 1;
  assert(!fetchIdlePermit(srvr, manifest, ethernet, error) && error == "permit_expired");
  permitDelayMs = 0;
  assert(fetchIdlePermit(srvr, manifest, ethernet, error) && !error.length());
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
  assert(!stage() && error == "idle_window_closed" && Update.aborts == 5);
  assert(Update.activations == 0 && commitChecks == 1 && Update.staging.empty());
  lease = true;
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
  startPdmOta();
  runningImage = wrongBoard;
  permitCode = -1;
  const int writesBeforeRejection = Update.writes;
  assert(!runWorkerCycle() && ETH.isDefault() && phase.load() == Phase::PermitRetry);
  assert(Update.writes == writesBeforeRejection && Update.activations == 1);
  permitCode = HTTP_CODE_OK;
  imageCode = 409;
  const uint32_t retryStarted = millis();
  assert(!runWorkerCycle() && ETH.isDefault());
  assert(phase.load() == Phase::Waiting && millis() - retryStarted == 5000);
  assert(Update.writes == writesBeforeRejection && Update.activations == 1);
  imageCode = HTTP_CODE_OK;
  dropIdleAfterPause = true;
  assert(!runWorkerCycle() && phase.load() == Phase::Waiting && !writerPaused);
  assert(Update.activations == 1);
  dropIdleAfterPause = false;
  permitCode = HTTP_CODE_OK;
  storageBusy = true;
  assert(!runWorkerCycle() && phase.load() == Phase::StorageBusy && !writerPaused);
  assert(Update.activations == 1);
  storageBusy = false;
  assert(runWorkerCycle() && phase.load() == Phase::Restarting);
  assert(Update.activations == 2 && runningImage == canonical);
  puts("PDM_OTA_HOST_PASS");
}
