#include <ETH.h>
#include <SPI.h>
#include "hal/uart_types.h"
#include "HV_P2P_RS485_Frame.h"
#include "HV_P2P_CTRL_TS_Firmware_Image.h"
#include <NetworkUdp.h>
#include <WebServer.h>
#include <Update.h>
#include <nvs_flash.h>
#include <Wire.h>
#include <Preferences.h>
#include "HV_P2P_SRVR_Authority_OTA.h"

// EdgeBox-ESP-100 CTRL hardware layer. The onboard SGM58031 at 0x48 is
// driven directly using its documented register map; no external ADS1115 is required.
static bool g_ads_inited = false;
static uint8_t ADS_ADDR = 0x48;

#define CTRL_VERSION "HV P2P CTRL EdgeBox v26.10.06.06"
#define CTRL_HMI_ARCH "EdgeBox ESP-100 + isolated RS485 Waveshare thin HMI"

IPAddress local_IP(172,20,1,101);
IPAddress gateway(172,20,1,1);
IPAddress subnet(255,255,0,0);
IPAddress server_IP(172,20,1,100);

#define UDP_PORT 5000

// Seeed EdgeBox-ESP-100 fixed peripheral mapping.
#define SDA_PIN 20
#define SCL_PIN 19
#define EDGEBOX_ETH_CS   10
#define EDGEBOX_ETH_MISO 11
#define EDGEBOX_ETH_MOSI 12
#define EDGEBOX_ETH_SCLK 13
#define EDGEBOX_ETH_INT  14
#define EDGEBOX_ETH_RST  15
#define EDGEBOX_RS485_TX 17
#define EDGEBOX_RS485_RX 18
#define EDGEBOX_RS485_RTS 8

#define HEARTBEAT_INTERVAL_MS 250
#define CONTROL_INTERVAL_MS   25
#define DISPLAY_FORWARD_MIN_MS 250
#define HMI_POLL_INTERVAL_MS 60
#define HMI_POLL_RESPONSE_TIMEOUT_MS 250
#define HMI_POLL_RECOVERY_QUIET_MS 300
#define DISPLAY_KEEPALIVE_MS   3000
#define HMI_STATE_KEEPALIVE_MS  1000
#define HMI_GEOMETRY_KEEPALIVE_MS 2500
#define HMI_MOTION_MIN_MS          80
#define HMI_MOTION_KEEPALIVE_MS    250
#define HMI_STARTUP_AUTH_GRACE_MS  1500
#define SRVR_DISPLAY_TIMEOUT_MS 5000
#define SRVR_PEER_TIMEOUT_MS     750
#define HMI_BAUD              115200
#define HMI_UART_RX EDGEBOX_RS485_RX
#define HMI_UART_TX EDGEBOX_RS485_TX
#define HMI_UART_RTS EDGEBOX_RS485_RTS

// CTRL EdgeBox input model (commissioned voltage-input hardware):
//   - The factory 249-ohm 4-20 mA shunts have been removed from AI0..AI3.
//   - AI0 carries the CTRL E-stop status as a 5 V normally-closed loop.
//   - AI1 carries the APEM 0-5 V joystick signal.
//     Healthy ~= 5 V; pressed/open/broken wire ~= 0 V. Mid-band values fail unsafe.
//   - The EdgeBox integrated SGM58031 at I2C 0x48 is multiplexed between AI0/AI1.
//   - AUX1..AUX5 are touchscreen-only and arrive from CTRL-TS over RS485.
//   - SRVR remains authoritative for Left/Centre/Right joystick calibration and deadband.
static const float CTRL_ESTOP_HEALTHY_MIN_V = 3.5f;
static const float CTRL_ESTOP_HEALTHY_MAX_V = 6.0f;
static const uint8_t CTRL_ESTOP_HEALTHY_CONFIRM_SAMPLES = 3;

#define FLAG_ESTOP_PRESSED        0x0010
#define FLAG_CANCEL_PRESSED       0x0001
#define FLAG_MODE_TOGGLE          0x0002
#define FLAG_BATT_CHANGE_TOGGLE   0x0004
#define FLAG_AUX1                 0x0020
#define FLAG_AUX2                 0x0040
#define FLAG_AUX3                 0x0080
#define FLAG_AUX4                 0x0100
#define FLAG_ADS1115_FAULT        0x0200  // wire-compatible name; now means CTRL analogue-input fault
#define FLAG_AUX5                 0x0400
#define FLAG_CTRL_HMI_FAULT       0x0800  // CTRL-TS RS485/compatibility safety fault (not physical E-stop)
#define FLAG_CTRL_FW_FAULT        0x1000  // SRVR firmware-authority safety fault (not physical E-stop)
#define FLAG_CAL_CANCEL           0x2000  // CTRL-TS calibration Cancel event, edge-captured by SRVR

NetworkUDP udp;
HardwareSerial HMI(1);
HVP2PRS485::Parser g_hmiParser;
static HVP2PRS485::Frame g_hmiRxFrame;
static uint16_t g_hmiSeq = 1;
static bool g_hmiCompatible = false;
static String g_hmiReportedVersion;
static String g_hmiReportedHash;
static String g_hmiReportedHw;
static String g_hmiReportedBootId;
static int g_hmiReportedResetReason = -1;
static uint8_t g_hmiReportedProto = 0;
static bool g_hmiSafeOtaCapable = false;
static uint8_t g_hmiSafeOtaLevel = 0;
static uint32_t g_lastHmiHelloTxMs = 0;
// After CTRL-TS acknowledges the transition to its display-off updater, hold
// discovery briefly so CTRL cannot rediscover the still-running pre-reboot UI
// and send another FW_BEGIN before the touchscreen's reboot deadline fires.
static uint32_t g_hmiSafeRebootHoldUntilMs = 0;
static uint32_t g_lastHmiPollTxMs = 0;
static uint16_t g_hmiOutstandingPollSeq = 0;
static uint16_t g_hmiPollSeq = 0;
static bool g_hmiPollOutstanding = false;
static uint32_t g_hmiPollStartedMs = 0;
static uint32_t g_hmiBusQuietUntilMs = 0;
static uint16_t g_hmiLastAcceptedEventId = 0;
static bool g_hmiHaveAcceptedEventId = false;
static String g_hmiLastAcceptedEventCmd;
static uint32_t g_hmiPollsSent = 0;
static uint32_t g_hmiPollTimeouts = 0;
static uint32_t g_hmiEventsAccepted = 0;
static uint32_t g_hmiEventsDuplicate = 0;
static uint32_t g_hmiEventsRejected = 0;
static uint32_t g_hmiFramesTx = 0;
static uint32_t g_hmiDisplayFramesTx = 0;
static uint32_t g_hmiTsQueueDrops = 0;
static uint32_t g_hmiTsParserCrc = 0;
static uint32_t g_hmiTsParserResync = 0;

// CTRL is the firmware authority for the Waveshare CTRL-TS. A generated
// HV_P2P_CTRL_TS_Firmware_Image.h embeds the exact exported .bin, version and
// SHA-256. When identity differs, CTRL keeps motion fail-safe stopped and
// performs a deterministic request/response transfer over the same RS485 link.
enum HmiFwTxState : uint8_t { HMI_FW_IDLE=0, HMI_FW_WAIT_READY, HMI_FW_WAIT_BLOCK_ACK, HMI_FW_WAIT_RESULT, HMI_FW_WAIT_REBOOT_ACK, HMI_FW_WAIT_REBOOT_CONFIRM };
static HmiFwTxState g_hmiFwState = HMI_FW_IDLE;
static size_t g_hmiFwOffset = 0;
static size_t g_hmiFwLastBlockLen = 0;
static uint16_t g_hmiFwSeq = 0;
static uint32_t g_hmiFwLastTxMs = 0;
static uint8_t g_hmiFwRetries = 0;
static int g_hmiFwLastPct = -1;
static String g_hmiFwPreUpdateBootId;
static uint32_t g_hmiFwRebootConfirmStartedMs = 0;
static uint8_t g_hmiFwRebootEnforceCount = 0;
static const size_t HMI_FW_BLOCK_DATA = 1024;
static const uint32_t HMI_FW_REPLY_TIMEOUT_MS = 3000;
static const uint32_t HMI_RS485_TURNAROUND_US = 2500;
static const uint8_t HMI_FW_MAX_RETRIES = 5;

static bool hmiSendText(const String &line);
static bool hmiFwActive();
static bool hmiNormalTxAllowed();

// -------------------- CTRL-TS editable network settings --------------------
// Settings are edited on CTRL-TS over UART, saved in CTRL NVS, and applied
// after CTRL resets. CTRL-TS remains UART-only; it does not use Ethernet.
static Preferences netPrefs;
static const char* NET_PREF_NS = "netcfg";

static String ipToString(const IPAddress &ip){
  return String(ip[0]) + "." + String(ip[1]) + "." + String(ip[2]) + "." + String(ip[3]);
}

static bool parseIpString(const String &s_in, IPAddress &out){
  String s = s_in;
  s.trim();
  int oct[4] = {0,0,0,0};
  int start = 0;
  for(int i=0;i<4;i++){
    int dot = s.indexOf('.', start);
    String part = (dot >= 0) ? s.substring(start, dot) : s.substring(start);
    part.trim();
    if(!part.length()) return false;
    for(size_t j=0;j<part.length();j++) if(!isDigit(part[j])) return false;
    int v = part.toInt();
    if(v < 0 || v > 255) return false;
    oct[i] = v;
    if(i < 3 && dot < 0) return false;
    if(i == 3 && dot >= 0) return false;
    start = dot + 1;
  }
  out = IPAddress((uint8_t)oct[0], (uint8_t)oct[1], (uint8_t)oct[2], (uint8_t)oct[3]);
  return true;
}

static String hvGetPipeField(const String &line, const char *key){
  String token = String("|") + key + "=";
  int st = line.indexOf(token);
  if(st < 0){
    if(line.startsWith(String(key) + "=")) st = -1;
    else return "";
  }
  if(st >= 0) st += token.length(); else st = strlen(key) + 1;
  int end = line.indexOf('|', st);
  if(end < 0) end = line.length();
  return line.substring(st, end);
}

static void hvLoadNetworkConfig(){
  netPrefs.begin(NET_PREF_NS, true);
  String s;
  IPAddress ip;
  s = netPrefs.getString("ctrl_ip", ""); if(s.length() && parseIpString(s, ip)) local_IP = ip;
  s = netPrefs.getString("srvr_ip", ""); if(s.length() && parseIpString(s, ip)) server_IP = ip;
  s = netPrefs.getString("subnet",  ""); if(s.length() && parseIpString(s, ip)) subnet = ip;
  s = netPrefs.getString("gateway", ""); if(s.length() && parseIpString(s, ip)) gateway = ip;
  netPrefs.end();
}

static void sendNetworkConfigToHmi(){
  String line = "CFG1|ctrl_ip=" + ipToString(local_IP) + "|srvr_ip=" + ipToString(server_IP) + "|subnet=" + ipToString(subnet) + "|gateway=" + ipToString(gateway);
  hmiSendText(line);
}

static bool saveNetworkConfigFromHmi(const String &line, String &note){
  IPAddress next_ctrl = local_IP;
  IPAddress next_srvr = server_IP;
  IPAddress next_subnet = subnet;
  IPAddress next_gateway = gateway;
  String v;
  v = hvGetPipeField(line, "ctrl_ip"); if(v.length() && !parseIpString(v, next_ctrl)){ note = "Bad CTRL IP"; return false; }
  v = hvGetPipeField(line, "srvr_ip"); if(v.length() && !parseIpString(v, next_srvr)){ note = "Bad SRVR IP"; return false; }
  v = hvGetPipeField(line, "subnet");  if(v.length() && !parseIpString(v, next_subnet)){ note = "Bad Subnet"; return false; }
  v = hvGetPipeField(line, "gateway"); if(v.length() && !parseIpString(v, next_gateway)){ note = "Bad Gateway"; return false; }
  local_IP = next_ctrl; server_IP = next_srvr; subnet = next_subnet; gateway = next_gateway;
  netPrefs.begin(NET_PREF_NS, false);
  netPrefs.putString("ctrl_ip", ipToString(local_IP));
  netPrefs.putString("srvr_ip", ipToString(server_IP));
  netPrefs.putString("subnet",  ipToString(subnet));
  netPrefs.putString("gateway", ipToString(gateway));
  netPrefs.end();
  note = "Saved; resetting CTRL";
  return true;
}


// -------------------- HMI UI layout/config server --------------------
// The EdgeBox CTRL is the Ethernet/network node and HMI UI authority.
// The Waveshare ESP32-S3-Touch-LCD-7 remains the thin display/touch terminal.
// UI/layout state is forwarded over the dedicated framed RS485 link as UIL1 packets.
static Preferences hmiPrefs;
static String g_hmiLayoutLine;
static String g_hmiLayoutUploadBuffer;
static bool g_hmiLayoutUploadOk = false;
static String g_hmiLayoutUploadError;
static uint32_t lastHmiLayoutForward = 0;
#define HMI_LAYOUT_FORWARD_MS 1500
#define HMI_LAYOUT_MAX_LEN 2200
static const char* HMI_LAYOUT_NVS_NS = "hmiui";
static const char* HMI_LAYOUT_NVS_KEY = "layout";
static const char* DEFAULT_HMI_LAYOUT_LINE = "UIL1|title=HV P2P CTRL-TS|subtitle=v26.10.06.06|layout=main5|theme=hv|aux1=AUX 1|aux2=AUX 2|aux3=AUX 3|aux4=AUX 4|aux5=AUX 5|hint=Ready";



// -------------------- HV P2P browser update / service page --------------------
// After the first USB flash, open http://172.20.1.101/ in a browser on the control LAN.
// Supported web actions:
//   1) Main App firmware OTA (.ino.bin)
//   2) Web/UI filesystem partition upload (.littlefs.bin / .spiffs.bin / fs .bin)
//   3) Saved Config / NVS reset
//
// Safety model:
//   - This updater deliberately does NOT overwrite bootloader or partition table.
//   - Filename checks provide early operator feedback only.
//   - App firmware is also content-verified for an embedded CTRL role signature before Update.end().
//   - Renaming a binary cannot make another HV P2P device role pass the app check.
static WebServer hvWebOta(80);

static const char* HV_UPDATE_NODE_NAME = "HV P2P CTRL";
static const char* HV_UPDATE_ROLE = "CTRL";
static const char* HV_UPDATE_APP_TOKEN = "HV_P2P_CTRL";
static const char* HV_UPDATE_FS_TOKEN = "HV_P2P_CTRL";
static const char* HV_UPDATE_REJECT_TOKENS = "CTRL_TS,W1P,W1P_TS";
static const char* HV_UPDATE_WARNING = "Upload only HV_P2P_CTRL_v*.ino.bin firmware. CTRL-TS and W1P files are rejected.";
static const char* HV_UPDATE_ROLE_SIGNATURE = "HV_P2P_FW_ROLE=CTRL;";
static const char* HV_UPDATE_BUILD_TOKEN = "HV_P2P_FW_ROLE=CTRL;HV_P2P_FW_TARGET=EDGEBOX_ESP100;HV_P2P_FW_VERSION=v26.10.06.06;";
static const char* HV_AUTH_ROLE = "CTRL";
static const char* HV_AUTH_TARGET = "EDGEBOX_ESP100";
static const char* HV_AUTH_VERSION = "v26.10.06.06";

static bool hvUploadAllowed = false;
static bool hvUploadIsFs = false;
static bool hvUploadFinished = false;
static bool hvUploadRoleMatched = false;
static size_t hvUploadRoleMatchLen = 0;
static String hvUploadError;

static void hvScanUploadRoleSignature(const uint8_t* data, size_t len) {
  if (hvUploadRoleMatched || !data || len == 0) return;
  const size_t tokenLen = strlen(HV_UPDATE_ROLE_SIGNATURE);
  for (size_t i = 0; i < len && !hvUploadRoleMatched; ++i) {
    const char c = (char)data[i];
    if (c == HV_UPDATE_ROLE_SIGNATURE[hvUploadRoleMatchLen]) {
      ++hvUploadRoleMatchLen;
      if (hvUploadRoleMatchLen == tokenLen) {
        hvUploadRoleMatched = true;
        hvUploadRoleMatchLen = 0;
      }
    } else {
      hvUploadRoleMatchLen = (c == HV_UPDATE_ROLE_SIGNATURE[0]) ? 1 : 0;
    }
  }
}

static String hvUpperName(String s) {
  s.replace("-", "_");
  s.toUpperCase();
  return s;
}

static bool hvNameHasToken(const String& upperName, const char* token) {
  String t(token);
  t.replace("-", "_");
  t.toUpperCase();
  return upperName.indexOf(t) >= 0;
}

static bool hvNameHasAnyRejectToken(const String& upperName) {
  String list(HV_UPDATE_REJECT_TOKENS);
  int start = 0;
  while(start < (int)list.length()) {
    int comma = list.indexOf(',', start);
    if(comma < 0) comma = list.length();
    String token = list.substring(start, comma);
    token.trim();
    if(token.length() && hvNameHasToken(upperName, token.c_str())) return true;
    start = comma + 1;
  }
  return false;
}

