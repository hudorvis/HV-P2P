#pragma once

#include <Arduino.h>
// Shared CTRL/W1P client for the read-only SRVR firmware authority service.
// It never chooses when an update is safe; each role must enter its own safety
// hold/gate before calling hvAuthorityDownloadAndStage().

#include <HTTPClient.h>
#include <NetworkClient.h>
#include <Update.h>
#include <esp_ota_ops.h>
#include <esp_partition.h>
#include <mbedtls/sha256.h>

static const uint16_t HV_SRVR_FIRMWARE_PORT = 8088;
static const size_t HV_EDGEBOX_MAX_APP_IMAGE = 0x600000;

struct HvAuthorityManifest {
  uint32_t schema = 0;
  String authority;
  String bundleId;
  String release;
  String role;
  String target;
  String version;
  String sha256;
  String identityToken;
  String targetToken;
  String imagePath;
  size_t size = 0;
};

static String hvAuthorityShaHex(const uint8_t digest[32]) {
  static const char* HEX = "0123456789abcdef";
  String out;
  out.reserve(64);
  for (size_t i = 0; i < 32; ++i) {
    out += HEX[(digest[i] >> 4) & 0x0F];
    out += HEX[digest[i] & 0x0F];
  }
  return out;
}

static bool hvAuthorityJsonString(const String& json, const char* key, String& out) {
  String needle = String("\"") + key + "\":";
  int p = json.indexOf(needle);
  if (p < 0) return false;
  p += needle.length();
  while (p < (int)json.length() && isspace((unsigned char)json[p])) ++p;
  if (p >= (int)json.length() || json[p] != '"') return false;
  ++p;
  int end = json.indexOf('"', p);
  if (end < 0) return false;
  out = json.substring(p, end);
  return out.indexOf('\\') < 0;  // authority metadata never needs escaped strings
}

static bool hvAuthorityJsonU32(const String& json, const char* key, uint32_t& out) {
  String needle = String("\"") + key + "\":";
  int p = json.indexOf(needle);
  if (p < 0) return false;
  p += needle.length();
  while (p < (int)json.length() && isspace((unsigned char)json[p])) ++p;
  if (p >= (int)json.length() || !isDigit(json[p])) return false;
  uint64_t value = 0;
  while (p < (int)json.length() && isDigit(json[p])) {
    value = value * 10ULL + uint64_t(json[p] - '0');
    if (value > 0xFFFFFFFFULL) return false;
    ++p;
  }
  out = uint32_t(value);
  return true;
}

static bool hvAuthorityJsonSize(const String& json, const char* key, size_t& out) {
  String needle = String("\"") + key + "\":";
  int p = json.indexOf(needle);
  if (p < 0) return false;
  p += needle.length();
  while (p < (int)json.length() && isspace((unsigned char)json[p])) ++p;
  if (p >= (int)json.length() || !isDigit(json[p])) return false;
  uint64_t value = 0;
  while (p < (int)json.length() && isDigit(json[p])) {
    value = value * 10ULL + uint64_t(json[p] - '0');
    if (value > HV_EDGEBOX_MAX_APP_IMAGE) return false;
    ++p;
  }
  out = size_t(value);
  return out > 0;
}

static bool hvAuthorityParseVersion(const String& version, uint32_t parts[4]) {
  String v = version;
  v.trim();
  if (v.startsWith("v")) v.remove(0, 1);
  int start = 0;
  for (int i = 0; i < 4; ++i) {
    int dot = v.indexOf('.', start);
    if ((i < 3 && dot < 0) || (i == 3 && dot >= 0)) return false;
    String piece = dot >= 0 ? v.substring(start, dot) : v.substring(start);
    if (!piece.length()) return false;
    uint64_t n = 0;
    for (size_t j = 0; j < piece.length(); ++j) {
      if (!isDigit(piece[j])) return false;
      n = n * 10ULL + uint64_t(piece[j] - '0');
      if (n > 0xFFFFFFFFULL) return false;
    }
    parts[i] = uint32_t(n);
    start = dot + 1;
  }
  return true;
}

static int hvAuthorityCompareVersions(const String& installed, const String& required, bool& valid) {
  uint32_t a[4] = {0,0,0,0}, b[4] = {0,0,0,0};
  valid = hvAuthorityParseVersion(installed, a) && hvAuthorityParseVersion(required, b);
  if (!valid) return 0;
  for (int i = 0; i < 4; ++i) {
    if (a[i] < b[i]) return -1;
    if (a[i] > b[i]) return 1;
  }
  return 0;
}

