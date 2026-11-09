#include "pdm_log.h"
#include "pdm_measure.h"
#include "pdm_ota.h"
#include "pdm_web_assets.h"

#include <ArduinoJson.h>
#include <ETH.h>
#include <Preferences.h>
#include <SD_MMC.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_netif.h>
#include <esp_system.h>
#include <esp_task_wdt.h>
#include <cmath>
#include <cstring>
#include <sys/time.h>

namespace {
constexpr char VERSION[] = "HV P2P PDM " HV_PDM_FIRMWARE_VERSION;
constexpr char CONFIG_KEY[] = "v2";
constexpr uint64_t HOUR_MS = 3600000;
constexpr uint64_t MAX_QUERY_TIME = 9007199254740990ULL;
constexpr unsigned HISTORY_PAGE_SIZE = 1536;

const IPAddress DEFAULT_LAN(172, 20, 1, 110);
const IPAddress DEFAULT_MASK(255, 255, 0, 0);
const IPAddress DEFAULT_GATEWAY(172, 20, 1, 254);
const IPAddress DEFAULT_AP(192, 168, 1, 1);
const IPAddress DEFAULT_AP_MASK(255, 255, 255, 0);

struct LanConfig {
  uint32_t ip = (uint32_t)DEFAULT_LAN;
  uint32_t mask = (uint32_t)DEFAULT_MASK;
  uint32_t gateway = (uint32_t)DEFAULT_GATEWAY;
  uint8_t dhcp = 0;
  uint8_t reserved[3]{};
};

struct WifiConfig {
  uint32_t ip = (uint32_t)DEFAULT_AP;
  uint32_t mask = (uint32_t)DEFAULT_AP_MASK;
  uint32_t gateway = (uint32_t)DEFAULT_AP;
  char ssid[33] = "HV P2P PDM";
  char pass[64] = "hvp2ppdm";
  uint8_t enabled = 1;
  uint8_t bridge = 1;
  uint8_t hidden = 0;
};

struct LogConfig {
  uint32_t period = 500;
  uint8_t hours = 12;
  uint8_t reserved[3]{};
};

struct ChannelConfig {
  float offset;
  float actual;
  float low;
  float high;
  uint8_t alarmSaved = 0;
  uint8_t reserved[3]{};
};

constexpr const char* DEFAULT_NAMES[] = {"48v Input #1", "48v Input #2", "24v Output", "12v Output"};
struct NameConfig {
  char name[4][129] = {"48v Input #1", "48v Input #2", "24v Output", "12v Output"};
};

LanConfig lan;
WifiConfig wifi;
LogConfig logConfig;
ChannelConfig channels[4] = {
    {0, NAN, 42.0f, 52.0f}, {0, NAN, 42.0f, 52.0f},
    {0, NAN, 20.0f, 28.0f}, {0, NAN, 10.5f, 14.5f}
};
NameConfig names;
String inheritedNames[4];
WebServer server(80);
char bootId[9];
uint32_t calibrationVersion = 0;
bool ethConfigOk = false;
bool apStarted = false;
bool apConfigOk = false;
bool naptActive = false;
const char* routingState = "starting";
uint64_t routingCheckAt = 0;
uint64_t rebootAt = 0;

bool parseUnsigned(const char* text, uint64_t& value) {
  if (!text || !*text) return false;
  value = 0;
  while (*text) {
    if (*text < '0' || *text > '9') return false;
    const unsigned digit = *text++ - '0';
    if (value > (MAX_QUERY_TIME - digit) / 10) return false;
    value = value * 10 + digit;
  }
  return true;
}

bool unsignedValue(JsonVariantConst v, uint64_t& value) {
  if (v.is<uint64_t>()) {
    value = v.as<uint64_t>();
    return value <= MAX_QUERY_TIME;
  }
  return parseUnsigned(v.as<const char*>(), value);
}

bool readText(JsonVariantConst v, const char*& text, size_t maxLength) {
  if (!v.is<const char*>()) return false;
  const JsonString s = v.as<JsonString>();
  text = s.c_str();
  return text && s.size() <= maxLength && strlen(text) == s.size();
}

bool parseAddress(const char* text, uint32_t& result) {
  if (!text) return false;
  uint8_t octet[4];
  for (unsigned i = 0; i < 4; ++i) {
    unsigned number = 0;
    unsigned digits = 0;
    while (*text >= '0' && *text <= '9') {
      number = number * 10 + (*text++ - '0');
      if (++digits > 3 || number > 255) return false;
    }
    if (!digits || *text != (i == 3 ? '\0' : '.')) return false;
    octet[i] = number;
    if (i != 3) ++text;
  }
  result = (uint32_t)IPAddress(octet);
  return true;
}

uint32_t hostOrder(uint32_t value) {
  const IPAddress ip(value);
  return (uint32_t)ip[0] << 24 | (uint32_t)ip[1] << 16 | (uint32_t)ip[2] << 8 | ip[3];
}

uint32_t ipOrder(uint32_t host) {
  return (uint32_t)IPAddress(host >> 24, host >> 16, host >> 8, host);
}

bool validStatic(uint32_t ip, uint32_t mask, uint32_t gateway) {
  const uint32_t host = hostOrder(ip);
  const uint32_t netmask = hostOrder(mask);
  const uint32_t gw = hostOrder(gateway);
  const uint32_t hostMask = ~netmask;
  const uint32_t suffix = host & hostMask;
  if (!host || !netmask || (hostMask & (hostMask + 1)) || (host >> 24) >= 224 ||
      (host >> 24) == 127 || (host >> 24) == 0) return false;
  if (hostMask > 1 && (!suffix || suffix == hostMask)) return false;
  if (!gw) return true;
  const uint32_t gatewaySuffix = gw & hostMask;
  return ((host ^ gw) & netmask) == 0 &&
         (hostMask <= 1 || (gatewaySuffix && gatewaySuffix != hostMask));
}

bool subnetsOverlap(uint32_t a, uint32_t aMask, uint32_t b, uint32_t bMask) {
  return ((a ^ b) & (aMask & bMask)) == 0;
}

uint32_t leaseStart(const WifiConfig& config) {
  const uint32_t ip = hostOrder(config.ip);
  const uint32_t mask = hostOrder(config.mask);
  const uint32_t gw = hostOrder(config.gateway);
  const uint32_t start = (ip & mask) + 1;
  const uint32_t last = (ip | ~mask) - 1;
  if (~mask < 15) return 0;
  const auto usable = [&](uint32_t base) {
    return base >= start && base <= last - 10 && !(ip >= base && ip <= base + 10) &&
           !(gw >= base && gw <= base + 10);
  };
  const uint32_t preferred = (ip & 0xffffff00) | 100;
  if (usable(preferred)) return ipOrder(preferred);
  if (usable(start)) return ipOrder(start);
  if (usable(ip + 1)) return ipOrder(ip + 1);
  if (usable(gw + 1)) return ipOrder(gw + 1);
  return 0;
}

bool validWifi(const WifiConfig& config) {
  const size_t ssidLen = strnlen(config.ssid, sizeof config.ssid);
  const size_t passLen = strnlen(config.pass, sizeof config.pass);
  return ssidLen > 0 && ssidLen < sizeof config.ssid && passLen < sizeof config.pass &&
         (passLen == 0 || passLen >= 8) && config.enabled <= 1 && config.bridge <= 1 &&
         config.hidden <= 1 && validStatic(config.ip, config.mask, config.gateway) &&
         leaseStart(config);
}

bool validPeriod(uint64_t ms) {
  return ms == 250 || ms == 500 || ms == 1000 || ms == 2000;
}

bool validAlarm(float low, float high) {
  return isfinite(low) && isfinite(high) && low < high && low >= -1000 && high <= 1000;
}

template<typename T>
bool loadBlob(Preferences& prefs, T& data) {
  return prefs.getBytesLength(CONFIG_KEY) == sizeof data &&
         prefs.getBytes(CONFIG_KEY, &data, sizeof data) == sizeof data;
}

template<typename T>
bool saveBlob(const char* space, const T& data) {
  Preferences prefs;
  if (!prefs.begin(space, false)) return false;
  return prefs.putBytes(CONFIG_KEY, &data, sizeof data) == sizeof data;
}

void readLegacyAddress(Preferences& prefs, const char* key, uint32_t& result) {
  const String text = prefs.getString(key);
  uint32_t parsed;
  if (parseAddress(text.c_str(), parsed)) result = parsed;
}

void loadSettings() {
  {
    Preferences prefs;
    if (prefs.begin("netcfg", true)) {
      LanConfig saved;
      const bool v2 = loadBlob(prefs, saved);
      if (!v2) {
        saved.dhcp = prefs.getBool("dhcp", false);
        readLegacyAddress(prefs, "ip", saved.ip);
        readLegacyAddress(prefs, "sn", saved.mask);
        readLegacyAddress(prefs, "gw", saved.gateway);
      }
      prefs.end();
      if (saved.dhcp <= 1 && validStatic(saved.ip, saved.mask, saved.gateway)) lan = saved;
      if (!v2 && !lan.dhcp && IPAddress(lan.ip) == IPAddress(172, 20, 1, 79) &&
          IPAddress(lan.mask) == DEFAULT_MASK && IPAddress(lan.gateway) == DEFAULT_GATEWAY) {
        lan.ip = (uint32_t)DEFAULT_LAN;
        if (!saveBlob("netcfg", lan)) Serial.println("NVS: LAN default migration could not be saved");
      }
    }
  }
  {
    Preferences prefs;
    if (prefs.begin("wificfg", true)) {
      WifiConfig saved;
      const bool v2 = loadBlob(prefs, saved);
      bool migrate = false;
      if (!v2) {
        saved.enabled = prefs.getBool("en", true);
        saved.bridge = prefs.getBool("br", true);
        saved.hidden = prefs.getBool("hid", false);
        const String ssid = prefs.getString("ssid", saved.ssid);
        const String pass = prefs.getString("pass", saved.pass);
        if (ssid.length() && ssid.length() < sizeof saved.ssid) ssid.toCharArray(saved.ssid, sizeof saved.ssid);
        if (pass.length() < sizeof saved.pass) pass.toCharArray(saved.pass, sizeof saved.pass);
        readLegacyAddress(prefs, "ip", saved.ip);
        readLegacyAddress(prefs, "sn", saved.mask);
        readLegacyAddress(prefs, "gw", saved.gateway);
        const IPAddress oldDefault(172, 20, 1, 1);
        if (IPAddress(saved.ip) == oldDefault && IPAddress(saved.mask) == DEFAULT_AP_MASK &&
            IPAddress(saved.gateway) == oldDefault) {
          saved.ip = (uint32_t)DEFAULT_AP;
          saved.gateway = (uint32_t)DEFAULT_AP;
          migrate = true;
        }
      }
      prefs.end();
      if (validWifi(saved)) wifi = saved;
      else Serial.println("NVS: invalid saved Wi-Fi settings, using defaults");
      if (migrate && !saveBlob("wificfg", wifi)) Serial.println("NVS: AP default migration could not be saved");
    }
  }
  {
    Preferences prefs;
    if (prefs.begin("logcfg", true)) {
      LogConfig saved;
      if (!loadBlob(prefs, saved)) {
        saved.period = prefs.getUInt("period", saved.period);
        saved.hours = prefs.getUChar("hours", saved.hours);
      }
      if (validPeriod(saved.period)) logConfig.period = saved.period;
      if (saved.hours >= 1 && saved.hours <= 12) logConfig.hours = saved.hours;
    }
  }
  {
    Preferences prefs;
    if (prefs.begin("calcfg", true)) {
      ChannelConfig saved[4];
      memcpy(saved, channels, sizeof saved);
      if (!loadBlob(prefs, saved)) {
        for (unsigned i = 0; i < 4; ++i) {
          char off[] = "off0";
          char act[] = "act0";
          off[3] += i;
          act[3] += i;
          saved[i].offset = prefs.getFloat(off, 0);
          saved[i].actual = prefs.getFloat(act, NAN);
        }
      }
      for (unsigned i = 0; i < 4; ++i) {
        if (isfinite(saved[i].offset) && fabsf(saved[i].offset) <= 1000) channels[i].offset = saved[i].offset;
        if (isfinite(saved[i].actual) && saved[i].actual >= 0 && saved[i].actual <= 1000) channels[i].actual = saved[i].actual;
        if (saved[i].alarmSaved == 1 && validAlarm(saved[i].low, saved[i].high)) {
          channels[i].alarmSaved = 1;
          channels[i].low = saved[i].low;
          channels[i].high = saved[i].high;
        }
      }
    }
  }
  {
    Preferences prefs;
    if (prefs.begin("chnames", true)) {
      NameConfig saved;
      const bool v2 = loadBlob(prefs, saved);
      for (unsigned i = 0; i < 4; ++i) {
        if (v2 && memchr(saved.name[i], '\0', sizeof saved.name[i]) && saved.name[i][0]) {
          strcpy(names.name[i], saved.name[i]);
          continue;
        }
        char key[] = "ch1";
        key[2] += i;
        const String legacyName = prefs.getString(key);
        if (legacyName.length() >= sizeof names.name[i]) {
          // Preserve an unusually long legacy label until this channel is edited.
          inheritedNames[i] = legacyName;
          names.name[i][0] = '\0';
        } else if (legacyName.length()) {
          legacyName.toCharArray(names.name[i], sizeof names.name[i]);
        }
      }
    }
  }
}

void sendJson(const JsonDocument& doc, int status = 200) {
  String out;
  if (!out.reserve(measureJson(doc) + 1)) {
    server.send(503, "application/json", "{\"ok\":false,\"error\":\"Response memory unavailable\"}");
    return;
  }
  serializeJson(doc, out);
  server.sendHeader("Cache-Control", "no-store");
  server.send(status, "application/json", out);
}

void errorJson(int status, const char* message) {
  JsonDocument doc;
  doc["ok"] = false;
  doc["error"] = message;
  sendJson(doc, status);
}

bool readBody(JsonDocument& doc) {
  String type = server.header("Content-Type");
  type.toLowerCase();
  if (type != "application/json" && !type.startsWith("application/json;")) {
    errorJson(415, "Use application/json");
    return false;
  }
  const String body = server.arg("plain");
  if (!body.length() || body.length() > 2048 ||
      deserializeJson(doc, body.c_str(), body.length(), DeserializationOption::NestingLimit(3)) || !doc.is<JsonObject>()) {
    errorJson(400, "Invalid JSON settings");
    return false;
  }
  return true;
}

void okJson() {
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", "{\"ok\":true}");
}

const char* activeLanMode() {
  esp_netif_dhcp_status_t status;
  if (ETH.netif() && esp_netif_dhcpc_get_status(ETH.netif(), &status) == ESP_OK) {
    if (status == ESP_NETIF_DHCP_STARTED) return "DHCP";
    if (status == ESP_NETIF_DHCP_STOPPED) {
      if (ETH.hasIP() || (ethConfigOk && !lan.dhcp)) return "Static";
      return "Unknown";
    }
  }
  return ethConfigOk ? (lan.dhcp ? "DHCP" : "Static") : "Unknown";
}

template<typename Object>
void addNetworkState(Object& doc) {
  doc["ipMode"] = activeLanMode();
  doc["ip"] = ETH.localIP().toString();
  doc["subnet"] = ETH.subnetMask().toString();
  doc["gateway"] = ETH.gatewayIP().toString();
  doc["eth_link"] = ETH.linkUp();
  doc["eth_config_ok"] = ethConfigOk;
  doc["eth_has_ip"] = ETH.hasIP();
  doc["ap_enabled"] = (bool)wifi.enabled;
  doc["ap_started"] = apStarted;
  doc["ap_config_ok"] = apConfigOk;
  doc["bridge_enabled"] = (bool)wifi.bridge;
  doc["napt_active"] = naptActive;
  doc["routing_state"] = routingState;
  doc["ap_hidden"] = (bool)wifi.hidden;
  doc["ap_ssid"] = wifi.ssid;
  doc["ap_ipMode"] = "Static";
  doc["ap_ip"] = (apStarted ? WiFi.AP.localIP() : IPAddress(wifi.ip)).toString();
  doc["ap_subnet"] = (apStarted ? WiFi.AP.subnetMask() : IPAddress(wifi.mask)).toString();
  doc["ap_gateway"] = (apStarted ? WiFi.AP.gatewayIP() : IPAddress(wifi.gateway)).toString();
}

template<typename Object>
void addLegacyCalibration(Object& doc) {
  for (unsigned i = 0; i < 4; ++i) {
    char off[] = "offset0";
    char act[] = "actual0";
    off[6] += i;
    act[6] += i;
    doc[off] = channels[i].offset;
    if (isfinite(channels[i].actual)) doc[act] = channels[i].actual;
    else doc[act] = nullptr;
  }
}

void sendCalibration(bool saved = false) {
  JsonDocument doc;
  if (saved) doc["ok"] = true;
  doc["calibration_version"] = calibrationVersion;
  JsonArray offsets = doc["offsets"].to<JsonArray>();
  JsonArray actuals = doc["actuals"].to<JsonArray>();
  JsonArray alarms = doc["thresholds"].to<JsonArray>();
  for (const auto& channel : channels) {
    offsets.add(channel.offset);
    if (isfinite(channel.actual)) actuals.add(channel.actual);
    else actuals.add(nullptr);
    JsonObject limits = alarms.add<JsonObject>();
    limits["low"] = channel.low;
    limits["high"] = channel.high;
    limits["saved"] = (bool)channel.alarmSaved;
  }
  sendJson(doc);
}

void handleCalibrationGet() { sendCalibration(); }

bool finiteValue(JsonVariantConst v, float& value, float minimum, float maximum) {
  if (!v.is<float>()) return false;
  value = v.as<float>();
  return isfinite(value) && value >= minimum && value <= maximum;
}

bool updateChannel(JsonObjectConst body, ChannelConfig (&updated)[4]) {
  uint64_t ch;
  if (!unsignedValue(body["channel"], ch) || ch < 1 || ch > 4) return false;
  auto& entry = updated[ch - 1];
  const bool migrate = body["migrate"].is<bool>() && body["migrate"].as<bool>();
  const bool hasLimits = !body["low"].isUnbound() || !body["high"].isUnbound();
  if (hasLimits && (!migrate || !entry.alarmSaved)) {
    if (!finiteValue(body["low"], entry.low, -1000, 1000) ||
        !finiteValue(body["high"], entry.high, -1000, 1000) ||
        !validAlarm(entry.low, entry.high)) return false;
    entry.alarmSaved = 1;
  }
  if (!body["actual"].isUnbound()) {
    if (migrate) return false;
    if (body["actual"].isNull()) {
      entry.actual = NAN;
      entry.offset = 0;
    } else {
      if (!finiteValue(body["actual"], entry.actual, 0, 1000)) return false;
      const LiveSnapshot state = liveSnapshot();
      const uint64_t maxAge = max((uint32_t)2000, 2 * logConfig.period);
      if (!state.hasSample || !isfinite(state.latest.v[ch - 1]) || state.now - state.latest.t > maxAge) return false;
      entry.offset = entry.actual - state.latest.v[ch - 1];
    }
  }
  return hasLimits || !body["actual"].isUnbound();
}

bool updateLegacyCalibration(JsonObjectConst body, ChannelConfig (&updated)[4]) {
  bool found = false;
  for (unsigned i = 0; i < 4; ++i) {
    char off[] = "offset0";
    char act[] = "actual0";
    off[6] += i;
    act[6] += i;
    if (!body[off].isUnbound()) {
      if (!finiteValue(body[off], updated[i].offset, -1000, 1000)) return false;
      found = true;
    }
    if (!body[act].isUnbound()) {
      if (body[act].isNull()) updated[i].actual = NAN;
      else if (!finiteValue(body[act], updated[i].actual, 0, 1000)) return false;
      found = true;
    }
  }
  return found;
}

void handleCalibrationPost() {
  JsonDocument request;
  if (!readBody(request)) return;
  ChannelConfig updated[4];
  memcpy(updated, channels, sizeof updated);
  const JsonObjectConst body = request.as<JsonObjectConst>();
  const bool ok = !body["channel"].isUnbound() ? updateChannel(body, updated) : updateLegacyCalibration(body, updated);
  if (!ok) {
    errorJson(400, "Invalid channel settings or no fresh ADC reading for calibration");
    return;
  }
  if (memcmp(updated, channels, sizeof updated) != 0) {
    if (!saveBlob("calcfg", updated)) { errorJson(503, "Calibration storage write failed"); return; }
    memcpy(channels, updated, sizeof channels);
    ++calibrationVersion;
  }
  sendCalibration(true);
}

void sendNames(bool saved = false) {
  JsonDocument doc;
  if (saved) doc["ok"] = true;
  for (unsigned i = 0; i < 4; ++i) {
    char key[] = "ch1";
    key[2] += i;
    doc[key] = names.name[i][0] ? names.name[i] : inheritedNames[i].c_str();
  }
  sendJson(doc);
}

void handleNamesGet() { sendNames(); }

void handleNamesPost() {
  JsonDocument doc;
  if (!readBody(doc)) return;
  NameConfig updated = names;
  bool found = false;
  for (unsigned i = 0; i < 4; ++i) {
    char key[] = "ch1";
    key[2] += i;
    if (doc.as<JsonObjectConst>()[key].isUnbound()) continue;
    const char* name;
    if (!readText(doc[key], name, sizeof updated.name[i] - 1)) {
      errorJson(400, "Channel names must fit in 128 UTF-8 bytes");
      return;
    }
    memset(updated.name[i], 0, sizeof updated.name[i]);
    strcpy(updated.name[i], *name ? name : DEFAULT_NAMES[i]);
    found = true;
  }
  if (!found) { errorJson(400, "No channel name supplied"); return; }
  if (memcmp(&updated, &names, sizeof names) != 0) {
    if (!saveBlob("chnames", updated)) { errorJson(503, "Channel name storage write failed"); return; }
    names = updated;
  }
  sendNames(true);
}

void sendLogConfig(bool saved = false) {
  JsonDocument doc;
  if (saved) doc["ok"] = true;
  doc["log_hours"] = logConfig.hours;
  doc["sample_period_ms"] = logConfig.period;
  sendJson(doc);
}

void handleLogGet() { sendLogConfig(); }

void handleLogPost() {
  JsonDocument doc;
  if (!readBody(doc)) return;
  const JsonObjectConst body = doc.as<JsonObjectConst>();
  const bool hasHours = !body["log_hours"].isUnbound();
  const bool hasPeriod = !body["sample_period_ms"].isUnbound();
  uint64_t hours = logConfig.hours;
  uint64_t periodMs = logConfig.period;
  if ((!hasHours && !hasPeriod) ||
      (hasHours && !unsignedValue(body["log_hours"], hours)) ||
      (hasPeriod && !unsignedValue(body["sample_period_ms"], periodMs)) ||
      hours < 1 || hours > 12 || !validPeriod(periodMs)) {
    errorJson(400, "Choose 1-12 hours and 250, 500, 1000 or 2000 ms");
    return;
  }
  if (logConfig.hours != hours || logConfig.period != periodMs) {
    const LogConfig updated{(uint32_t)periodMs, (uint8_t)hours, {}};
    if (!saveBlob("logcfg", updated)) { errorJson(503, "Log settings storage write failed"); return; }
    logConfig = updated;
    setLogHours(logConfig.hours);
    setSamplePeriod(logConfig.period);
  }
  sendLogConfig(true);
}

void handleNetGet() {
  JsonDocument doc;
  addNetworkState(doc);
  doc["configured_ipMode"] = lan.dhcp ? "DHCP" : "Static";
  doc["configured_ip"] = IPAddress(lan.ip).toString();
  doc["configured_subnet"] = IPAddress(lan.mask).toString();
  doc["configured_gateway"] = IPAddress(lan.gateway).toString();
  sendJson(doc);
}

void handleWifiGet() {
  JsonDocument doc;
  addNetworkState(doc);
  doc["ap_pass"] = wifi.pass;
  sendJson(doc);
}

void acknowledgeRestart() {
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", "{\"ok\":true,\"rebooting\":true}");
  rebootAt = uptimeMs() + 350;
}

bool getStaticAddresses(JsonObjectConst body, uint32_t& ip, uint32_t& mask, uint32_t& gateway) {
  const char *ipText, *maskText, *gatewayText;
  return readText(body["ip"], ipText, 15) && readText(body["subnet"], maskText, 15) &&
         readText(body["gateway"], gatewayText, 15) && parseAddress(ipText, ip) &&
         parseAddress(maskText, mask) && parseAddress(gatewayText, gateway) && validStatic(ip, mask, gateway);
}

void handleNetPost() {
  if (rebootAt) { errorJson(409, "Restart already pending"); return; }
  JsonDocument doc;
  if (!readBody(doc)) return;
  const char* mode;
  if (!readText(doc["ipMode"], mode, 6) ||
      (strcasecmp(mode, "DHCP") && strcasecmp(mode, "Static"))) {
    errorJson(400, "Choose DHCP or Static");
    return;
  }
  LanConfig updated = lan;
  updated.dhcp = strcasecmp(mode, "DHCP") == 0;
  if (!updated.dhcp && !getStaticAddresses(doc.as<JsonObjectConst>(), updated.ip, updated.mask, updated.gateway)) {
    errorJson(400, "Invalid LAN IP, subnet or gateway");
    return;
  }
  if (!saveBlob("netcfg", updated)) { errorJson(503, "LAN settings storage write failed"); return; }
  acknowledgeRestart();
}

bool updateFlag(JsonObjectConst doc, const char* key, uint8_t& flag) {
  if (doc[key].isUnbound()) return true;
  if (!doc[key].is<bool>()) return false;
  flag = doc[key].as<bool>();
  return true;
}

void handleWifiPost() {
  if (rebootAt) { errorJson(409, "Restart already pending"); return; }
  JsonDocument doc;
  if (!readBody(doc)) return;
  const JsonObjectConst body = doc.as<JsonObjectConst>();
  WifiConfig updated = wifi;
  const char* text;
  if (!updateFlag(body, "enabled", updated.enabled) || !updateFlag(body, "bridge", updated.bridge) ||
      !updateFlag(body, "hidden", updated.hidden) ||
      (!body["ipMode"].isUnbound() && (!readText(body["ipMode"], text, 6) || strcasecmp(text, "Static")))) {
    errorJson(400, "Wi-Fi AP requires a static address and boolean flags");
    return;
  }
  if (!body["ssid"].isUnbound()) {
    if (!readText(body["ssid"], text, 32) || !*text) { errorJson(400, "SSID must be 1-32 UTF-8 bytes"); return; }
    strcpy(updated.ssid, text);
  }
  if (!body["pass"].isUnbound()) {
    if (!readText(body["pass"], text, 63) || (*text && strlen(text) < 8)) {
      errorJson(400, "Password must be blank or 8-63 bytes");
      return;
    }
    strcpy(updated.pass, text);
  }
  if ((!body["ip"].isUnbound() || !body["subnet"].isUnbound() || !body["gateway"].isUnbound()) &&
      !getStaticAddresses(body, updated.ip, updated.mask, updated.gateway)) {
    errorJson(400, "Invalid Wi-Fi AP IP, subnet or gateway");
    return;
  }
  if (!validWifi(updated)) { errorJson(400, "Wi-Fi settings leave no usable DHCP lease range"); return; }
  if (!saveBlob("wificfg", updated)) { errorJson(503, "Wi-Fi settings storage write failed"); return; }
  acknowledgeRestart();
}

void startNetwork() {
  ethConfigOk = ETH.begin();
  if (ethConfigOk && !lan.dhcp) {
    ethConfigOk = ETH.config(IPAddress(lan.ip), IPAddress(lan.gateway), IPAddress(lan.mask), IPAddress(lan.gateway));
  }
  Serial.printf("LAN: %s, requested %s\n", ethConfigOk ? "configured" : "configuration failed",
                lan.dhcp ? "DHCP" : IPAddress(lan.ip).toString().c_str());
  if (!wifi.enabled) {
    WiFi.mode(WIFI_OFF);
    return;
  }
  if (!WiFi.mode(WIFI_AP)) return;
  WiFi.setSleep(false);
  const IPAddress dns = ETH.dnsIP();
  apConfigOk = WiFi.softAPConfig(IPAddress(wifi.ip), IPAddress(wifi.gateway), IPAddress(wifi.mask),
                                 IPAddress(leaseStart(wifi)), (uint32_t)dns ? dns : IPAddress(lan.gateway));
  apStarted = WiFi.softAP(wifi.ssid, *wifi.pass ? wifi.pass : nullptr, 6, wifi.hidden);
  Serial.printf("AP: %s, actual IP %s, configuration %s\n", apStarted ? "started" : "start failed",
                WiFi.softAPIP().toString().c_str(), apConfigOk ? "OK" : "failed");
}

void serviceRouting() {
  const uint64_t now = uptimeMs();
  if (now < routingCheckAt) return;
  routingCheckAt = now + 1000;
  const char* previous = routingState;
  const bool ethOnline = ethConfigOk && ETH.linkUp() && ETH.hasIP();
  if (ethOnline && !ETH.isDefault()) ETH.setDefault();
  if (!wifi.bridge) routingState = "disabled";
  else if (!apStarted || !apConfigOk) routingState = "AP unavailable";
  else if (!ethOnline || !ETH.isDefault()) routingState = "waiting for Ethernet";
  else if (subnetsOverlap((uint32_t)WiFi.AP.localIP(), (uint32_t)WiFi.AP.subnetMask(),
                          (uint32_t)ETH.localIP(), (uint32_t)ETH.subnetMask())) routingState = "subnets overlap";
  else if (naptActive || WiFi.AP.enableNAPT(true)) {
    naptActive = true;
    routingState = "active";
  } else {
    routingState = "NAPT enable failed";
    routingCheckAt = now + 5000;
  }
  if (strcmp(routingState, "active") && naptActive) {
    if (WiFi.AP.enableNAPT(false)) naptActive = false;
    else routingState = "NAPT disable failed";
  }
  if (strcmp(previous, routingState)) Serial.printf("NAPT: %s\n", routingState);
}

const char* alarmFor(unsigned ch, float raw) {
  if (!isfinite(raw)) return "--";
  const float voltage = raw + channels[ch].offset;
  if (voltage <= channels[ch].low) return "LOW";
  if (voltage >= channels[ch].high) return "HIGH";
  return "OK";
}


double rawMillivolts(float value) {
  return (double)lroundf(value * 1000.0f) / 1000.0;
}

bool allVoltages(const LiveSnapshot& state) {
  if (!state.hasSample || state.now - state.latest.t > max((uint32_t)2000, 2 * logConfig.period)) return false;
  for (float value : state.latest.v) {
    if (!isfinite(value)) return false;
  }
  return true;
}

void addHealth(JsonDocument& doc, const LiveSnapshot& state) {
  doc["adc_ok"] = allVoltages(state);
  doc["sd_ok"] = state.sdMounted;
  doc["log_healthy"] = state.logHealthy;
  doc["log_dropped"] = state.dropped;
  doc["sample_missed"] = missedSampleSlots();
  doc["stored_through"] = state.storedThrough;
  doc["fw_version"] = HV_PDM_FIRMWARE_VERSION;
  doc["fw_update"] = pdmOtaPhase();
  doc["fw_progress"] = pdmOtaPercent();
}

void handleVoltages() {
  uint64_t after = 0;
  const bool hasCursor = server.hasArg("after");
  if (hasCursor && !parseUnsigned(server.arg("after").c_str(), after)) {
    errorJson(400, "Invalid live sample cursor");
    return;
  }
  Sample recent[RECENT_PAGE];
  const LiveSnapshot state = liveSnapshot(after, hasCursor ? recent : nullptr);
  JsonDocument doc;
  const char* keys[] = {"v48_1", "v48_2", "v24", "v12"};
  JsonArray alarms = doc["alarms"].to<JsonArray>();
  const bool fresh = state.hasSample && state.now - state.latest.t <= max((uint32_t)2000, 2 * logConfig.period);
  for (unsigned i = 0; i < 4; ++i) {
    const float v = fresh ? state.latest.v[i] : NAN;
    if (isfinite(v)) doc[keys[i]] = rawMillivolts(v);
    else doc[keys[i]] = nullptr;
    alarms.add(alarmFor(i, v));
  }
  doc["t"] = state.hasSample ? state.latest.t : 0;
  doc["utc_ms"] = state.hasSample ? state.latest.utc : 0;
  doc["now_t"] = state.now;
  doc["now_utc_ms"] = utcMs();
  doc["boot"] = bootId;
  doc["generation"] = state.generation;
  doc["log_hours"] = logConfig.hours;
  doc["sample_period_ms"] = logConfig.period;
  doc["calibration_version"] = calibrationVersion;
  addHealth(doc, state);
  addNetworkState(doc);
  addLegacyCalibration(doc);
  if (hasCursor) {
    doc["gap"] = state.gap;
    doc["more"] = state.more;
    JsonArray rows = doc["recent"].to<JsonArray>();
    for (unsigned i = 0; i < state.count; ++i) {
      JsonArray row = rows.add<JsonArray>();
      row.add(recent[i].t);
      row.add(recent[i].utc);
      for (float value : recent[i].v) {
        if (isfinite(value)) row.add(rawMillivolts(value));
        else row.add(nullptr);
      }
    }
  }
  sendJson(doc);
}

void handleSelfTest() {
  JsonDocument doc;
  const LiveSnapshot state = liveSnapshot();
  addHealth(doc, state);
  addNetworkState(doc);
  doc["version"] = VERSION;
  doc["uptime_ms"] = uptimeMs();
  doc["heap_free"] = ESP.getFreeHeap();
  doc["heap_minimum"] = ESP.getMinFreeHeap();
  sendJson(doc);
}

void handleTimePost() {
  JsonDocument doc;
  if (!readBody(doc)) return;
  uint64_t value;
  if (!unsignedValue(doc["utc_ms"], value) || value < 1577836800000ULL || value >= 4102444800000ULL) {
    errorJson(400, "Invalid UTC time");
    return;
  }
  if (!utcMs()) {
    const timeval now{(time_t)(value / 1000), (suseconds_t)(value % 1000 * 1000)};
    if (settimeofday(&now, nullptr) != 0) { errorJson(503, "Clock sync failed"); return; }
  }
  okJson();
}

class ChunkOutput {
 public:
  explicit ChunkOutput(const char* type) : deadline(uptimeMs() + 20000) {
    server.sendHeader("Cache-Control", "no-store");
    server.chunkResponseBegin(type);
  }