static bool hvAllowedUploadFilename(String filename, bool filesystem, String& reason) {
  filename.trim();
  if(filename.length() == 0) { reason = "No filename supplied."; return false; }
  String n = hvUpperName(filename);
  if(!n.endsWith(".BIN")) { reason = "Rejected: file must end with .bin"; return false; }
  if(filesystem) {
    if(!hvNameHasToken(n, HV_UPDATE_FS_TOKEN)) { reason = "Rejected: filesystem image name must include "; reason += HV_UPDATE_FS_TOKEN; return false; }
    bool looksFs = (n.indexOf("LITTLEFS") >= 0) || (n.indexOf("SPIFFS") >= 0) || (n.indexOf("FILESYSTEM") >= 0) || (n.indexOf("_FS") >= 0);
    if(!looksFs) { reason = "Rejected: filesystem image name must include LITTLEFS, SPIFFS, FILESYSTEM, or _FS."; return false; }
    return true;
  }
  if(!hvNameHasToken(n, HV_UPDATE_APP_TOKEN)) { reason = "Rejected: firmware name must include "; reason += HV_UPDATE_APP_TOKEN; return false; }
  if(hvNameHasAnyRejectToken(n)) { reason = "Rejected: filename contains another HV P2P device role."; return false; }
  if(n.indexOf(".INO.BIN") < 0 && n.indexOf("_APP.BIN") < 0 && n.indexOf("FIRMWARE.BIN") < 0) {
    reason = "Rejected: app firmware should be the exported Arduino .ino.bin or an approved *_APP.bin / *FIRMWARE.bin.";
    return false;
  }
  return true;
}

static String hvOtaIndexHtml(const char* nodeName, const char* version, const String& ip) {
  String html;
  html.reserve(8800);
  html += "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>";
  html += "<title>"; html += nodeName; html += " Update</title>";
  html += "<style>body{font-family:Arial,sans-serif;background:#07111c;color:#eaf4ff;margin:0;padding:24px}";
  html += ".wrap{max-width:880px;margin:auto}.card{background:#102033;border:1px solid #2d4b67;border-radius:16px;padding:20px;margin:14px 0;box-shadow:0 10px 24px rgba(0,0,0,.22)}";
  html += "h1{margin:0 0 6px;font-size:25px}h2{margin:0 0 8px;font-size:18px}.muted{color:#a8c1d9}.warn{color:#ffd18a}.bad{color:#ff9b9b}.ok{color:#9ff0b5}";
  html += ".drop{border:2px dashed #4d7396;border-radius:14px;padding:24px;text-align:center;background:#0a1725;cursor:pointer;transition:.15s}.drop.drag{background:#17304a;border-color:#7fc4ff}";
  html += ".drop input{display:none}button{font-size:15px;padding:10px 16px;border-radius:10px;border:0;background:#256aa3;color:white;cursor:pointer}button.danger{background:#a83b38}";
  html += ".bar{height:10px;background:#07111c;border:1px solid #2d4b67;border-radius:99px;overflow:hidden;margin-top:12px}.fill{width:0%;height:100%;background:#53b7ff}code{color:#d7ecff}";
  html += ".row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.pill{display:inline-block;border:1px solid #365c7a;border-radius:999px;padding:4px 10px;margin:3px;color:#cfe6ff;background:#0a1725}";
  html += "</style></head><body><div class='wrap'>";
  html += "<div class='card'><h1>"; html += nodeName; html += "</h1>";
  html += "<div class='muted'>Firmware: <b>"; html += version; html += "</b><br>Role: <b>"; html += HV_UPDATE_ROLE; html += "</b><br>IP: <b>"; html += ip; html += "</b></div>";
  html += "<p class='warn'>"; html += HV_UPDATE_WARNING; html += "</p>";
  html += "<span class='pill'>App token: "; html += HV_UPDATE_APP_TOKEN; html += "</span><span class='pill'>Filesystem token: "; html += HV_UPDATE_FS_TOKEN; html += "</span>";
  html += "</div>";
  html += "<div class='card'><h2>Main App Firmware</h2><p class='muted'>Drag and drop the exported Arduino <code>.ino.bin</code> here. Filename is checked first; the uploaded binary must also contain the embedded CTRL role identity before it can be activated.</p>";
  html += "<div id='appDrop' class='drop'>Drop app firmware here<br><span class='muted'>or click to select</span><input id='appFile' type='file' accept='.bin'></div>";
  html += "<div class='bar'><div id='appFill' class='fill'></div></div><p id='appMsg' class='muted'></p></div>";
  html += "<div class='card'><h2>Web/UI Filesystem Partition</h2><p class='muted'>Optional. Use only if this device build includes a LittleFS/SPIFFS web/UI partition. Filename should include <code>LITTLEFS</code>, <code>SPIFFS</code>, <code>FILESYSTEM</code>, or <code>_FS</code>.</p>";
  html += "<div id='fsDrop' class='drop'>Drop filesystem image here<br><span class='muted'>or click to select</span><input id='fsFile' type='file' accept='.bin'></div>";
  html += "<div class='bar'><div id='fsFill' class='fill'></div></div><p id='fsMsg' class='muted'></p></div>";
  html += "<div class='card'><h2>Service Actions</h2><div class='row'><button onclick='postAction(\"/reboot\",\"svcMsg\")'>Reboot Device</button>";
  html += "<button class='danger' onclick='confirmReset()'>Reset Saved Config / NVS</button></div><p id='svcMsg' class='muted'></p>";
  html += "<p class='bad'>NVS reset clears saved device settings/preferences and restarts the ESP32. It does not change bootloader or partition table.</p></div>";
  html += "<div class='card'><h2>HMI Layout / UI Config on CTRL</h2><p class='muted'>Upload a line-based layout file stored on the EdgeBox CTRL and sent to the Waveshare RS485 thin HMI. File must start with <code>UIL1|</code>.</p>";
  html += "<div id='layoutDrop' class='drop'>Drop HMI layout config here<br><span class='muted'>Accepted: HV_P2P_HMI_LAYOUT*.txt/.hmi/.json/.cfg</span><input id='layoutFile' type='file' accept='.txt,.hmi,.json,.cfg'></div>";
  html += "<div class='bar'><div id='layoutFill' class='fill'></div></div><p id='layoutMsg' class='muted'></p><div class='row'><button onclick='window.open(&quot;/hmi-layout&quot;,&quot;_blank&quot;)'>View Current Layout</button><button onclick='postAction(&quot;/hmi-layout/reset&quot;,&quot;layoutMsg&quot;)'>Reset Default Layout</button></div></div>";
  html += "<script>const role='"; html += HV_UPDATE_ROLE; html += "', appToken='"; html += HV_UPDATE_APP_TOKEN; html += "', fsToken='"; html += HV_UPDATE_FS_TOKEN; html += "';";
  html += "function norm(n){return n.toUpperCase().replaceAll('-','_')}";
  html += "function has(n,t){return norm(n).indexOf(norm(t))>=0}";
  html += "function msg(id,t,c){let e=document.getElementById(id);e.className=c||'muted';e.textContent=t}";
  html += "function validApp(f){let n=norm(f.name);if(!n.endsWith('.BIN'))return 'File must end with .bin';if(!has(n,appToken))return 'Wrong device: filename must include '+appToken;";
  html += "if(role==='CTRL'&&(has(n,'CTRL_TS')||has(n,'W1P')))return 'Wrong device: this CTRL page will not accept CTRL-TS or W1P firmware';";
  html += "if(role==='W1P'&&(has(n,'CTRL')||has(n,'CTRL_TS')))return 'Wrong device: this W1P page will not accept CTRL or CTRL-TS firmware';";
  html += "if(role==='CTRL_TS'&&has(n,'W1P'))return 'Wrong device: this CTRL-TS page will not accept W1P firmware';";
  html += "if(n.indexOf('.INO.BIN')<0&&n.indexOf('_APP.BIN')<0&&n.indexOf('FIRMWARE.BIN')<0)return 'Use exported Arduino .ino.bin or approved app firmware .bin';return ''}";
  html += "function validFs(f){let n=norm(f.name);if(!n.endsWith('.BIN'))return 'File must end with .bin';if(!has(n,fsToken))return 'Wrong device: filename must include '+fsToken;";
  html += "if(!(has(n,'LITTLEFS')||has(n,'SPIFFS')||has(n,'FILESYSTEM')||has(n,'_FS')))return 'Filesystem image name must include LITTLEFS, SPIFFS, FILESYSTEM, or _FS';return ''}";
  html += "function wire(dropId,fileId,url,fillId,msgId,validator){let d=document.getElementById(dropId),i=document.getElementById(fileId);d.onclick=()=>i.click();['dragenter','dragover'].forEach(ev=>d.addEventListener(ev,e=>{e.preventDefault();d.classList.add('drag')}));['dragleave','drop'].forEach(ev=>d.addEventListener(ev,e=>{e.preventDefault();d.classList.remove('drag')}));d.addEventListener('drop',e=>{let f=e.dataTransfer.files[0];if(f)upload(f,url,fillId,msgId,validator)});i.onchange=()=>{let f=i.files[0];if(f)upload(f,url,fillId,msgId,validator)}}";
  html += "function upload(f,url,fillId,msgId,validator){let bad=validator(f);if(bad){msg(msgId,bad,'bad');return}let fd=new FormData();fd.append('file',f,f.name);let x=new XMLHttpRequest();x.upload.onprogress=e=>{if(e.lengthComputable)document.getElementById(fillId).style.width=Math.round(e.loaded*100/e.total)+'%'};x.onload=()=>{let ok=x.status>=200&&x.status<300;msg(msgId,x.responseText,ok?'ok':'bad')};x.onerror=()=>msg(msgId,'Upload failed','bad');msg(msgId,'Uploading '+f.name+' ...','muted');x.open('POST',url);x.send(fd)}";
  html += "async function postAction(url,msgId){let r=await fetch(url,{method:'POST'});let t=await r.text();msg(msgId,t,r.ok?'ok':'bad')}";
  html += "function confirmReset(){if(confirm('Reset saved config/NVS on this ESP32 and reboot?'))postAction('/reset-nvs','svcMsg')}";
  html += "function validLayout(f){let n=norm(f.name);if(!(n.endsWith('.TXT')||n.endsWith('.HMI')||n.endsWith('.JSON')||n.endsWith('.CFG')))return 'Layout file must be .txt, .hmi, .json, or .cfg';if(!(has(n,'HV_P2P_HMI_LAYOUT')||has(n,'CTRL_HMI_LAYOUT')||has(n,'WS_HMI_LAYOUT')))return 'Layout filename should include HV_P2P_HMI_LAYOUT, CTRL_HMI_LAYOUT, or WS_HMI_LAYOUT';return ''}";
  html += "wire('appDrop','appFile','/update/app','appFill','appMsg',validApp);wire('fsDrop','fsFile','/update/fs','fsFill','fsMsg',validFs);wire('layoutDrop','layoutFile','/hmi-layout/upload','layoutFill','layoutMsg',validLayout);</script>";
  html += "</div></body></html>";
  return html;
}

static void hvHandleUpload(bool filesystem) {
  HTTPUpload& upload = hvWebOta.upload();
  if(upload.status == UPLOAD_FILE_START) {
    hvUploadIsFs = filesystem;
    hvUploadAllowed = false;
    hvUploadFinished = false;
    hvUploadRoleMatched = filesystem;
    hvUploadRoleMatchLen = 0;
    hvUploadError = "";
    Serial.printf("[OTA] %s upload start: %s\n", filesystem ? "FS" : "APP", upload.filename.c_str());
    if(!hvAllowedUploadFilename(upload.filename, filesystem, hvUploadError)) {
      Serial.printf("[OTA] Rejected: %s\n", hvUploadError.c_str());
      return;
    }
    int command = filesystem ? U_SPIFFS : U_FLASH;
    if(!Update.begin(UPDATE_SIZE_UNKNOWN, command)) {
      hvUploadError = "Update.begin failed. Check partition scheme and free OTA space.";
      Update.printError(Serial);
      return;
    }
    hvUploadAllowed = true;
  } else if(upload.status == UPLOAD_FILE_WRITE) {
    if(!hvUploadAllowed) return;
    if(!filesystem) hvScanUploadRoleSignature(upload.buf, upload.currentSize);
    if(Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
      hvUploadError = "Update.write failed.";
      Update.printError(Serial);
    }
  } else if(upload.status == UPLOAD_FILE_END) {
    if(!hvUploadAllowed) return;
    if(!filesystem && !hvUploadRoleMatched) {
      hvUploadError = String("Rejected: firmware contents do not contain expected role signature ") + HV_UPDATE_ROLE_SIGNATURE;
      Update.abort();
      hvUploadAllowed = false;
      Serial.printf("[OTA] Rejected by content identity: %s\n", hvUploadError.c_str());
      return;
    }
    if(Update.end(true)) {
      hvUploadFinished = true;
      Serial.printf("[OTA] %s update success: %u bytes%s\n", filesystem ? "FS" : "APP", upload.totalSize, filesystem ? "" : " (CTRL role verified)");
    } else {
      hvUploadError = "Update.end failed.";
      Update.printError(Serial);
    }
  } else if(upload.status == UPLOAD_FILE_ABORTED) {
    hvUploadError = "Upload aborted.";
    Update.abort();
    Serial.println("[OTA] Aborted");
  }
}

static void hvUpdatePostReply(bool filesystem) {
  hvWebOta.sendHeader("Connection", "close");
  if(hvUploadAllowed && hvUploadFinished && hvUploadError.length() == 0 && !Update.hasError()) {
    String msg = filesystem ? "FILESYSTEM UPDATE OK - rebooting" : "APP FIRMWARE UPDATE OK - rebooting";
    hvWebOta.send(200, "text/plain", msg);
    delay(350);
    ESP.restart();
  } else {
    String msg = hvUploadError.length() ? hvUploadError : "Update failed or rejected.";
    hvWebOta.send(400, "text/plain", msg);
  }
}

static void hvHandleLayoutUpload();
static void hvLayoutUploadReply();
static void hvResetHmiLayoutConfig();
static void sendHmiLayout();

static void hvBeginWebUpdater() {
  hvWebOta.on("/", HTTP_GET, [](){
    hvWebOta.send(200, "text/html", hvOtaIndexHtml(HV_UPDATE_NODE_NAME, CTRL_VERSION, ETH.localIP().toString()));
  });
  hvWebOta.on("/update", HTTP_GET, [](){
    hvWebOta.send(200, "text/html", hvOtaIndexHtml(HV_UPDATE_NODE_NAME, CTRL_VERSION, ETH.localIP().toString()));
  });
  hvWebOta.on("/update/app", HTTP_POST, [](){ hvUpdatePostReply(false); }, [](){ hvHandleUpload(false); });
  hvWebOta.on("/update/fs", HTTP_POST, [](){ hvUpdatePostReply(true); }, [](){ hvHandleUpload(true); });
  hvWebOta.on("/reboot", HTTP_POST, [](){
    hvWebOta.send(200, "text/plain", "Rebooting device...");
    delay(250);
    ESP.restart();
  });
  hvWebOta.on("/reset-nvs", HTTP_POST, [](){
    hvWebOta.send(200, "text/plain", "Saved config/NVS erased - rebooting...");
    delay(250);
    nvs_flash_erase();
    nvs_flash_init();
    ESP.restart();
  });
  hvWebOta.on("/hmi-layout", HTTP_GET, [](){
    hvWebOta.send(200, "text/plain", g_hmiLayoutLine.length() ? g_hmiLayoutLine : String(DEFAULT_HMI_LAYOUT_LINE));
  });
  hvWebOta.on("/hmi-layout/upload", HTTP_POST, [](){ hvLayoutUploadReply(); }, [](){ hvHandleLayoutUpload(); });
  hvWebOta.on("/hmi-layout/reset", HTTP_POST, [](){
    hvResetHmiLayoutConfig();
    sendHmiLayout();
    hvWebOta.send(200, "text/plain", "Default HMI layout restored and forwarded to Waveshare terminal.");
  });
  hvWebOta.onNotFound([](){
    hvWebOta.send(404, "text/plain", "Not found");
  });
  hvWebOta.begin();
  Serial.printf("[OTA] Browser service page ready: http://%s/ role=%s\n", ETH.localIP().toString().c_str(), HV_UPDATE_ROLE);
}

static void hvHandleWebUpdater() {
  hvWebOta.handleClient();
}


static bool hvValidateHmiLayoutLine(String line, String& reason) {
  line.trim();
  if(line.length() == 0) { reason = "Layout file is empty."; return false; }
  line.replace("\r", "");
  int nl = line.indexOf('\n');
  if(nl >= 0) line = line.substring(0, nl);
  line.trim();
  if(line.length() > HMI_LAYOUT_MAX_LEN) { reason = "Layout line is too long."; return false; }
  if(!line.startsWith("UIL1|")) { reason = "Layout must start with UIL1|"; return false; }
  if(line.indexOf("|title=") < 0) { reason = "Layout must include |title=."; return false; }
  reason = "";
  return true;
}