static String hvAuthorityBaseUrl(const IPAddress& srvrIp) {
  return String("http://") + srvrIp.toString() + ":" + String(HV_SRVR_FIRMWARE_PORT);
}

static bool hvAuthorityFetchManifest(const IPAddress& srvrIp, const char* expectedRole,
                                     HvAuthorityManifest& out, String& reason) {
  HTTPClient http;
  const String roleLower = String(expectedRole) == "CTRL" ? "ctrl" : "w1p";
  const String url = hvAuthorityBaseUrl(srvrIp) + "/firmware/" + roleLower + "/manifest";
  http.setConnectTimeout(1200);
  http.setTimeout(2000);
  if (!http.begin(url)) { reason = "manifest HTTP begin failed"; return false; }
  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    reason = String("manifest HTTP status ") + code;
    http.end();
    return false;
  }
  const int declared = http.getSize();
  if (declared <= 0 || declared > 8192) {
    reason = "manifest Content-Length invalid";
    http.end();
    return false;
  }
  String json = http.getString();
  http.end();
  if (json.length() != (size_t)declared) { reason = "manifest length mismatch"; return false; }
  if (!hvAuthorityJsonU32(json, "schema", out.schema) ||
      !hvAuthorityJsonString(json, "authority", out.authority) ||
      !hvAuthorityJsonString(json, "bundle_id", out.bundleId) ||
      !hvAuthorityJsonString(json, "release", out.release) ||
      !hvAuthorityJsonString(json, "role", out.role) ||
      !hvAuthorityJsonString(json, "target", out.target) ||
      !hvAuthorityJsonString(json, "version", out.version) ||
      !hvAuthorityJsonString(json, "sha256", out.sha256) ||
      !hvAuthorityJsonString(json, "identity_token", out.identityToken) ||
      !hvAuthorityJsonString(json, "target_token", out.targetToken) ||
      !hvAuthorityJsonString(json, "image", out.imagePath) ||
      !hvAuthorityJsonSize(json, "size", out.size)) {
    reason = "manifest fields missing/invalid";
    return false;
  }
  out.sha256.toLowerCase();
  out.bundleId.toLowerCase();
  if (out.schema != 1 || out.authority != "HV_P2P_SRVR" || out.bundleId.length() != 64 ||
      out.release != out.version || out.role != expectedRole || out.target != "EDGEBOX_ESP100" ||
      out.size == 0 || out.size > HV_EDGEBOX_MAX_APP_IMAGE || out.sha256.length() != 64 ||
      out.identityToken != (String("HV_P2P_FW_ROLE=") + expectedRole + ";HV_P2P_FW_VERSION=" + out.version) ||
      out.targetToken != "HV_P2P_FW_TARGET=EDGEBOX_ESP100;" ||
      out.imagePath != (String("/firmware/") + roleLower + "/image")) {
    reason = "manifest role/target/release identity rejected";
    return false;
  }
  for (size_t i = 0; i < out.sha256.length(); ++i) {
    const char c = out.sha256[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) {
      reason = "manifest SHA-256 is not lowercase hex";
      return false;
    }
  }
  for (size_t i = 0; i < out.bundleId.length(); ++i) {
    const char c = out.bundleId[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) {
      reason = "manifest bundle_id is not lowercase SHA-256 hex";
      return false;
    }
  }
  return true;
}

static bool hvAuthorityRunningImageSha(size_t expectedSize, String& shaHex, String& reason) {
  const esp_partition_t* running = esp_ota_get_running_partition();
  if (!running || expectedSize == 0 || expectedSize > running->size || expectedSize > HV_EDGEBOX_MAX_APP_IMAGE) {
    reason = "running OTA partition/expected size invalid";
    return false;
  }
  mbedtls_sha256_context ctx;
  mbedtls_sha256_init(&ctx);
  if (mbedtls_sha256_starts(&ctx, 0) != 0) {
    mbedtls_sha256_free(&ctx);
    reason = "running SHA-256 init failed";
    return false;
  }
  uint8_t buf[1024];
  size_t offset = 0;
  while (offset < expectedSize) {
    const size_t n = min(sizeof(buf), expectedSize - offset);
    if (esp_partition_read(running, offset, buf, n) != ESP_OK || mbedtls_sha256_update(&ctx, buf, n) != 0) {
      mbedtls_sha256_free(&ctx);
      reason = "running image read/SHA-256 failed";
      return false;
    }
    offset += n;
    yield();
  }
  uint8_t digest[32];
  if (mbedtls_sha256_finish(&ctx, digest) != 0) {
    mbedtls_sha256_free(&ctx);
    reason = "running SHA-256 finish failed";
    return false;
  }
  mbedtls_sha256_free(&ctx);
  shaHex = hvAuthorityShaHex(digest);
  return true;
}

