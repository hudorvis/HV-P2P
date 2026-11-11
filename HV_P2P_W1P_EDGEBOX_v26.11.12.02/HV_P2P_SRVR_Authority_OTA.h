#pragma once

// HV P2P SRVR-authoritative Ethernet OTA helper for EdgeBox ESP32-S3 nodes.
// The calling sketch remains responsible for deciding whether it is safe to
// perform an update. This helper only fetches/verifies the immutable SRVR
// manifest/image and never enables motion or changes application safety state.

#include <Arduino.h>
#include <HTTPClient.h>
#include <NetworkClient.h>
#include <Update.h>
#include <esp_ota_ops.h>
#include <esp_partition.h>
#include <mbedtls/sha256.h>

namespace HVP2PAuthorityOTA {

static constexpr uint16_t AUTHORITY_PORT = 5088;
static constexpr size_t MIN_APP_IMAGE_BYTES = 32768;
static constexpr uint32_t HTTP_CONNECT_TIMEOUT_MS = 1500;
static constexpr uint32_t HTTP_IO_TIMEOUT_MS = 4000;
static constexpr uint32_t IMAGE_STALL_TIMEOUT_MS = 5000;
static constexpr uint8_t ESP_IMAGE_MAGIC = 0xE9;

using ProgressCallback = void (*)(size_t received, size_t total, const char *phase);

struct Manifest {
  String schema;
  String authority;
  String bundleId;
  String release;
  String role;
  String target;
  String version;
  String sha256;
  size_t size = 0;
  bool valid = false;
};

static inline String lowerCopy(String s) {
  s.toLowerCase();
  return s;
}

static inline int hexNibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return 10 + c - 'a';
  if (c >= 'A' && c <= 'F') return 10 + c - 'A';
  return -1;
}

static inline bool isSha256Hex(const String &s) {
  if (s.length() != 64) return false;
  for (size_t i = 0; i < s.length(); ++i) if (hexNibble(s[i]) < 0) return false;
  return true;
}

static inline String sha256Hex(const uint8_t digest[32]) {
  static const char HEX_DIGITS[] = "0123456789abcdef";
  char out[65];
  for (int i = 0; i < 32; ++i) {
    out[i * 2] = HEX_DIGITS[(digest[i] >> 4) & 0x0F];
    out[i * 2 + 1] = HEX_DIGITS[digest[i] & 0x0F];
  }
  out[64] = 0;
  return String(out);
}

static inline bool parseVersion(const String &input, uint32_t parts[4]) {
  String s = input;
  s.trim();
  if (s.startsWith("v") || s.startsWith("V")) s.remove(0, 1);
  int start = 0;
  for (int i = 0; i < 4; ++i) {
    int dot = s.indexOf('.', start);
    String p = (dot >= 0) ? s.substring(start, dot) : s.substring(start);
    if (!p.length()) return false;
    for (size_t j = 0; j < p.length(); ++j) if (!isDigit(p[j])) return false;
    unsigned long v = strtoul(p.c_str(), nullptr, 10);
    if (v > 999999UL) return false;
    parts[i] = (uint32_t)v;
    if (i < 3 && dot < 0) return false;
    if (i == 3 && dot >= 0) return false;
    start = dot + 1;
  }
  return true;
}

// -1 if installed < required, 0 if equal, +1 if installed > required.
static inline int compareVersions(const String &installed, const String &required, bool &ok) {
  uint32_t a[4] = {0,0,0,0}, b[4] = {0,0,0,0};
  ok = parseVersion(installed, a) && parseVersion(required, b);
  if (!ok) return 0;
  for (int i = 0; i < 4; ++i) {
    if (a[i] < b[i]) return -1;
    if (a[i] > b[i]) return 1;
  }
  return 0;
}

static inline String jsonString(const String &json, const char *key) {
  String token = String("\"") + key + "\"";
  int p = json.indexOf(token);
  if (p < 0) return "";
  p = json.indexOf(':', p + token.length());
  if (p < 0) return "";
  ++p;
  while (p < (int)json.length() && isspace((unsigned char)json[p])) ++p;
  if (p >= (int)json.length() || json[p] != '"') return "";
  ++p;
  String out;
  bool esc = false;
  for (; p < (int)json.length(); ++p) {
    char c = json[p];
    if (esc) { out += c; esc = false; continue; }
    if (c == '\\') { esc = true; continue; }
    if (c == '"') return out;
    out += c;
  }
  return "";
}