static void hvLoadHmiLayoutConfig() {
  String reason;
  hmiPrefs.begin(HMI_LAYOUT_NVS_NS, true);
  String stored = hmiPrefs.getString(HMI_LAYOUT_NVS_KEY, "");
  hmiPrefs.end();
  if(hvValidateHmiLayoutLine(stored, reason)) {
    stored.replace("\r", "");
    int nl = stored.indexOf('\n');
    if(nl >= 0) stored = stored.substring(0, nl);
    stored.trim();
    // v26.10.06.06 migration: older CTRL NVS layouts were main4/aux1-aux4.
    // Preserve the operator's stored labels/settings but expose the new AUX5 tile.
    if(stored.indexOf("|layout=main4") >= 0) stored.replace("|layout=main4", "|layout=main5");
    if(stored.indexOf("|aux5=") < 0) stored += "|aux5=AUX 5";
    g_hmiLayoutLine = stored;
    Serial.println("[HMI UI] Loaded/migrated layout from CTRL NVS");
  } else {
    g_hmiLayoutLine = DEFAULT_HMI_LAYOUT_LINE;
    Serial.println("[HMI UI] Using default layout");
  }
}

static bool hvSaveHmiLayoutConfig(String line, String& reason) {
  line.replace("\r", "");
  int nl = line.indexOf('\n');
  if(nl >= 0) line = line.substring(0, nl);
  line.trim();
  if(!hvValidateHmiLayoutLine(line, reason)) return false;
  hmiPrefs.begin(HMI_LAYOUT_NVS_NS, false);
  bool ok = hmiPrefs.putString(HMI_LAYOUT_NVS_KEY, line) > 0;
  hmiPrefs.end();
  if(!ok) { reason = "Failed to save layout to NVS."; return false; }
  g_hmiLayoutLine = line;
  reason = "";
  return true;
}

static void hvResetHmiLayoutConfig() {
  hmiPrefs.begin(HMI_LAYOUT_NVS_NS, false);
  hmiPrefs.remove(HMI_LAYOUT_NVS_KEY);
  hmiPrefs.end();
  g_hmiLayoutLine = DEFAULT_HMI_LAYOUT_LINE;
}

static void sendHmiLayout() {
  if(!g_hmiLayoutLine.length()) g_hmiLayoutLine = DEFAULT_HMI_LAYOUT_LINE;
  hmiSendText(g_hmiLayoutLine);
}

static bool hvAllowedLayoutFilename(String filename, String& reason) {
  filename.trim();
  if(filename.length() == 0) { reason = "No filename supplied."; return false; }
  String n = hvUpperName(filename);
  bool ext_ok = n.endsWith(".TXT") || n.endsWith(".HMI") || n.endsWith(".JSON") || n.endsWith(".CFG");
  if(!ext_ok) { reason = "Layout file must be .txt, .hmi, .json, or .cfg."; return false; }
  if(n.indexOf("HV_P2P_HMI_LAYOUT") < 0 && n.indexOf("CTRL_HMI_LAYOUT") < 0 && n.indexOf("WS_HMI_LAYOUT") < 0) {
    reason = "Layout filename should include HV_P2P_HMI_LAYOUT, CTRL_HMI_LAYOUT, or WS_HMI_LAYOUT.";
    return false;
  }
  return true;
}

static void hvHandleLayoutUpload() {
  HTTPUpload& upload = hvWebOta.upload();
  if(upload.status == UPLOAD_FILE_START) {
    g_hmiLayoutUploadBuffer = "";
    g_hmiLayoutUploadError = "";
    g_hmiLayoutUploadOk = false;
    Serial.printf("[HMI UI] layout upload start: %s\n", upload.filename.c_str());
    if(!hvAllowedLayoutFilename(upload.filename, g_hmiLayoutUploadError)) {
      Serial.printf("[HMI UI] layout rejected: %s\n", g_hmiLayoutUploadError.c_str());
      return;
    }
  } else if(upload.status == UPLOAD_FILE_WRITE) {
    if(g_hmiLayoutUploadError.length()) return;
    if((g_hmiLayoutUploadBuffer.length() + upload.currentSize) > HMI_LAYOUT_MAX_LEN) {
      g_hmiLayoutUploadError = "Layout file too large.";
      return;
    }
    for(size_t i=0; i<upload.currentSize; ++i) g_hmiLayoutUploadBuffer += (char)upload.buf[i];
  } else if(upload.status == UPLOAD_FILE_END) {
    if(g_hmiLayoutUploadError.length()) return;
    String reason;
    if(hvSaveHmiLayoutConfig(g_hmiLayoutUploadBuffer, reason)) {
      g_hmiLayoutUploadOk = true;
      Serial.println("[HMI UI] layout saved and will be forwarded to Waveshare");
      sendHmiLayout();
    } else {
      g_hmiLayoutUploadError = reason;
      Serial.printf("[HMI UI] layout save failed: %s\n", reason.c_str());
    }
  } else if(upload.status == UPLOAD_FILE_ABORTED) {
    g_hmiLayoutUploadError = "Layout upload aborted.";
  }
}

static void hvLayoutUploadReply() {
  hvWebOta.sendHeader("Connection", "close");
  if(g_hmiLayoutUploadOk && !g_hmiLayoutUploadError.length()) {
    hvWebOta.send(200, "text/plain", "HMI LAYOUT UPDATE OK - forwarded to Waveshare terminal");
  } else {
    hvWebOta.send(400, "text/plain", g_hmiLayoutUploadError.length() ? g_hmiLayoutUploadError : "Layout update failed or rejected.");
  }
}

static uint32_t lastHeartbeat = 0;
static uint32_t lastControl   = 0;
static uint32_t lastDisplayForward = 0;
static bool srvrOnline = false;

// EdgeBox joystick transport. SRVR remains the calibration authority.
// The 0-10 V EdgeBox option uses an approximately 2:1 input divider before the
// SGM58031 (10 k series / 10 k to ADC_GND in the Seeed schematic). Therefore a
// nominal 0-5 V joystick appears as about 0-2.5 V at the ADC. With
// GAIN_TWOTHIRDS (±6.144 V ADC range), the nominal 5 V field endpoint is about
// 13333 counts. This scaling only makes the UDP transport convenient; the real
// Left/Centre/Right values are still captured and corrected by SRVR.
static const uint8_t JOY_SAMPLES = 5;  // low-latency trimmed mean: discard one high + one low sample
static const float EDGEBOX_JOY_5V_COUNTS = 13333.3f;
static float g_joy_filtered = 0.0f;
static bool g_joy_ready = false;
static int16_t g_joyLastRaw = 0;
static float g_joyLastFieldV = 0.0f;
static bool g_ctrlEstopActive = true;
static float g_ctrlEstopFieldV = 0.0f;
static uint8_t g_ctrlEstopHealthySamples = 0;
static uint32_t g_lastAdsDiagMs = 0;
static const uint32_t ADS_DIAG_INTERVAL_MS = 5000;
static const uint32_t ADS_HEALTH_CHECK_INTERVAL_MS = 250;
static const uint32_t ADS_RECOVERY_RETRY_MS = 1000;
static uint32_t g_lastAdsHealthCheckMs = 0;
static uint32_t g_lastAdsRecoveryAttemptMs = 0;

static uint32_t g_virtualAuxUntil[5] = {0,0,0,0,0};
static uint32_t g_virtualCalCancelUntil = 0;
static String g_latestDisplayPacket;
static String g_latestHmiStatePacket;
static bool g_hmiStatePacketPending = false;
static String g_latestHmiGeometryPacket;
static bool g_hmiGeometryPacketPending = false;
static String g_latestHmiMotionPacket;
static bool g_hmiMotionPacketPending = false;
static uint32_t g_lastHmiStateTxMs = 0;
static uint32_t g_lastHmiGeometryTxMs = 0;
static uint32_t g_lastHmiMotionTxMs = 0;
static uint32_t g_ctrlBootMs = 0;
static uint32_t g_lastSrvrDisplayMs = 0;
static uint32_t g_lastSrvrRxMs = 0;
static bool g_srvrExplicitOffline = false;
static uint32_t g_lastUnexpectedSrvrLogMs = 0;
static uint32_t g_lastHmiRxMs = 0;
static uint32_t g_lastHmiStatusReportMs = 0;
static String g_lastForwardedDisplayPacket;
static uint32_t g_lastHmiDisplayKeepaliveMs = 0;
static uint32_t g_hmiBulkSuppressUntilMs = 0;
static uint32_t g_hmiTsHeapFree = 0;
static uint32_t g_hmiTsHeapMin = 0;
static uint32_t g_hmiTsPsramFree = 0;
static const uint32_t HMI_LINK_TIMEOUT_MS = 3000;

// SRVR is the release authority. CTRL remains fail-closed until the running
// application is proven to be the exact immutable image bundled with SRVR.
static bool g_srvrFirmwareMatched = false;
static String g_srvrFirmwareState = "unverified";
static String g_srvrRequiredVersion;
static String g_srvrRequiredSha;
static uint32_t g_fwAuthorityLastAttemptMs = 0;
static uint32_t g_fwAuthorityRetryDelayMs = 1500;
static uint32_t g_fwAuthorityFastRetryUntilMs = 0;
static bool g_ctrlAuthorityUpdatePending = false;
static String g_srvrFirmwareSession;
// SRVR coordinates the multi-node update order.  Keep the CTRL-TS final-stage
// grant independent of DSP1/HMI presentation traffic so a display-packet race
// cannot strand an older touchscreen at "Waiting for CTRL".
static bool g_hmiTsCoordinatorSeen = false;
static bool g_hmiTsUpdateAllowed = false;
// Once an authorised CTRL-TS has accepted the first FW_BEGIN and requested its
// safe display-off reboot, keep that exact update authorised across the reboot.
// The headless second stage must not be stranded because W1P/coordinator state
// changes while the screen is black. A new SRVR session invalidates this latch.
static bool g_hmiSafeUpdateContinuation = false;
static uint32_t g_hmiIdentitySeenMs = 0;
// Independent final-stage recovery. Normal operation still honours SRVR's
// CTRL -> W1P -> CTRL-TS grant, but an approved safe-OTA touchscreen must not
// remain stranded forever if that later-stage grant packet is lost/stuck.
static uint32_t g_hmiMismatchSinceMs = 0;
static const uint32_t HMI_COORDINATOR_FALLBACK_MS = 12000;


static bool i2cProbe(uint8_t addr) {
  Wire.beginTransmission(addr);
  return (Wire.endTransmission() == 0);
}

static void scanI2CBus() {
  Serial.printf("[I2C] EdgeBox SDA=%d SCL=%d clock=100k\n", SDA_PIN, SCL_PIN);
  for(uint8_t a = 1; a < 127; ++a) {
    if(i2cProbe(a)) { Serial.printf("[I2C] found 0x%02X\n", a); }
    yield();
  }
}

// EdgeBox SGM58031 direct driver.  The SGM58031 shares the ADS1x15-style
// conversion/config register layout, but its data-rate codes are different.
// Using the actual device register map avoids depending on ADS1115 timing
// assumptions. AI1 is run continuously at 800 SPS, +/-6.144 V full scale for the joystick.
static const uint8_t SGM_REG_CONVERSION = 0x00;
static const uint8_t SGM_REG_CONFIG     = 0x01;
static const uint8_t SGM_REG_CONFIG1    = 0x04;
static const uint8_t SGM_REG_CHIP_ID    = 0x05;
static const uint16_t SGM_CONFIG_AI0_CONT_800SPS_6V144 = 0x40E3;
static const uint16_t SGM_CONFIG_AI1_CONT_800SPS_6V144 = 0x50E3;
static const uint16_t SGM_CONFIG1_DEFAULT = 0x0000; // DR_SEL=0 -> DR=111 is 800 SPS.
static float rawJoystickTransportAxis(int16_t raw);

static bool sgmWriteRegister(uint8_t reg, uint16_t value) {
  Wire.beginTransmission(ADS_ADDR);
  Wire.write(reg);
  Wire.write(uint8_t(value >> 8));
  Wire.write(uint8_t(value & 0xFF));
  return Wire.endTransmission() == 0;
}

static bool sgmReadRegister(uint8_t reg, uint16_t &value) {
  Wire.beginTransmission(ADS_ADDR);
  Wire.write(reg);
  if(Wire.endTransmission(false) != 0) return false;
  if(Wire.requestFrom(int(ADS_ADDR), 2) != 2) return false;
  value = (uint16_t(Wire.read()) << 8) | uint16_t(Wire.read());
  return true;
}

static bool sgmReadConversion(int16_t &raw) {
  uint16_t u = 0;
  if(!sgmReadRegister(SGM_REG_CONVERSION, u)) return false;
  raw = int16_t(u);
  return true;
}

static bool sgmSelectChannelVerified(uint16_t expectedConfig, const char *label) {
  if(!sgmWriteRegister(SGM_REG_CONFIG, expectedConfig)) {
    Serial.printf("[AI] Failed selecting %s channel\n", label ? label : "ADC");
    return false;
  }
  uint16_t actual = 0;
  if(!sgmReadRegister(SGM_REG_CONFIG, actual) ||
     ((actual & 0x7FFFu) != (expectedConfig & 0x7FFFu))) {
    Serial.printf("[AI] %s mux verify failed cfg=0x%04X expected=0x%04X\n",
                  label ? label : "ADC", unsigned(actual), unsigned(expectedConfig));
    return false;
  }
  // After any mux change, discard the old conversion and wait >2 fresh 800-SPS periods.
  delayMicroseconds(3000);
  int16_t discard = 0;
  if(!sgmReadConversion(discard)) return false;
  delayMicroseconds(1400);
  return true;
}

static bool sgmEnsureChannelVerified(uint16_t expectedConfig, const char *label) {
  // If the converter is already on the required continuous channel, a config
  // readback proves channel identity without paying another mux-settle delay.
  // Any mismatch falls back to the full write/readback/fresh-conversion path.
  uint16_t actual = 0;
  if(sgmReadRegister(SGM_REG_CONFIG, actual) &&
     ((actual & 0x7FFFu) == (expectedConfig & 0x7FFFu))) return true;
  return sgmSelectChannelVerified(expectedConfig, label);
}

static void failAnalogueUnsafe(const char *reason) {
  g_ads_inited = false;
  g_joy_ready = false;
  g_joy_filtered = 0.0f;
  g_ctrlEstopActive = true;
  g_ctrlEstopHealthySamples = 0;
  if(reason) Serial.println(reason);
}

static bool detectSgm58031() {
  ADS_ADDR = 0x48;
  if(!i2cProbe(ADS_ADDR)) {
    g_ads_inited = false;
    g_joy_ready = false;
    Serial.println("[AI] EdgeBox SGM58031 not detected @0x48 - joystick forced neutral");
    return false;
  }

  // Explicitly select the SGM58031's standard data-rate table and configure
  // AI1 single-ended, +/-6.144 V PGA, continuous conversion, 800 SPS for the joystick.
  if(!sgmWriteRegister(SGM_REG_CONFIG1, SGM_CONFIG1_DEFAULT) ||
     !sgmWriteRegister(SGM_REG_CONFIG, SGM_CONFIG_AI1_CONT_800SPS_6V144)) {
    g_ads_inited = false;
    g_joy_ready = false;
    Serial.println("[AI] SGM58031 configuration write failed - joystick forced neutral");
    return false;
  }

  delay(5); // > 3 conversion periods at 800 SPS before accepting first sample.
  uint16_t cfg = 0, chip = 0;
  int16_t first = 0;
  const bool cfgOk = sgmReadRegister(SGM_REG_CONFIG, cfg);
  const bool idOk = sgmReadRegister(SGM_REG_CHIP_ID, chip);
  const bool sampleOk = sgmReadConversion(first);
  if(!cfgOk || !sampleOk || ((cfg & 0x7FFFu) != (SGM_CONFIG_AI1_CONT_800SPS_6V144 & 0x7FFFu))) {
    g_ads_inited = false;
    g_joy_ready = false;
    Serial.printf("[AI] SGM58031 verify failed cfg_ok=%d cfg=0x%04X sample_ok=%d\n",
                  cfgOk ? 1 : 0, unsigned(cfg), sampleOk ? 1 : 0);
    return false;
  }

  g_ads_inited = true;
  g_joy_ready = true;
  g_joyLastRaw = first;
  g_joyLastFieldV = float(first) * (6.144f / 32768.0f) * 2.0f;
  g_joy_filtered = rawJoystickTransportAxis(first);
  Serial.printf("[AI] EdgeBox SGM58031 OK @0x48 AI1 joystick continuous 800SPS FS=+/-6.144V chip=0x%04X%s\n",
                unsigned(chip), idOk ? "" : " (ID read unavailable)");
  return true;
}

static void refreshAdsHealth() {
  const uint32_t now = millis();
  if((now - g_lastAdsHealthCheckMs) < ADS_HEALTH_CHECK_INTERVAL_MS) return;
  g_lastAdsHealthCheckMs = now;
  if(g_ads_inited) {
    uint16_t cfg = 0;
    if(!i2cProbe(ADS_ADDR) || !sgmReadRegister(SGM_REG_CONFIG, cfg)) {
      failAnalogueUnsafe("[AI] SGM58031 LOST/config read failed - joystick neutral + analogue/E-stop fault");
      return;
    }
    const uint16_t mux = cfg & 0x7000u;
    const uint16_t ai0Mux = SGM_CONFIG_AI0_CONT_800SPS_6V144 & 0x7000u;
    const uint16_t ai1Mux = SGM_CONFIG_AI1_CONT_800SPS_6V144 & 0x7000u;
    if(mux != ai0Mux && mux != ai1Mux) {
      failAnalogueUnsafe("[AI] SGM58031 mux entered an unexpected channel - fail unsafe");
    }
    return;
  }
  if((now - g_lastAdsRecoveryAttemptMs) < ADS_RECOVERY_RETRY_MS) return;
  g_lastAdsRecoveryAttemptMs = now;
  if(detectSgm58031()) Serial.println("[AI] SGM58031 RECOVERED");
}

