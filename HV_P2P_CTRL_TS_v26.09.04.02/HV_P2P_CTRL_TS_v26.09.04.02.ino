#include <Arduino.h>
#include <math.h>
#include <lvgl.h>
#include "HV_P2P_RS485_Frame.h"
#include <Waveshare_ST7262_LVGL.h>
#include <ESP_IOExpander_Library.h>
#include <SPI.h>
#include <SD.h>
#include <JPEGDEC.h>
#include <Update.h>
#include <Preferences.h>
#include <mbedtls/sha256.h>
#include <esp_ota_ops.h>

#define CTRL_TS_SEMVER "v26.09.04.02"
#define CTRL_TS_VERSION "HV P2P CTRL-TS " CTRL_TS_SEMVER
#define CTRL_TS_HW_ID "WS-ESP32S3-7"
#define HMI_BAUD 115200
// Waveshare ESP32-S3-Touch-LCD-7 onboard automatic-direction RS485.
#define HMI_UART_RX 15
#define HMI_UART_TX 16
#define HMI_TIMEOUT_MS 30000
#define AUX_LATCH_MS 180
#define AUX_PHYSICAL_DEBOUNCE_MS 250
#define AUX_COUNT 5

static HardwareSerial HMI(1);
static HVP2PRS485::Parser g_rs485Parser;
static HVP2PRS485::Frame g_rs485RxFrame;
static uint16_t g_rs485Seq = 1;
static bool g_ctrl_fw_compatible = false;
static String g_event_queue[8];
static uint8_t g_event_head = 0, g_event_tail = 0;

// Automatic CTRL-hosted CTRL-TS firmware receiver. The currently running
// application remains untouched unless FW_END validates successfully; an
// interrupted transfer therefore boots the existing image again.
static bool g_fw_update_active = false;
static size_t g_fw_expected_size = 0;
static size_t g_fw_received = 0;
static String g_fw_expected_sha;
static String g_fw_expected_version;
static mbedtls_sha256_context g_fw_sha_ctx;
static bool g_fw_sha_active = false;
static String g_fw_image_hash = "bootstrap";
// Retain the final verified result until reboot so a lost FW_RESULT can be
// answered idempotently when CTRL retries FW_END on the half-duplex link.
static bool g_fw_finalized = false;
static size_t g_fw_final_size = 0;
static String g_fw_final_sha;
static uint32_t g_fw_last_rx_ms = 0;
static uint32_t g_fw_reboot_due_ms = 0;
static Preferences g_fw_prefs;
static const uint32_t FW_RX_TIMEOUT_MS = 5000;
static const size_t FW_MAX_IMAGE_SIZE = 0x380000; // matches the conservative app0/app1 slot size
// ESP32 Arduino Update.write() takes a mutable buffer even though it does not
// need to modify the received block. Keep the parsed RS485 frame const and copy
// only the OTA data bytes into this dedicated scratch buffer before writing.
static uint8_t g_fw_write_buf[HVP2PRS485::MAX_PAYLOAD - 4];
// LVGL 8.3 provides 10%% opacity steps only. Preserve the approved 35%% ramp
// appearance with an explicit 8-bit opacity value (round(0.35 * 255) = 89).
static constexpr lv_opa_t HV_OPA_35 = (lv_opa_t)89;


// Boot splash support. Put splash.jpg in the root of the Waveshare microSD card.
// WS-27078 is the ESP32-S3-Touch-LCD-7: native 800x480 panel.
static const char* SPLASH_FILENAME = "/splash.jpg";
static const uint32_t SPLASH_HOLD_MS = 10000;
static const int SPLASH_CANVAS_W = 800;
static const int SPLASH_CANVAS_H = 480;
static const int SPLASH_STATUS_H = 42;
static const int SD_MOSI = 11;
static const int SD_CLK  = 12;
static const int SD_MISO = 13;
#ifndef SD_CS
#define SD_CS 4
#endif
static const int SD_SS   = -1;  // Waveshare TF CS is CH422G EXIO4 / SD_CS
extern ESP_IOExpander *expander;
static lv_obj_t *boot_scr = nullptr;
static lv_obj_t *boot_status_bar = nullptr;
static lv_obj_t *boot_status_lbl = nullptr;
static lv_obj_t *boot_canvas = nullptr;
static lv_color_t *boot_canvas_buf = nullptr;
static int boot_w = 0;
static int boot_h = 0;
static JPEGDEC boot_jpeg;
static bool g_boot_ctrl_confirmed = false;
static bool g_boot_srvr_confirmed = false;
static uint32_t g_boot_last_ping_ms = 0;
static uint32_t g_boot_last_layout_req_ms = 0;
static String g_boot_rx_line;
static String g_boot_status_cache;
static String g_pending_boot_hmi_line;


// -------------------- Framed RS485 thin-HMI link --------------------
// Waveshare is intentionally not an Ethernet node in this architecture.
// It is flashed once with this generic LVGL runtime, then receives layout/state
// from the EdgeBox CTRL over framed RS485 and returns queued touch events only when polled.
static bool g_uart_ok = false;
static bool g_ui_ready = false;
static uint32_t g_last_screen_keepalive_ms = 0;
static String g_rx_line;

static lv_obj_t *lbl_to_near,*lbl_to_far,*lbl_speed_combo,*lbl_touch_debug,*current_marker,*travel_near_marker,*travel_ref_marker,*travel_far_marker,*aux_btn[AUX_COUNT],*aux_state[AUX_COUNT];
static lv_obj_t *lbl_title,*lbl_subtitle;
static lv_obj_t *travel_panel,*travel_near_lbl,*travel_ref_lbl,*travel_far_lbl,*ramp_l,*ramp_r;
static lv_obj_t *preset_line[12], *preset_lbl[12], *preset_tri[12];
static lv_obj_t *pill_ctrl,*pill_srvr,*pill_w1p,*lbl_ctrl,*lbl_srvr,*lbl_w1p;
static lv_obj_t *dot_ctrl,*dot_w1p,*lbl_ctrl_ip,*lbl_w1p_ip;
static lv_obj_t *pill_estop,*lbl_estop;
static lv_obj_t *middle_panel,*cell_to_near,*cell_speed,*cell_to_far;
static lv_obj_t *lbl_max_speed,*lbl_current_kmh,*lbl_max_kmh,*lbl_current_pos;
static lv_obj_t *lbl_drive_mode,*lbl_accel_mode,*lbl_battery_mode,*lbl_srvr_time,*lbl_uptime,*lbl_near_value,*lbl_far_value;
static lv_obj_t *aux_text_lbl[AUX_COUNT];
static int selected_aux=-1,confirmed_aux=-1;
static uint32_t clear_confirm_at=0,last_hb=0,last_hmi_rx=0;
static uint16_t g_last_flags=0;
static bool g_ctrl_ok=false,g_srvr_ok=false,g_w1p_ok=false,g_estop_active=false;
static int g_w1p_health=0; // 0=Error/node unreachable, 1=OK, 2=Fault/node alive with RS485/drive fault
static String g_estop_source = "SRVR";
static String g_status_text = "CTRL Link Loss";
static int g_status_level = 2;  // 0=green, 1=yellow/service, 2=red/safety
static String g_hmi_line;
static String g_last_applied_hmi_line;

static float g_pos=0.0f, g_near=0.0f, g_ref=50.0f, g_far=100.0f, g_to_near=0.0f, g_to_far=0.0f;
static bool g_ref_visible = true;
static float g_speed_mps=0.0f, g_speed_kmh=0.0f, g_max_mps=0.0f, g_max_kmh=0.0f;
static float g_ramp_near=0.0f, g_ramp_far=0.0f;
static String g_mode="Mode 1";
static String g_drive_mode="Mode A";
static String g_accel_mode="Speed";
static String g_battery_mode="Off";
static String g_srvr_time="---- -- --  --:--:--";
static String g_uptime="00:00:00";
static String g_ctrl_ip="172.20.1.101";
static String g_w1p_ip="172.20.1.102";
static String g_aux_labels[AUX_COUNT] = {"Battery Change | Off","Drive Mode | Mode A","Accel Mode | Speed","Goto Ref","AUX 5"};
static String g_preset_names[12] = {"","","","","","","","","","","",""};
static float g_preset_pos[12] = {0,0,0,0,0,0,0,0,0,0,0,0};
static bool g_preset_visible[12] = {false,false,false,false,false,false,false,false,false,false,false,false};
static int g_preset_count = 12;

static const int BAR_LIMIT_LEFT = 58;
static const int BAR_LIMIT_RIGHT = 722;
static const int BAR_LIMIT_WIDTH = BAR_LIMIT_RIGHT - BAR_LIMIT_LEFT;
static uint32_t g_last_aux_physical_ms[AUX_COUNT] = {0,0,0,0,0};
static uint32_t g_last_aux_touch_ms[AUX_COUNT] = {0,0,0,0,0};
static uint32_t g_aux_suppress_until_ms[AUX_COUNT] = {0,0,0,0,0};
static uint32_t g_selected_aux_ms = 0;
static const uint32_t AUX_PENDING_TIMEOUT_MS = 3000;
static const uint32_t AUX_TOUCH_CONFIRM_GAP_MS = 250;
static int g_current_marker_x = -1;
static String g_last_mode = "";
static String g_last_preset_names_field = "";
static String g_last_preset_pos_field = "";
static String g_last_preset_abs_field = "";
static String g_last_preset_vis_field = "";
static int g_aux_visual_state[AUX_COUNT] = {-1,-1,-1,-1,-1};
static int g_last_status_visual[3] = {-1,-1,-1};
static int g_last_estop_visual = -1;
static String g_last_estop_source = "";
static String g_last_status_text = "";
static uint32_t g_last_middle_bg = 0xffffffff;
static uint32_t g_last_middle_border = 0xffffffff;
static float g_last_ref_draw = -999999.0f;
static float g_last_near_draw = -999999.0f;
static float g_last_far_draw = -999999.0f;
static float g_last_ramp_near_draw = -999999.0f;
static float g_last_ramp_far_draw = -999999.0f;

// -------------------- CTRL-TS Settings page --------------------
// Safe v26.09.04.02 approach: no backlight/brightness writes. This page only
// edits CTRL network settings over UART and therefore should preserve the known
// Keep the proven splash/boot path; do not write to the backlight controller.
static lv_obj_t *settings_overlay = nullptr;
static lv_obj_t *settings_btn = nullptr;
static lv_obj_t *lbl_settings_value[4] = {nullptr,nullptr,nullptr,nullptr};
static lv_obj_t *settings_row_panel[4] = {nullptr,nullptr,nullptr,nullptr};
static lv_obj_t *lbl_settings_note = nullptr;
static lv_obj_t *lbl_settings_selected = nullptr;
static bool g_settings_visible = false;
static bool g_settings_dirty = false;
static int g_settings_selected_field = 0;
static int g_settings_selected_octet = 0;
static uint32_t g_settings_reset_due_ms = 0;
static String g_cfg_srvr_ip = "172.20.1.100";
static String g_cfg_ctrl_ip = "172.20.1.101";
static String g_cfg_subnet  = "255.255.0.0";
static String g_cfg_gateway = "172.20.1.1";
static String g_edit_srvr_ip = "172.20.1.100";
static String g_edit_ctrl_ip = "172.20.1.101";
static String g_edit_subnet  = "255.255.0.0";
static String g_edit_gateway = "172.20.1.1";

enum SettingsButtonId {
  SET_BTN_OPEN = 1,
  SET_BTN_CANCEL = 2,
  SET_BTN_SELECT_SRVR = 10,
  SET_BTN_SELECT_CTRL = 11,
  SET_BTN_SELECT_SUBNET = 12,
  SET_BTN_SELECT_GATEWAY = 13,
  SET_BTN_OCTET_PREV = 20,
  SET_BTN_OCTET_NEXT = 21,
  SET_BTN_OCTET_DOWN = 22,
  SET_BTN_OCTET_UP = 23,
  SET_BTN_APPLY_RESET = 24,
};

static void force_screen_refresh(){
  // Keep the LVGL framebuffer/render task nudged so the screen never remains blank
  // after local boot, even if CTRL UART/layout data is missing or malformed.
  if(!g_ui_ready) return;
  lv_obj_t *scr = lv_scr_act();
  if(scr) lv_obj_invalidate(scr);
#if defined(LV_VERSION_MAJOR) && (LV_VERSION_MAJOR >= 8)
  lv_refr_now(NULL);
#endif
}

static void screen_keepalive(){
  // v26.09.04.02: no periodic full-screen or left-strip invalidation or brightness writes.
  // The Waveshare/LVGL port refreshes changed objects itself; forcing a full
  // screen refresh every second caused the visible 1-second flicker/glitch.
  if(!g_ui_ready) return;
}

static void set_label_text_if_changed(lv_obj_t *lbl, const char *txt){
  if(!lbl || !txt) return;
  const char *cur = lv_label_get_text(lbl);
  if(cur && strcmp(cur, txt) == 0) return;
  lv_label_set_text(lbl, txt);
  // v26.09.04.02: label-only invalidation. Parent/full-strip invalidation can
  // cause the known vertical tear on the left AUX area of this panel.
  lv_obj_invalidate(lbl);
}