static inline size_t jsonSize(const String &json, const char *key) {
  String token = String("\"") + key + "\"";
  int p = json.indexOf(token);
  if (p < 0) return 0;
  p = json.indexOf(':', p + token.length());
  if (p < 0) return 0;
  ++p;
  while (p < (int)json.length() && isspace((unsigned char)json[p])) ++p;
  int e = p;
  while (e < (int)json.length() && isDigit(json[e])) ++e;
  if (e == p) return 0;
  return (size_t)strtoull(json.substring(p, e).c_str(), nullptr, 10);
}

static inline String rolePath(const char *role) {
  String r(role ? role : "");
  r.toLowerCase();
  return r;
}

static inline bool fetchManifest(const IPAddress &server, const char *role, Manifest &out, String &error) {
  out = Manifest();
  NetworkClient client;
  HTTPClient http;
  String url = String("http://") + server.toString() + ":" + String(AUTHORITY_PORT) +
               "/firmware/" + rolePath(role) + "/manifest";
  http.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
  http.setTimeout(HTTP_IO_TIMEOUT_MS);
  if (!http.begin(client, url)) { error = "manifest_http_begin"; return false; }
  const int code = http.GET();
  if (code != HTTP_CODE_OK) {
    error = String("manifest_http_") + code;
    http.end();
    return false;
  }
  const String body = http.getString();
  http.end();
  out.schema = jsonString(body, "schema");
  out.authority = jsonString(body, "authority");
  out.bundleId = jsonString(body, "bundle_id");
  out.release = jsonString(body, "release");
  out.role = jsonString(body, "role");
  out.target = jsonString(body, "target");
  out.version = jsonString(body, "version");
  out.sha256 = lowerCopy(jsonString(body, "sha256"));
  out.size = jsonSize(body, "size");
  out.valid = out.schema == "hv-p2p-firmware-manifest-v1" &&
              out.authority == "HV_P2P_SRVR" && out.bundleId.length() >= 8 &&
              out.release.length() >= 2 && out.role.length() >= 3 &&
              out.target.length() >= 3 && out.version.length() >= 2 &&
              out.size >= MIN_APP_IMAGE_BYTES && isSha256Hex(out.sha256);
  if (!out.valid) { error = "manifest_invalid"; return false; }
  return true;
}

static inline bool hashRunningPrefix(size_t imageSize, String &outSha, String &error) {
  const esp_partition_t *running = esp_ota_get_running_partition();
  if (!running) { error = "running_partition_missing"; return false; }
  if (imageSize < MIN_APP_IMAGE_BYTES || imageSize > running->size) { error = "running_hash_size_invalid"; return false; }
  mbedtls_sha256_context ctx;
  mbedtls_sha256_init(&ctx);
  if (mbedtls_sha256_starts(&ctx, 0) != 0) { mbedtls_sha256_free(&ctx); error = "running_hash_init"; return false; }
  uint8_t buf[1024];
  size_t offset = 0;
  while (offset < imageSize) {
    const size_t n = min(sizeof(buf), imageSize - offset);
    if (esp_partition_read(running, offset, buf, n) != ESP_OK) {
      mbedtls_sha256_free(&ctx); error = "running_partition_read"; return false;
    }
    if (mbedtls_sha256_update(&ctx, buf, n) != 0) {
      mbedtls_sha256_free(&ctx); error = "running_hash_update"; return false;
    }
    offset += n;
    yield();
  }
  uint8_t digest[32];
  if (mbedtls_sha256_finish(&ctx, digest) != 0) { mbedtls_sha256_free(&ctx); error = "running_hash_finish"; return false; }
  mbedtls_sha256_free(&ctx);
  outSha = sha256Hex(digest);
  return true;
}

class TokenScanner {
 public:
  TokenScanner(const String &role, const String &target, const String &version)
      : roleToken_(String("HV_P2P_FW_ROLE=") + role + ";"),
        targetToken_(String("HV_P2P_FW_TARGET=") + target + ";"),
        versionToken_(String("HV_P2P_FW_VERSION=") + version + ";") {}

  void feed(const uint8_t *data, size_t len) {
    if (!data || !len) return;
    scanOne(roleToken_, rolePos_, roleFound_, data, len);
    scanOne(targetToken_, targetPos_, targetFound_, data, len);
    scanOne(versionToken_, versionPos_, versionFound_, data, len);
  }

  bool complete() const { return roleFound_ && targetFound_ && versionFound_; }