static float rawJoystickTransportAxis(int16_t raw) {
  // SRVR calibration authoritative: Set Left / Set Centre / Set Right captures remain authoritative.
  // Installed APEM wiring is electrically high at physical Left and low at Right.
  // Normalise at the hardware boundary so every downstream consumer uses the same
  // physical convention: Left=-1, Centre=0, Right=+1.
  float axis = 1.0f - (2.0f * (float(raw) / EDGEBOX_JOY_5V_COUNTS));
  return constrain(axis, -1.0f, 1.0f);
}

static float readJoystickAxis() {
  if(!g_ads_inited || !g_joy_ready) return 0.0f;

  // Never trust the converter's previous mux state. Select and verify AI1 for
  // every joystick transaction, then accept only conversions produced after the
  // verified switch. This makes AI0 E-stop samples unable to leak into joystick.
  if(!sgmEnsureChannelVerified(SGM_CONFIG_AI1_CONT_800SPS_6V144, "AI1 joystick")) {
    failAnalogueUnsafe("[AI] AI1 joystick select/verify failed - fail unsafe");
    return 0.0f;
  }

  int32_t sum = 0;
  int16_t minRaw = 32767;
  int16_t maxRaw = -32768;
  for(uint8_t i=0; i<JOY_SAMPLES; ++i) {
    int16_t raw = 0;
    if(!sgmReadConversion(raw)) {
      failAnalogueUnsafe("[AI] AI1 joystick sample read failed - joystick neutral + analogue/E-stop fault");
      return 0.0f;
    }
    sum += raw;
    if(raw < minRaw) minRaw = raw;
    if(raw > maxRaw) maxRaw = raw;
    if(i + 1 < JOY_SAMPLES) delayMicroseconds(1400);
  }
  const int32_t trimmedSum = sum - int32_t(minRaw) - int32_t(maxRaw);
  const int16_t raw = int16_t(trimmedSum / int32_t(JOY_SAMPLES - 2));
  g_joyLastRaw = raw;
  g_joyLastFieldV = float(raw) * (6.144f / 32768.0f) * 2.0f;
  const float axis = rawJoystickTransportAxis(raw);
  // The trimmed-mean window already rejects spikes. Keep only a light
  // one-pole filter so a full-scale operator step reaches >96% within two 25 ms
  // control cycles instead of taking ~0.5-1 s to settle as in .03.
  g_joy_filtered = (0.20f * g_joy_filtered) + (0.80f * axis);
  return constrain(g_joy_filtered, -1.0f, 1.0f);
}

static void sampleCtrlEstopAI0() {
  if(!g_ads_inited) {
    g_ctrlEstopActive = true;
    g_ctrlEstopHealthySamples = 0;
    return;
  }

  bool sampleOk = sgmSelectChannelVerified(SGM_CONFIG_AI0_CONT_800SPS_6V144, "AI0 E-stop");
  int32_t sum = 0;
  if(sampleOk) {
    for(uint8_t i=0; i<2; ++i) {
      int16_t raw = 0;
      if(!sgmReadConversion(raw)) { sampleOk = false; break; }
      sum += raw;
      if(i == 0) delayMicroseconds(1400);
    }
  }

  if(sampleOk) {
    const int16_t raw = int16_t(sum / 2);
    const float adcV = float(raw) * (6.144f / 32768.0f);
    g_ctrlEstopFieldV = adcV * 2.0f;
    const bool healthyVoltage = (g_ctrlEstopFieldV >= CTRL_ESTOP_HEALTHY_MIN_V &&
                                 g_ctrlEstopFieldV <= CTRL_ESTOP_HEALTHY_MAX_V);
    if(healthyVoltage) {
      if(g_ctrlEstopHealthySamples < CTRL_ESTOP_HEALTHY_CONFIRM_SAMPLES) ++g_ctrlEstopHealthySamples;
      if(g_ctrlEstopHealthySamples >= CTRL_ESTOP_HEALTHY_CONFIRM_SAMPLES) g_ctrlEstopActive = false;
    } else {
      // E-stop assertion is immediate. Only clearing requires consecutive healthy samples.
      g_ctrlEstopHealthySamples = 0;
      g_ctrlEstopActive = true;
    }
  } else {
    g_ctrlEstopActive = true;
    g_ctrlEstopHealthySamples = 0;
    Serial.println("[AI] AI0 E-stop select/sample failed - fail unsafe");
  }

  // Always restore and verify AI1, even when the AI0 transaction failed. This
  // removes the .06 early-return path that could strand the converter on AI0.
  const bool restored = sgmSelectChannelVerified(SGM_CONFIG_AI1_CONT_800SPS_6V144, "AI1 joystick restore");
  if(!sampleOk || !restored) {
    failAnalogueUnsafe(!restored ? "[AI] Failed restoring/verifying AI1 joystick channel - fail unsafe" : nullptr);
  }
}

static void printAdsDiagnostics() {
  if(!g_ads_inited) return;
  const uint32_t now = millis();
  if(now - g_lastAdsDiagMs < ADS_DIAG_INTERVAL_MS) return;
  g_lastAdsDiagMs = now;
  Serial.printf("[AI] SGM58031 AI1_JOY=%d field~=%.3fV transport_axis=%.4f ESTOP_AI0=%.3fV %s (cached channel-bound samples)\n",
                int(g_joyLastRaw), g_joyLastFieldV, rawJoystickTransportAxis(g_joyLastRaw),
                g_ctrlEstopFieldV, g_ctrlEstopActive ? "ACTIVE/FAULT" : "HEALTHY");
}

static void handleSerialJoystickCommands() {
  while(Serial.available()) {
    char c = char(Serial.read());
    if(c=='j' || c=='J') {
      const bool ok = g_ads_inited && g_joy_ready;
      Serial.printf("[JOY] ok=%d AI1=%d field~=%.3fV axis=%.4f; cached channel-bound sample; use SRVR Set Left/Centre/Right wizard\n",
                    ok ? 1 : 0, int(g_joyLastRaw), g_joyLastFieldV, ok ? rawJoystickTransportAxis(g_joyLastRaw) : 0.0f);
    }
  }
}

static void sendHeartbeat()
{
  uint8_t pkt[1] = { 0xA5 };
  udp.beginPacket(server_IP, UDP_PORT);
  udp.write(pkt, 1);
  udp.endPacket();
}

static bool hmiLinkConnected()
{
  uint32_t now = millis();
  return g_hmiCompatible && (g_lastHmiRxMs > 0) && ((now - g_lastHmiRxMs) <= HMI_LINK_TIMEOUT_MS);
}

static const char* hmiFwStateText()
{
  if(g_hmiSafeRebootHoldUntilMs && millis() < g_hmiSafeRebootHoldUntilMs) return "safe_reboot";
  switch(g_hmiFwState) {
    case HMI_FW_WAIT_READY:      return "starting";
    case HMI_FW_WAIT_BLOCK_ACK:  return "transferring";
    case HMI_FW_WAIT_RESULT:     return "verifying";
    case HMI_FW_WAIT_REBOOT_ACK: return "rebooting";
    case HMI_FW_WAIT_REBOOT_CONFIRM: return "confirming reboot";
    default:
      if(!g_hmiCompatible && g_hmiReportedVersion.length() && !HV_CTRL_TS_IMAGE_AVAILABLE) return "image_missing";
      if(!g_hmiCompatible && g_hmiReportedVersion.length() &&
         g_hmiReportedHw == HV_CTRL_TS_REQUIRED_HW && g_hmiReportedProto == HV_CTRL_TS_REQUIRED_PROTOCOL &&
         !g_hmiSafeOtaCapable) return "manual_bootstrap";
      return "idle";
  }
}

static int hmiFwProgressPct()
{
  if(g_hmiSafeRebootHoldUntilMs && millis() < g_hmiSafeRebootHoldUntilMs) return 0;
  if(g_hmiFwState == HMI_FW_WAIT_RESULT) return 99;
  if(g_hmiFwState == HMI_FW_WAIT_REBOOT_ACK || g_hmiFwState == HMI_FW_WAIT_REBOOT_CONFIRM) return 100;
  if(g_hmiFwState == HMI_FW_WAIT_READY) return 0;
  if(g_hmiFwState == HMI_FW_WAIT_BLOCK_ACK && HV_CTRL_TS_IMAGE_SIZE > 0){
    const unsigned long long done = (unsigned long long)g_hmiFwOffset;
    int pct = int((100ULL * done) / (unsigned long long)HV_CTRL_TS_IMAGE_SIZE);
    if(pct < 0) pct = 0;
    if(pct > 99) pct = 99;
    return pct;
  }
  return 0;
}

static void sendHmiStatusToSrvr()
{
  uint32_t now = millis();
  uint32_t age = g_lastHmiRxMs ? (now - g_lastHmiRxMs) : 999999;
  String line = "HMI_STATUS";
  line += "|ctrl_ts=" + String(hmiLinkConnected() ? 1 : 0);
  line += "|ctrl_version=v26.10.06.06";
  line += "|fw_match=" + String(g_srvrFirmwareMatched ? 1 : 0);
  line += "|fw_authority=" + g_srvrFirmwareState;
  line += "|fw_required=" + (g_srvrRequiredVersion.length() ? g_srvrRequiredVersion : String("unknown"));
  line += "|ads=" + String(g_ads_inited ? 1 : 0);
  line += "|age_ms=" + String((unsigned long)age);
  // Report the identity actually returned by the Waveshare rather than the CTRL
  // application version. This lets SRVR Setup diagnose a mismatch/update.
  line += "|version=" + (g_hmiReportedVersion.length() ? g_hmiReportedVersion : String("unknown"));
  line += "|required=" + String(HV_CTRL_TS_REQUIRED_VERSION);
  line += "|compatible=" + String(g_hmiCompatible ? 1 : 0);
  line += "|safe_ota=" + String((unsigned)g_hmiSafeOtaLevel);
  line += "|boot_id=" + (g_hmiReportedBootId.length() ? g_hmiReportedBootId : String("unknown"));
  line += "|reset_reason=" + String(g_hmiReportedResetReason);
  line += "|image=" + String(HV_CTRL_TS_IMAGE_AVAILABLE ? 1 : 0);
  line += "|fw_state=" + String(hmiFwStateText());
  line += "|fw_pct=" + String(hmiFwProgressPct());
  line += "|ts_grant=" + String(g_hmiTsCoordinatorSeen ? (g_hmiTsUpdateAllowed ? 1 : 0) : -1);
  line += "|polls=" + String((unsigned long)g_hmiPollsSent);
  line += "|poll_timeouts=" + String((unsigned long)g_hmiPollTimeouts);
  line += "|events_ok=" + String((unsigned long)g_hmiEventsAccepted);
  line += "|events_dup=" + String((unsigned long)g_hmiEventsDuplicate);
  line += "|events_reject=" + String((unsigned long)g_hmiEventsRejected);
  line += "|last_event_id=" + String((unsigned)g_hmiLastAcceptedEventId);
  line += "|last_event_cmd=" + (g_hmiLastAcceptedEventCmd.length() ? g_hmiLastAcceptedEventCmd : String("none"));
  line += "|parser_crc=" + String((unsigned long)g_hmiParser.crcErrors());
  line += "|parser_resync=" + String((unsigned long)g_hmiParser.resyncs());
  line += "|hmi_tx=" + String((unsigned long)g_hmiFramesTx);
  line += "|display_tx=" + String((unsigned long)g_hmiDisplayFramesTx);
  line += "|ts_queue_drops=" + String((unsigned long)g_hmiTsQueueDrops);
  line += "|ts_parser_crc=" + String((unsigned long)g_hmiTsParserCrc);
  line += "|ts_parser_resync=" + String((unsigned long)g_hmiTsParserResync);
  line += "|ts_heap=" + String((unsigned long)g_hmiTsHeapFree);
  line += "|ts_min_heap=" + String((unsigned long)g_hmiTsHeapMin);
  line += "|ts_psram=" + String((unsigned long)g_hmiTsPsramFree);
  udp.beginPacket(server_IP, UDP_PORT);
  udp.print(line);
  udp.endPacket();
}

static void sendControl(float axis, uint16_t flags)
{
  uint8_t pkt[10];
  pkt[0] = 0xA7;
  pkt[1] = (uint8_t)((flags >> 8) & 0xFF);
  pkt[2] = (uint8_t)(flags & 0xFF);

  union { float f; uint8_t b[4]; } u;
  u.f = axis;

  pkt[3] = u.b[3];
  pkt[4] = u.b[2];
  pkt[5] = u.b[1];
  pkt[6] = u.b[0];
  pkt[7] = 0;
  pkt[8] = 0;
  pkt[9] = 0;

  udp.beginPacket(server_IP, UDP_PORT);
  udp.write(pkt, 10);
  udp.endPacket();
}

static bool forwardDisplayPacketToHmi(const String &line)
{
  if(!line.length()) return false;
  return hmiSendText(line);
}

static String buildFallbackDisplayPacket(uint16_t flags_now)
{
  String line = "HMI1";
  line += "|pos=0.00";
  line += "|to_near=0.00";
  line += "|to_far=0.00";
  line += "|speed_mps=0.00";
  line += "|speed_kmh=0.00";
  line += "|near=0.00";
  line += "|ref=0.00";
  line += "|far=0.00";
  line += "|ramp_near=0.00";
  line += "|ramp_far=0.00";
  line += "|ref_vis=0";
  // Fail-safe: if SRVR is not online, the displayed system state must be E-Stop active.
  const bool ctrl_estop = (flags_now & FLAG_ESTOP_PRESSED);
  const bool ctrl_interface_fault = (flags_now & (FLAG_CTRL_HMI_FAULT | FLAG_CTRL_FW_FAULT));
  const bool srvr_missing_estop = !srvrOnline;
  const bool ads_fault = !g_ads_inited;
  const bool ctrl_safety = ctrl_estop || ctrl_interface_fault || ads_fault;
  line += "|estop=" + String((ctrl_safety || srvr_missing_estop) ? 1 : 0);
  line += "|estop_src=";
  line += (ctrl_safety ? "CTRL" : (srvr_missing_estop ? "SRVR" : ""));
  if (ctrl_estop) line += "|status=E-Stop CTRL|status_level=red";
  else if (ads_fault) line += "|status=CTRL Analogue Input Fault|status_level=red";
  else if (ctrl_interface_fault) line += "|status=CTRL Safety Fault|status_level=red";
  else if (srvr_missing_estop) line += "|status=E-Stop|status_level=red";
  else line += "|status=System / Active|status_level=green";
  line += "|ctrl=1";
  line += "|srvr=" + String(srvrOnline ? 1 : 0);
  line += "|w1p=0";
  // SRVR is the sole authority for AUX assignment semantics. Fallback packets
  // use neutral names so a stale CTRL NVS layout can never masquerade as the
  // current operator configuration while SRVR is absent/reconnecting.
  line += "|aux1=AUX 1";
  line += "|aux2=AUX 2";
  line += "|aux3=AUX 3";
  line += "|aux4=AUX 4";
  line += "|aux5=AUX 5";
  line += "|max_mps=0.00";
  line += "|max_kmh=0.00";
  line += "|mode=Mode 1";
  line += "|flags=" + String((unsigned long)flags_now);
  line += "|preset_names=";
  line += "|preset_pos=";
  line += "|preset_vis=0,0,0,0,0,0,0,0,0,0,0,0";
  return line;
}


static bool applySrvrFirmwareBeacon(const String &line)
{
  String announced;
  if(line.startsWith("SRVR_FW|")) announced = hvGetPipeField(line, "version");
  else if(line.startsWith("DSP1|")) announced = hvGetPipeField(line, "srvr_fw");
  else return false;

  if(!announced.length()) return false;
  srvrOnline = true;
  g_lastSrvrRxMs = millis();
  const String session = hvGetPipeField(line, "session").length() ? hvGetPipeField(line, "session") : hvGetPipeField(line, "fw_session");
  const bool newSession = session.length() && session != g_srvrFirmwareSession;
  const bool releaseChanged = announced != HV_AUTH_VERSION;
  if(newSession) {
    g_srvrFirmwareSession = session;
    g_hmiTsCoordinatorSeen = false;
    g_hmiTsUpdateAllowed = false;
    g_hmiSafeUpdateContinuation = false;
    g_hmiMismatchSinceMs = 0;
  }
  // The coordinator grant is repeated in SRVR_FW and also accepted from DSP1
  // for backwards compatibility.  This must not depend on the bulk display
  // packet arriving at the same moment as a CTRL-TS HELLO response.
  String tsGrant = hvGetPipeField(line, "ts_allowed");
  if(!tsGrant.length()) tsGrant = hvGetPipeField(line, "fw_ts_allowed");
  if(tsGrant.length()) {
    g_hmiTsCoordinatorSeen = true;
    g_hmiTsUpdateAllowed = (tsGrant == "1");
  }
  if(releaseChanged || newSession) {
    const bool wasMatched = g_srvrFirmwareMatched;
    // A new SRVR process is an authority-session boundary even if the semantic
    // version string is unchanged. Fail closed and re-verify the immutable
    // manifest/SHA once so a stale previous-session match can never persist.
    g_srvrFirmwareMatched = false;
    g_srvrFirmwareState = releaseChanged ? "authority_changed" : "authority_session_changed";
    // SRVR starts its HTTP authority before constructing the backend, but keep a
    // fast retry window for network/startup races instead of requiring a reboot.
    g_fwAuthorityLastAttemptMs = 0;
    g_fwAuthorityRetryDelayMs = 0;
    g_fwAuthorityFastRetryUntilMs = millis() + 15000;
    if(wasMatched || releaseChanged) {
      Serial.printf("[FW AUTH] SRVR authority boundary release=%s announced=%s new_session=%u; re-verifying exact image\n",
                    HV_AUTH_VERSION, announced.c_str(), newSession ? 1U : 0U);
    }
  }
  return true;
}