static String display_aux_label(String s){
  // HMI packets use '|' as a field separator, so SRVR safely sends ' / ' inside
  // labels. Convert it back for the touchscreen so AUX tiles match SRVR buttons.
  s.replace(" / ", " | ");
  s.replace("Traditional", "Power");
  s.replace("Dynamic", "Speed");
  s.replace("Normal", "Power");
  return s;
}

static String aux_action_part(const String &label){
  int cut = label.indexOf(" | ");
  if(cut < 0) return label;
  return label.substring(0, cut);
}

static String aux_value_part(const String &label){
  int cut = label.indexOf(" | ");
  if(cut < 0) return "Ready";
  String out = label.substring(cut + 3);
  return out.length() ? out : "Ready";
}

static void refresh_aux_text(int i){
  if(i < 0 || i >= AUX_COUNT) return;
  String action = aux_action_part(g_aux_labels[i]);
  String value = aux_value_part(g_aux_labels[i]);
  if(aux_text_lbl[i]) set_label_text_if_changed(aux_text_lbl[i], action.c_str());
  if(aux_state[i] && selected_aux != i && confirmed_aux != i) set_label_text_if_changed(aux_state[i], value.c_str());
}

static void invalidate_left_motion_strip(){
  // Targeted redraw for the left-side AUX / To Near / travel-scale area.
  // This avoids the old full-screen flicker while clearing the slight left-column tearing
  // seen on the Waveshare panel after repeated AUX/status updates.
  if(aux_btn[0]) lv_obj_invalidate(aux_btn[0]);
  if(aux_btn[1]) lv_obj_invalidate(aux_btn[1]);
  if(cell_to_near) lv_obj_invalidate(cell_to_near);
  if(lbl_to_near) lv_obj_invalidate(lbl_to_near);
  if(travel_panel) lv_obj_invalidate(travel_panel);
  if(travel_near_marker) lv_obj_invalidate(travel_near_marker);
  if(current_marker) lv_obj_invalidate(current_marker);
}


static void boot_set_status(const char *txt){
  String next = String(txt ? txt : "");
  if(next == g_boot_status_cache) return;
  g_boot_status_cache = next;
  if(!boot_status_lbl) return;
  lvgl_port_lock(-1);
  lv_label_set_text(boot_status_lbl, next.c_str());
  if(boot_status_bar) lv_obj_move_foreground(boot_status_bar);
  lv_obj_invalidate(boot_status_lbl);
  lvgl_port_unlock();
  Serial.print("[BOOT] "); Serial.println(next);
}

static String boot_get_field(const String &line, const char *key){
  String token = String("|") + key + "=";
  int start = line.indexOf(token);
  if(start < 0){
    if(line.startsWith(String(key) + "=")) start = -1;
    else return "";
  }
  if(start >= 0) start += token.length();
  else start = strlen(key) + 1;
  int end = line.indexOf('|', start);
  if(end < 0) end = line.length();
  return line.substring(start, end);
}

static bool queue_hmi_event(const String &line){
  uint8_t next = uint8_t((g_event_head + 1) % 8);
  if(next == g_event_tail) return false;
  g_event_queue[g_event_head] = line;
  g_event_head = next;
  return true;
}
static String pop_hmi_event(){
  if(g_event_tail == g_event_head) return String();
  String out = g_event_queue[g_event_tail];
  g_event_queue[g_event_tail] = "";
  g_event_tail = uint8_t((g_event_tail + 1) % 8);
  return out;
}
static String fw_meta_key(const char *prefix, const char *partitionLabel){
  String key = String(prefix) + "_" + String(partitionLabel ? partitionLabel : "");
  // ESP32 NVS keys are limited to 15 characters. Our custom OTA labels are app0/app1.
  if(key.length() > 15) return String();
  return key;
}

static void load_fw_identity(){
  g_fw_image_hash = "bootstrap";
  const esp_partition_t *running = esp_ota_get_running_partition();
  if(!running) return;
  String verKey = fw_meta_key("ver", running->label);
  String shaKey = fw_meta_key("sha", running->label);
  String okKey  = fw_meta_key("ok",  running->label);
  if(!verKey.length() || !shaKey.length() || !okKey.length()) return;
  if(!g_fw_prefs.begin("hvfw", true)) return;
  String storedVersion = g_fw_prefs.getString(verKey.c_str(), "");
  String storedHash = g_fw_prefs.getString(shaKey.c_str(), "");
  String committedHash = g_fw_prefs.getString(okKey.c_str(), "");
  g_fw_prefs.end();
  // Identity is trusted only for the partition that is actually running and only
  // after the commit marker was written last. This prevents a partial NVS write
  // from making an older app falsely claim a newly staged hash.
  if(storedVersion == CTRL_TS_SEMVER && storedHash.length() == 64 && committedHash == storedHash)
    g_fw_image_hash = storedHash;
}

static bool save_fw_identity(const String &version, const String &sha){
  if(version.length() < 2 || sha.length() != 64) return false;
  // Update.end(true) selects the new inactive OTA partition as the next boot target.
  // Store identity against that partition, not globally. The commit key is removed
  // first and written LAST, giving the three-field metadata update transactional
  // semantics even if power or NVS write failure interrupts this routine.
  const esp_partition_t *target = esp_ota_get_boot_partition();
  if(!target) return false;
  String verKey = fw_meta_key("ver", target->label);
  String shaKey = fw_meta_key("sha", target->label);
  String okKey  = fw_meta_key("ok",  target->label);
  if(!verKey.length() || !shaKey.length() || !okKey.length()) return false;
  if(!g_fw_prefs.begin("hvfw", false)) return false;
  g_fw_prefs.remove(okKey.c_str());
  bool ok1 = g_fw_prefs.putString(verKey.c_str(), version) > 0;
  bool ok2 = g_fw_prefs.putString(shaKey.c_str(), sha) > 0;
  bool ok3 = ok1 && ok2 && (g_fw_prefs.putString(okKey.c_str(), sha) > 0);
  bool verify = ok3 && g_fw_prefs.getString(verKey.c_str(), "") == version
                     && g_fw_prefs.getString(shaKey.c_str(), "") == sha
                     && g_fw_prefs.getString(okKey.c_str(), "") == sha;
  g_fw_prefs.end();
  // Do NOT change g_fw_image_hash while the old application is still running.
  // The transferred hash belongs to the newly selected OTA partition. The new
  // application loads it only after reboot, from metadata keyed to its own running
  // partition and protected by the commit marker above.
  return verify;
}

static String fw_identity_line(){
  return String("hw=") + CTRL_TS_HW_ID + "|proto=" + String(HVP2PRS485::PROTOCOL_VERSION) +
         "|version=" + String(CTRL_TS_SEMVER) + "|hash=" + g_fw_image_hash;
}

static bool boot_get_bool(const String &line, const char *key, bool def){
  String v = boot_get_field(line, key);
  if(!v.length()) return def;
  return (v == "1" || v == "true" || v == "TRUE");
}

static void boot_process_line(String line){
  line.trim();
  if(!line.length()) return;
  if(line.startsWith("DSP1|")) line.replace("DSP1|", "HMI1|");
  if(line.startsWith("HMI1|")){
    bool has_ctrl = line.indexOf("|ctrl=") >= 0;
    bool has_srvr = line.indexOf("|srvr=") >= 0;
    if(has_ctrl || has_srvr){
      g_pending_boot_hmi_line = line;
      g_boot_ctrl_confirmed = boot_get_bool(line, "ctrl", g_boot_ctrl_confirmed);
      g_boot_srvr_confirmed = boot_get_bool(line, "srvr", g_boot_srvr_confirmed);
      last_hmi_rx = millis();
      if(g_boot_ctrl_confirmed && g_boot_srvr_confirmed) boot_set_status("CTRL OK | SRVR OK | holding splash");
      else if(g_boot_ctrl_confirmed) boot_set_status("CTRL OK | waiting for SRVR");
      else boot_set_status("Waiting for CTRL");
    }
  } else if(line == "PONG"){
    g_boot_ctrl_confirmed = true;
    last_hmi_rx = millis();
    if(!g_boot_srvr_confirmed) boot_set_status("CTRL OK | waiting for SRVR");
  }
}

static void process_rs485_frame(const HVP2PRS485::Frame &frame, bool boot_phase);

static void poll_rs485(bool boot_phase){
  while(HMI.available()){
    if(g_rs485Parser.feed((uint8_t)HMI.read(), g_rs485RxFrame)) process_rs485_frame(g_rs485RxFrame, boot_phase);
  }
}

static void boot_service_uart(){
  // RS485 is deterministic master/slave: CTRL-TS never initiates traffic.
  // CTRL sends HELLO/TEXT/POLL frames; this routine only receives/responds.
  poll_rs485(true);
}

static bool boot_prepare_splash_canvas(){
  boot_w = SPLASH_CANVAS_W;
  boot_h = SPLASH_CANVAS_H;
  if(boot_canvas_buf){
    free(boot_canvas_buf);
    boot_canvas_buf = nullptr;
  }
  boot_canvas_buf = (lv_color_t*)ps_malloc((size_t)boot_w * (size_t)boot_h * sizeof(lv_color_t));
  if(!boot_canvas_buf){
    Serial.println("[BOOT] splash canvas allocation failed");
    return false;
  }
  memset(boot_canvas_buf, 0, (size_t)boot_w * (size_t)boot_h * sizeof(lv_color_t));
  lvgl_port_lock(-1);
  boot_canvas = lv_canvas_create(boot_scr);
  lv_canvas_set_buffer(boot_canvas, boot_canvas_buf, boot_w, boot_h, LV_IMG_CF_TRUE_COLOR);
  lv_obj_align(boot_canvas, LV_ALIGN_CENTER, 0, 0);
  lvgl_port_unlock();
  Serial.printf("[BOOT] splash canvas ready %dx%d\n", boot_w, boot_h);
  return true;
}

static int boot_jpeg_draw(JPEGDRAW *pDraw){
  if(!boot_canvas_buf || boot_w <= 0 || boot_h <= 0) return 0;
  int y0 = pDraw->y;
  int x0 = pDraw->x;
  for(int y=0; y<pDraw->iHeight; y++){
    int dy = y0 + y;
    if(dy < 0 || dy >= boot_h) continue;
    int sx = 0;
    int dx = x0;
    int w = pDraw->iWidth;
    if(dx < 0){ sx = -dx; w -= sx; dx = 0; }
    if(dx + w > boot_w) w = boot_w - dx;
    if(w <= 0) continue;
    memcpy(&boot_canvas_buf[dy * boot_w + dx], &pDraw->pPixels[y * pDraw->iWidth + sx], w * sizeof(lv_color_t));
  }
  return 1;
}

static bool boot_init_sd(){
  if(!expander){ Serial.println("[BOOT] expander not ready"); return false; }
  expander->digitalWrite(SD_CS, LOW);
  SPI.setHwCs(false);
  SPI.begin(SD_CLK, SD_MISO, SD_MOSI, SD_SS);
  if(!SD.begin(SD_SS, SPI)){
    Serial.println("[BOOT] SD.begin failed");
    return false;
  }
  if(SD.cardType() == CARD_NONE){
    Serial.println("[BOOT] no microSD card detected");
    return false;
  }
  return true;
}

static bool boot_load_splash_jpg(){
  if(!boot_canvas_buf || !boot_canvas){
    if(!boot_prepare_splash_canvas()) return false;
  }

  File jf = SD.open(SPLASH_FILENAME, FILE_READ);
  if(!jf){
    Serial.println("[BOOT] /splash.jpg not found");
    return false;
  }
  if(!boot_jpeg.open(jf, boot_jpeg_draw)){
    Serial.print("[BOOT] JPEG open failed, error="); Serial.println(boot_jpeg.getLastError());
    jf.close();
    return false;
  }
  Serial.printf("[BOOT] JPEG opened %dx%d, target canvas %dx%d\n", boot_jpeg.getWidth(), boot_jpeg.getHeight(), boot_w, boot_h);
  boot_jpeg.setPixelType(RGB565_LITTLE_ENDIAN);
  int ok = boot_jpeg.decode(0, 0, 0);
  boot_jpeg.close();
  jf.close();
  lvgl_port_lock(-1);
  if(boot_canvas) lv_obj_invalidate(boot_canvas);
  if(boot_status_bar) lv_obj_move_foreground(boot_status_bar);
#if defined(LV_VERSION_MAJOR) && (LV_VERSION_MAJOR >= 8)
  lv_refr_now(NULL);
#endif
  lvgl_port_unlock();
  Serial.printf("[BOOT] JPEG decode result=%d\n", ok);
  return ok == 1;
}