  bool add(const char* line, size_t length) {
    if (length > sizeof buffer) return false;
    if (used + length > sizeof buffer && !flush()) return false;
    memcpy(buffer + used, line, length);
    used += length;
    return true;
  }

  bool add(const char* text) { return add(text, strlen(text)); }

  bool finish(bool ok) {
    if (ok) ok = flush();
    if (!ok) server.client().stop();
    server.chunkResponseEnd();
    return ok;
  }

 private:
  bool flush() {
    if (uptimeMs() >= deadline || !server.client().connected()) return false;
    if (used) {
      server.chunkWrite(buffer, used);
      used = 0;
    }
    return server.client().connected();
  }

  const uint64_t deadline;
  char buffer[1024];
  size_t used = 0;
};

struct CsvOutput {
  ChunkOutput& out;
  bool legacy;
};

bool emitCsv(const Sample& sample, void* ptr) {
  auto& sink = *static_cast<CsvOutput*>(ptr);
  char v[4][18];
  for (unsigned i = 0; i < 4; ++i) {
    if (isfinite(sample.v[i])) snprintf(v[i], sizeof v[i], "%.3f", (double)sample.v[i]);
    else v[i][0] = '\0';
  }
  char line[128];
  const int n = sink.legacy
      ? snprintf(line, sizeof line, "%llu,%s,%s,%s,%s\n", (unsigned long long)sample.t, v[0], v[1], v[2], v[3])
      : snprintf(line, sizeof line, "%llu,%llu,%s,%s,%s,%s\n", (unsigned long long)sample.t,
                 (unsigned long long)sample.utc, v[0], v[1], v[2], v[3]);
  return n > 0 && n < (int)sizeof line && sink.out.add(line, n);
}

struct JsonOutput {
  ChunkOutput& out;
  uint64_t end;
  uint64_t stride;
  unsigned maxPoints;
  uint64_t last = 0;
  unsigned emitted = 0;
};

bool emitJson(const Sample& sample, void* ptr) {
  auto& sink = *static_cast<JsonOutput*>(ptr);
  if (sample.t != sink.end && (sink.emitted >= sink.maxPoints - 1 ||
      (sink.emitted && sample.t - sink.last < sink.stride))) return true;
  char v[4][18];
  for (unsigned i = 0; i < 4; ++i) {
    if (isfinite(sample.v[i])) snprintf(v[i], sizeof v[i], "%.3f", (double)sample.v[i]);
    else strcpy(v[i], "null");
  }
  char line[192];
  const int n = snprintf(line, sizeof line, "%s{\"t\":%llu,\"utc_ms\":%llu,\"v48_1\":%s,\"v48_2\":%s,\"v24\":%s,\"v12\":%s}",
                         sink.emitted ? "," : "", (unsigned long long)sample.t,
                         (unsigned long long)sample.utc, v[0], v[1], v[2], v[3]);
  sink.last = sample.t;
  ++sink.emitted;
  return n > 0 && n < (int)sizeof line && sink.out.add(line, n);
}

bool readQuery(const char* key, uint64_t& value) {
  return !server.hasArg(key) || parseUnsigned(server.arg(key).c_str(), value);
}

void handleHistory() {
  SdReadLease lease;
  const LiveSnapshot state = liveSnapshot();
  const bool csv = server.arg("format") == "csv";
  uint64_t hours = csv ? logConfig.hours : 1;
  uint64_t points = 720;
  uint64_t end = state.now;
  uint64_t before = 0;
  uint64_t offset = 0;
  uint64_t generation = state.generation;
  if (!readQuery("hours", hours) || !readQuery("maxPoints", points) || !readQuery("end", end) ||
      !readQuery("before", before) || !readQuery("offset", offset) || !readQuery("generation", generation)) {
    errorJson(400, "Invalid history range");
    return;
  }
  if (generation != state.generation) { errorJson(409, "History source changed"); return; }
  hours = std::min<uint64_t>(logConfig.hours, std::max<uint64_t>(1, hours));
  end = min(end, state.now);
  const uint64_t cutoff = end > hours * HOUR_MS ? end - hours * HOUR_MS : 0;
  const uint64_t storedEnd = min(end, state.storedThrough);
  if (csv) {
    if (!lease) { errorJson(503, "SD history unavailable"); return; }
    if (!before || before > storedEnd + 1) before = storedEnd + 1;
    ChunkOutput out("text/csv; charset=utf-8");
    CsvOutput sink{out, false};
    out.add("t_ms,utc_ms,v48_1,v48_2,v24,v12\n");
    const HistoryPage page = readHistoryPage(storedEnd, cutoff, before, offset, HISTORY_PAGE_SIZE, emitCsv, &sink);
    char trailer[64];
    snprintf(trailer, sizeof trailer, "#end,%llu,%llu\n",
             (unsigned long long)page.before, (unsigned long long)page.legacyOffset);
    out.finish(page.ok && out.add(trailer));
    return;
  }
  points = min(1440ULL, max(60ULL, (unsigned long long)points));
  JsonDocument meta;
  addNetworkState(meta);
  addLegacyCalibration(meta);
  addHealth(meta, state);
  String details;
  serializeJson(meta, details);
  if (details.length() < 2) { errorJson(503, "History metadata unavailable"); return; }
  ChunkOutput out("application/json");
  JsonOutput sink{out, storedEnd, max(1ULL, (unsigned long long)(hours * HOUR_MS / (points - 1))), (unsigned)points};
  out.add("{\"samples\":[");
  const bool ok = !lease || readHistoryForward(storedEnd, cutoff, emitJson, &sink);
  out.finish(ok && out.add("],") && out.add(details.c_str() + 1));
}

void handleRawCsv() {
  SdReadLease lease;
  if (!lease) { errorJson(503, "SD history unavailable"); return; }
  const LiveSnapshot state = liveSnapshot();
  const uint64_t span = logConfig.hours * HOUR_MS;
  const uint64_t cutoff = state.now > span ? state.now - span : 0;
  ChunkOutput out("text/csv; charset=utf-8");
  CsvOutput sink{out, true};
  out.add("unix,v48_1,v48_2,v24,v12\n");
  out.finish(readHistoryForward(state.storedThrough, cutoff, emitCsv, &sink));
}

template<size_t N>
void serveAsset(const uint8_t (&data)[N], const char* type) {
  server.sendHeader("Cache-Control", "no-cache");
  server.sendHeader("Content-Encoding", "gzip");
  server.send_P(200, type, reinterpret_cast<PGM_P>(data), N);
}

void setupWatchdog() {
  uint32_t idleMask = 0;
#if CONFIG_ESP_TASK_WDT_CHECK_IDLE_TASK_CPU0
  idleMask |= 1;
#endif
#if CONFIG_ESP_TASK_WDT_CHECK_IDLE_TASK_CPU1
  idleMask |= 2;
#endif
  const esp_task_wdt_config_t config{20000, idleMask, true};
  const esp_err_t status = esp_task_wdt_status(nullptr);
  const esp_err_t result = status == ESP_ERR_INVALID_STATE ? esp_task_wdt_init(&config) : esp_task_wdt_reconfigure(&config);
  if (result != ESP_OK) Serial.printf("WDT: configuration failed (%s)\n", esp_err_to_name(result));
}
}  // namespace