static String buildHmiStatePacketFromSrvr(const String &line)
{
  // State/config changes are much smaller and more important than the full
  // ~900-byte telemetry packet. Forward this compact packet at priority so
  // Drive Mode, Battery Change and calibration state do not wait behind bulk
  // position/preset telemetry.
  static const char *keys[] = {
    "ctrl", "srvr", "w1p", "w1p_state", "estop", "estop_src",
    "status", "status_level", "mode", "drive_mode", "accel_mode",
    "battery_change", "service", "flags", "cal_active", "cal_kind",
    "cal_step", "cal_title", "cal_instruction",
    "aux1", "aux2", "aux3", "aux4", "aux5", "max_mps", "max_kmh",
    // Firmware progress is compact/high-priority. This keeps the update
    // dashboard responsive even while bulk telemetry is deliberately throttled.
    "fw_ctrl_active", "fw_ctrl_phase", "fw_ctrl_pct",
    "fw_w1p_active", "fw_w1p_phase", "fw_w1p_pct", "fw_ts_allowed"
  };
  String out = "HMS1";
  for(size_t i=0; i<(sizeof(keys)/sizeof(keys[0])); ++i){
    String v = hvGetPipeField(line, keys[i]);
    if(v.length()) out += String("|") + keys[i] + "=" + v;
  }
  // Live calibration position is useful at ~10 Hz while the wizard is open,
  // but must not turn HMS1 into continuous telemetry during ordinary motion.
  if(hvGetPipeField(line, "cal_active") == "1"){
    static const char *calKeys[] = {
      "cal_pos", "cal_near", "cal_ref", "cal_far",
      "cal_joy", "cal_left", "cal_centre", "cal_right"
    };
    for(size_t i=0; i<(sizeof(calKeys)/sizeof(calKeys[0])); ++i){
      String v = hvGetPipeField(line, calKeys[i]);
      if(v.length()) out += String("|") + calKeys[i] + "=" + v;
    }
  }
  return out;
}

static String buildHmiGeometryPacketFromSrvr(const String &line)
{
  // Geometry changes are sparse but operator-visible. Keep them independent of
  // both the high-rate HMS1 state delta and the ~900-byte bulk telemetry frame
  // so Ref/ramp/preset markers converge immediately without consuming event
  // bandwidth on every position update.
  static const char *keys[] = {
    "near", "ref", "far", "ref_frac", "ref_vis",
    "ramp_near", "ramp_far", "ramp_near_frac", "ramp_far_frac",
    "preset_names", "preset_pos", "preset_abs", "preset_vis"
  };
  String out = "HMG1";
  for(size_t i=0; i<(sizeof(keys)/sizeof(keys[0])); ++i){
    String v = hvGetPipeField(line, keys[i]);
    if(v.length()) out += String("|") + keys[i] + "=" + v;
  }
  return out;
}

static String buildHmiMotionPacketFromSrvr(const String &line)
{
  // Small live-motion delta for a smooth CTRL-TS marker/readout without
  // returning the ~900-byte bulk frame to 10 Hz. At SRVR's 10 Hz DSP cadence
  // this consumes only a modest fraction of the 115200 baud RS485 bus.
  static const char *keys[] = {
    "pos", "pos_frac", "to_near", "to_far", "speed_mps", "speed_kmh"
  };
  String out = "HMM1";
  for(size_t i=0; i<(sizeof(keys)/sizeof(keys[0])); ++i){
    String v = hvGetPipeField(line, keys[i]);
    if(v.length()) out += String("|") + keys[i] + "=" + v;
  }
  return out;
}

static void handleUdpRx()
{
  int size = udp.parsePacket();
  if(!size) return;
  const IPAddress remoteIp = udp.remoteIP();
  if(remoteIp != server_IP) {
    while(udp.available()) udp.read();
    if((millis() - g_lastUnexpectedSrvrLogMs) >= 5000) {
      g_lastUnexpectedSrvrLogMs = millis();
      Serial.printf("[UDP] Ignored packet from unexpected host %s\n", remoteIp.toString().c_str());
    }
    return;
  }

  if(size > 2047) {
    while(udp.available()) udp.read();
    Serial.printf("[UDP] Dropped oversized SRVR packet (%d bytes)\n", size);
    return;
  }

  uint8_t buf[2048];
  int n = udp.read(buf, sizeof(buf)-1);
  if(n <= 0) return;
  buf[n] = 0;

  if(buf[0] == 0x5A) {
    // Once SRVR explicitly announces shutdown, do not let a delayed heartbeat
    // ACK resurrect the old desktop session. A fresh SRVR_FW/DSP packet from a
    // restarted application clears this latch.
    if(g_srvrExplicitOffline) return;
    if(!srvrOnline) Serial.println("[SRVR] Handshake OK");
    srvrOnline = true;
    g_lastSrvrRxMs = millis();
    return;
  }

  String line = String((const char*)buf);
  line.trim();
  if(line == "AUX1") { g_virtualAuxUntil[0] = millis() + 300; return; }
  if(line == "AUX2") { g_virtualAuxUntil[1] = millis() + 300; return; }
  if(line == "AUX3") { g_virtualAuxUntil[2] = millis() + 300; return; }
  if(line == "AUX4") { g_virtualAuxUntil[3] = millis() + 300; return; }
  if(line == "AUX5") { g_virtualAuxUntil[4] = millis() + 300; return; }
  if(line == "SRVR_ALIVE") {
    // Background-safe liveness packet from SRVR communications worker. It carries
    // no safety/config state; it only proves that the SRVR process/transport is
    // alive independently of macOS Qt window scheduling.
    g_srvrExplicitOffline = false;
    srvrOnline = true;
    g_lastSrvrRxMs = millis();
    return;
  }
  if(line == "SRVR_OFFLINE") {
    // Graceful desktop shutdown is an explicit safety/connection transition,
    // not a 5-second display freshness event. The next POLL carries srvr=0,
    // taking CTRL-TS back to Waiting for SRVR within one poll interval.
    srvrOnline = false;
    g_srvrExplicitOffline = true;
    g_lastSrvrRxMs = 0;
    g_lastSrvrDisplayMs = 0;
    g_latestDisplayPacket = "";
    g_latestHmiStatePacket = "";
    g_hmiStatePacketPending = false;
    g_latestHmiMotionPacket = "";
    g_hmiMotionPacketPending = false;
    g_hmiTsCoordinatorSeen = false;
    g_hmiTsUpdateAllowed = false;
    g_hmiSafeUpdateContinuation = false;
    g_hmiMismatchSinceMs = 0;
    Serial.println("[SRVR] explicit offline notification received");
    return;
  }
  if(line == "PING") {
    udp.beginPacket(udp.remoteIP(), udp.remotePort());
    udp.print("PONG");
    udp.endPacket();
    return;
  }
  if(line.startsWith("SRVR_FW|")) {
    g_srvrExplicitOffline = false;
    srvrOnline = true;
    g_lastSrvrRxMs = millis();
    applySrvrFirmwareBeacon(line);
    return;
  }
  if(line.startsWith("DSP1|")) {
    g_srvrExplicitOffline = false;
    srvrOnline = true;
    g_lastSrvrRxMs = millis();
    g_lastSrvrDisplayMs = millis();

    // DSP1 still carries the release for compatibility, while .03 also accepts
    // a dedicated lightweight SRVR_FW beacon so firmware convergence does not
    // depend on HMI packet-change/keepalive timing. Neither path performs HTTP
    // while matched; they only invalidate the old authority match.
    applySrvrFirmwareBeacon(line);

    g_latestDisplayPacket = line;
    g_latestDisplayPacket.replace("DSP1|", "HMI1|");
    String nextState = buildHmiStatePacketFromSrvr(line);
    if(nextState != g_latestHmiStatePacket){
      g_latestHmiStatePacket = nextState;
      g_hmiStatePacketPending = true;
    }
    String nextGeometry = buildHmiGeometryPacketFromSrvr(line);
    if(nextGeometry != g_latestHmiGeometryPacket){
      g_latestHmiGeometryPacket = nextGeometry;
      g_hmiGeometryPacketPending = true;
    }
    String nextMotion = buildHmiMotionPacketFromSrvr(line);
    if(nextMotion != g_latestHmiMotionPacket){
      g_latestHmiMotionPacket = nextMotion;
      g_hmiMotionPacketPending = true;
    }
    // Store latest SRVR display packet only. The UART forward is rate-limited
    // in loop() so CTRL-TS is not flooded with repeated redraw pressure.
  }
}

static void pollButtonsAndUpdateLatches(uint16_t &flags_out)
{
  // EdgeBox CTRL: AI0 is the physical 5 V NC E-stop status input; AUX1..AUX5
  // are CTRL-TS touch events. ADC/input faults fail unsafe through g_ctrlEstopActive.
  flags_out = 0;
  const uint32_t now = millis();

  const bool estop_active = g_ctrlEstopActive;
  const bool hmi_safety = !hmiLinkConnected();
  const bool firmware_safety = !g_srvrFirmwareMatched;
  // Preserve source identity on the wire: physical AI0 alone owns the physical
  // E-stop bit. CTRL-TS and firmware-authority faults remain equally fail-safe,
  // but use dedicated bits so SRVR diagnostics cannot mislabel them as AI0.
  if(estop_active) flags_out |= FLAG_ESTOP_PRESSED;
  if(hmi_safety) flags_out |= FLAG_CTRL_HMI_FAULT;
  if(firmware_safety) flags_out |= FLAG_CTRL_FW_FAULT;

  if(now < g_virtualAuxUntil[0]) flags_out |= FLAG_AUX1;
  if(now < g_virtualAuxUntil[1]) flags_out |= FLAG_AUX2;
  if(now < g_virtualAuxUntil[2]) flags_out |= FLAG_AUX3;
  if(now < g_virtualAuxUntil[3]) flags_out |= FLAG_AUX4;
  if(now < g_virtualAuxUntil[4]) flags_out |= FLAG_AUX5;
  if(now < g_virtualCalCancelUntil) flags_out |= FLAG_CAL_CANCEL;
}

static void handleHmiEventLine(String line)
{
  line.trim();
  if(!line.length()) return;
  g_lastHmiRxMs = millis();
  if(line == "AUX1") g_virtualAuxUntil[0] = millis() + 300;
  else if(line == "AUX2") g_virtualAuxUntil[1] = millis() + 300;
  else if(line == "AUX3") g_virtualAuxUntil[2] = millis() + 300;
  else if(line == "AUX4") g_virtualAuxUntil[3] = millis() + 300;
  else if(line == "AUX5") g_virtualAuxUntil[4] = millis() + 300;
  else if(line == "CAL_CANCEL") g_virtualCalCancelUntil = millis() + 300;
  else if(line == "LAYOUT?") sendHmiLayout();
  else if(line == "CFG?") sendNetworkConfigToHmi();
  else if(line.startsWith("CFG1|")) {
    String note;
    bool ok = saveNetworkConfigFromHmi(line, note);
    hmiSendText(String("CFG_ACK|ok=") + (ok ? "1" : "0") + "|note=" + note);
    sendNetworkConfigToHmi();
    if(ok && hvGetPipeField(line, "reset") == "1") { delay(250); ESP.restart(); }
  }
}

static inline void hmiMasterTurnaroundGuard()
{
  // Real EdgeBox/Waveshare hardware needs substantially more bus-release margin
  // than the old 150 us assumption. 2.5 ms is still negligible at 115200 baud
  // but prevents the master from re-driving the pair while the slave transceiver
  // is finishing its response.
  delayMicroseconds(HMI_RS485_TURNAROUND_US);
}

static bool hmiBusRecoveryQuiet()
{
  return g_hmiBusQuietUntilMs && ((int32_t)(millis() - g_hmiBusQuietUntilMs) < 0);
}

static bool hmiNormalTxAllowed()
{
  return g_hmiCompatible && !hmiFwActive() && !g_hmiPollOutstanding && !hmiBusRecoveryQuiet();
}

static bool hmiSendText(const String &line)
{
  if(!line.length() || !hmiNormalTxAllowed()) return false;
  hmiMasterTurnaroundGuard();
  const bool ok = HVP2PRS485::sendText(HMI, HVP2PRS485::TEXT, g_hmiSeq++, line);
  if(ok) {
    g_hmiFramesTx++;
    // A bulk HMI1 frame occupies roughly 95 ms at 115200 baud. Start the next
    // POLL interval when that transmission has fully drained, not from an older
    // poll timestamp, so CTRL-TS gets a quiet apply/render window before it must
    // answer the next master request.
    g_lastHmiPollTxMs = millis();
  }
  return ok;
}

static bool hmiSendFirmwareStatusText(const String &line)
{
  // CTRL deliberately drops normal HMI compatibility before programming its
  // own OTA partition. Firmware progress must still reach the operator display
  // during that interval, but it must obey the exact same half-duplex ownership
  // rules as every other RS485 transmission.
  if(!line.length() || hmiFwActive() || g_hmiPollOutstanding || hmiBusRecoveryQuiet()) return false;
  hmiMasterTurnaroundGuard();
  const bool ok = HVP2PRS485::sendText(HMI, HVP2PRS485::TEXT, g_hmiSeq++, line);
  if(ok){
    g_hmiFramesTx++;
    g_lastHmiPollTxMs = millis();
  }
  return ok;
}

static void hmiAckEvent(uint16_t pollSeq, uint16_t eventId)
{
  if(hmiFwActive() || g_hmiPollOutstanding || hmiBusRecoveryQuiet()) return;
  char ack[24];
  snprintf(ack, sizeof(ack), "event_id=%u", unsigned(eventId));
  hmiMasterTurnaroundGuard();
  if(HVP2PRS485::sendFrame(HMI, HVP2PRS485::ACK, pollSeq, reinterpret_cast<const uint8_t*>(ack), uint16_t(strlen(ack)))) g_hmiFramesTx++;
}

static String hmiFwField(const String &line, const char *key){
  return hvGetPipeField(line, key);
}

static bool hmiFwActive(){ return g_hmiFwState != HMI_FW_IDLE; }

static void hmiFwReset(const char *reason){
  if(reason && *reason) Serial.printf("[HMI FW] %s\n", reason);
  g_hmiFwState = HMI_FW_IDLE;
  g_hmiFwOffset = 0;
  g_hmiFwLastBlockLen = 0;
  g_hmiFwSeq = 0;
  g_hmiFwLastTxMs = 0;
  g_hmiFwRetries = 0;
  g_hmiFwLastPct = -1;
  g_hmiFwPreUpdateBootId = "";
  g_hmiFwRebootConfirmStartedMs = 0;
  g_hmiFwRebootEnforceCount = 0;
  g_hmiCompatible = false;
}

static void hmiFwSendBegin(bool retry=false){
  if(!HV_CTRL_TS_IMAGE_AVAILABLE || HV_CTRL_TS_IMAGE_SIZE == 0 || strlen(HV_CTRL_TS_REQUIRED_SHA256) != 64){
    hmiFwReset("image not staged; cannot auto-update CTRL-TS");
    return;
  }
  if(!retry) g_hmiFwSeq = g_hmiSeq++;
  String meta = String("hw=") + HV_CTRL_TS_REQUIRED_HW +
                "|proto=" + String((unsigned)HV_CTRL_TS_REQUIRED_PROTOCOL) +
                "|size=" + String((unsigned long)HV_CTRL_TS_IMAGE_SIZE) +
                "|version=" + HV_CTRL_TS_REQUIRED_VERSION +
                "|sha256=" + HV_CTRL_TS_REQUIRED_SHA256 +
                "|block=" + String((unsigned)HMI_FW_BLOCK_DATA);
  hmiMasterTurnaroundGuard();
  HVP2PRS485::sendText(HMI, HVP2PRS485::FW_BEGIN, g_hmiFwSeq, meta);
  g_hmiFwState = HMI_FW_WAIT_READY;
  g_hmiFwLastTxMs = millis();
  Serial.printf("[HMI FW] FW_BEGIN %s size=%u%s\n", HV_CTRL_TS_REQUIRED_VERSION, (unsigned)HV_CTRL_TS_IMAGE_SIZE, retry?" retry":"");
}