static void show_boot_splash(){
  uint32_t t0 = millis();
  int disp_w = lv_disp_get_hor_res(NULL);
  int disp_h = lv_disp_get_ver_res(NULL);
  if(disp_w <= 0) disp_w = SPLASH_CANVAS_W;
  if(disp_h <= 0) disp_h = SPLASH_CANVAS_H;

  lvgl_port_lock(-1);
  boot_scr = lv_obj_create(NULL);
  lv_obj_clear_flag(boot_scr, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_style_bg_color(boot_scr, lv_color_hex(0x06101c), 0);
  lv_obj_set_style_bg_opa(boot_scr, LV_OPA_COVER, 0);
  lv_scr_load(boot_scr);
  lvgl_port_unlock();

  // Create the splash canvas first, then the bottom status bar, so the status
  // bar is the only overlay on top of /splash.jpg.
  boot_prepare_splash_canvas();

  lvgl_port_lock(-1);
  boot_status_bar = lv_obj_create(boot_scr);
  lv_obj_set_pos(boot_status_bar, 0, disp_h - SPLASH_STATUS_H);
  lv_obj_set_size(boot_status_bar, disp_w, SPLASH_STATUS_H);
  lv_obj_set_style_bg_color(boot_status_bar, lv_color_hex(0x02070d), 0);
  lv_obj_set_style_bg_opa(boot_status_bar, LV_OPA_80, 0);
  lv_obj_set_style_border_width(boot_status_bar, 0, 0);
  lv_obj_set_style_radius(boot_status_bar, 0, 0);
  lv_obj_set_style_pad_all(boot_status_bar, 0, 0);
  lv_obj_clear_flag(boot_status_bar, LV_OBJ_FLAG_SCROLLABLE);

  boot_status_lbl = lv_label_create(boot_status_bar);
  lv_label_set_text(boot_status_lbl, "Booting...");
  lv_obj_set_style_text_font(boot_status_lbl, &lv_font_montserrat_14, 0);
  lv_obj_set_style_text_color(boot_status_lbl, lv_color_hex(0xd8ecff), 0);
  lv_obj_set_width(boot_status_lbl, disp_w);
  lv_obj_set_style_text_align(boot_status_lbl, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_align(boot_status_lbl, LV_ALIGN_CENTER, 0, 0);
  lv_obj_move_foreground(boot_status_bar);
  lvgl_port_unlock();

  boot_set_status("Display initialised | splash target 800x480");
  delay(100);
  boot_set_status("Checking microSD for /splash.jpg");
  bool sd_ok = boot_init_sd();
  if(sd_ok){
    boot_set_status("Loading splash.jpg");
    if(boot_load_splash_jpg()) boot_set_status("splash.jpg loaded | waiting for CTRL");
    else boot_set_status("splash.jpg not found/unsupported | waiting for CTRL");
  } else {
    boot_set_status("microSD not available | waiting for CTRL");
  }

  g_boot_last_ping_ms = 0;
  g_boot_last_layout_req_ms = 0;
  while(true){
    uint32_t now = millis();
    boot_service_uart();
    bool min_hold_done = (now - t0) >= SPLASH_HOLD_MS;
    if(g_boot_ctrl_confirmed && g_boot_srvr_confirmed){
      if(min_hold_done) break;
      uint32_t remain = (SPLASH_HOLD_MS - (now - t0) + 999) / 1000;
      char msg[96];
      snprintf(msg, sizeof(msg), "CTRL OK | SRVR OK | starting in %lus", (unsigned long)remain);
      boot_set_status(msg);
    } else if(g_boot_ctrl_confirmed){
      boot_set_status("CTRL OK | waiting for SRVR");
    } else {
      boot_set_status("Waiting for CTRL");
    }
    delay(50);
  }
  boot_set_status("CTRL OK | SRVR OK | starting interface");
  delay(150);
}

static bool is_valid_hmi_packet(const String &line){
  if(!line.startsWith("HMI1|")) return false;
  if(line.indexOf("|ctrl=") < 0) return false;
  if(line.indexOf("|srvr=") < 0) return false;
  if(line.indexOf("|w1p=") < 0) return false;
  if(line.indexOf("|flags=") < 0) return false;
  if(line.indexOf("|speed_mps=") < 0) return false;
  return true;
}

static lv_obj_t *make_label(lv_obj_t *parent,const char *txt,lv_coord_t x,lv_coord_t y,const lv_font_t *font,lv_color_t color, lv_coord_t w=LV_SIZE_CONTENT){
  lv_obj_t *lbl=lv_label_create(parent);
  lv_label_set_text(lbl,txt); lv_obj_set_pos(lbl,x,y);
  if(w!=LV_SIZE_CONTENT) lv_obj_set_width(lbl,w);
  lv_obj_set_style_text_align(lbl,LV_TEXT_ALIGN_CENTER,0);
  lv_obj_set_style_text_font(lbl,font,0);
  lv_obj_set_style_text_color(lbl,color,0);
  lv_obj_set_style_bg_opa(lbl,LV_OPA_TRANSP,0);
  lv_obj_set_style_border_width(lbl,0,0);
  lv_obj_add_flag(lbl, LV_OBJ_FLAG_EVENT_BUBBLE);
  return lbl;
}
static lv_obj_t *make_panel(lv_obj_t *parent,lv_coord_t x,lv_coord_t y,lv_coord_t w,lv_coord_t h,uint32_t bg,uint32_t border,lv_coord_t radius,lv_opa_t opa=LV_OPA_COVER){
  lv_obj_t *obj=lv_obj_create(parent);
  lv_obj_set_pos(obj,x,y); lv_obj_set_size(obj,w,h);
  lv_obj_set_style_bg_color(obj,lv_color_hex(bg),0); lv_obj_set_style_bg_opa(obj,opa,0);
  lv_obj_set_style_border_color(obj,lv_color_hex(border),0); lv_obj_set_style_border_width(obj,1,0);
  lv_obj_set_style_radius(obj,radius,0); lv_obj_set_style_shadow_width(obj,0,0); lv_obj_set_style_outline_width(obj,0,0);
  lv_obj_set_style_pad_all(obj,0,0); lv_obj_clear_flag(obj,LV_OBJ_FLAG_SCROLLABLE); return obj;
}
static lv_obj_t *make_button(lv_obj_t *parent,lv_coord_t x,lv_coord_t y,lv_coord_t w,lv_coord_t h){
  lv_obj_t *obj=lv_btn_create(parent);
  lv_obj_set_pos(obj,x,y); lv_obj_set_size(obj,w,h);
  lv_obj_set_style_bg_color(obj,lv_color_hex(0x171c20),0); lv_obj_set_style_bg_opa(obj,LV_OPA_COVER,0);
  lv_obj_set_style_border_color(obj,lv_color_hex(0x4a4f52),0); lv_obj_set_style_border_width(obj,1,0);
  lv_obj_set_style_radius(obj,9,0); lv_obj_set_style_shadow_width(obj,0,0); lv_obj_set_style_outline_width(obj,0,0);
  lv_obj_set_style_pad_all(obj,0,0); lv_obj_add_flag(obj, LV_OBJ_FLAG_CLICKABLE); lv_obj_clear_flag(obj,LV_OBJ_FLAG_SCROLLABLE); return obj;
}
static bool mode_is_service(){
  String m = g_mode;
  m.toLowerCase();
  return (m.indexOf("battery change") >= 0) || (m.indexOf("calibration") >= 0) || (m.indexOf("not calibrated") >= 0) || (m.indexOf("un-calibrated") >= 0) || (m.indexOf("uncalibrated") >= 0);
}

static bool aux_label_matches_service(int idx){
  if(idx < 0 || idx >= AUX_COUNT) return false;
  String s = g_aux_labels[idx];
  s.toLowerCase();
  if(g_mode.indexOf("Battery Change") >= 0) return s.indexOf("battery change") >= 0;
  if(g_mode.indexOf("Calibration") >= 0 || g_mode.indexOf("Not Calibrated") >= 0){
    return s.indexOf("start calibration") >= 0 || s.indexOf("set near") >= 0 || s.indexOf("set far") >= 0 || s.indexOf("set ref") >= 0;
  }
  return false;
}

static void clear_nonconfirmed_aux();
static void style_aux(int i,bool selected,bool confirmed);

static void sync_service_aux_visual(){
  // Service/calibration mode is a system state, not an AUX press. AUX tiles must
  // remain Ready until a real touchscreen or physical AUX edge selects one.
  // This prevents Start Calibration appearing pre-pressed as Confirm? at boot.
  if(selected_aux < 0 && confirmed_aux < 0) clear_nonconfirmed_aux();
}

static void style_aux(int i,bool selected,bool confirmed){
  if(i < 0 || i >= AUX_COUNT) return;
  int next_state = confirmed ? 2 : (selected ? 1 : 0);
  if(g_aux_visual_state[i] == next_state) { if(!selected && !confirmed) refresh_aux_text(i); return; }
  g_aux_visual_state[i] = next_state;
  lv_obj_set_style_bg_color(aux_btn[i],lv_color_hex(selected||confirmed?0x1f2b2f:0x171c20),0);
  lv_obj_set_style_border_color(aux_btn[i],lv_color_hex(selected||confirmed?0x26d5ff:0x4a4f52),0);
  if(confirmed) set_label_text_if_changed(aux_state[i],"Confirmed");
  else if(selected) set_label_text_if_changed(aux_state[i],"Confirm?");
  else refresh_aux_text(i);
}
static void clear_nonconfirmed_aux(){
  for(int i=0;i<AUX_COUNT;i++) if(i != confirmed_aux) style_aux(i,false,false);
}

static void cancel_pending_aux(){
  if(selected_aux >= 0){
    style_aux(selected_aux, false, false);
    selected_aux = -1;
    g_selected_aux_ms = 0;
    set_touch_debug("Ready");
  }
}

static void confirm_aux_idx(int idx, bool send_command){
  char msg[40];
  if(idx < 0 || idx >= AUX_COUNT) return;
  uint32_t now_ms = millis();
  if(g_aux_suppress_until_ms[idx] && now_ms < g_aux_suppress_until_ms[idx]) return;
  if(send_command){
    if(now_ms - g_last_aux_touch_ms[idx] < AUX_TOUCH_CONFIRM_GAP_MS) return;
    g_last_aux_touch_ms[idx] = now_ms;
  }
  if(selected_aux != -1 && selected_aux != idx){
    style_aux(selected_aux,false,false);
    selected_aux = -1;
    g_selected_aux_ms = 0;
  }
  if(confirmed_aux == idx && now_ms < clear_confirm_at) return;
  if(selected_aux != idx){
    clear_nonconfirmed_aux();
    selected_aux = idx;
    g_selected_aux_ms = now_ms;
    style_aux(idx,true,false);
    snprintf(msg,sizeof(msg),"AUX %d Confirm?", idx+1);
    set_touch_debug(msg);
    return;
  }
  if((now_ms - g_selected_aux_ms) < AUX_TOUCH_CONFIRM_GAP_MS) return;
  selected_aux = -1;
  g_selected_aux_ms = 0;
  confirmed_aux = idx;
  clear_confirm_at = now_ms + 2000;  // v26.09.04.02: confirmed AUX tile stays lit for 2 seconds
  g_aux_suppress_until_ms[idx] = now_ms + 400;
  style_aux(idx,false,true);
  snprintf(msg,sizeof(msg),"AUX %d Confirmed", idx+1);
  set_touch_debug(msg);
  if(send_command){
    String cmd = String("AUX") + String(idx + 1);
    send_hmi_command(cmd.c_str());
  }
}

static void apply_flags_to_aux(uint16_t flags){
  const uint16_t masks[AUX_COUNT] = {0x0020, 0x0040, 0x0080, 0x0100, 0x0400};
  uint32_t now_ms = millis();
  for(int i=0;i<AUX_COUNT;i++){
    bool was = (g_last_flags & masks[i]) != 0;
    bool now = (flags & masks[i]) != 0;
    if(now && !was && (now_ms - g_last_aux_physical_ms[i] >= AUX_PHYSICAL_DEBOUNCE_MS)){
      g_last_aux_physical_ms[i] = now_ms;
      if(!(g_aux_suppress_until_ms[i] && now_ms < g_aux_suppress_until_ms[i])){
        confirm_aux_idx(i, false);
      }
    }
  }
  g_last_flags = flags;
}
static void set_touch_debug(const char *txt){
  static String last;
  String next = String(txt ? txt : "");
  if(next == last) return;
  last = next;
  set_label_text_if_changed(lbl_touch_debug, next.c_str());
  Serial.println(next);
}

static void style_status_pill_cached(int idx, lv_obj_t *pill, lv_obj_t *lbl, const char *name, bool ok){
  if(idx < 0 || idx > 2) return;
  int next = ok ? 1 : 0;
  if(g_last_status_visual[idx] == next) return;
  g_last_status_visual[idx] = next;
  set_label_text_if_changed(lbl, name);
  if(pill){
    lv_obj_set_style_bg_color(pill,lv_color_hex(0x171c20),0);
    lv_obj_set_style_border_color(pill,lv_color_hex(0x4a4f52),0);
  }
  lv_obj_t *dot = (idx == 0) ? dot_ctrl : nullptr;
  if(dot) lv_obj_set_style_bg_color(dot,lv_color_hex(ok?0x63d84e:0xef5757),0);
}

static void style_w1p_status_pill(int state){
  int next = (state == 1) ? 1 : ((state == 2) ? 2 : 0);
  if(g_last_status_visual[2] == next) return;
  g_last_status_visual[2] = next;
  set_label_text_if_changed(lbl_w1p, "W1P");
  if(pill_w1p){
    lv_obj_set_style_bg_color(pill_w1p,lv_color_hex(0x171c20),0);
    lv_obj_set_style_border_color(pill_w1p,lv_color_hex(0x4a4f52),0);
  }
  if(dot_w1p) lv_obj_set_style_bg_color(dot_w1p,lv_color_hex(next==1?0x63d84e:(next==2?0xf0b35b:0xef5757)),0);
}

static void style_estop_pill(bool active){
  // v26.09.04.02: the middle status banner follows the SRVR-resolved state.
  // A local CTRL-TS UART/display gap must not invent "E-Stop CTRL" while SRVR
  // is still sending Status | Active. Real CTRL/W1P E-Stops are still shown
  // immediately when SRVR sends status=E-Stop... / status_level=red.
  int level = g_status_level;
  String text = g_status_text.length() ? g_status_text : "Active";
  const bool explicit_fault = (text.indexOf("Fault") >= 0) || (text.indexOf("Link Loss") >= 0);
  if(g_estop_active && !text.startsWith("E-Stop") && !explicit_fault){
    String src = g_estop_source.length() ? g_estop_source : "CTRL";
    src.replace("+", " & ");
    text = "E-Stop " + src;
    level = 2;
  }
  if(g_last_estop_visual == level && g_last_status_text == text) return;
  g_last_estop_visual = level;
  g_last_status_text = text;

  if(level >= 2){
    lv_obj_set_style_bg_color(pill_estop,lv_color_hex(0x3a1619),0);
    lv_obj_set_style_border_color(pill_estop,lv_color_hex(0x8b3b42),0);
    lv_obj_set_style_text_color(lbl_estop,lv_color_hex(0xef5757),0);
  } else if(level == 1){
    lv_obj_set_style_bg_color(pill_estop,lv_color_hex(0x3a2d16),0);
    lv_obj_set_style_border_color(pill_estop,lv_color_hex(0x8b6b32),0);
    lv_obj_set_style_text_color(lbl_estop,lv_color_hex(0xf0b35b),0);
  } else {
    lv_obj_set_style_bg_color(pill_estop,lv_color_hex(0x16331a),0);
    lv_obj_set_style_border_color(pill_estop,lv_color_hex(0x34783b),0);
    lv_obj_set_style_text_color(lbl_estop,lv_color_hex(0x63d84e),0);
  }
  String shown;
  if(level >= 2){
    String detail = text;
    if(detail.startsWith("E-Stop ")) detail = detail.substring(7);
    shown = "◇  E-STOP | " + detail;
  } else {
    shown = "◇  STATE | " + text;
  }
  set_label_text_if_changed(lbl_estop, shown.c_str());
}

static void refresh_status_ui(){
  style_status_pill_cached(0,pill_ctrl,lbl_ctrl,"CTRL",g_ctrl_ok);
  if(pill_srvr && lbl_srvr) style_status_pill_cached(1,pill_srvr,lbl_srvr,"SRVR",g_srvr_ok);
  style_w1p_status_pill(g_w1p_health);
  // v26.09.04.02: do not turn the main middle box red purely because the
  // CTRL-TS local UART/display link hiccuped. The SRVR status packet is the
  // authoritative source for Active / Un-Calibrated / E-Stop display state.
  bool stopped_visual = (g_status_level >= 2) || g_estop_active;
  bool service_visual = (!stopped_visual) && ((g_status_level == 1) || mode_is_service());
  style_estop_pill(stopped_visual);
  // v18: keep the large middle panel/cells static during E-Stop/service changes.
  // Recolouring the full middle region caused the visible screen flicker/jump and
  // the recurring left-side AUX-area tear. The status pill and link pills still
  // show red/yellow/green, but large parent panels are no longer invalidated.
  (void)service_visual;
  sync_service_aux_visual();
}

static void send_hmi_command(const char *cmd){
  if(!cmd || !*cmd) return;
  if(!queue_hmi_event(String(cmd))) Serial.println("[WS-HMI] event queue full; event dropped");
  else Serial.printf("[WS-HMI EVENT QUEUED] %s\n", cmd);
}

static bool is_within_aux(lv_obj_t *target){
  lv_obj_t *obj = target;
  while(obj){
    for(int i=0;i<AUX_COUNT;i++) if(obj == aux_btn[i]) return true;
    obj = lv_obj_get_parent(obj);
  }
  return false;
}

static void bg_event_cb(lv_event_t *e){
  if(lv_event_get_code(e) != LV_EVENT_CLICKED) return;
  lv_obj_t *target = lv_event_get_target(e);
  if(is_within_aux(target)) return;
  cancel_pending_aux();
}

static void aux_event_cb(lv_event_t *e){
  int idx=(int)(intptr_t)lv_event_get_user_data(e);
  confirm_aux_idx(idx, true);
}

static String getField(const String &line, const char *key){
  String token = String("|") + key + "=";
  int start = line.indexOf(token);
  if(start < 0){
    if(line.startsWith(String(key) + "=")) start = -1;
    else return "";
  }
  if(start >= 0) start += token.length();
  else start = strlen(key) + 1;
  int end = line.indexOf('|', start);
  if(end < 0) end = line.length();
  return line.substring(start, end);
}

static float getFieldFloat(const String &line, const char *key, float def){
  String v = getField(line, key);
  if(!v.length()) return def;
  return v.toFloat();
}

static bool getFieldBool(const String &line, const char *key, bool def){
  String v = getField(line, key);
  if(!v.length()) return def;
  return (v == "1" || v == "true" || v == "TRUE");
}

static int split_csv(const String &src, String out[], int max_items){
  int count = 0;
  int start = 0;
  while(count < max_items) {
    int comma = src.indexOf(',', start);
    if(comma < 0) {
      String item = src.substring(start);
      item.trim();
      if(item.length() || start < src.length()) out[count++] = item;
      break;
    }
    String item = src.substring(start, comma);
    item.trim();
    out[count++] = item;
    start = comma + 1;
  }
  return count;
}

static int clamp_int(int v, int lo, int hi){
  if(v < lo) return lo;
  if(v > hi) return hi;
  return v;
}

static void split_ip_octets(const String &ip, int octets[4]){
  octets[0]=octets[1]=octets[2]=octets[3]=0;
  int start = 0;
  for(int i=0;i<4;i++){
    int dot = ip.indexOf('.', start);
    String part = (dot >= 0) ? ip.substring(start, dot) : ip.substring(start);
    part.trim();
    octets[i] = clamp_int(part.toInt(), 0, 255);
    if(dot < 0) break;
    start = dot + 1;
  }
}

static String make_ip_from_octets(const int octets[4]){
  return String(octets[0]) + "." + String(octets[1]) + "." + String(octets[2]) + "." + String(octets[3]);
}

static String& selected_edit_ip_string(){
  if(g_settings_selected_field == 1) return g_edit_ctrl_ip;
  if(g_settings_selected_field == 2) return g_edit_subnet;
  if(g_settings_selected_field == 3) return g_edit_gateway;
  return g_edit_srvr_ip;
}

static void refresh_settings_labels(){
  if(lbl_settings_value[0]) set_label_text_if_changed(lbl_settings_value[0], g_edit_srvr_ip.c_str());
  if(lbl_settings_value[1]) set_label_text_if_changed(lbl_settings_value[1], g_edit_ctrl_ip.c_str());
  if(lbl_settings_value[2]) set_label_text_if_changed(lbl_settings_value[2], g_edit_subnet.c_str());
  if(lbl_settings_value[3]) set_label_text_if_changed(lbl_settings_value[3], g_edit_gateway.c_str());
  const char* names[4] = {"SRVR IP", "CTRL IP", "Subnet", "Gateway"};
  if(lbl_settings_selected){
    String s = String("Editing: ") + names[clamp_int(g_settings_selected_field,0,3)] + " / Octet " + String(g_settings_selected_octet + 1);
    set_label_text_if_changed(lbl_settings_selected, s.c_str());
  }
  for(int i=0;i<4;i++){
    if(settings_row_panel[i]){
      bool sel = (i == g_settings_selected_field);
      lv_obj_set_style_border_color(settings_row_panel[i], lv_color_hex(sel ? 0xf0b35b : 0x34536f), 0);
      lv_obj_set_style_border_width(settings_row_panel[i], sel ? 2 : 1, 0);
    }
  }
}

static void copy_current_settings_to_edit(){
  g_edit_srvr_ip = g_cfg_srvr_ip;
  g_edit_ctrl_ip = g_cfg_ctrl_ip;
  g_edit_subnet = g_cfg_subnet;
  g_edit_gateway = g_cfg_gateway;
  g_settings_dirty = false;
}

static void send_settings_to_ctrl(bool reset_after_save){
  String cmd = "CFG1|srvr_ip=" + g_edit_srvr_ip + "|ctrl_ip=" + g_edit_ctrl_ip + "|subnet=" + g_edit_subnet + "|gateway=" + g_edit_gateway;
  if(reset_after_save) cmd += "|reset=1";
  send_hmi_command(cmd.c_str());
}

static void apply_cfg_packet(const String &line){
  String s;
  s = getField(line, "srvr_ip"); if(s.length()) g_cfg_srvr_ip = s;
  s = getField(line, "ctrl_ip"); if(s.length()) g_cfg_ctrl_ip = s;
  s = getField(line, "subnet");  if(s.length()) g_cfg_subnet = s;
  s = getField(line, "gateway"); if(s.length()) g_cfg_gateway = s;
  if(g_settings_visible && !g_settings_dirty){
    copy_current_settings_to_edit();
  }
  refresh_settings_labels();
  if(lbl_settings_note && g_settings_visible) set_label_text_if_changed(lbl_settings_note, "Loaded IP settings from CTRL");
}

static void set_settings_visible(bool visible){
  g_settings_visible = visible;
  if(!settings_overlay) return;
  if(visible){
    copy_current_settings_to_edit();
    refresh_settings_labels();
    lv_obj_clear_flag(settings_overlay, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(settings_overlay);
    if(lbl_settings_note) set_label_text_if_changed(lbl_settings_note, "Change IP settings, then Apply & Reset or Cancel");
    send_hmi_command("CFG?");
  } else {
    lv_obj_add_flag(settings_overlay, LV_OBJ_FLAG_HIDDEN);
  }
}

static void settings_event_cb(lv_event_t *e){
  if(lv_event_get_code(e) != LV_EVENT_CLICKED) return;
  int id = (int)(intptr_t)lv_event_get_user_data(e);
  if(id == SET_BTN_OPEN){
    cancel_pending_aux();
    set_settings_visible(true);
    return;
  }
  if(id == SET_BTN_CANCEL){
    copy_current_settings_to_edit();
    set_settings_visible(false);
    return;
  }
  if(id >= SET_BTN_SELECT_SRVR && id <= SET_BTN_SELECT_GATEWAY){
    g_settings_selected_field = id - SET_BTN_SELECT_SRVR;
    refresh_settings_labels();
    return;
  }
  if(id == SET_BTN_OCTET_PREV || id == SET_BTN_OCTET_NEXT){
    g_settings_selected_octet += (id == SET_BTN_OCTET_NEXT) ? 1 : -1;
    if(g_settings_selected_octet < 0) g_settings_selected_octet = 3;
    if(g_settings_selected_octet > 3) g_settings_selected_octet = 0;
    refresh_settings_labels();
    return;
  }
  if(id == SET_BTN_OCTET_DOWN || id == SET_BTN_OCTET_UP){
    String &ip = selected_edit_ip_string();
    int octets[4]; split_ip_octets(ip, octets);
    int delta = (id == SET_BTN_OCTET_UP) ? 1 : -1;
    octets[g_settings_selected_octet] = clamp_int(octets[g_settings_selected_octet] + delta, 0, 255);
    ip = make_ip_from_octets(octets);
    g_settings_dirty = true;
    refresh_settings_labels();
    return;
  }
  if(id == SET_BTN_APPLY_RESET){
    g_cfg_srvr_ip = g_edit_srvr_ip;
    g_cfg_ctrl_ip = g_edit_ctrl_ip;
    g_cfg_subnet = g_edit_subnet;
    g_cfg_gateway = g_edit_gateway;
    send_settings_to_ctrl(true);
    if(lbl_settings_note) set_label_text_if_changed(lbl_settings_note, "Applied. Resetting CTRL-TS and CTRL...");
    g_settings_reset_due_ms = millis() + 900;
    return;
  }
}

static void create_settings_overlay(){
  if(!middle_panel || settings_overlay) return;
  settings_overlay = make_panel(middle_panel,0,0,780,324,0x182c41,0x34536f,12);
  lv_obj_add_flag(settings_overlay, LV_OBJ_FLAG_HIDDEN);
  make_label(settings_overlay,"Settings",16,10,&lv_font_montserrat_18,lv_color_hex(0xffffff),160);
  make_label(settings_overlay,"Network settings are stored in CTRL and apply after reset.",190,16,&lv_font_montserrat_10,lv_color_hex(0xa9c3db),400);

  const char* row_names[4] = {"SRVR IP", "CTRL IP", "Subnet", "Gateway"};
  for(int i=0;i<4;i++){
    int y = 58 + i*42;
    settings_row_panel[i] = make_panel(settings_overlay,24,y,530,32,0x102337,0x34536f,8);
    make_label(settings_row_panel[i],row_names[i],12,9,&lv_font_montserrat_10,lv_color_hex(0xa9c3db),100);
    lbl_settings_value[i] = make_label(settings_row_panel[i],"0.0.0.0",150,7,&lv_font_montserrat_14,lv_color_hex(0xffffff),180);
    lv_obj_t *sel = make_button(settings_row_panel[i],410,4,104,24);
    lv_obj_add_event_cb(sel,settings_event_cb,LV_EVENT_CLICKED,(void*)(intptr_t)(SET_BTN_SELECT_SRVR+i));
    make_label(sel,"Edit",0,6,&lv_font_montserrat_10,lv_color_hex(0xffffff),104);
  }

  lv_obj_t *op = make_button(settings_overlay,584,70,82,30); lv_obj_add_event_cb(op,settings_event_cb,LV_EVENT_CLICKED,(void*)(intptr_t)SET_BTN_OCTET_PREV); make_label(op,"Octet <",0,9,&lv_font_montserrat_10,lv_color_hex(0xffffff),82);
  lv_obj_t *om = make_button(settings_overlay,680,70,42,30); lv_obj_add_event_cb(om,settings_event_cb,LV_EVENT_CLICKED,(void*)(intptr_t)SET_BTN_OCTET_DOWN); make_label(om,"-",0,7,&lv_font_montserrat_16,lv_color_hex(0xffffff),42);
  lv_obj_t *oplus = make_button(settings_overlay,730,70,42,30); lv_obj_add_event_cb(oplus,settings_event_cb,LV_EVENT_CLICKED,(void*)(intptr_t)SET_BTN_OCTET_UP); make_label(oplus,"+",0,7,&lv_font_montserrat_16,lv_color_hex(0xffffff),42);
  lv_obj_t *on = make_button(settings_overlay,584,112,82,30); lv_obj_add_event_cb(on,settings_event_cb,LV_EVENT_CLICKED,(void*)(intptr_t)SET_BTN_OCTET_NEXT); make_label(on,"Octet >",0,9,&lv_font_montserrat_10,lv_color_hex(0xffffff),82);
  lbl_settings_selected = make_label(settings_overlay,"Editing: SRVR IP / Octet 1",574,154,&lv_font_montserrat_10,lv_color_hex(0xdff0ff),190);

  lv_obj_t *apply = make_button(settings_overlay,490,276,136,34);
  lv_obj_add_event_cb(apply,settings_event_cb,LV_EVENT_CLICKED,(void*)(intptr_t)SET_BTN_APPLY_RESET);
  make_label(apply,"Apply & Reset",0,10,&lv_font_montserrat_12,lv_color_hex(0xffffff),136);
  lv_obj_t *cancel = make_button(settings_overlay,638,276,116,34);
  lv_obj_add_event_cb(cancel,settings_event_cb,LV_EVENT_CLICKED,(void*)(intptr_t)SET_BTN_CANCEL);
  make_label(cancel,"Cancel",0,10,&lv_font_montserrat_12,lv_color_hex(0xffffff),116);
  lbl_settings_note = make_label(settings_overlay,"",24,286,&lv_font_montserrat_10,lv_color_hex(0xa9c3db),450);
  refresh_settings_labels();
}

static void progress_marker_anim_exec(void * obj, int32_t v){
  if(obj) lv_obj_set_x((lv_obj_t*)obj, (lv_coord_t)v);
}

static void set_progress_marker_x_smooth(int target_x){
  if(!current_marker) return;
  // v16: no local animation tail. SRVR now sends finer/faster verified position
  // packets, so the marker can snap to each verified point. This is more
  // faithful when the motor physically stops and prevents the progress bar from
  // coasting for another second.
  lv_anim_del(current_marker, NULL);
  lv_obj_set_x(current_marker, target_x);
  g_current_marker_x = target_x;
}

static void update_progress_marker(){
  const int bar_left = BAR_LIMIT_LEFT;
  const int bar_right = BAR_LIMIT_RIGHT;
  const int marker_w = 5;
  float pos = g_pos;
  float nearp = g_near;
  float farp = g_far;
  float frac = 0.0f;
  if(farp > nearp + 0.001f) frac = (pos - nearp) / (farp - nearp);
  if(frac < 0.0f) frac = 0.0f;
  if(frac > 1.0f) frac = 1.0f;
  int x = (int)(bar_left + frac * (float)(bar_right - bar_left - marker_w));
  if(x < bar_left) x = bar_left;
  if(x > bar_right - marker_w) x = bar_right - marker_w;
  // v16: always snap to the latest verified SRVR/drive position.
  set_progress_marker_x_smooth(x);
}

static void update_reference_marker(){
  if(!travel_panel || !travel_ref_lbl || !travel_ref_marker) return;
  if(!g_ref_visible){
    lv_obj_add_flag(travel_ref_lbl, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(travel_ref_marker, LV_OBJ_FLAG_HIDDEN);
    return;
  }
  lv_obj_clear_flag(travel_ref_lbl, LV_OBJ_FLAG_HIDDEN);
  lv_obj_clear_flag(travel_ref_marker, LV_OBJ_FLAG_HIDDEN);
  const int bar_left = BAR_LIMIT_LEFT;
  const int bar_right = BAR_LIMIT_RIGHT;
  const int marker_w = 3;
  float frac = 0.0f;
  if(g_far > g_near + 0.001f) frac = (g_ref - g_near) / (g_far - g_near);
  if(frac < 0.0f) frac = 0.0f;
  if(frac > 1.0f) frac = 1.0f;
  int marker_x = (int)(bar_left + frac * (float)(bar_right - bar_left - marker_w));
  if(marker_x < bar_left) marker_x = bar_left;
  if(marker_x > bar_right - marker_w) marker_x = bar_right - marker_w;
  int center_x = marker_x + (marker_w / 2);
  int label_x = center_x - 20;
  if(label_x < bar_left - 10) label_x = bar_left - 10;
  if(label_x > bar_right - 30) label_x = bar_right - 30;
  lv_obj_set_x(travel_ref_lbl, label_x);
  lv_obj_set_pos(travel_ref_marker, marker_x, 38);
  lv_obj_set_size(travel_ref_marker, marker_w, 5);
}

static void update_ramp_markers(){
  if(!ramp_l || !ramp_r) return;
  const int bar_left = BAR_LIMIT_LEFT;
  const int bar_right = BAR_LIMIT_RIGHT;
  const int bar_w = bar_right - bar_left;
  const int ramp_y = 51;
  const int ramp_h = 7;
  float span = g_far - g_near;
  if(span < 0.001f) span = 0.001f;
  float frac_near = g_ramp_near / span;
  float frac_far = g_ramp_far / span;
  if(frac_near < 0.0f) frac_near = 0.0f;
  if(frac_near > 1.0f) frac_near = 1.0f;
  if(frac_far < 0.0f) frac_far = 0.0f;
  if(frac_far > 1.0f) frac_far = 1.0f;
  int near_w = (int)(bar_w * frac_near);
  int far_w = (int)(bar_w * frac_far);
  if(near_w < 0) near_w = 0;
  if(near_w > bar_w) near_w = bar_w;
  if(far_w < 0) far_w = 0;
  if(far_w > bar_w) far_w = bar_w;
  lv_obj_set_pos(ramp_l, bar_left, ramp_y);
  lv_obj_set_size(ramp_l, near_w, ramp_h);
  lv_obj_set_pos(ramp_r, bar_right - far_w, ramp_y);
  lv_obj_set_size(ramp_r, far_w, ramp_h);
}

static void update_preset_markers(){
  if(!travel_panel) return;
  const int bar_left = BAR_LIMIT_LEFT;
  const int bar_right = BAR_LIMIT_RIGHT;
  const int marker_w = 5;
  const int line_w = 2;
  const int line_top_y = 38;
  const int line_h = 11;
  const int label_w = 42;
  const int label_y_top = 27;
  const int label_y_bottom = 58;

  for(int i=0;i<12;i++){
    bool has_name = g_preset_names[i].length() > 0;
    bool show = g_preset_visible[i] && has_name;
    if(!show){
      lv_obj_add_flag(preset_line[i], LV_OBJ_FLAG_HIDDEN);
      lv_obj_add_flag(preset_lbl[i], LV_OBJ_FLAG_HIDDEN);
      lv_obj_add_flag(preset_tri[i], LV_OBJ_FLAG_HIDDEN);
      continue;
    }
    float frac = 0.0f;
    if(g_far > g_near + 0.001f) frac = (g_preset_pos[i] - g_near) / (g_far - g_near);
    if(frac < 0.0f) frac = 0.0f;
    if(frac > 1.0f) frac = 1.0f;
    // Use the exact same left-edge travel span as update_progress_marker(), then
    // place the 2 px preset line on the centre of the 5 px live marker.
    int marker_left_x = (int)(bar_left + frac * (float)(bar_right - bar_left - marker_w));
    int x = marker_left_x + (marker_w / 2) - (line_w / 2);
    if(x < bar_left) x = bar_left;
    if(x > bar_right - line_w) x = bar_right - line_w;
    int lbl_y = (i % 2 == 0) ? label_y_top : label_y_bottom;

    lv_obj_clear_flag(preset_line[i], LV_OBJ_FLAG_HIDDEN);
    lv_obj_clear_flag(preset_lbl[i], LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(preset_tri[i], LV_OBJ_FLAG_HIDDEN);

    lv_obj_set_pos(preset_line[i], x, line_top_y);
    lv_obj_set_size(preset_line[i], line_w, line_h);
    lv_obj_set_pos(preset_lbl[i], x - (label_w / 2), lbl_y);
    lv_obj_set_width(preset_lbl[i], label_w);
    lv_label_set_long_mode(preset_lbl[i], LV_LABEL_LONG_CLIP);
    set_label_text_if_changed(preset_lbl[i], g_preset_names[i].c_str());
  }
}

static void apply_hmi_packet(const String &line){
  bool prev_estop = g_estop_active;
  bool prev_ctrl = g_ctrl_ok;
  bool prev_srvr = g_srvr_ok;
  bool prev_w1p = g_w1p_ok;
  int prev_w1p_health = g_w1p_health;
  String prev_estop_source = g_estop_source;
  String prev_status_text = g_status_text;
  int prev_status_level = g_status_level;
  g_pos       = getFieldFloat(line, "pos", g_pos);
  g_near      = getFieldFloat(line, "near", g_near);
  g_ref       = getFieldFloat(line, "ref", g_ref);
  g_far       = getFieldFloat(line, "far", g_far);
  g_to_near   = getFieldFloat(line, "to_near", g_to_near);
  g_to_far    = getFieldFloat(line, "to_far", g_to_far);
  g_speed_mps = getFieldFloat(line, "speed_mps", g_speed_mps);
  g_speed_kmh = getFieldFloat(line, "speed_kmh", g_speed_kmh);
  g_ramp_near = getFieldFloat(line, "ramp_near", g_ramp_near);
  g_ramp_far = getFieldFloat(line, "ramp_far", g_ramp_far);
  g_ref_visible = getFieldBool(line, "ref_vis", g_ref_visible);
  g_mode      = getField(line, "mode");
  if(g_mode == "Normal") g_mode = "Power";
  if(!g_mode.length()) g_mode = "Mode 1";
  String driveField = getField(line, "drive_mode"); if(driveField.length()) g_drive_mode = driveField; else g_drive_mode = g_mode;
  String accelField = getField(line, "accel_mode"); if(accelField.length()) g_accel_mode = display_aux_label(accelField);
  String batteryField = getField(line, "battery_change"); if(batteryField.length()) g_battery_mode = batteryField;
  String timeField = getField(line, "srvr_time"); if(timeField.length()) g_srvr_time = timeField;
  String uptimeField = getField(line, "uptime"); if(uptimeField.length()) g_uptime = uptimeField;
  String ctrlIpField = getField(line, "ctrl_ip"); if(ctrlIpField.length()) g_ctrl_ip = ctrlIpField;
  String w1pIpField = getField(line, "w1p_ip"); if(w1pIpField.length()) g_w1p_ip = w1pIpField;
  g_max_mps = getFieldFloat(line, "max_mps", g_max_mps);
  g_max_kmh = getFieldFloat(line, "max_kmh", g_max_kmh);
  bool mode_changed = (g_mode != g_last_mode);
  g_last_mode = g_mode;
  bool packet_estop = getFieldBool(line, "estop", g_estop_active);
  String srcField = getField(line, "estop_src");
  String statusField = getField(line, "status");
  String levelField = getField(line, "status_level");
  g_ctrl_ok      = getFieldBool(line, "ctrl", g_ctrl_ok);
  g_srvr_ok      = getFieldBool(line, "srvr", g_srvr_ok);
  g_w1p_ok       = getFieldBool(line, "w1p", g_w1p_ok);
  String w1pStateField = getField(line, "w1p_state");
  if(w1pStateField.length()){
    w1pStateField.toLowerCase();
    if(w1pStateField.indexOf("fault") >= 0) g_w1p_health = 2;
    else if(w1pStateField.indexOf("ok") >= 0 || w1pStateField.indexOf("healthy") >= 0) g_w1p_health = 1;
    else g_w1p_health = 0;
  } else {
    g_w1p_health = g_w1p_ok ? 1 : 0;
  }

  if(statusField.length()) g_status_text = statusField;
  if(levelField.length()){
    levelField.toLowerCase();
    if(levelField.indexOf("red") >= 0 || levelField.indexOf("stop") >= 0) g_status_level = 2;
    else if(levelField.indexOf("yellow") >= 0 || levelField.indexOf("service") >= 0) g_status_level = 1;
    else g_status_level = 0;
  } else if(statusField.length()){
    String sf = statusField; sf.toLowerCase();
    if(sf.indexOf("e-stop") >= 0 || sf.indexOf("link loss") >= 0) g_status_level = 2;
    else if(sf.indexOf("calibr") >= 0 || sf.indexOf("battery") >= 0) g_status_level = 1;
    else g_status_level = 0;
  }

  // v26.09.04.02: if SRVR sends explicit status/status_level, trust it as
  // the authoritative display state. Do not override it locally with a CTRL
  // error just because the touchscreen/CTRL UART side saw a transient gap.
  g_estop_active = packet_estop;
  if(srcField.length()) g_estop_source = srcField;
  else if(g_estop_active) g_estop_source = "CTRL";
  else g_estop_source = "";

  if(!statusField.length()){
    if(!g_ctrl_ok){
      // Do not invent a red E-Stop CTRL state from a transient display/config gap.
      // SRVR sends the authoritative status/status_level fields for real E-stops.
      g_status_text = g_status_text.length() ? g_status_text : "Active";
      if(g_status_text == "E-Stop CTRL") { g_status_text = "Active"; g_status_level = 0; g_estop_active = false; g_estop_source = ""; }
    } else if(!g_srvr_ok){
      g_estop_active = true;
      g_estop_source = "SRVR";
      g_status_text = "E-Stop SRVR";
      g_status_level = 2;
    } else if(g_estop_active){
      String src = g_estop_source.length() ? g_estop_source : "CTRL";
      src.replace("+", " & ");
      g_status_text = "E-Stop " + src;
      g_status_level = 2;
    } else if(mode_is_service()){
      g_status_text = g_mode;
      g_status_level = 1;
    } else {
      g_status_text = "Active";
      g_status_level = 0;
    }
  }
  uint16_t flags_now = (uint16_t)getFieldFloat(line, "flags", (float)g_last_flags);

  String s;
  s = String(g_to_near, 2); set_label_text_if_changed(lbl_to_near, s.c_str());
  s = String(g_to_far, 2); set_label_text_if_changed(lbl_to_far, s.c_str());
  s = String(g_speed_mps, 1); set_label_text_if_changed(lbl_speed_combo, s.c_str());
  s = String(g_speed_kmh, 1); set_label_text_if_changed(lbl_current_kmh, s.c_str());
  s = String(g_max_mps, 1); set_label_text_if_changed(lbl_max_speed, s.c_str());
  s = String(g_max_kmh, 1); set_label_text_if_changed(lbl_max_kmh, s.c_str());
  s = String(g_pos, 2); set_label_text_if_changed(lbl_current_pos, s.c_str());
  set_label_text_if_changed(lbl_drive_mode, g_drive_mode.c_str());
  set_label_text_if_changed(lbl_accel_mode, g_accel_mode.c_str());
  set_label_text_if_changed(lbl_battery_mode, g_battery_mode.c_str());
  set_label_text_if_changed(lbl_srvr_time, g_srvr_time.c_str());
  set_label_text_if_changed(lbl_uptime, g_uptime.c_str());
  set_label_text_if_changed(lbl_ctrl_ip, g_ctrl_ip.c_str());
  set_label_text_if_changed(lbl_w1p_ip, g_w1p_ip.c_str());
  s = String(g_near, 2) + " m"; set_label_text_if_changed(lbl_near_value, s.c_str());
  s = String(g_far, 2) + " m"; set_label_text_if_changed(lbl_far_value, s.c_str());

  String aux;
  aux = getField(line, "aux1"); if(aux.length()){ aux = display_aux_label(aux); g_aux_labels[0] = aux; refresh_aux_text(0); }
  aux = getField(line, "aux2"); if(aux.length()){ aux = display_aux_label(aux); g_aux_labels[1] = aux; refresh_aux_text(1); }
  aux = getField(line, "aux3"); if(aux.length()){ aux = display_aux_label(aux); g_aux_labels[2] = aux; refresh_aux_text(2); }
  aux = getField(line, "aux4"); if(aux.length()){ aux = display_aux_label(aux); g_aux_labels[3] = aux; refresh_aux_text(3); }
  aux = getField(line, "aux5"); if(aux.length()){ aux = display_aux_label(aux); g_aux_labels[4] = aux; refresh_aux_text(4); }

  String preset_names_field = getField(line, "preset_names");
  String preset_pos_field = getField(line, "preset_pos");
  String preset_abs_field = getField(line, "preset_abs");
  String preset_vis_field = getField(line, "preset_vis");
  bool preset_fields_changed = (preset_names_field != g_last_preset_names_field) || (preset_pos_field != g_last_preset_pos_field) || (preset_abs_field != g_last_preset_abs_field) || (preset_vis_field != g_last_preset_vis_field);
  if((preset_names_field.length() || preset_pos_field.length() || preset_vis_field.length()) && preset_fields_changed){
    g_last_preset_names_field = preset_names_field;
    g_last_preset_pos_field = preset_pos_field;
    g_last_preset_abs_field = preset_abs_field;
    g_last_preset_vis_field = preset_vis_field;
    String names[12];
    String pos[12];
    String abspos[12];
    String vis[12];
    int name_count = split_csv(preset_names_field, names, 12);
    int pos_count = split_csv(preset_pos_field, pos, 12);
    int abs_count = split_csv(preset_abs_field, abspos, 12);
    int vis_count = split_csv(preset_vis_field, vis, 12);
    g_preset_count = 12;
    for(int i=0;i<12;i++){
      g_preset_names[i] = (i < name_count && names[i].length()) ? names[i] : String("P") + String(i + 1);
      if(i < abs_count && abspos[i].length()) g_preset_pos[i] = abspos[i].toFloat();
      else g_preset_pos[i] = (i < pos_count && pos[i].length()) ? pos[i].toFloat() : 0.0f;
      g_preset_visible[i] = (i < vis_count) ? (vis[i].toInt() != 0) : (i < pos_count && pos[i].length());
    }
    update_preset_markers();
  }

  apply_flags_to_aux(flags_now);
  update_progress_marker();
  bool ref_changed = (fabsf(g_ref - g_last_ref_draw) > 0.05f) || (fabsf(g_near - g_last_near_draw) > 0.05f) || (fabsf(g_far - g_last_far_draw) > 0.05f);
  if(ref_changed){
    g_last_ref_draw = g_ref;
    g_last_near_draw = g_near;
    g_last_far_draw = g_far;
    update_reference_marker();
    update_preset_markers();
  }
  bool ramp_changed = ref_changed || (fabsf(g_ramp_near - g_last_ramp_near_draw) > 0.05f) || (fabsf(g_ramp_far - g_last_ramp_far_draw) > 0.05f);
  if(ramp_changed){
    g_last_ramp_near_draw = g_ramp_near;
    g_last_ramp_far_draw = g_ramp_far;
    update_ramp_markers();
  }
  sync_service_aux_visual();
  if(mode_changed || (prev_status_text != g_status_text) || (prev_status_level != g_status_level) || (prev_estop != g_estop_active) || (prev_estop_source != g_estop_source) || (prev_ctrl != g_ctrl_ok) || (prev_srvr != g_srvr_ok) || (prev_w1p != g_w1p_ok) || (prev_w1p_health != g_w1p_health)) {
    refresh_status_ui();
  }
  // v26.09.04.02: no left-strip/full-screen invalidation on packets; progress marker animates locally.
}


static void apply_layout_packet(const String &line){
  // Keep the header fixed locally so a stored layout
  // on CTRL cannot overwrite the screen title/version or trigger header redraws.
  String hint = getField(line, "hint");
  if(lbl_title) set_label_text_if_changed(lbl_title, "HV P2P\nCTRL-TS");
  if(lbl_subtitle) set_label_text_if_changed(lbl_subtitle, "v26.09.04.02");
  if(hint.length() && hint.startsWith("ERROR")) set_touch_debug(hint.c_str());
  for(int i=0;i<AUX_COUNT;i++){
    String key = String("aux") + String(i+1);
    String v = getField(line, key.c_str());
    if(v.length()){
      g_aux_labels[i] = v;
      refresh_aux_text(i);
    }
  }
  Serial.println("[WS-HMI] layout applied from CTRL");
}

static void process_text_from_ctrl(String line, bool boot_phase){
  line.trim();
  if(!line.length()) return;
  if(line.startsWith("DSP1|")) line.replace("DSP1|", "HMI1|");
  last_hmi_rx = millis();
  if(boot_phase){
    boot_process_line(line);
    return;
  }
  if(line.startsWith("CFG1|")) {
    apply_cfg_packet(line);
  } else if(line.startsWith("CFG_ACK|")) {
    String ok = getField(line, "ok");
    String note = getField(line, "note");
    if(lbl_settings_note && g_settings_visible) set_label_text_if_changed(lbl_settings_note, note.length() ? note.c_str() : (ok == "1" ? "CTRL saved settings" : "CTRL rejected settings"));
  } else if(line.startsWith("UIL1|")) {
    apply_layout_packet(line);
    bool changed = !g_ctrl_ok;
    g_ctrl_ok = true;
    if(changed) refresh_status_ui();
  } else if(is_valid_hmi_packet(line)) {
    if(line != g_last_applied_hmi_line){ g_last_applied_hmi_line = line; apply_hmi_packet(line); }
    set_touch_debug("Ready");
  }
}

static inline void rs485_slave_turnaround_guard();

static uint32_t read_be32(const uint8_t *p){
  return (uint32_t(p[0])<<24) | (uint32_t(p[1])<<16) | (uint32_t(p[2])<<8) | uint32_t(p[3]);
}

static void fw_send_text(uint8_t type, uint16_t seq, const String &text){
  rs485_slave_turnaround_guard();
  HVP2PRS485::sendText(HMI, type, seq, text);
}

static String sha256_hex(const uint8_t digest[32]){
  static const char HEX_DIGITS[] = "0123456789abcdef";
  char out[65];
  for(size_t i=0;i<32;i++){ out[i*2]=HEX_DIGITS[digest[i]>>4]; out[i*2+1]=HEX_DIGITS[digest[i]&0x0F]; }
  out[64]='\0';
  return String(out);
}

static void fw_sha_release(){
  if(g_fw_sha_active){ mbedtls_sha256_free(&g_fw_sha_ctx); g_fw_sha_active=false; }
}

static void fw_abort(const char *reason, uint16_t seq=0){
  if(g_fw_update_active) Update.abort();
  fw_sha_release();
  g_fw_update_active = false;
  g_fw_finalized = false;
  g_fw_final_size = 0;
  g_fw_final_sha = "";
  g_fw_expected_size = 0;
  g_fw_received = 0;
  g_fw_expected_sha = "";
  g_fw_expected_version = "";
  g_ctrl_fw_compatible = false;
  String msg = String("fw_abort|") + (reason ? reason : "unknown");
  Serial.printf("[FW RX] %s\n", msg.c_str());
  if(seq) fw_send_text(HVP2PRS485::ERROR_MSG, seq, msg);
  boot_set_status("Firmware update failed | waiting for CTRL");
}

static void fw_handle_begin(const HVP2PRS485::Frame &frame){
  String meta = HVP2PRS485::payloadString(frame);
  String targetHw = boot_get_field(meta, "hw");
  String protoText = boot_get_field(meta, "proto");
  String sizeText = boot_get_field(meta, "size");
  String version = boot_get_field(meta, "version");
  String sha = boot_get_field(meta, "sha256");
  size_t imageSize = (size_t)strtoull(sizeText.c_str(), nullptr, 10);
  uint32_t proto = (uint32_t)strtoul(protoText.c_str(), nullptr, 10);
  // A firmware stream is accepted only when it explicitly targets this exact
  // Waveshare hardware identity and protocol. This is a second safety boundary
  // in addition to CTRL checking HELLO before it starts an update.
  if(targetHw != CTRL_TS_HW_ID || proto != HVP2PRS485::PROTOCOL_VERSION){
    fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "fw_begin_wrong_target");
    return;
  }
  if(imageSize < 32768 || imageSize > FW_MAX_IMAGE_SIZE || version.length() < 2 || sha.length() != 64){
    fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "fw_begin_invalid");
    return;
  }
  if(g_fw_update_active) Update.abort();
  g_fw_finalized = false;
  g_fw_final_size = 0;
  g_fw_final_sha = "";
  if(!Update.begin(imageSize, U_FLASH)){
    Serial.println("[FW RX] Update.begin failed");
    fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "fw_begin_no_space");
    return;
  }
  fw_sha_release();
  mbedtls_sha256_init(&g_fw_sha_ctx);
  if(mbedtls_sha256_starts(&g_fw_sha_ctx, 0) != 0){
    Update.abort();
    mbedtls_sha256_free(&g_fw_sha_ctx);
    fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "fw_begin_sha_init");
    return;
  }
  g_fw_sha_active = true;
  g_fw_update_active = true;
  g_fw_expected_size = imageSize;
  g_fw_received = 0;
  g_fw_expected_sha = sha;
  g_fw_expected_version = version;
  g_fw_last_rx_ms = millis();
  g_ctrl_fw_compatible = false;
  boot_set_status("Updating CTRL-TS firmware | 0%");
  Serial.printf("[FW RX] begin version=%s size=%u sha=%s\n", version.c_str(), (unsigned)imageSize, sha.c_str());
  fw_send_text(HVP2PRS485::FW_READY, frame.seq, "ok=1|next=0");
}

static void fw_handle_block(const HVP2PRS485::Frame &frame){
  if(!g_fw_update_active || frame.length < 5){
    fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "fw_block_not_ready");
    return;
  }
  const uint32_t offset = read_be32(frame.payload);
  const size_t dataLen = frame.length - 4;
  if(offset != g_fw_received || (g_fw_received + dataLen) > g_fw_expected_size){
    fw_send_text(HVP2PRS485::FW_ACK, frame.seq, String("ok=0|next=") + String((unsigned)g_fw_received));
    return;
  }
  if(dataLen > sizeof(g_fw_write_buf)){
    fw_abort("block_too_large", frame.seq);
    return;
  }
  memcpy(g_fw_write_buf, frame.payload + 4, dataLen);
  const size_t wrote = Update.write(g_fw_write_buf, dataLen);
  if(wrote != dataLen){
    fw_abort("write_failed", frame.seq);
    return;
  }
  if(!g_fw_sha_active || mbedtls_sha256_update(&g_fw_sha_ctx, frame.payload + 4, dataLen) != 0){
    fw_abort("sha_update_failed", frame.seq);
    return;
  }
  g_fw_received += wrote;
  g_fw_last_rx_ms = millis();
  int pct = g_fw_expected_size ? int((100ULL * g_fw_received) / g_fw_expected_size) : 0;
  char status[64]; snprintf(status,sizeof(status),"Updating CTRL-TS firmware | %d%%", pct);
  boot_set_status(status);
  fw_send_text(HVP2PRS485::FW_ACK, frame.seq, String("ok=1|next=") + String((unsigned)g_fw_received));
}