 private:
  static void scanOne(const String &token, size_t &pos, bool &found, const uint8_t *data, size_t len) {
    if (found || !token.length()) return;
    for (size_t i = 0; i < len && !found; ++i) {
      char c = (char)data[i];
      if (c == token[pos]) {
        ++pos;
        if (pos == token.length()) { found = true; pos = 0; }
      } else {
        pos = (c == token[0]) ? 1 : 0;
      }
    }
  }
  String roleToken_, targetToken_, versionToken_;
  size_t rolePos_ = 0, targetPos_ = 0, versionPos_ = 0;
  bool roleFound_ = false, targetFound_ = false, versionFound_ = false;
};

static inline bool downloadAndStage(const IPAddress &server, const Manifest &m,
                                    const char *expectedRole, const char *expectedTarget,
                                    String &error, ProgressCallback progress = nullptr) {
  if (!m.valid || m.role != expectedRole || m.target != expectedTarget) { error = "manifest_target_mismatch"; return false; }
  const esp_partition_t *next = esp_ota_get_next_update_partition(nullptr);
  if (!next || m.size > next->size) { error = "ota_slot_too_small"; return false; }

  NetworkClient client;
  HTTPClient http;
  String url = String("http://") + server.toString() + ":" + String(AUTHORITY_PORT) +
               "/firmware/" + rolePath(expectedRole) + "/image";
  http.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
  http.setTimeout(HTTP_IO_TIMEOUT_MS);
  if (!http.begin(client, url)) { error = "image_http_begin"; return false; }
  const int code = http.GET();
  if (code != HTTP_CODE_OK) { error = String("image_http_") + code; http.end(); return false; }
  const int reportedSize = http.getSize();
  if (reportedSize >= 0 && (size_t)reportedSize != m.size) { error = "image_content_length_mismatch"; http.end(); return false; }

  if (!Update.begin(m.size, U_FLASH)) { error = "update_begin"; http.end(); return false; }
  mbedtls_sha256_context ctx;
  mbedtls_sha256_init(&ctx);
  if (mbedtls_sha256_starts(&ctx, 0) != 0) {
    mbedtls_sha256_free(&ctx); Update.abort(); http.end(); error = "image_hash_init"; return false;
  }
  TokenScanner scanner(m.role, m.target, m.version);
  NetworkClient *stream = http.getStreamPtr();
  uint8_t buf[1024];
  size_t total = 0;
  uint32_t lastProgress = millis();
  int lastPct = -1;
  if (progress) progress(0, m.size, "Downloading");
  bool ok = true;
  while (total < m.size) {
    const size_t remain = m.size - total;
    const int avail = stream ? stream->available() : 0;
    if (avail > 0) {
      const size_t want = min((size_t)avail, min(sizeof(buf), remain));
      const int got = stream->read(buf, want);
      if (got <= 0) { ok = false; error = "image_stream_read"; break; }
      if (total == 0 && buf[0] != ESP_IMAGE_MAGIC) { ok = false; error = "image_magic"; break; }
      scanner.feed(buf, (size_t)got);
      if (mbedtls_sha256_update(&ctx, buf, (size_t)got) != 0) { ok = false; error = "image_hash_update"; break; }
      if (Update.write(buf, (size_t)got) != (size_t)got) { ok = false; error = "image_flash_write"; break; }
      total += (size_t)got;
      lastProgress = millis();
      const int pct = m.size ? int((100ULL * total) / m.size) : 0;
      if (progress && pct != lastPct) { lastPct = pct; progress(total, m.size, "Downloading"); }
    } else {
      if (!http.connected() && total < m.size) { ok = false; error = "image_stream_closed"; break; }
      if ((millis() - lastProgress) > IMAGE_STALL_TIMEOUT_MS) { ok = false; error = "image_stream_stall"; break; }
      delay(2);
      yield();
    }
  }

  if (ok && progress) progress(total, m.size, "Verifying");
  uint8_t digest[32];
  if (ok && mbedtls_sha256_finish(&ctx, digest) != 0) { ok = false; error = "image_hash_finish"; }
  mbedtls_sha256_free(&ctx);
  http.end();

  if (!ok || total != m.size) { Update.abort(); return false; }
  const String actual = sha256Hex(digest);
  if (actual != lowerCopy(m.sha256)) { Update.abort(); error = "image_sha256_mismatch"; return false; }
  if (!scanner.complete()) { Update.abort(); error = "image_embedded_identity_mismatch"; return false; }
  if (!Update.end(true) || Update.hasError()) { Update.abort(); error = "update_finalize"; return false; }
  if (progress) progress(m.size, m.size, "Complete");
  return true;
}

}  // namespace HVP2PAuthorityOTA