static void hmiFwSendBlock(bool retry=false){
  if(g_hmiFwOffset >= HV_CTRL_TS_IMAGE_SIZE){
    if(!retry) g_hmiFwSeq = g_hmiSeq++;
    String end = String("size=") + String((unsigned long)HV_CTRL_TS_IMAGE_SIZE) + "|sha256=" + HV_CTRL_TS_REQUIRED_SHA256;
    hmiMasterTurnaroundGuard();
    HVP2PRS485::sendText(HMI, HVP2PRS485::FW_END, g_hmiFwSeq, end);
    g_hmiFwState = HMI_FW_WAIT_RESULT;
    g_hmiFwLastTxMs = millis();
    return;
  }
  size_t remain = HV_CTRL_TS_IMAGE_SIZE - g_hmiFwOffset;
  size_t chunk = remain < HMI_FW_BLOCK_DATA ? remain : HMI_FW_BLOCK_DATA;
  static uint8_t payload[4 + HMI_FW_BLOCK_DATA];
  uint32_t off = (uint32_t)g_hmiFwOffset;
  payload[0]=uint8_t(off>>24); payload[1]=uint8_t(off>>16); payload[2]=uint8_t(off>>8); payload[3]=uint8_t(off);
  memcpy(payload+4, HV_CTRL_TS_IMAGE + g_hmiFwOffset, chunk);
  if(!retry) g_hmiFwSeq = g_hmiSeq++;
  hmiMasterTurnaroundGuard();
  HVP2PRS485::sendFrame(HMI, HVP2PRS485::FW_BLOCK, g_hmiFwSeq, payload, uint16_t(chunk+4));
  g_hmiFwLastBlockLen = chunk;
  g_hmiFwState = HMI_FW_WAIT_BLOCK_ACK;
  g_hmiFwLastTxMs = millis();
}

static void hmiFwSendEnd(bool retry=false){
  if(!retry) g_hmiFwSeq = g_hmiSeq++;
  String end = String("size=") + String((unsigned long)HV_CTRL_TS_IMAGE_SIZE) + "|sha256=" + HV_CTRL_TS_REQUIRED_SHA256;
  hmiMasterTurnaroundGuard();
  HVP2PRS485::sendText(HMI, HVP2PRS485::FW_END, g_hmiFwSeq, end);
  g_hmiFwState = HMI_FW_WAIT_RESULT;
  g_hmiFwLastTxMs = millis();
  Serial.println("[HMI FW] FW_END sent; waiting for inactive-partition verification");
}

static void hmiFwSendReboot(bool retry=false){
  if(!retry) g_hmiFwSeq = g_hmiSeq++;
  hmiMasterTurnaroundGuard();
  HVP2PRS485::sendText(HMI, HVP2PRS485::REBOOT, g_hmiFwSeq, "apply=1");
  g_hmiFwState = HMI_FW_WAIT_REBOOT_ACK;
  g_hmiFwLastTxMs = millis();
}

static void hmiFwStart(bool coordinatorFallback=false){
  if(!g_srvrFirmwareMatched){
    Serial.println("[HMI FW] update deferred until CTRL matches SRVR firmware authority");
    return;
  }
  // CTRL-TS is the final stage of the coordinated update.  The grant is a
  // dedicated firmware-coordinator state repeated by SRVR_FW (and mirrored by
  // DSP1 for backwards compatibility), not a one-shot property of the latest
  // display packet.  This removes the boot/reconnect timing race that could
  // leave a mismatched CTRL-TS permanently waiting for CTRL.
  const bool coordinatorGrant = g_hmiTsCoordinatorSeen && g_hmiTsUpdateAllowed;
  if(!coordinatorGrant && !g_hmiSafeUpdateContinuation && !coordinatorFallback){
    static uint32_t lastDeferLogMs = 0;
    const uint32_t now = millis();
    if(!lastDeferLogMs || (now - lastDeferLogMs) >= 2000){
      lastDeferLogMs = now;
      Serial.println("[HMI FW] CTRL-TS update deferred until SRVR coordinator grants final-stage update");
    }
    return;
  }
  if(coordinatorFallback && !coordinatorGrant && !g_hmiSafeUpdateContinuation){
    Serial.println("[HMI FW] bounded coordinator recovery: approved mismatched CTRL-TS has waited 12 s; starting independent final stage");
  }
  if(g_hmiSafeUpdateContinuation && !coordinatorGrant){
    Serial.println("[HMI FW] continuing already-authorised CTRL-TS safe update after display-off reboot");
  }
  // One-time recovery boundary: only a CTRL-TS that explicitly advertises the
  // Only a peer advertising the safe_ota=2 display-off updater may receive an automatic self-update.
  // Older receivers write OTA flash while RGB framebuffers are live in PSRAM,
  // which is the failure mode that produced the observed colour/scale corruption.
  if(!g_hmiSafeOtaCapable){
    Serial.println("[HMI FW] automatic CTRL-TS update BLOCKED: peer lacks safe_ota=2 capability; manual USB bootstrap to v26.10.03.04 or newer required");
    return;
  }
  if(hmiFwActive()) return;
  // Final reboot completion must be proven by a different boot_id, not by the
  // old updater merely ACKing the REBOOT command. Preserve the pre-update boot
  // identity for the entire transfer.
  g_hmiFwPreUpdateBootId = g_hmiReportedBootId;
  g_hmiCompatible = false;
  g_hmiFwOffset = 0;
  g_hmiFwRetries = 0;
  g_hmiFwLastPct = -1;
  hmiFwSendBegin(false);
}

static bool hmiFwHandleFrame(const HVP2PRS485::Frame &frame){
  if(!hmiFwActive()) return false;
  String text = HVP2PRS485::payloadString(frame);
  // Every updater response must correlate to the exact outstanding request.
  // This prevents delayed/stale ACKs from advancing the transfer state after a
  // retry or after the 16-bit normal HMI sequence has moved on.
  const bool updaterResponse = frame.type == HVP2PRS485::FW_READY || frame.type == HVP2PRS485::FW_ACK ||
                               frame.type == HVP2PRS485::FW_RESULT || frame.type == HVP2PRS485::ACK ||
                               frame.type == HVP2PRS485::ERROR_MSG;
  if(updaterResponse && frame.seq != g_hmiFwSeq){
    Serial.printf("[HMI FW] ignored stale response type=0x%02X seq=%u expected=%u\n", unsigned(frame.type), unsigned(frame.seq), unsigned(g_hmiFwSeq));
    return true;
  }
  if(frame.type == HVP2PRS485::ERROR_MSG){
    if(g_hmiFwState == HMI_FW_WAIT_REBOOT_CONFIRM){
      // A freshly booted application may reject one of the bounded REBOOT
      // enforcement frames because its updater transaction no longer exists.
      // That is not update failure; only HELLO with a new boot_id + exact image
      // identity is allowed to complete this phase. Keep soliciting identity.
      Serial.printf("[HMI FW] post-reboot peer replied ERROR while confirmation is pending: %s\n", text.c_str());
      g_lastHmiHelloTxMs = 0;
      g_hmiFwLastTxMs = millis();
      return true;
    }
    // v26.10.06.06 safe self-update handoff: the displayed CTRL-TS deliberately
    // refuses to program flash, stages the exact target for a safe reboot, and asks CTRL to retry
    // after it has rebooted into its display-off updater. Treat this one response
    // as an expected transport transition, not as a failed firmware update.
    if(g_hmiFwState == HMI_FW_WAIT_READY && text == "fw_safe_reboot_retry"){
      Serial.println("[HMI FW] CTRL-TS entering safe headless updater; holding discovery until reboot completes");
      g_hmiSafeUpdateContinuation = true;
      hmiFwReset(nullptr);
      // CTRL-TS schedules its software restart 350 ms after this response. Give
      // it a generous non-blocking 1.8 s quiet window. The main CTRL control loop
      // continues normally; only HMI discovery/firmware traffic is held.
      g_hmiSafeRebootHoldUntilMs = millis() + 3000;
      g_lastHmiHelloTxMs = millis();
      return true;
    }
    Serial.printf("[HMI FW] CTRL-TS updater error: %s\n", text.c_str());
    hmiFwReset("transfer aborted by CTRL-TS");
    return true;
  }
  if(g_hmiFwState == HMI_FW_WAIT_READY && frame.type == HVP2PRS485::FW_READY){
    if(hmiFwField(text,"ok") != "1"){ hmiFwReset("CTRL-TS did not accept FW_BEGIN"); return true; }
    String next = hmiFwField(text,"next");
    size_t reported = next.length() ? (size_t)strtoull(next.c_str(),nullptr,10) : 0;
    // v1 receiver restarts each FW_BEGIN from zero; resume offsets are not trusted
    // until a future protocol revision explicitly authenticates resume state.
    if(reported != 0){ hmiFwReset("invalid FW_READY offset"); return true; }
    g_hmiFwOffset = 0;
    g_hmiFwRetries = 0;
    hmiFwSendBlock(false);
    return true;
  }
  if(g_hmiFwState == HMI_FW_WAIT_BLOCK_ACK && frame.type == HVP2PRS485::FW_ACK){
    String next = hmiFwField(text,"next");
    if(!next.length()){ hmiFwReset("FW_ACK missing next offset"); return true; }
    size_t reported = (size_t)strtoull(next.c_str(),nullptr,10);
    const size_t expectedNext = g_hmiFwOffset + g_hmiFwLastBlockLen;
    // An ACK may carry ok=0 after CTRL retransmits a block whose first ACK was
    // lost; the authoritative next offset must still equal the exact block end.
    if(reported != expectedNext || reported > HV_CTRL_TS_IMAGE_SIZE){ hmiFwReset("invalid FW_ACK offset"); return true; }
    g_hmiFwOffset = reported;
    g_hmiFwRetries = 0;
    int pct = HV_CTRL_TS_IMAGE_SIZE ? int((100ULL*g_hmiFwOffset)/HV_CTRL_TS_IMAGE_SIZE) : 0;
    if(pct/5 != g_hmiFwLastPct/5){ g_hmiFwLastPct=pct; Serial.printf("[HMI FW] %d%% (%u/%u)\n",pct,(unsigned)g_hmiFwOffset,(unsigned)HV_CTRL_TS_IMAGE_SIZE); }
    if(g_hmiFwOffset >= HV_CTRL_TS_IMAGE_SIZE) hmiFwSendEnd(false); else hmiFwSendBlock(false);
    return true;
  }
  if(g_hmiFwState == HMI_FW_WAIT_RESULT && frame.type == HVP2PRS485::FW_RESULT){
    String ok = hmiFwField(text,"ok");
    String sha = hmiFwField(text,"sha256"); sha.toLowerCase();
    String sizeText = hmiFwField(text,"size");
    const size_t reportedSize = sizeText.length() ? (size_t)strtoull(sizeText.c_str(), nullptr, 10) : 0;
    String requiredSha = String(HV_CTRL_TS_REQUIRED_SHA256); requiredSha.toLowerCase();
    // A successful finalize is accepted only when the receiver echoes the exact
    // image size and SHA-256 of the carrier embedded in this CTRL build. Missing
    // integrity fields are a failure, never an implicit success.
    if(ok == "1" && reportedSize == HV_CTRL_TS_IMAGE_SIZE && sha.length() == 64 && sha == requiredSha){
      Serial.println("[HMI FW] image verified by CTRL-TS; rebooting into new image");
      g_hmiFwRetries = 0;
      hmiFwSendReboot(false);
    } else hmiFwReset("CTRL-TS rejected final image identity");
    return true;
  }
  if((g_hmiFwState == HMI_FW_WAIT_REBOOT_ACK || g_hmiFwState == HMI_FW_WAIT_REBOOT_CONFIRM) && frame.type == HVP2PRS485::ACK){
    // ACK proves only that the still-running updater received REBOOT. .05.06
    // incorrectly treated this as completion, which stranded older headless
    // updaters on a black screen if their local restart did not fire. Keep the
    // transaction alive until a new boot_id and exact version/SHA are observed.
    if(g_hmiFwState == HMI_FW_WAIT_REBOOT_ACK){
      Serial.println("[HMI FW] reboot command acknowledged; awaiting new boot identity");
      g_hmiFwState = HMI_FW_WAIT_REBOOT_CONFIRM;
      g_hmiFwRebootConfirmStartedMs = millis();
      g_hmiFwRebootEnforceCount = 0;
      g_hmiFwRetries = 0;
      g_lastHmiHelloTxMs = 0;
    }
    g_hmiFwLastTxMs = millis();
    return true;
  }
  return false;
}

static void hmiFwServiceTimeout(){
  if(!hmiFwActive()) return;
  const uint32_t now=millis();
  if(g_hmiFwState == HMI_FW_WAIT_REBOOT_CONFIRM){
    // Keep enforcing REBOOT even after an ACK. This is deliberately bounded and
    // interleaved with HELLO discovery; success is declared only by a new boot.
    if(g_hmiFwRebootConfirmStartedMs && (now - g_hmiFwRebootConfirmStartedMs) > 14000U){
      hmiFwReset("CTRL-TS reboot was not confirmed by a new boot identity");
      g_lastHmiHelloTxMs = 0;
      return;
    }
    if((now - g_hmiFwLastTxMs) >= 1500U && g_hmiFwRebootEnforceCount < 8U){
      g_hmiFwSeq = g_hmiSeq++;
      hmiMasterTurnaroundGuard();
      HVP2PRS485::sendText(HMI, HVP2PRS485::REBOOT, g_hmiFwSeq, "apply=1");
      g_hmiFwLastTxMs = millis();
      ++g_hmiFwRebootEnforceCount;
      Serial.printf("[HMI FW] reboot enforcement %u/8; still waiting for new boot_id\n", unsigned(g_hmiFwRebootEnforceCount));
    }
    return;
  }
  const uint32_t replyTimeout = (g_hmiFwState == HMI_FW_WAIT_REBOOT_ACK) ? 750U : HMI_FW_REPLY_TIMEOUT_MS;
  const uint8_t maxRetries = (g_hmiFwState == HMI_FW_WAIT_REBOOT_ACK) ? 8U : HMI_FW_MAX_RETRIES;
  if((now-g_hmiFwLastTxMs) < replyTimeout) return;
  if(++g_hmiFwRetries > maxRetries){ hmiFwReset("RS485 firmware update timed out"); return; }
  Serial.printf("[HMI FW] response timeout; retry %u/%u\n",g_hmiFwRetries,maxRetries);
  if(g_hmiFwState == HMI_FW_WAIT_READY) hmiFwSendBegin(true);
  else if(g_hmiFwState == HMI_FW_WAIT_BLOCK_ACK) hmiFwSendBlock(true);
  else if(g_hmiFwState == HMI_FW_WAIT_RESULT) hmiFwSendEnd(true);
  else if(g_hmiFwState == HMI_FW_WAIT_REBOOT_ACK) hmiFwSendReboot(true);
}

static bool hmiTransportCompatible()
{
  // Never attempt an automatic flash unless the peer proves it is the exact
  // supported Waveshare target and speaks this updater protocol. A wrong board
  // or future incompatible protocol stays fail-safe and requires service.
  return g_hmiReportedHw == HV_CTRL_TS_REQUIRED_HW &&
         g_hmiReportedProto == HV_CTRL_TS_REQUIRED_PROTOCOL;
}

static bool hmiIdentityMatches()
{
  if(!hmiTransportCompatible()) return false;
  if(g_hmiReportedVersion != HV_CTRL_TS_REQUIRED_VERSION) return false;
  // Production CTRL firmware is built only after the matching CTRL-TS binary
  // has been embedded. The SHA-256 is therefore always part of compatibility.
  if(!HV_CTRL_TS_IMAGE_AVAILABLE || strlen(HV_CTRL_TS_REQUIRED_SHA256) != 64) return false;
  if(g_hmiReportedHash != HV_CTRL_TS_REQUIRED_SHA256) return false;
  if(g_hmiSafeOtaLevel < 2) return false;
  return true;
}