static void fw_handle_end(const HVP2PRS485::Frame &frame){
  // FW_END is deliberately idempotent. If the first FW_RESULT was lost, CTRL
  // retries the same request and receives the already-verified result instead of
  // converting a successful OTA into a false failure.
  if(g_fw_finalized){
    fw_send_text(HVP2PRS485::FW_RESULT, frame.seq, String("ok=1|size=") + String((unsigned)g_fw_final_size) + "|sha256=" + g_fw_final_sha);
    return;
  }
  if(!g_fw_update_active || g_fw_received != g_fw_expected_size){
    fw_send_text(HVP2PRS485::FW_RESULT, frame.seq, String("ok=0|received=") + String((unsigned)g_fw_received));
    return;
  }
  uint8_t digest[32];
  if(!g_fw_sha_active || mbedtls_sha256_finish(&g_fw_sha_ctx, digest) != 0){
    fw_abort("sha_finish_failed");
    fw_send_text(HVP2PRS485::FW_RESULT, frame.seq, "ok=0|reason=sha");
    return;
  }
  fw_sha_release();
  String actualSha = sha256_hex(digest);
  String expectedSha = g_fw_expected_sha; expectedSha.toLowerCase();
  if(actualSha != expectedSha){
    Serial.printf("[FW RX] SHA mismatch expected=%s actual=%s\n", expectedSha.c_str(), actualSha.c_str());
    fw_abort("sha_mismatch");
    fw_send_text(HVP2PRS485::FW_RESULT, frame.seq, "ok=0|reason=sha_mismatch");
    return;
  }
  bool ok = Update.end(true);
  if(!ok || Update.hasError()){
    fw_abort("finalize_failed");
    fw_send_text(HVP2PRS485::FW_RESULT, frame.seq, "ok=0|reason=finalize");
    return;
  }
  // Update.end(true) has already selected the new OTA partition for next boot.
  // Firmware identity metadata is part of the compatibility contract, so if NVS
  // persistence fails, restore the currently-running partition as the boot target
  // rather than leaving a new image selected that can only report 'bootstrap'.
  bool metaOk = save_fw_identity(g_fw_expected_version, actualSha);
  if(!metaOk){
    const esp_partition_t *running = esp_ota_get_running_partition();
    if(running) esp_ota_set_boot_partition(running);
    g_fw_update_active = false;
    g_fw_finalized = false;
    fw_send_text(HVP2PRS485::FW_RESULT, frame.seq, "ok=0|reason=metadata");
    boot_set_status("Firmware metadata failed | existing image retained");
    return;
  }
  g_fw_update_active = false;
  g_fw_finalized = true;
  g_fw_final_size = g_fw_received;
  g_fw_final_sha = actualSha;
  Serial.printf("[FW RX] complete %u bytes; reboot requested by CTRL next\n", (unsigned)g_fw_received);
  boot_set_status("Firmware verified | waiting to reboot");
  fw_send_text(HVP2PRS485::FW_RESULT, frame.seq, String("ok=1|size=") + String((unsigned)g_fw_final_size) + "|sha256=" + g_fw_final_sha);
}

