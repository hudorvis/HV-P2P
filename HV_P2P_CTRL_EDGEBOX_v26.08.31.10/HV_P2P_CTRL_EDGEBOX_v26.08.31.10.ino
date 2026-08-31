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

// EdgeBox-ESP-100 CTRL hardware layer. The onboard SGM58031 at 0x48 is
// driven directly using its documented register map; no external ADS1115 is required.
static bool g_ads_inited = false;
static uint8_t ADS_ADDR = 0x48;

#define CTRL_VERSION "HV P2P CTRL EdgeBox v26.08.31.10"
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
#define CONTROL_INTERVAL_MS   50
#define DISPLAY_FORWARD_MIN_MS 100
#define DISPLAY_KEEPALIVE_MS   3000
#define SRVR_DISPLAY_TIMEOUT_MS 5000
#define HMI_BAUD              115200
#define HMI_UART_RX EDGEBOX_RS485_RX
#define HMI_UART_TX EDGEBOX_RS485_TX
#define HMI_UART_RTS EDGEBOX_RS485_RTS

#define CTRL_ESTOP_PIN 4  // EdgeBox isolated DI0
// EdgeBox DI optocoupler output is HIGH when the 24 V field input is asserted.
// Wire the E-stop status as a 24 V NC loop: HIGH=healthy, LOW/open=unsafe.
static const int CTRL_ESTOP_HEALTHY_LEVEL = HIGH;

// CTRL EdgeBox input model:
//   - EdgeBox 0-10 V option required. Existing 0-5 V joystick connects to AI0.
//   - EdgeBox integrated SGM58031 ADC at I2C 0x48 reads AI0.
//   - EdgeBox isolated DI0 is the only physical CTRL switch input (E-stop).
//   - AUX1..AUX5 are touchscreen-only and arrive from CTRL-TS over RS485.
//   - SRVR remains authoritative for Left/Centre/Right joystick calibration and deadband.

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

NetworkUDP udp;
HardwareSerial HMI(1);
HVP2PRS485::Parser g_hmiParser;
static HVP2PRS485::Frame g_hmiRxFrame;
static uint16_t g_hmiSeq = 1;
static bool g_hmiCompatible = false;
static String g_hmiReportedVersion;
static String g_hmiReportedHash;
static String g_hmiReportedHw;
static uint8_t g_hmiReportedProto = 0;
static uint32_t g_lastHmiHelloTxMs = 0;
static uint32_t g_lastHmiPollTxMs = 0;

// CTRL is the firmware authority for the Waveshare CTRL-TS. A generated
// HV_P2P_CTRL_TS_Firmware_Image.h embeds the exact exported .bin, version and
// SHA-256. When identity differs, CTRL keeps motion fail-safe stopped and
// performs a deterministic request/response transfer over the same RS485 link.
enum HmiFwTxState : uint8_t { HMI_FW_IDLE=0, HMI_FW_WAIT_READY, HMI_FW_WAIT_BLOCK_ACK, HMI_FW_WAIT_RESULT, HMI_FW_WAIT_REBOOT_ACK };
static HmiFwTxState g_hmiFwState = HMI_FW_IDLE;
static size_t g_hmiFwOffset = 0;
static size_t g_hmiFwLastBlockLen = 0;
static uint16_t g_hmiFwSeq = 0;
static uint32_t g_hmiFwLastTxMs = 0;
static uint8_t g_hmiFwRetries = 0;
static int g_hmiFwLastPct = -1;
static const size_t HMI_FW_BLOCK_DATA = 2048;
static const uint32_t HMI_FW_REPLY_TIMEOUT_MS = 1200;
static const uint8_t HMI_FW_MAX_RETRIES = 5;

static bool hmiSendText(const String &line);

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
static const char* DEFAULT_HMI_LAYOUT_LINE = "UIL1|title=HV P2P CTRL-TS|subtitle=v26.08.31.10|layout=main5|theme=hv|aux1=AUX 1|aux2=AUX 2|aux3=AUX 3|aux4=AUX 4|aux5=AUX 5|hint=Ready";



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
static const char* HV_UPDATE_BUILD_TOKEN = "HV_P2P_FW_ROLE=CTRL;HV_P2P_FW_VERSION=v26.08.31.10";

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
    // v26.08.31.10 migration: older CTRL NVS layouts were main4/aux1-aux4.
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
static const uint8_t JOY_SAMPLES = 12;
static const float EDGEBOX_JOY_5V_COUNTS = 13333.3f;
static float g_joy_filtered = 0.0f;
static bool g_joy_ready = false;
static uint32_t g_lastAdsDiagMs = 0;
static const uint32_t ADS_DIAG_INTERVAL_MS = 5000;
static const uint32_t ADS_HEALTH_CHECK_INTERVAL_MS = 250;
static const uint32_t ADS_RECOVERY_RETRY_MS = 1000;
static uint32_t g_lastAdsHealthCheckMs = 0;
static uint32_t g_lastAdsRecoveryAttemptMs = 0;