static void handleHmiFrame(const HVP2PRS485::Frame &frame)
{
  g_lastHmiRxMs = millis();
  if(hmiFwHandleFrame(frame)) return;
  if(frame.type == HVP2PRS485::HELLO_RESP) {
    g_hmiPollOutstanding = false;
    g_hmiSafeRebootHoldUntilMs = 0;
    g_hmiIdentitySeenMs = millis();
    String line = HVP2PRS485::payloadString(frame);
    g_hmiReportedHw = hvGetPipeField(line, "hw");
    g_hmiReportedVersion = hvGetPipeField(line, "version");
    g_hmiReportedHash = hvGetPipeField(line, "hash");
    // Keep the current HELLO boot identity in the HELLO_RESP scope because the
    // post-update convergence checks below must compare it with the pre-update
    // boot_id.  Do not hide this value inside a nested block.
    String newBootId = hvGetPipeField(line, "boot_id");
    String rr = hvGetPipeField(line, "reset_reason");
    if(newBootId.length() && newBootId != g_hmiReportedBootId){
      if(g_hmiReportedBootId.length()) Serial.printf("[HMI] CTRL-TS reboot detected old_boot=%s new_boot=%s reset_reason=%d\n", g_hmiReportedBootId.c_str(), newBootId.c_str(), rr.length()?rr.toInt():-1);
      else Serial.printf("[HMI] CTRL-TS boot=%s reset_reason=%d\n", newBootId.c_str(), rr.length()?rr.toInt():-1);
      g_hmiReportedBootId = newBootId;
      g_hmiHaveAcceptedEventId = false;
    }
    if(rr.length()) g_hmiReportedResetReason = rr.toInt();
    String pv = hvGetPipeField(line, "proto");
    g_hmiReportedProto = (uint8_t)pv.toInt();
    {
      String safeOtaText = hvGetPipeField(line, "safe_ota");
      long safeOtaLevel = safeOtaText.length() ? safeOtaText.toInt() : 0;
      if(safeOtaLevel < 0) safeOtaLevel = 0;
      if(safeOtaLevel > 255) safeOtaLevel = 255;
      g_hmiSafeOtaLevel = (uint8_t)safeOtaLevel;
      g_hmiSafeOtaCapable = g_hmiSafeOtaLevel >= 2;
    }
    bool match = hmiIdentityMatches();
    if(match){
      g_hmiMismatchSinceMs = 0;
      g_hmiSafeUpdateContinuation = false;
      if(g_hmiFwState == HMI_FW_WAIT_REBOOT_CONFIRM){
        const bool bootChanged = g_hmiFwPreUpdateBootId.length() && newBootId.length() && newBootId != g_hmiFwPreUpdateBootId;
        // Legacy safe-updater firmware may not report boot_id. In that case an
        // exact target version+SHA is itself sufficient reboot proof because the
        // running updater deliberately never advertises the staged image as active.
        const bool legacyExactIdentityProof = !g_hmiFwPreUpdateBootId.length();
        if(bootChanged || legacyExactIdentityProof){
          if(bootChanged){
            Serial.printf("[HMI FW] reboot confirmed old_boot=%s new_boot=%s; exact image identity active\n",
                          g_hmiFwPreUpdateBootId.c_str(), newBootId.c_str());
          } else {
            Serial.println("[HMI FW] reboot confirmed by exact target identity (legacy peer did not provide pre-update boot_id)");
          }
          hmiFwReset("updated CTRL-TS identity confirmed after reboot");
        } else {
          Serial.println("[HMI FW] exact image identity reported without a changed boot_id; reboot transaction remains open");
          match = false;
        }
      } else if(hmiFwActive()) {
        hmiFwReset("updated CTRL-TS identity confirmed");
      }
    } else if(g_hmiFwState == HMI_FW_WAIT_REBOOT_CONFIRM && g_hmiFwPreUpdateBootId.length() && newBootId.length() && newBootId != g_hmiFwPreUpdateBootId){
      // The peer did reboot, but did not come back as the verified target. Drop
      // the completed transfer and let ordinary mismatch convergence decide the
      // next safe action.
      hmiFwReset("CTRL-TS rebooted but target version/SHA was not active");
    }
    if(match && g_srvrFirmwareMatched && !g_hmiCompatible) {
      g_hmiCompatible = true;
      Serial.printf("[HMI] Compatible CTRL-TS %s proto=%u hash=%s\n", g_hmiReportedVersion.c_str(), unsigned(g_hmiReportedProto), g_hmiReportedHash.c_str());
      hmiMasterTurnaroundGuard();
      if(HVP2PRS485::sendText(HMI, HVP2PRS485::COMPATIBLE, g_hmiSeq++, String("version=") + HV_CTRL_TS_REQUIRED_VERSION + "|hash=" + HV_CTRL_TS_REQUIRED_SHA256)) g_hmiFramesTx++;
      // A reconnect must force the current full display state immediately. Never
      // let a packet that was refused while incompatible remain cached as sent.
      g_lastForwardedDisplayPacket = "";
      g_lastHmiDisplayKeepaliveMs = 0;
      lastDisplayForward = 0;
      g_hmiBusQuietUntilMs = 0;
      if(g_latestHmiStatePacket.length()) g_hmiStatePacketPending = true;
      if(g_latestHmiGeometryPacket.length()) g_hmiGeometryPacketPending = true;
      if(g_latestHmiMotionPacket.length()) g_hmiMotionPacketPending = true;
      sendHmiLayout();
      // Layout is presentation-only. Re-assert live SRVR-owned state/geometry
      // after it so old persisted UIL1 content can never win a reconnect race.
      if(g_latestHmiStatePacket.length()) g_hmiStatePacketPending = true;
      if(g_latestHmiGeometryPacket.length()) g_hmiGeometryPacketPending = true;
      if(g_latestHmiMotionPacket.length()) g_hmiMotionPacketPending = true;
      sendNetworkConfigToHmi();
    } else if(match && !g_srvrFirmwareMatched) {
      g_hmiCompatible = false;
      Serial.println("[HMI] CTRL-TS identity matches, but CTRL is still held by SRVR firmware authority.");
    } else if(!match) {
      g_hmiCompatible = false;
      if(g_srvrFirmwareMatched && srvrOnline && g_srvrFirmwareSession.length() &&
         g_hmiReportedVersion.length() && hmiTransportCompatible() && g_hmiSafeOtaCapable){
        if(!g_hmiMismatchSinceMs) g_hmiMismatchSinceMs = millis();
      } else {
        g_hmiMismatchSinceMs = 0;
      }
      Serial.printf("[HMI] INCOMPATIBLE hw=%s proto=%u version=%s hash=%s; required=%s\n",
                    g_hmiReportedHw.c_str(), unsigned(g_hmiReportedProto), g_hmiReportedVersion.c_str(),
                    g_hmiReportedHash.c_str(), HV_CTRL_TS_REQUIRED_VERSION);
      if(!hmiTransportCompatible()) {
        Serial.println("[HMI] Automatic update BLOCKED: peer hardware/protocol is not the approved CTRL-TS target.");
      } else if(!g_hmiSafeOtaCapable) {
        // Do not ask a level-0/1 receiver to self-flash. Level 1 (.03) contains
        // the safe-reboot discovery race found on bench; level 2 (.04+) fixes
        // both ends of that transition. One manual USB bootstrap to .04 is the
        // conservative recovery boundary, after which automatic updates resume.
        Serial.printf("[HMI] SAFE RECOVERY REQUIRED: CTRL-TS %s lacks safe_ota=2; manual USB bootstrap to %s is required once.\n",
                      g_hmiReportedVersion.c_str(), HV_CTRL_TS_REQUIRED_VERSION);
      } else if(HV_CTRL_TS_IMAGE_AVAILABLE && g_srvrFirmwareMatched) {
        Serial.println("[HMI] Approved safe-OTA target detected and identity differs; starting automatic RS485 CTRL-TS update.");
        hmiFwStart();
      } else if(HV_CTRL_TS_IMAGE_AVAILABLE) {
        Serial.println("[HMI] Approved CTRL-TS mismatch detected; update deferred until CTRL matches SRVR authority.");
      } else {
        // Normal production builds cannot reach this path because the build
        // pipeline refuses to compile CTRL until the real CTRL-TS image header
        // has been generated. Keep this guard for defensive service builds.
        Serial.println("[HMI] Automatic update unavailable: CTRL was built without a staged CTRL-TS image.");
      }
    }
    return;
  }
  if(frame.type == HVP2PRS485::EVENT) {
    if(!g_hmiPollOutstanding || frame.seq != g_hmiPollSeq) {
      g_hmiEventsRejected++;
      Serial.printf("[HMI] ignoring stale/unexpected EVENT seq=%u expected=%u outstanding=%d\n",
                    unsigned(frame.seq), unsigned(g_hmiPollSeq), g_hmiPollOutstanding ? 1 : 0);
      return;
    }
    g_hmiPollOutstanding = false;
    g_hmiPollStartedMs = 0;
    // POLL cadence is measured from transaction completion, not merely from
    // the previous request start. If CTRL-TS was slow to answer, immediately
    // issuing the next POLL here would permanently starve queued HMS1/HMI1
    // master traffic even though the bus is otherwise serialized.
    g_lastHmiPollTxMs = millis();
    const String payload = HVP2PRS485::payloadString(frame);
    const String idText = hvGetPipeField(payload, "id");
    const int cmdPos = payload.indexOf("|cmd=");
    const String cmd = (cmdPos >= 0) ? payload.substring(cmdPos + 5) : String();
    const String dropsText = hvGetPipeField(payload, "drops");
    const String tsCrcText = hvGetPipeField(payload, "crc");
    const String tsResyncText = hvGetPipeField(payload, "resync");
    const String tsHeapText = hvGetPipeField(payload, "heap");
    const String tsMinHeapText = hvGetPipeField(payload, "minheap");
    const String tsPsramText = hvGetPipeField(payload, "psram");
    if(dropsText.length()) g_hmiTsQueueDrops = (uint32_t)strtoul(dropsText.c_str(), nullptr, 10);
    if(tsCrcText.length()) g_hmiTsParserCrc = (uint32_t)strtoul(tsCrcText.c_str(), nullptr, 10);
    if(tsResyncText.length()) g_hmiTsParserResync = (uint32_t)strtoul(tsResyncText.c_str(), nullptr, 10);
    if(tsHeapText.length()) g_hmiTsHeapFree = (uint32_t)strtoul(tsHeapText.c_str(), nullptr, 10);
    if(tsMinHeapText.length()) g_hmiTsHeapMin = (uint32_t)strtoul(tsMinHeapText.c_str(), nullptr, 10);
    if(tsPsramText.length()) g_hmiTsPsramFree = (uint32_t)strtoul(tsPsramText.c_str(), nullptr, 10);
    const uint16_t eventId = idText.length() ? (uint16_t)idText.toInt() : 0;
    if(eventId && cmd.length()) {
      const bool duplicate = g_hmiHaveAcceptedEventId && eventId == g_hmiLastAcceptedEventId;
      if(duplicate) {
        g_hmiEventsDuplicate++;
      } else {
        g_hmiLastAcceptedEventId = eventId;
        g_hmiHaveAcceptedEventId = true;
        // HMI_STATUS is pipe-delimited, so expose only the compact AUX token
        // verbatim. Other event families are represented generically rather than
        // allowing embedded configuration separators into the diagnostics line.
        g_hmiLastAcceptedEventCmd = (cmd.startsWith("AUX") || cmd == "CAL_CANCEL") ? cmd : String("OTHER");
        g_hmiEventsAccepted++;
        // AUX confirmation is the touchscreen's busiest UI moment. Keep the
        // ~900-byte bulk packet off the bus briefly; the compact HMS1 state
        // packet still propagates Drive/Battery/calibration changes immediately.
        g_hmiBulkSuppressUntilMs = millis() + 1000;
        handleHmiEventLine(cmd);
      }
      // Dequeue occurs only after CTRL-TS receives this explicit ACK. If this
      // ACK is lost, the same event_id is resent and deduplicated above.
      hmiAckEvent(frame.seq, eventId);
    }
    return;
  }
  if(frame.type == HVP2PRS485::ERROR_MSG) {
    Serial.printf("[HMI] CTRL-TS error: %s\n", HVP2PRS485::payloadString(frame).c_str());
    g_hmiCompatible = false;
    g_hmiPollOutstanding = false;
    g_hmiPollStartedMs = 0;
    g_hmiBusQuietUntilMs = 0;
    g_lastHmiHelloTxMs = 0;
  }
}

static void handleHmiRx()
{
  while(HMI.available()) {
    if(g_hmiParser.feed((uint8_t)HMI.read(), g_hmiRxFrame)) handleHmiFrame(g_hmiRxFrame);
  }

  const uint32_t now = millis();
  hmiFwServiceTimeout();
  if(g_hmiFwState == HMI_FW_WAIT_REBOOT_CONFIRM) {
    // After REBOOT ACK, discovery must continue while the firmware transaction
    // remains open. Space HELLO away from the bounded REBOOT enforcement sends
    // so the half-duplex bus still has only one master request at a time.
    if((now - g_lastHmiHelloTxMs) >= 500U && (now - g_hmiFwLastTxMs) >= 120U){
      g_lastHmiHelloTxMs = now;
      String req = String("required=") + HV_CTRL_TS_REQUIRED_VERSION + "|proto=" + String(HVP2PRS485::PROTOCOL_VERSION);
      hmiMasterTurnaroundGuard();
      if(HVP2PRS485::sendText(HMI, HVP2PRS485::HELLO_REQ, g_hmiSeq++, req)) g_hmiFramesTx++;
    }
  } else if(hmiFwActive()) {
    // Firmware transfer owns the half-duplex bus until verification/reboot.
  } else if(g_hmiPollOutstanding) {
    // A POLL/EVENT exchange owns the bus even if compatibility changes while
    // the response is in flight. HELLO/TEXT cannot pre-empt this transaction.
    if((now - g_hmiPollStartedMs) >= HMI_POLL_RESPONSE_TIMEOUT_MS) {
      g_hmiPollTimeouts++;
      g_hmiPollOutstanding = false;
      g_hmiPollStartedMs = 0;
      // A late EVENT can still be in the slave's LVGL/RS485 service path. Keep
      // the master silent before reusing the bus, otherwise abandoning a timed
      // out sequence can recreate a half-duplex collision with that late EVENT.
      g_hmiBusQuietUntilMs = now + HMI_POLL_RECOVERY_QUIET_MS;
      Serial.printf("[HMI] POLL timeout seq=%u timeouts=%lu; recovery quiet %u ms\n", unsigned(g_hmiPollSeq), (unsigned long)g_hmiPollTimeouts, unsigned(HMI_POLL_RECOVERY_QUIET_MS));
    }
  } else if(hmiBusRecoveryQuiet()) {
    // RX remains active above, but the master must not drive the pair during the
    // post-timeout quiet window. A late EVENT is deliberately left un-ACKed and
    // will be retried on the next clean POLL.
  } else if(!g_hmiCompatible) {
    const bool safeRebootHold = g_hmiSafeRebootHoldUntilMs && ((int32_t)(now - g_hmiSafeRebootHoldUntilMs) < 0);
    // If SRVR grants the final stage after we already learned the mismatched
    // touchscreen identity, start the transfer from that fresh identity without
    // waiting for a lucky grant/HELLO coincidence.  A fresh HELLO is required
    // after the display-off safe reboot before the second FW_BEGIN is sent.
    const bool freshIdentity = g_hmiIdentitySeenMs && (now - g_hmiIdentitySeenMs) <= 1200;
    const bool coordinatorGrant = g_hmiTsCoordinatorSeen && g_hmiTsUpdateAllowed;
    const bool coordinatorFallback = g_hmiMismatchSinceMs && srvrOnline && g_srvrFirmwareMatched &&
                                     g_srvrFirmwareSession.length() &&
                                     (now - g_hmiMismatchSinceMs) >= HMI_COORDINATOR_FALLBACK_MS;
    if(!g_ctrlAuthorityUpdatePending && !safeRebootHold && freshIdentity &&
       g_srvrFirmwareMatched && (g_hmiSafeUpdateContinuation || coordinatorGrant || coordinatorFallback) &&
       g_hmiReportedVersion.length() && !hmiIdentityMatches() &&
       hmiTransportCompatible() && g_hmiSafeOtaCapable) {
      hmiFwStart(coordinatorFallback);
      if(hmiFwActive()) return;
    }
    if(!g_ctrlAuthorityUpdatePending && !safeRebootHold && (now - g_lastHmiHelloTxMs) >= 500) {
      g_lastHmiHelloTxMs = now;
      String req = String("required=") + HV_CTRL_TS_REQUIRED_VERSION + "|proto=" + String(HVP2PRS485::PROTOCOL_VERSION);
      hmiMasterTurnaroundGuard();
      if(HVP2PRS485::sendText(HMI, HVP2PRS485::HELLO_REQ, g_hmiSeq++, req)) g_hmiFramesTx++;
    }
  } else if((now - g_lastHmiPollTxMs) >= HMI_POLL_INTERVAL_MS) {
    g_lastHmiPollTxMs = now;
    g_hmiPollSeq = g_hmiSeq++;
    char pollStatus[20];
    snprintf(pollStatus, sizeof(pollStatus), "P1|srvr=%u", srvrOnline ? 1U : 0U);
    hmiMasterTurnaroundGuard();
    if(HVP2PRS485::sendFrame(HMI, HVP2PRS485::POLL, g_hmiPollSeq,
                             reinterpret_cast<const uint8_t*>(pollStatus), uint16_t(strlen(pollStatus)))) {
      g_hmiPollOutstanding = true;
      g_hmiPollStartedMs = millis();
      g_hmiPollsSent++;
      g_hmiFramesTx++;
    }
  }

  if(!hmiFwActive() && g_lastHmiRxMs && (now - g_lastHmiRxMs) > HMI_LINK_TIMEOUT_MS) {
    if(g_hmiCompatible) Serial.println("[HMI] RS485 link timeout - compatibility/safety gate dropped");
    g_hmiCompatible = false;
    g_hmiPollOutstanding = false;
    g_hmiPollStartedMs = 0;
    g_hmiBusQuietUntilMs = 0;
    g_lastHmiHelloTxMs = 0;
    // Do not keep presenting a stale detected version/hash after the peer is gone.
    g_hmiReportedVersion = "";
    g_hmiReportedHash = "";
    g_hmiReportedHw = "";
    g_hmiReportedProto = 0;
    g_hmiSafeOtaCapable = false;
    g_hmiSafeOtaLevel = 0;
    g_hmiIdentitySeenMs = 0;
    g_hmiMismatchSinceMs = 0;
  }
}