static void fw_handle_reboot(const HVP2PRS485::Frame &frame){
  if(!g_fw_finalized){
    fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "reboot_without_verified_image");
    return;
  }
  fw_send_text(HVP2PRS485::ACK, frame.seq, "rebooting");
  g_fw_reboot_due_ms = millis() + 250;
}

static void fw_service_timeout(){
  if(g_fw_update_active && g_fw_last_rx_ms && (millis() - g_fw_last_rx_ms) > FW_RX_TIMEOUT_MS){
    fw_abort("timeout");
  }
}

static inline void rs485_slave_turnaround_guard(){
  // Give the EdgeBox master time to release DE after its final stop bit before
  // the Waveshare auto-direction transceiver starts a reply. 150 us is ~1.7
  // character times at 115200 8N1 and is negligible at the 20 Hz HMI poll rate.
  delayMicroseconds(150);
}

static void process_rs485_frame(const HVP2PRS485::Frame &frame, bool boot_phase){
  last_hmi_rx = millis();
  if(frame.type == HVP2PRS485::HELLO_REQ){
    rs485_slave_turnaround_guard();
    HVP2PRS485::sendText(HMI, HVP2PRS485::HELLO_RESP, frame.seq, fw_identity_line());
    return;
  }
  if(frame.type == HVP2PRS485::COMPATIBLE){
    g_ctrl_fw_compatible = true;
    g_boot_ctrl_confirmed = true;
    if(!g_boot_srvr_confirmed) boot_set_status("CTRL firmware compatible | waiting for SRVR");
    return;
  }
  if(frame.type == HVP2PRS485::TEXT){
    process_text_from_ctrl(HVP2PRS485::payloadString(frame), boot_phase);
    return;
  }
  if(frame.type == HVP2PRS485::POLL){
    // This is the only normal-operating transmit opportunity for CTRL-TS.
    String ev = pop_hmi_event();
    rs485_slave_turnaround_guard();
    HVP2PRS485::sendText(HMI, HVP2PRS485::EVENT, frame.seq, ev);
    return;
  }
  if(frame.type == HVP2PRS485::FW_BEGIN){ fw_handle_begin(frame); return; }
  if(frame.type == HVP2PRS485::FW_BLOCK){ fw_handle_block(frame); return; }
  if(frame.type == HVP2PRS485::FW_END){ fw_handle_end(frame); return; }
  if(frame.type == HVP2PRS485::REBOOT){ fw_handle_reboot(frame); return; }
}