static uint32_t g_virtualAuxUntil[5] = {0,0,0,0,0};
static String g_latestDisplayPacket;
static uint32_t g_lastSrvrDisplayMs = 0;
static uint32_t g_lastSrvrRxMs = 0;
static uint32_t g_lastUnexpectedSrvrLogMs = 0;
static uint32_t g_lastHmiRxMs = 0;
static uint32_t g_lastHmiStatusReportMs = 0;
static String g_lastForwardedDisplayPacket;
static uint32_t g_lastHmiDisplayKeepaliveMs = 0;
static const uint32_t HMI_LINK_TIMEOUT_MS = 3000;

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
// assumptions. AI0 is run continuously at 800 SPS, +/-6.144 V full scale.
static const uint8_t SGM_REG_CONVERSION = 0x00;
static const uint8_t SGM_REG_CONFIG     = 0x01;
static const uint8_t SGM_REG_CONFIG1    = 0x04;
static const uint8_t SGM_REG_CHIP_ID    = 0x05;
static const uint16_t SGM_CONFIG_AI0_CONT_800SPS_6V144 = 0x40E3;
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

static bool sgmReadAI0(int16_t &raw) {
  uint16_t u = 0;
  if(!sgmReadRegister(SGM_REG_CONVERSION, u)) return false;
  raw = int16_t(u);
  return true;
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
  // AI0 single-ended, +/-6.144 V PGA, continuous conversion, 800 SPS.
  if(!sgmWriteRegister(SGM_REG_CONFIG1, SGM_CONFIG1_DEFAULT) ||
     !sgmWriteRegister(SGM_REG_CONFIG, SGM_CONFIG_AI0_CONT_800SPS_6V144)) {
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
  const bool sampleOk = sgmReadAI0(first);
  if(!cfgOk || !sampleOk || ((cfg & 0x7FFFu) != (SGM_CONFIG_AI0_CONT_800SPS_6V144 & 0x7FFFu))) {
    g_ads_inited = false;
    g_joy_ready = false;
    Serial.printf("[AI] SGM58031 verify failed cfg_ok=%d cfg=0x%04X sample_ok=%d\n",
                  cfgOk ? 1 : 0, unsigned(cfg), sampleOk ? 1 : 0);
    return false;
  }

  g_ads_inited = true;
  g_joy_ready = true;
  g_joy_filtered = rawJoystickTransportAxis(first);
  Serial.printf("[AI] EdgeBox SGM58031 OK @0x48 AI0 continuous 800SPS FS=+/-6.144V chip=0x%04X%s\n",
                unsigned(chip), idOk ? "" : " (ID read unavailable)");
  return true;
}

static void refreshAdsHealth() {
  const uint32_t now = millis();
  if((now - g_lastAdsHealthCheckMs) < ADS_HEALTH_CHECK_INTERVAL_MS) return;
  g_lastAdsHealthCheckMs = now;
  if(g_ads_inited) {
    int16_t raw = 0;
    if(!i2cProbe(ADS_ADDR) || !sgmReadAI0(raw)) {
      g_ads_inited = false; g_joy_ready = false; g_joy_filtered = 0.0f;
      Serial.println("[AI] SGM58031 LOST/read failed - joystick neutral + analogue fault flag");
    }
    return;
  }
  if((now - g_lastAdsRecoveryAttemptMs) < ADS_RECOVERY_RETRY_MS) return;
  g_lastAdsRecoveryAttemptMs = now;
  if(detectSgm58031()) Serial.println("[AI] SGM58031 RECOVERED");
}

static float rawJoystickTransportAxis(int16_t raw) {
  float axis = (2.0f * (float(raw) / EDGEBOX_JOY_5V_COUNTS)) - 1.0f;
  return constrain(axis, -1.0f, 1.0f);
}

static float readJoystickAxis() {
  if(!g_ads_inited || !g_joy_ready) return 0.0f;

  // At 800 SPS each fresh conversion is ~1.25 ms. Take four genuinely spaced
  // samples (~5 ms total), reject a read failure immediately, then apply only a
  // light low-pass. SRVR remains the only Left/Centre/Right calibration layer.
  int32_t sum = 0;
  static const uint8_t SAMPLE_COUNT = 4;
  for(uint8_t i=0; i<SAMPLE_COUNT; ++i) {
    int16_t raw = 0;
    if(!sgmReadAI0(raw)) {
      g_ads_inited = false; g_joy_ready = false; g_joy_filtered = 0.0f;
      Serial.println("[AI] SGM58031 sample read failed - joystick neutral + analogue fault flag");
      return 0.0f;
    }
    sum += raw;
    if(i + 1 < SAMPLE_COUNT) delayMicroseconds(1400);
  }
  int16_t raw = int16_t(sum / SAMPLE_COUNT);
  float axis = rawJoystickTransportAxis(raw);
  g_joy_filtered = (0.70f * g_joy_filtered) + (0.30f * axis);
  return constrain(g_joy_filtered, -1.0f, 1.0f);
}

static void printAdsDiagnostics() {
  if(!g_ads_inited) return;
  const uint32_t now = millis();
  if(now - g_lastAdsDiagMs < ADS_DIAG_INTERVAL_MS) return;
  g_lastAdsDiagMs = now;
  int16_t a0 = 0;
  if(!sgmReadAI0(a0)) return;
  const float adcV = float(a0) * (6.144f / 32768.0f);
  const float fieldV = adcV * 2.0f;
  Serial.printf("[AI] SGM58031 AI0=%d adc=%.3fV field~=%.3fV transport_axis=%.4f (SRVR calibration authoritative)\n",
                int(a0), adcV, fieldV, rawJoystickTransportAxis(a0));
}

static void handleSerialJoystickCommands() {
  while(Serial.available()) {
    char c = char(Serial.read());
    if(c=='j' || c=='J') {
      int16_t raw = 0;
      const bool ok = g_ads_inited && sgmReadAI0(raw);
      const float adcV = float(raw) * (6.144f / 32768.0f);
      const float fieldV = adcV * 2.0f;
      Serial.printf("[JOY] ok=%d AI0=%d field~=%.3fV axis=%.4f; use SRVR Set Left/Centre/Right wizard\n",
                    ok ? 1 : 0, int(raw), fieldV, ok ? rawJoystickTransportAxis(raw) : 0.0f);
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
  switch(g_hmiFwState) {
    case HMI_FW_WAIT_READY:      return "starting";
    case HMI_FW_WAIT_BLOCK_ACK:  return "transferring";
    case HMI_FW_WAIT_RESULT:     return "verifying";
    case HMI_FW_WAIT_REBOOT_ACK: return "rebooting";
    default:
      if(!g_hmiCompatible && g_hmiReportedVersion.length() && !HV_CTRL_TS_IMAGE_AVAILABLE) return "image_missing";
      return "idle";
  }
}

static void sendHmiStatusToSrvr()
{
  uint32_t now = millis();
  uint32_t age = g_lastHmiRxMs ? (now - g_lastHmiRxMs) : 999999;
  String line = "HMI_STATUS";
  line += "|ctrl_ts=" + String(hmiLinkConnected() ? 1 : 0);
  line += "|ctrl_version=v26.08.31.10";
  line += "|ads=" + String(g_ads_inited ? 1 : 0);
  line += "|age_ms=" + String((unsigned long)age);
  // Report the identity actually returned by the Waveshare rather than the CTRL
  // application version. This lets SRVR Setup diagnose a mismatch/update.
  line += "|version=" + (g_hmiReportedVersion.length() ? g_hmiReportedVersion : String("unknown"));
  line += "|required=" + String(HV_CTRL_TS_REQUIRED_VERSION);
  line += "|compatible=" + String(g_hmiCompatible ? 1 : 0);
  line += "|image=" + String(HV_CTRL_TS_IMAGE_AVAILABLE ? 1 : 0);
  line += "|fw_state=" + String(hmiFwStateText());
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

static void forwardDisplayPacketToHmi(const String &line)
{
  if(!line.length()) return;
  hmiSendText(line);
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
  const bool srvr_missing_estop = !srvrOnline;
  const bool ads_fault = !g_ads_inited;
  line += "|estop=" + String((ctrl_estop || srvr_missing_estop || ads_fault) ? 1 : 0);
  line += "|estop_src=";
  line += (ctrl_estop ? "CTRL" : (srvr_missing_estop ? "SRVR" : ""));
  if (ctrl_estop) line += "|status=E-Stop CTRL|status_level=red";
  else if (ads_fault) line += "|status=CTRL Analogue Input Fault|status_level=red";
  else if (srvr_missing_estop) line += "|status=E-Stop|status_level=red";
  else line += "|status=Active|status_level=blue";
  line += "|ctrl=1";
  line += "|srvr=" + String(srvrOnline ? 1 : 0);
  line += "|w1p=0";
  line += "|aux1=Battery Change";
  line += "|aux2=Drive Mode";
  line += "|aux3=Accel Type";
  line += "|aux4=Goto Ref";
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
    if(!srvrOnline) Serial.println("[SRVR] Handshake OK");
    srvrOnline = true;
    g_lastSrvrRxMs = millis();
    return;
  }

  String line = String((const char*)buf);
  line.trim();
  if(line == "AUX1") { g_virtualAuxUntil[0] = millis() + 120; return; }
  if(line == "AUX2") { g_virtualAuxUntil[1] = millis() + 120; return; }
  if(line == "AUX3") { g_virtualAuxUntil[2] = millis() + 120; return; }
  if(line == "AUX4") { g_virtualAuxUntil[3] = millis() + 120; return; }
  if(line == "AUX5") { g_virtualAuxUntil[4] = millis() + 120; return; }
  if(line == "PING") {
    udp.beginPacket(udp.remoteIP(), udp.remotePort());
    udp.print("PONG");
    udp.endPacket();
    return;
  }
  if(line.startsWith("DSP1|")) {
    srvrOnline = true;
    g_lastSrvrRxMs = millis();
    g_lastSrvrDisplayMs = millis();
    g_latestDisplayPacket = line;
    g_latestDisplayPacket.replace("DSP1|", "HMI1|");
    // v26.08.31.10: store latest SRVR display packet only. The UART
    // forward is rate-limited in loop() so CTRL-TS is not flooded and the
    // left-side LVGL elements do not flicker from repeated redraw pressure.
  }
}

static void pollButtonsAndUpdateLatches(uint16_t &flags_out)
{
  // EdgeBox CTRL: only DI0 E-stop is physical; AUX1..AUX5 are CTRL-TS touch events.
  flags_out = 0;
  const uint32_t now = millis();

  const int estop_raw = digitalRead(CTRL_ESTOP_PIN);
  const bool estop_active = (estop_raw != CTRL_ESTOP_HEALTHY_LEVEL);
  const bool hmi_safety = !hmiLinkConnected();
  if(estop_active || hmi_safety) flags_out |= FLAG_ESTOP_PRESSED;

  if(now < g_virtualAuxUntil[0]) flags_out |= FLAG_AUX1;
  if(now < g_virtualAuxUntil[1]) flags_out |= FLAG_AUX2;
  if(now < g_virtualAuxUntil[2]) flags_out |= FLAG_AUX3;
  if(now < g_virtualAuxUntil[3]) flags_out |= FLAG_AUX4;
  if(now < g_virtualAuxUntil[4]) flags_out |= FLAG_AUX5;
}

static void handleHmiEventLine(String line)
{
  line.trim();
  if(!line.length()) return;
  g_lastHmiRxMs = millis();
  if(line == "AUX1") g_virtualAuxUntil[0] = millis() + 120;
  else if(line == "AUX2") g_virtualAuxUntil[1] = millis() + 120;
  else if(line == "AUX3") g_virtualAuxUntil[2] = millis() + 120;
  else if(line == "AUX4") g_virtualAuxUntil[3] = millis() + 120;
  else if(line == "AUX5") g_virtualAuxUntil[4] = millis() + 120;
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

static bool hmiSendText(const String &line)
{
  if(!g_hmiCompatible || !line.length()) return false;
  return HVP2PRS485::sendText(HMI, HVP2PRS485::TEXT, g_hmiSeq++, line);
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
  HVP2PRS485::sendText(HMI, HVP2PRS485::FW_BEGIN, g_hmiFwSeq, meta);
  g_hmiFwState = HMI_FW_WAIT_READY;
  g_hmiFwLastTxMs = millis();
  Serial.printf("[HMI FW] FW_BEGIN %s size=%u%s\n", HV_CTRL_TS_REQUIRED_VERSION, (unsigned)HV_CTRL_TS_IMAGE_SIZE, retry?" retry":"");
}

static void hmiFwSendBlock(bool retry=false){
  if(g_hmiFwOffset >= HV_CTRL_TS_IMAGE_SIZE){
    if(!retry) g_hmiFwSeq = g_hmiSeq++;
    String end = String("size=") + String((unsigned long)HV_CTRL_TS_IMAGE_SIZE) + "|sha256=" + HV_CTRL_TS_REQUIRED_SHA256;
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
  HVP2PRS485::sendFrame(HMI, HVP2PRS485::FW_BLOCK, g_hmiFwSeq, payload, uint16_t(chunk+4));
  g_hmiFwLastBlockLen = chunk;
  g_hmiFwState = HMI_FW_WAIT_BLOCK_ACK;
  g_hmiFwLastTxMs = millis();
}

static void hmiFwSendEnd(bool retry=false){
  if(!retry) g_hmiFwSeq = g_hmiSeq++;
  String end = String("size=") + String((unsigned long)HV_CTRL_TS_IMAGE_SIZE) + "|sha256=" + HV_CTRL_TS_REQUIRED_SHA256;
  HVP2PRS485::sendText(HMI, HVP2PRS485::FW_END, g_hmiFwSeq, end);
  g_hmiFwState = HMI_FW_WAIT_RESULT;
  g_hmiFwLastTxMs = millis();
  Serial.println("[HMI FW] FW_END sent; waiting for inactive-partition verification");
}

static void hmiFwSendReboot(bool retry=false){
  if(!retry) g_hmiFwSeq = g_hmiSeq++;
  HVP2PRS485::sendText(HMI, HVP2PRS485::REBOOT, g_hmiFwSeq, "apply=1");
  g_hmiFwState = HMI_FW_WAIT_REBOOT_ACK;
  g_hmiFwLastTxMs = millis();
}

static void hmiFwStart(){
  if(hmiFwActive()) return;
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
  if(g_hmiFwState == HMI_FW_WAIT_REBOOT_ACK && frame.type == HVP2PRS485::ACK){
    Serial.println("[HMI FW] reboot acknowledged; waiting for new HELLO identity");
    hmiFwReset(nullptr);
    g_lastHmiHelloTxMs = 0;
    return true;
  }
  return false;
}

static void hmiFwServiceTimeout(){
  if(!hmiFwActive()) return;
  const uint32_t now=millis();
  if((now-g_hmiFwLastTxMs) < HMI_FW_REPLY_TIMEOUT_MS) return;
  if(++g_hmiFwRetries > HMI_FW_MAX_RETRIES){ hmiFwReset("RS485 firmware update timed out"); return; }
  Serial.printf("[HMI FW] response timeout; retry %u/%u\n",g_hmiFwRetries,HMI_FW_MAX_RETRIES);
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
  return true;
}

static void handleHmiFrame(const HVP2PRS485::Frame &frame)
{
  g_lastHmiRxMs = millis();
  if(hmiFwHandleFrame(frame)) return;
  if(frame.type == HVP2PRS485::HELLO_RESP) {
    String line = HVP2PRS485::payloadString(frame);
    g_hmiReportedHw = hvGetPipeField(line, "hw");
    g_hmiReportedVersion = hvGetPipeField(line, "version");
    g_hmiReportedHash = hvGetPipeField(line, "hash");
    String pv = hvGetPipeField(line, "proto");
    g_hmiReportedProto = (uint8_t)pv.toInt();
    bool match = hmiIdentityMatches();
    if(match && hmiFwActive()) hmiFwReset("updated CTRL-TS identity confirmed");
    if(match && !g_hmiCompatible) {
      g_hmiCompatible = true;
      Serial.printf("[HMI] Compatible CTRL-TS %s proto=%u hash=%s\n", g_hmiReportedVersion.c_str(), unsigned(g_hmiReportedProto), g_hmiReportedHash.c_str());
      HVP2PRS485::sendText(HMI, HVP2PRS485::COMPATIBLE, g_hmiSeq++, String("version=") + HV_CTRL_TS_REQUIRED_VERSION + "|hash=" + HV_CTRL_TS_REQUIRED_SHA256);
      sendHmiLayout();
      sendNetworkConfigToHmi();
    } else if(!match) {
      g_hmiCompatible = false;
      Serial.printf("[HMI] INCOMPATIBLE hw=%s proto=%u version=%s hash=%s; required=%s\n",
                    g_hmiReportedHw.c_str(), unsigned(g_hmiReportedProto), g_hmiReportedVersion.c_str(),
                    g_hmiReportedHash.c_str(), HV_CTRL_TS_REQUIRED_VERSION);
      if(!hmiTransportCompatible()) {
        Serial.println("[HMI] Automatic update BLOCKED: peer hardware/protocol is not the approved CTRL-TS target.");
      } else if(HV_CTRL_TS_IMAGE_AVAILABLE) {
        Serial.println("[HMI] Approved target detected and identity differs; starting automatic RS485 CTRL-TS update.");
        hmiFwStart();
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
    handleHmiEventLine(HVP2PRS485::payloadString(frame));
    return;
  }
  if(frame.type == HVP2PRS485::ERROR_MSG) {
    Serial.printf("[HMI] CTRL-TS error: %s\n", HVP2PRS485::payloadString(frame).c_str());
    g_hmiCompatible = false;
  }
}

static void handleHmiRx()
{
  while(HMI.available()) {
    if(g_hmiParser.feed((uint8_t)HMI.read(), g_hmiRxFrame)) handleHmiFrame(g_hmiRxFrame);
  }

  const uint32_t now = millis();
  hmiFwServiceTimeout();
  if(hmiFwActive()) {
    // Firmware transfer owns the half-duplex bus until verification/reboot.
  } else if(!g_hmiCompatible) {
    if((now - g_lastHmiHelloTxMs) >= 500) {
      g_lastHmiHelloTxMs = now;
      String req = String("required=") + HV_CTRL_TS_REQUIRED_VERSION + "|proto=" + String(HVP2PRS485::PROTOCOL_VERSION);
      HVP2PRS485::sendText(HMI, HVP2PRS485::HELLO_REQ, g_hmiSeq++, req);
    }
  } else if((now - g_lastHmiPollTxMs) >= 50) {
    g_lastHmiPollTxMs = now;
    HVP2PRS485::sendFrame(HMI, HVP2PRS485::POLL, g_hmiSeq++);
  }

  if(!hmiFwActive() && g_lastHmiRxMs && (now - g_lastHmiRxMs) > HMI_LINK_TIMEOUT_MS) {
    if(g_hmiCompatible) Serial.println("[HMI] RS485 link timeout - compatibility/safety gate dropped");
    g_hmiCompatible = false;
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

  HMI.begin(HMI_BAUD, SERIAL_8N1, HMI_UART_RX, HMI_UART_TX);
  HMI.setPins(HMI_UART_RX, HMI_UART_TX, -1, HMI_UART_RTS);
  if(!HMI.setMode(UART_MODE_RS485_HALF_DUPLEX)) Serial.println("[HMI] ERROR setting EdgeBox RS485 half-duplex mode");
  Serial.printf("[HMI] EdgeBox isolated RS485 RX=%d TX=%d RTS=%d @ %d\n", HMI_UART_RX, HMI_UART_TX, HMI_UART_RTS, HMI_BAUD);

  pinMode(CTRL_ESTOP_PIN, INPUT);
  Serial.printf("[IO] EdgeBox DI0 GPIO%d: 24V NC loop HIGH=healthy, LOW/open=E-Stop\n", CTRL_ESTOP_PIN);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  delay(50);
  scanI2CBus();

  Serial.println("[IO] AUX1..AUX5 touchscreen-only; no physical AUX GPIO module");

  if(detectSgm58031()) {
    Serial.println("[JOY] AI0 ready. Re-run SRVR Set Left / Set Centre / Set Right after EdgeBox migration.");
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
    float axis = readJoystickAxis();
    uint16_t flags = 0;
    pollButtonsAndUpdateLatches(flags);
    if(!g_ads_inited) flags |= FLAG_ADS1115_FAULT;
    sendControl(axis, flags);
  }

  if((now - g_lastSrvrDisplayMs) > SRVR_DISPLAY_TIMEOUT_MS) {
    srvrOnline = false;
    g_latestDisplayPacket = "";
  }

  // v26.08.31.10: do not resend UIL1 layout on a timer.
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
    if(changed || keepalive_due) {
      lastDisplayForward = now;
      g_lastHmiDisplayKeepaliveMs = now;
      g_lastForwardedDisplayPacket = nextDisplay;
      forwardDisplayPacketToHmi(nextDisplay);
    } else {
      // Event-driven HMI path: unchanged packets are not re-sent on every CTRL
      // loop pass. This keeps the touchscreen/LVGL side stable during 10-12 hour days.
      lastDisplayForward = now;
    }
  }

  delay(5);
}