struct HvAuthorityTokenScanner {
  String token;
  size_t matched = 0;
  bool found = false;
  explicit HvAuthorityTokenScanner(const String& t) : token(t) {}
  void feed(const uint8_t* data, size_t len) {
    if (found || token.length() == 0) return;
    for (size_t i = 0; i < len && !found; ++i) {
      const char c = (char)data[i];
      if (c == token[matched]) {
        ++matched;
        if (matched == token.length()) { found = true; matched = 0; }
      } else {
        matched = (c == token[0]) ? 1 : 0;
      }
    }
  }
};

static bool hvAuthorityDownloadAndStage(const IPAddress& srvrIp, const HvAuthorityManifest& manifest,
                                        String& reason) {
  HTTPClient http;
  const String url = hvAuthorityBaseUrl(srvrIp) + manifest.imagePath;
  http.setConnectTimeout(1500);
  http.setTimeout(3500);
  if (!http.begin(url)) { reason = "image HTTP begin failed"; return false; }
  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    reason = String("image HTTP status ") + code;
    http.end();
    return false;
  }
  if (http.getSize() != (int)manifest.size) {
    reason = "image Content-Length does not match manifest";
    http.end();
    return false;
  }
  if (!Update.begin(manifest.size, U_FLASH)) {
    reason = "Update.begin rejected inactive OTA partition";
    http.end();
    return false;
  }

  NetworkClient* stream = http.getStreamPtr();
  stream->setTimeout(3500);
  mbedtls_sha256_context ctx;
  mbedtls_sha256_init(&ctx);
  if (mbedtls_sha256_starts(&ctx, 0) != 0) {
    Update.abort(); http.end(); mbedtls_sha256_free(&ctx);
    reason = "download SHA-256 init failed"; return false;
  }
  HvAuthorityTokenScanner identity(manifest.identityToken);
  HvAuthorityTokenScanner target(manifest.targetToken);
  uint8_t buf[2048];
  size_t received = 0;
  bool magicOk = false;
  bool failed = false;
  while (received < manifest.size) {
    const size_t want = min(sizeof(buf), manifest.size - received);
    const size_t n = stream->readBytes(buf, want);
    if (n == 0) { reason = "image download interrupted/timeout"; failed = true; break; }
    if (received == 0) magicOk = (buf[0] == 0xE9);
    if (mbedtls_sha256_update(&ctx, buf, n) != 0) { reason = "download SHA-256 update failed"; failed = true; break; }
    identity.feed(buf, n);
    target.feed(buf, n);
    if (Update.write(buf, n) != n) { reason = "Update.write failed"; failed = true; break; }
    received += n;
    yield();
  }
  uint8_t digest[32] = {0};
  if (!failed && mbedtls_sha256_finish(&ctx, digest) != 0) { reason = "download SHA-256 finish failed"; failed = true; }
  mbedtls_sha256_free(&ctx);
  http.end();

  if (!failed && received != manifest.size) { reason = "download byte count mismatch"; failed = true; }
  if (!failed && !magicOk) { reason = "download is not an ESP application image"; failed = true; }
  if (!failed && hvAuthorityShaHex(digest) != manifest.sha256) { reason = "download SHA-256 mismatch"; failed = true; }
  if (!failed && !identity.found) { reason = "download embedded role/version identity missing"; failed = true; }
  if (!failed && !target.found) { reason = "download embedded EdgeBox target identity missing"; failed = true; }
  if (failed) {
    Update.abort();
    return false;
  }

  // Finalize only after role, target, exact size and complete-image SHA-256 have
  // all been validated. An interrupted/invalid transfer can never be activated.
  if (!Update.end(true)) {
    reason = "Update.end failed; inactive image not activated";
    Update.abort();
    return false;
  }
  reason = "verified authority image staged for reboot";
  return true;
}