static void handle_hmi_rx(){
  poll_rs485(false);
}

static void create_ui(){
  lv_obj_t *scr=lv_scr_act();
  lv_obj_set_style_bg_color(scr,lv_color_hex(0x0f1316),0);
  lv_obj_set_style_bg_opa(scr,LV_OPA_COVER,0);

  lv_obj_t *frame=lv_obj_create(scr);
  lv_obj_set_pos(frame,0,0); lv_obj_set_size(frame,800,480);
  lv_obj_add_event_cb(frame,bg_event_cb,LV_EVENT_PRESSED,nullptr);
  lv_obj_set_style_bg_color(frame,lv_color_hex(0x0f1316),0); lv_obj_set_style_bg_opa(frame,LV_OPA_COVER,0);
  lv_obj_set_style_border_color(frame,lv_color_hex(0x4a4f52),0); lv_obj_set_style_border_width(frame,1,0);
  lv_obj_set_style_radius(frame,7,0); lv_obj_set_style_pad_all(frame,0,0); lv_obj_clear_flag(frame,LV_OBJ_FLAG_SCROLLABLE);

  const uint32_t C_BG=0x0f1316, C_PANEL=0x171c20, C_BORDER=0x4a4f52, C_FG=0xf0f2f1, C_MUTED=0xaeb4b1, C_CYAN=0x26d5ff, C_GREEN=0x72ed21;
  const int SX=10, SW=780, GAP=6;
  const int HEADER_Y=8, HEADER_H=43;
  const int BANNER_Y=HEADER_Y+HEADER_H+GAP, BANNER_H=32;
  const int AUX_Y=BANNER_Y+BANNER_H+GAP, AUX_H=76;
  const int TRAVEL_Y=AUX_Y+AUX_H+GAP, TRAVEL_H=83;
  const int INFO_Y=TRAVEL_Y+TRAVEL_H+GAP, INFO_H=126;
  const int FOOT_Y=INFO_Y+INFO_H+GAP, FOOT_H=31;

  // Header: locked logo, CTRL/W1P link cards, version.
  lv_obj_t *brand=make_panel(frame,SX,HEADER_Y,70,HEADER_H,C_BG,0x63d84e,7);
  lbl_title=make_label(brand,"HV P2P\nCTRL-TS",0,6,&lv_font_montserrat_12,lv_color_hex(C_FG),70);
  lv_obj_set_style_text_line_space(lbl_title,-2,0);
  lbl_subtitle=make_label(frame,"v26.09.04.02",690,21,&lv_font_montserrat_10,lv_color_hex(C_MUTED),92);

  pill_ctrl=make_panel(frame,255,HEADER_Y,126,HEADER_H,C_PANEL,C_BORDER,5);
  dot_ctrl=lv_obj_create(pill_ctrl); lv_obj_set_pos(dot_ctrl,9,15); lv_obj_set_size(dot_ctrl,8,8); lv_obj_set_style_radius(dot_ctrl,LV_RADIUS_CIRCLE,0); lv_obj_set_style_border_width(dot_ctrl,0,0); lv_obj_set_style_bg_color(dot_ctrl,lv_color_hex(0xef5757),0); lv_obj_clear_flag(dot_ctrl,LV_OBJ_FLAG_SCROLLABLE);
  lbl_ctrl=make_label(pill_ctrl,"CTRL",25,6,&lv_font_montserrat_12,lv_color_hex(C_FG),92);
  lbl_ctrl_ip=make_label(pill_ctrl,g_ctrl_ip.c_str(),25,23,&lv_font_montserrat_10,lv_color_hex(C_MUTED),92);

  pill_w1p=make_panel(frame,389,HEADER_Y,126,HEADER_H,C_PANEL,C_BORDER,5);
  dot_w1p=lv_obj_create(pill_w1p); lv_obj_set_pos(dot_w1p,9,15); lv_obj_set_size(dot_w1p,8,8); lv_obj_set_style_radius(dot_w1p,LV_RADIUS_CIRCLE,0); lv_obj_set_style_border_width(dot_w1p,0,0); lv_obj_set_style_bg_color(dot_w1p,lv_color_hex(0xef5757),0); lv_obj_clear_flag(dot_w1p,LV_OBJ_FLAG_SCROLLABLE);
  lbl_w1p=make_label(pill_w1p,"W1P",25,6,&lv_font_montserrat_12,lv_color_hex(C_FG),92);
  lbl_w1p_ip=make_label(pill_w1p,g_w1p_ip.c_str(),25,23,&lv_font_montserrat_10,lv_color_hex(C_MUTED),92);
  pill_srvr=nullptr; lbl_srvr=nullptr;
  lbl_touch_debug=nullptr; // production face: no service/debug text in the approved header

  pill_estop=make_panel(frame,SX,BANNER_Y,SW,BANNER_H,0x3a1619,0x8b3b42,4);
  lbl_estop=make_label(pill_estop,"◇  E-STOP | CTRL & W1P",0,8,&lv_font_montserrat_14,lv_color_hex(0xef5757),SW);

  // Five AUX cards: same grey/cyan/green visual language as SRVR.
  const int AUX_GAP=6, AUX_W=(SW-(AUX_COUNT-1)*AUX_GAP)/AUX_COUNT;
  const char *aux_heads[AUX_COUNT]={"⚙  AUX 1","⚙  AUX 2","⚙  AUX 3","⚙  AUX 4","⚙  AUX 5"};
  for(int i=0;i<AUX_COUNT;i++){
    aux_btn[i]=make_button(frame,SX+i*(AUX_W+AUX_GAP),AUX_Y,AUX_W,AUX_H);
    lv_obj_add_event_cb(aux_btn[i],aux_event_cb,LV_EVENT_CLICKED,(void*)(intptr_t)i);
    make_label(aux_btn[i],aux_heads[i],8,8,&lv_font_montserrat_10,lv_color_hex(C_CYAN),AUX_W-16);
    aux_text_lbl[i]=make_label(aux_btn[i],aux_action_part(g_aux_labels[i]).c_str(),8,32,&lv_font_montserrat_12,lv_color_hex(C_FG),AUX_W-16);
    aux_state[i]=make_label(aux_btn[i],aux_value_part(g_aux_labels[i]).c_str(),8,52,&lv_font_montserrat_12,lv_color_hex(C_GREEN),AUX_W-16);
  }

  // Cable/travel panel. Presets green, Ref blue, current skate white/green.
  travel_panel=make_panel(frame,SX,TRAVEL_Y,SW,TRAVEL_H,C_PANEL,C_BORDER,4);
  lv_obj_add_event_cb(travel_panel,bg_event_cb,LV_EVENT_PRESSED,nullptr);
  travel_near_lbl=make_label(travel_panel,"NEAR",8,8,&lv_font_montserrat_10,lv_color_hex(C_MUTED),48);
  lbl_near_value=make_label(travel_panel,"0.00 m",8,22,&lv_font_montserrat_10,lv_color_hex(C_FG),48);
  travel_far_lbl=make_label(travel_panel,"FAR",724,8,&lv_font_montserrat_10,lv_color_hex(C_MUTED),48);
  lbl_far_value=make_label(travel_panel,"100.00 m",716,22,&lv_font_montserrat_10,lv_color_hex(C_FG),58);
  travel_ref_lbl=make_label(travel_panel,"REF",332,12,&lv_font_montserrat_10,lv_color_hex(C_GREEN),40);

  // horizontal travel line
  lv_obj_t *track=lv_obj_create(travel_panel); lv_obj_set_pos(track,BAR_LIMIT_LEFT,43); lv_obj_set_size(track,BAR_LIMIT_WIDTH,1); lv_obj_set_style_bg_color(track,lv_color_hex(0xd7dad8),0); lv_obj_set_style_border_width(track,0,0); lv_obj_clear_flag(track,LV_OBJ_FLAG_SCROLLABLE);
  // ramp zones below the line
  ramp_l=make_panel(travel_panel,BAR_LIMIT_LEFT,51,0,7,0x687074,0x687074,0,HV_OPA_35); lv_obj_set_style_border_width(ramp_l,0,0);
  ramp_r=make_panel(travel_panel,BAR_LIMIT_RIGHT,51,0,7,0x687074,0x687074,0,HV_OPA_35); lv_obj_set_style_border_width(ramp_r,0,0);

  travel_near_marker=lv_obj_create(travel_panel); lv_obj_set_pos(travel_near_marker,BAR_LIMIT_LEFT,37); lv_obj_set_size(travel_near_marker,2,14); lv_obj_set_style_bg_color(travel_near_marker,lv_color_hex(0xd7dad8),0); lv_obj_set_style_border_width(travel_near_marker,0,0); lv_obj_clear_flag(travel_near_marker,LV_OBJ_FLAG_SCROLLABLE);
  travel_ref_marker=lv_obj_create(travel_panel); lv_obj_set_pos(travel_ref_marker,360,38); lv_obj_set_size(travel_ref_marker,5,5); lv_obj_set_style_radius(travel_ref_marker,1,0); lv_obj_set_style_bg_color(travel_ref_marker,lv_color_hex(C_GREEN),0); lv_obj_set_style_border_width(travel_ref_marker,0,0); lv_obj_clear_flag(travel_ref_marker,LV_OBJ_FLAG_SCROLLABLE);
  travel_far_marker=lv_obj_create(travel_panel); lv_obj_set_pos(travel_far_marker,BAR_LIMIT_RIGHT,37); lv_obj_set_size(travel_far_marker,2,14); lv_obj_set_style_bg_color(travel_far_marker,lv_color_hex(0xd7dad8),0); lv_obj_set_style_border_width(travel_far_marker,0,0); lv_obj_clear_flag(travel_far_marker,LV_OBJ_FLAG_SCROLLABLE);
  current_marker=lv_obj_create(travel_panel); lv_obj_set_pos(current_marker,BAR_LIMIT_LEFT,35); lv_obj_set_size(current_marker,6,18); lv_obj_set_style_bg_color(current_marker,lv_color_hex(0xf0f2f1),0); lv_obj_set_style_border_color(current_marker,lv_color_hex(0x697074),0); lv_obj_set_style_border_width(current_marker,1,0); lv_obj_clear_flag(current_marker,LV_OBJ_FLAG_SCROLLABLE);

  for(int i=0;i<12;i++){
    preset_line[i]=lv_obj_create(travel_panel); lv_obj_set_size(preset_line[i],1,9); lv_obj_set_style_bg_color(preset_line[i],lv_color_hex(C_GREEN),0); lv_obj_set_style_border_width(preset_line[i],0,0); lv_obj_clear_flag(preset_line[i],LV_OBJ_FLAG_SCROLLABLE); lv_obj_add_flag(preset_line[i],LV_OBJ_FLAG_HIDDEN);
    preset_tri[i]=lv_obj_create(travel_panel); lv_obj_set_size(preset_tri[i],1,1); lv_obj_set_style_bg_opa(preset_tri[i],LV_OPA_TRANSP,0); lv_obj_set_style_border_width(preset_tri[i],0,0); lv_obj_add_flag(preset_tri[i],LV_OBJ_FLAG_HIDDEN);
    preset_lbl[i]=make_label(travel_panel,"",0,28,&lv_font_montserrat_8,lv_color_hex(C_MUTED),42); lv_obj_add_flag(preset_lbl[i],LV_OBJ_FLAG_HIDDEN);
  }

  // Bottom row: Drive / Speed / Position.
  const int DRIVE_W=232, SPEED_W=264, POS_W=272;
  lv_obj_t *drive=make_panel(frame,SX,INFO_Y,DRIVE_W,INFO_H,C_PANEL,C_BORDER,4);
  make_label(drive,"⚙  DRIVE",10,10,&lv_font_montserrat_12,lv_color_hex(C_CYAN),90);
  make_label(drive,"Drive Mode",10,40,&lv_font_montserrat_10,lv_color_hex(C_FG),105); lbl_drive_mode=make_label(drive,g_drive_mode.c_str(),125,40,&lv_font_montserrat_10,lv_color_hex(C_FG),95);
  make_label(drive,"Acceleration Mode",10,68,&lv_font_montserrat_10,lv_color_hex(C_FG),105); lbl_accel_mode=make_label(drive,g_accel_mode.c_str(),125,68,&lv_font_montserrat_10,lv_color_hex(C_FG),95);
  make_label(drive,"Battery Change Mode",10,96,&lv_font_montserrat_10,lv_color_hex(C_FG),105); lbl_battery_mode=make_label(drive,g_battery_mode.c_str(),125,96,&lv_font_montserrat_10,lv_color_hex(C_FG),95);

  lv_obj_t *speed=make_panel(frame,SX+DRIVE_W+GAP,INFO_Y,SPEED_W,INFO_H,C_PANEL,C_BORDER,4);
  make_label(speed,"◴  SPEED",10,10,&lv_font_montserrat_12,lv_color_hex(C_CYAN),90);
  make_label(speed,"CURRENT SPEED",10,39,&lv_font_montserrat_10,lv_color_hex(C_MUTED),110);
  lbl_speed_combo=make_label(speed,"0.0",8,55,&lv_font_montserrat_24,lv_color_hex(C_FG),92); make_label(speed,"m/s",88,68,&lv_font_montserrat_10,lv_color_hex(C_MUTED),36);
  lbl_current_kmh=make_label(speed,"0.0",8,92,&lv_font_montserrat_16,lv_color_hex(C_GREEN),75); make_label(speed,"km/h",80,97,&lv_font_montserrat_10,lv_color_hex(C_MUTED),42);
  make_label(speed,"MAX SPEED",144,39,&lv_font_montserrat_10,lv_color_hex(C_MUTED),100);
  lbl_max_speed=make_label(speed,"0.0",140,55,&lv_font_montserrat_24,lv_color_hex(C_FG),78); make_label(speed,"m/s",211,68,&lv_font_montserrat_10,lv_color_hex(C_MUTED),36);
  lbl_max_kmh=make_label(speed,"0.0",140,92,&lv_font_montserrat_16,lv_color_hex(C_GREEN),75); make_label(speed,"km/h",208,97,&lv_font_montserrat_10,lv_color_hex(C_MUTED),42);

  lv_obj_t *position=make_panel(frame,SX+DRIVE_W+GAP+SPEED_W+GAP,INFO_Y,POS_W,INFO_H,C_PANEL,C_BORDER,4);
  make_label(position,"⌖  POSITION",10,10,&lv_font_montserrat_12,lv_color_hex(C_CYAN),100);
  make_label(position,"CURRENT POSITION",70,37,&lv_font_montserrat_10,lv_color_hex(C_MUTED),132);
  lbl_current_pos=make_label(position,"0.00",66,52,&lv_font_montserrat_24,lv_color_hex(C_GREEN),122); make_label(position,"m",190,67,&lv_font_montserrat_10,lv_color_hex(C_MUTED),24);
  make_label(position,"TO NEAR",18,91,&lv_font_montserrat_10,lv_color_hex(C_MUTED),78); lbl_to_near=make_label(position,"0.00",14,105,&lv_font_montserrat_14,lv_color_hex(C_GREEN),74); make_label(position,"m",85,108,&lv_font_montserrat_10,lv_color_hex(C_MUTED),18);
  make_label(position,"TO FAR",154,91,&lv_font_montserrat_10,lv_color_hex(C_MUTED),70); lbl_to_far=make_label(position,"0.00",150,105,&lv_font_montserrat_14,lv_color_hex(C_GREEN),70); make_label(position,"m",220,108,&lv_font_montserrat_10,lv_color_hex(C_MUTED),18);
  middle_panel=position; cell_to_near=position; cell_speed=speed; cell_to_far=position;

  lv_obj_t *footer=make_panel(frame,SX,FOOT_Y,SW,FOOT_H,C_PANEL,C_BORDER,4);
  make_label(footer,"SRVR TIME",12,9,&lv_font_montserrat_10,lv_color_hex(C_MUTED),66);
  lbl_srvr_time=make_label(footer,g_srvr_time.c_str(),82,8,&lv_font_montserrat_10,lv_color_hex(C_FG),180);
  make_label(footer,"UPTIME",648,9,&lv_font_montserrat_10,lv_color_hex(C_MUTED),55);
  lbl_uptime=make_label(footer,g_uptime.c_str(),705,8,&lv_font_montserrat_10,lv_color_hex(C_FG),68);

  // Network settings code remains compiled for service builds, but the locked
  // production face has no separate Settings control. Network values are owned
  // by CTRL/SRVR Setup, keeping the touchscreen surface visually identical.

  update_reference_marker();
  update_ramp_markers();
  update_preset_markers();
  update_progress_marker();
  refresh_status_ui();
  for(int i=0;i<AUX_COUNT;i++) refresh_aux_text(i);
  set_touch_debug("Ready");
  g_ui_ready = true;
}