static bool initEthernetStatic()
{
  // EdgeBox uses the onboard W5500 on FSPI; bare ETH.begin() would select the
  // legacy RMII assumptions and is therefore intentionally not used.
  bool ok = ETH.begin(ETH_PHY_W5500, 1, EDGEBOX_ETH_CS, EDGEBOX_ETH_INT, EDGEBOX_ETH_RST,
                      SPI2_HOST, EDGEBOX_ETH_SCLK, EDGEBOX_ETH_MISO, EDGEBOX_ETH_MOSI);
  if(!ok) { Serial.println("[ETH] EdgeBox W5500 begin failed"); return false; }
  delay(100);
  if(!ETH.config(local_IP, gateway, subnet)) { Serial.println("[ETH] static config failed"); return false; }
  uint32_t t0=millis();
  while(millis()-t0 < 2000 && ETH.localIP()==IPAddress(0,0,0,0)) delay(10);
  return ETH.localIP()!=IPAddress(0,0,0,0);
}


static void reportCtrlAuthorityUpdateProgress(size_t received, size_t total, const char *phase)
{
  const int pct = total ? int((100ULL * received) / total) : 0;
  static int lastPct = -1;
  static String lastPhase;
  static uint32_t lastReportMs = 0;
  const String phaseText = String(phase ? phase : "Updating");
  const uint32_t now = millis();
  const bool phaseChanged = phaseText != lastPhase;
  const bool complete = phaseText == "Complete";
  if(!phaseChanged && !complete && pct == lastPct) return;
  if(!phaseChanged && !complete && lastReportMs && (now - lastReportMs) < 100) return;
  lastPct = pct;
  lastPhase = phaseText;
  lastReportMs = now;
  String msg = String("FWSTAT|device=CTRL|active=") + ((phase && strcmp(phase, "Complete") == 0) ? "0" : "1") +
               "|phase=" + phaseText + "|pct=" + String(constrain(pct, 0, 100));
  // CTRL is the RS485 master and CTRL-TS is the operator-visible update surface.
  // Never pre-empt an outstanding POLL/EVENT transaction merely to show progress.
  // A skipped progress sample is preferable to driving both ends of the bus.
  (void)hmiSendFirmwareStatusText(msg);
  // SRVR's Settings/Firmware field must show the same live CTRL update progress,
  // not only the version reported before/after the reboot. Use the existing UDP
  // control socket; this is update-only diagnostic traffic and does not affect
  // the normal high-rate A7 control packet cadence.
  const bool active = !(phase && strcmp(phase, "Complete") == 0);
  String srvrMsg = String("FW_PROGRESS|device=CTRL|active=") + (active ? "1" : "0") +
                   "|phase=" + String(phase ? phase : "Updating") +
                   "|pct=" + String(constrain(pct, 0, 100));
  udp.beginPacket(server_IP, UDP_PORT);
  udp.print(srvrMsg);
  udp.endPacket();
  Serial.printf("[FW AUTH] CTRL progress %s %d%%\n", phase ? phase : "Updating", pct);
}

static void serviceSrvrFirmwareAuthority()
{
  // Give the RS485 HELLO/update dashboard a brief chance to come alive before a
  // boot-time CTRL authority download blocks the main loop. Motion is already
  // fail-closed while g_srvrFirmwareMatched is false, so this grace period does
  // not weaken safety. It lets CTRL-TS show CTRL's real pull/update progress.
  if(!g_srvrFirmwareMatched && g_lastHmiRxMs == 0 && g_ctrlBootMs &&
     (millis() - g_ctrlBootMs) < HMI_STARTUP_AUTH_GRACE_MS) return;
  // Once verified, the motion/control loop never performs HTTP. SRVR release
  // changes arrive through the normal DSP1 beacon in handleUdpRx(), which clears
  // this match and re-enters the fail-closed fetch/update path below.
  if(g_srvrFirmwareMatched) return;
  if(ETH.localIP() == IPAddress(0,0,0,0) || !ETH.linkUp()) return;
  const uint32_t now = millis();
  if(g_fwAuthorityLastAttemptMs && (now - g_fwAuthorityLastAttemptMs) < g_fwAuthorityRetryDelayMs) return;
  g_fwAuthorityLastAttemptMs = now;

  HVP2PAuthorityOTA::Manifest manifest;
  String err;
  if(!HVP2PAuthorityOTA::fetchManifest(server_IP, HV_AUTH_ROLE, manifest, err)) {
    g_srvrFirmwareState = String("authority_") + err;
    // During a newly-started SRVR session the beacon may beat the HTTP server
    // to readiness. Fast retry prevents the old node sitting apparently idle.
    g_fwAuthorityRetryDelayMs = (g_fwAuthorityFastRetryUntilMs && (int32_t)(now - g_fwAuthorityFastRetryUntilMs) < 0) ? 500 : 5000;
    return;
  }
  if(manifest.role != HV_AUTH_ROLE || manifest.target != HV_AUTH_TARGET || manifest.version != manifest.release) {
    g_srvrFirmwareMatched = false;
    g_srvrFirmwareState = "manifest_identity_mismatch";
    g_fwAuthorityRetryDelayMs = 10000;
    Serial.printf("[FW AUTH] rejected manifest role=%s target=%s version=%s release=%s\n",
                  manifest.role.c_str(), manifest.target.c_str(), manifest.version.c_str(), manifest.release.c_str());
    return;
  }

  g_srvrRequiredVersion = manifest.version;
  g_srvrRequiredSha = manifest.sha256;

  bool versionOk = false;
  const int relation = HVP2PAuthorityOTA::compareVersions(HV_AUTH_VERSION, manifest.version, versionOk);
  if(!versionOk) {
    g_srvrFirmwareState = "version_parse_error";
    g_fwAuthorityRetryDelayMs = 10000;
    return;
  }
  if(relation > 0) {
    // Never silently downgrade a newer field node. Hold motion and require an
    // operator/service decision instead.
    g_srvrFirmwareState = "newer_than_srvr_no_downgrade";
    g_fwAuthorityRetryDelayMs = 30000;
    Serial.printf("[FW AUTH] installed %s is newer than SRVR %s; automatic downgrade blocked\n", HV_AUTH_VERSION, manifest.version.c_str());
    return;
  }

  if(relation == 0) {
    String runningSha;
    if(HVP2PAuthorityOTA::hashRunningPrefix(manifest.size, runningSha, err) && runningSha == manifest.sha256) {
      g_srvrFirmwareMatched = true;
      g_ctrlAuthorityUpdatePending = false;
      g_srvrFirmwareState = "matched";
      g_fwAuthorityRetryDelayMs = 1500;
      g_fwAuthorityFastRetryUntilMs = 0;
      g_lastHmiHelloTxMs = 0;
      Serial.printf("[FW AUTH] CTRL exact SRVR image verified %s sha=%s\n", manifest.version.c_str(), runningSha.c_str());
      return;
    }
    Serial.printf("[FW AUTH] same version but SHA mismatch (%s); replacing with exact SRVR image\n", err.c_str());
  } else {
    Serial.printf("[FW AUTH] installed %s older than required %s; automatic OTA requested\n", HV_AUTH_VERSION, manifest.version.c_str());
  }

  // CTRL has no direct motor output. The firmware-authority hold above forces
  // the control packet E-stop flag and prevents subordinate CTRL-TS updating.
  // First quiesce the RS485 master. A blocking HTTP/flash operation entered with
  // a POLL outstanding would suppress every FWSTAT progress sample because the
  // EVENT can no longer be serviced until the download returns. Mark the update
  // pending so handleHmiRx stops issuing new POLLs/HELLOs, then begin only once
  // the current transaction/recovery window has fully completed.
  g_ctrlAuthorityUpdatePending = true;
  g_hmiCompatible = false;
  if(hmiFwActive()) hmiFwReset("CTRL SRVR-authority update owns firmware path");
  if(g_hmiPollOutstanding || hmiBusRecoveryQuiet()) {
    g_fwAuthorityRetryDelayMs = 50;
    return;
  }
  g_srvrFirmwareState = "updating";
  if(HVP2PAuthorityOTA::downloadAndStage(server_IP, manifest, HV_AUTH_ROLE, HV_AUTH_TARGET, err, reportCtrlAuthorityUpdateProgress)) {
    g_srvrFirmwareState = "rebooting";
    Serial.println("[FW AUTH] CTRL image verified and staged; rebooting");
    delay(150);
    ESP.restart();
  }
  g_ctrlAuthorityUpdatePending = false;
  g_srvrFirmwareState = String("update_failed_") + err;
  g_fwAuthorityRetryDelayMs = 10000;
  Serial.printf("[FW AUTH] CTRL automatic OTA failed: %s\n", err.c_str());
}


void setup()
{
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println(CTRL_VERSION);
  Serial.printf("[OTA] Build identity: %s\n", HV_UPDATE_BUILD_TOKEN);
  Serial.println(CTRL_HMI_ARCH);
  hvLoadHmiLayoutConfig();
  hvLoadNetworkConfig();

  HMI.setRxBufferSize(4096);
  HMI.begin(HMI_BAUD, SERIAL_8N1, HMI_UART_RX, HMI_UART_TX);
  HMI.setPins(HMI_UART_RX, HMI_UART_TX, -1, HMI_UART_RTS);
  if(!HMI.setMode(UART_MODE_RS485_HALF_DUPLEX)) Serial.println("[HMI] ERROR setting EdgeBox RS485 half-duplex mode");
  Serial.printf("[HMI] EdgeBox isolated RS485 RX=%d TX=%d RTS=%d @ %d\n", HMI_UART_RX, HMI_UART_TX, HMI_UART_RTS, HMI_BAUD);

  Serial.println("[IO] CTRL E-stop: EdgeBox AI0 (pin 14) 5V NC loop; >=3.5V healthy, open/low/mid-band unsafe");

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  delay(50);
  scanI2CBus();

  Serial.println("[IO] AUX1..AUX5 touchscreen-only; no physical AUX GPIO module");

  if(detectSgm58031()) {
    Serial.println("[JOY] AI1 (pin 16) ready with 5-sample low-latency trimmed-mean filtering. Re-run SRVR Set Left / Set Centre / Set Right after EdgeBox migration.");
    Serial.println("[ESTOP] AI0 (pin 14) ready for 5V normally-closed status loop; E-stop remains active until 3 healthy samples are proven.");
  } else {
    Serial.println("[JOY] analogue input unavailable - joystick output forced neutral for safety");
  }

  if(initEthernetStatic()) {
    Serial.print("[ETH] Local IP: ");
    Serial.println(ETH.localIP());
  }

  udp.begin(UDP_PORT);
  Serial.print("[UDP] Listening on "); Serial.println(UDP_PORT);
  hvBeginWebUpdater();
  Serial.print("[UDP] Target SRVR: "); Serial.print(server_IP); Serial.print(":"); Serial.println(UDP_PORT);
  Serial.println("[FW AUTH] CTRL held fail-closed until exact SRVR firmware manifest/SHA is verified.");
  g_ctrlBootMs = millis();
  g_fwAuthorityFastRetryUntilMs = g_ctrlBootMs + 15000;

  uint16_t startup_flags = 0;
  pollButtonsAndUpdateLatches(startup_flags);
  if(!g_ads_inited) startup_flags |= FLAG_ADS1115_FAULT;
  (void)startup_flags;
  Serial.println("[HMI] Waiting for framed CTRL-TS HELLO response; motion remains E-stopped until compatible.");
}

void loop()
{
  handleUdpRx();
  hvHandleWebUpdater();
  handleHmiRx();
  serviceSrvrFirmwareAuthority();
  refreshAdsHealth();
  printAdsDiagnostics();
  handleSerialJoystickCommands();

  const uint32_t now = millis();
  if(now - lastHeartbeat >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeat = now;
    sendHeartbeat();
  }

  if(now - g_lastHmiStatusReportMs >= 250) {
    g_lastHmiStatusReportMs = now;
    sendHmiStatusToSrvr();
  }

  if(now - lastControl >= CONTROL_INTERVAL_MS) {
    lastControl = now;
    float axis = g_srvrFirmwareMatched ? readJoystickAxis() : 0.0f;
    sampleCtrlEstopAI0();
    uint16_t flags = 0;
    pollButtonsAndUpdateLatches(flags);
    if(!g_ads_inited) flags |= FLAG_ADS1115_FAULT;
    sendControl(axis, flags);
  }

  // Connection/safety presence follows the 250 ms heartbeat, not the much
  // slower bulk-display freshness timer. Three missed heartbeat intervals are
  // enough to mark SRVR offline; graceful shutdown is faster via SRVR_OFFLINE.
  if(srvrOnline && g_lastSrvrRxMs && (now - g_lastSrvrRxMs) > SRVR_PEER_TIMEOUT_MS) {
    srvrOnline = false;
    Serial.println("[SRVR] heartbeat timeout; marking SRVR offline");
  }
  if(g_lastSrvrDisplayMs && (now - g_lastSrvrDisplayMs) > SRVR_DISPLAY_TIMEOUT_MS) {
    g_latestDisplayPacket = "";
  }

  // Priority state/config delta: this is intentionally sent before the bulk HMI
  // telemetry packet so operator state changes cannot be hidden behind an
  // ~900-byte transfer. Periodic compact refreshes make the display self-healing
  // if a delta arrived while the update dashboard owned the screen or after a
  // transient reconnect.
  if(g_latestHmiStatePacket.length() && (now - g_lastHmiStateTxMs) >= HMI_STATE_KEEPALIVE_MS) g_hmiStatePacketPending = true;
  if(g_latestHmiGeometryPacket.length() && (now - g_lastHmiGeometryTxMs) >= HMI_GEOMETRY_KEEPALIVE_MS) g_hmiGeometryPacketPending = true;
  if(g_latestHmiMotionPacket.length() && (now - g_lastHmiMotionTxMs) >= HMI_MOTION_KEEPALIVE_MS) g_hmiMotionPacketPending = true;
  bool hmiPriorityPacketSent = false;
  if(g_hmiStatePacketPending && g_latestHmiStatePacket.length() && hmiNormalTxAllowed()) {
    if(hmiSendText(g_latestHmiStatePacket)) {
      g_hmiStatePacketPending = false;
      g_lastHmiStateTxMs = now;
      hmiPriorityPacketSent = true;
    }
  }
  if(!hmiPriorityPacketSent && g_hmiGeometryPacketPending && g_latestHmiGeometryPacket.length() && hmiNormalTxAllowed()) {
    if(hmiSendText(g_latestHmiGeometryPacket)) {
      g_hmiGeometryPacketPending = false;
      g_lastHmiGeometryTxMs = now;
      hmiPriorityPacketSent = true;
    }
  }
  if(!hmiPriorityPacketSent && g_hmiMotionPacketPending && g_latestHmiMotionPacket.length() &&
     (now - g_lastHmiMotionTxMs) >= HMI_MOTION_MIN_MS && hmiNormalTxAllowed()) {
    if(hmiSendText(g_latestHmiMotionPacket)) {
      g_hmiMotionPacketPending = false;
      g_lastHmiMotionTxMs = now;
      hmiPriorityPacketSent = true;
    }
  }

  // v26.10.06.06: do not resend UIL1 layout on a timer.
  // Some Waveshare/LVGL builds visibly flicker when the layout header/config
  // is resent periodically. Layout is now sent only at boot, upload/reset,
  // and in response to a CTRL-TS PING/reconnect request.

  if(now - lastDisplayForward >= DISPLAY_FORWARD_MIN_MS) {
    uint16_t flags = 0;
    pollButtonsAndUpdateLatches(flags);
    String nextDisplay;
    if(g_latestDisplayPacket.length() && ((now - g_lastSrvrDisplayMs) <= SRVR_DISPLAY_TIMEOUT_MS)) {
      nextDisplay = g_latestDisplayPacket;
    } else {
      nextDisplay = buildFallbackDisplayPacket(flags);
    }

    const bool changed = (nextDisplay != g_lastForwardedDisplayPacket);
    const bool keepalive_due = ((now - g_lastHmiDisplayKeepaliveMs) >= DISPLAY_KEEPALIVE_MS);
    const bool bulk_suppressed = g_hmiBulkSuppressUntilMs && ((int32_t)(now - g_hmiBulkSuppressUntilMs) < 0);
    if(!hmiPriorityPacketSent && !bulk_suppressed && (changed || keepalive_due) && hmiNormalTxAllowed()) {
      lastDisplayForward = now;
      if(forwardDisplayPacketToHmi(nextDisplay)) {
        g_hmiDisplayFramesTx++;
        g_lastHmiDisplayKeepaliveMs = now;
        g_lastForwardedDisplayPacket = nextDisplay;
      }
    } else {
      // Event-driven HMI path: unchanged packets are not re-sent on every CTRL
      // loop pass. This keeps the touchscreen/LVGL side stable during 10-12 hour days.
      lastDisplayForward = now;
    }
  }

  delay(5);
}