void pdmSetup() {
  Serial.begin(115200);
  Serial.printf("\n=== %s ===\n", VERSION);
  snprintf(bootId, sizeof bootId, "%08lx", (unsigned long)esp_random());
  loadSettings();
  setupWatchdog();
  if (!startLogWorker(logConfig.hours)) Serial.println("SD: could not start worker");
  if (!startSampler(logConfig.period)) Serial.println("ADC: could not start sampler");
  startNetwork();

  const char* headers[] = {"Content-Type"};
  server.collectHeaders(headers, sizeof headers / sizeof headers[0]);
  server.on("/", HTTP_GET, [] { serveAsset(PdmWeb::index, "text/html; charset=utf-8"); });
  server.on("/index.html", HTTP_GET, [] { serveAsset(PdmWeb::index, "text/html; charset=utf-8"); });
  server.on("/index_ios.html", HTTP_GET, [] { serveAsset(PdmWeb::indexIos, "text/html; charset=utf-8"); });
  server.on("/chart.umd.min.js", HTTP_GET, [] { serveAsset(PdmWeb::chart, "application/javascript"); });
  server.on("/pdm.js", HTTP_GET, [] { serveAsset(PdmWeb::dashboard, "application/javascript"); });
  server.on("/Chart.js-LICENSE.txt", HTTP_GET, [] { serveAsset(PdmWeb::chartLicense, "text/plain; charset=utf-8"); });
  server.on("/pdm_log.csv", HTTP_GET, handleRawCsv);
  server.on("/api/voltages", HTTP_GET, handleVoltages);
  server.on("/api/history", HTTP_GET, handleHistory);
  server.on("/api/net", HTTP_GET, handleNetGet);
  server.on("/api/net", HTTP_POST, handleNetPost);
  server.on("/api/wifi", HTTP_GET, handleWifiGet);
  server.on("/api/wifi", HTTP_POST, handleWifiPost);
  server.on("/api/calibration", HTTP_GET, handleCalibrationGet);
  server.on("/api/calibration", HTTP_POST, handleCalibrationPost);
  server.on("/api/logcfg", HTTP_GET, handleLogGet);
  server.on("/api/logcfg", HTTP_POST, handleLogPost);
  server.on("/api/names", HTTP_GET, handleNamesGet);
  server.on("/api/names", HTTP_POST, handleNamesPost);
  server.on("/api/self-test", HTTP_GET, handleSelfTest);
  server.on("/api/time", HTTP_POST, handleTimePost);
  server.onNotFound([] { server.send(404, "text/plain", "Not found"); });
  server.begin();
  startPdmOta();
  Serial.println("HTTP server started on port 80.");
}

void pdmLoop() {
  if (rebootAt && uptimeMs() >= rebootAt) ESP.restart();
  serviceRouting();
  servicePdmOtaConsole();
  server.handleClient();
  delay(2);
}