static void service_link_state(){
  if(selected_aux >= 0 && g_selected_aux_ms && (millis() - g_selected_aux_ms > AUX_PENDING_TIMEOUT_MS)){
    cancel_pending_aux();
  }
  if(confirmed_aux>=0 && millis()>clear_confirm_at) {
    style_aux(confirmed_aux,false,false);
    confirmed_aux=-1;
    lv_label_set_text(lbl_touch_debug,"Ready");
  }

  bool link_alive = last_hmi_rx && ((millis() - last_hmi_rx) <= HMI_TIMEOUT_MS);
  if(!link_alive) {
    // v26.09.04.02: local UART/display timeout is a CTRL-TS link warning, not
    // proof of a real CTRL E-Stop. Keep the last SRVR-resolved status banner so
    // the touchscreen cannot randomly show "Status | E-Stop CTRL" while SRVR
    // remains "Status | Active". The CTRL status pill can still show ERROR.
    bool changed = g_ctrl_ok;
    g_ctrl_ok = false;
    if(changed) refresh_status_ui();
    set_touch_debug("ERROR: CTRL-TS RS485");
  }
}

void setup(){
  Serial.begin(115200);
  delay(200);
  Serial.println(CTRL_TS_VERSION);
  load_fw_identity();
  Serial.printf("[FW RX] identity hash=%s\n", g_fw_image_hash.c_str());
  Serial.println("[WS-HMI] boot: starting framed RS485 thin-HMI runtime");
  HMI.begin(HMI_BAUD, SERIAL_8N1, HMI_UART_RX, HMI_UART_TX);
  g_uart_ok = true;
  Serial.printf("[WS-HMI] onboard RS485 RX=%d TX=%d baud=%d (auto direction)\n", HMI_UART_RX, HMI_UART_TX, HMI_BAUD);
  Serial.println("[WS-HMI] boot: lcd_init()");
  lcd_init();
  Serial.println("[WS-HMI] boot: splash");
  show_boot_splash();
  Serial.println("[WS-HMI] boot: create main UI");
  lvgl_port_lock(-1);
  lv_obj_t *old_boot_scr = boot_scr;
  lv_obj_t *main_scr = lv_obj_create(NULL);
  lv_obj_clear_flag(main_scr, LV_OBJ_FLAG_SCROLLABLE);
  lv_scr_load(main_scr);
  if(old_boot_scr) lv_obj_del(old_boot_scr);
  boot_scr = nullptr;
  boot_status_bar = nullptr;
  boot_status_lbl = nullptr;
  boot_canvas = nullptr;
  if(boot_canvas_buf){
    free(boot_canvas_buf);
    boot_canvas_buf = nullptr;
  }
  create_ui();
  if(g_pending_boot_hmi_line.length() && is_valid_hmi_packet(g_pending_boot_hmi_line)){
    apply_hmi_packet(g_pending_boot_hmi_line);
  }
  // v18: no forced full-screen refresh after applying pending HMI state.
  lvgl_port_unlock();
  delay(50);
  Serial.println("[WS-HMI] boot: UI ready after CTRL and SRVR confirmed");

}

void loop(){
  if((g_settings_reset_due_ms && millis() >= g_settings_reset_due_ms) || (g_fw_reboot_due_ms && millis() >= g_fw_reboot_due_ms)){
    ESP.restart();
  }
  lvgl_port_lock(-1);
  handle_hmi_rx();
  service_link_state();
  screen_keepalive();
  lvgl_port_unlock();
  fw_service_timeout();
  delay(20);
}
