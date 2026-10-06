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
#include <esp_system.h>
#include <esp_attr.h>

#define CTRL_TS_SEMVER "v26.10.06.06"
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
static const uint8_t HMI_EVENT_QUEUE_SIZE = 8;
static const size_t HMI_EVENT_TEXT_MAX = 224;
struct HmiQueuedEvent { uint16_t id; char text[HMI_EVENT_TEXT_MAX]; };
static HmiQueuedEvent g_event_queue[HMI_EVENT_QUEUE_SIZE];
static uint16_t g_next_event_id = 1;
static uint32_t g_event_queue_drops = 0;
static uint32_t g_last_event_diag_ms = 0;
static uint8_t g_event_head = 0, g_event_tail = 0;
// LVGL callbacks execute in the Waveshare LVGL task. Keep them heap-free and
// side-effect-free: a touch callback only queues an AUX index, and the Arduino
// main loop performs all AUX state/UI/protocol work under the LVGL mutex.
static portMUX_TYPE g_aux_touch_mux = portMUX_INITIALIZER_UNLOCKED;
static uint8_t g_aux_touch_queue[8] = {0};
static volatile uint8_t g_aux_touch_head = 0, g_aux_touch_tail = 0;
static volatile bool g_aux_cancel_pending = false;
static uint32_t g_boot_id = 0;
static esp_reset_reason_t g_boot_reset_reason = ESP_RST_UNKNOWN;

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
static const uint32_t RS485_SLAVE_TURNAROUND_US = 2500;
static const size_t FW_MAX_IMAGE_SIZE = 0x380000; // matches the conservative app0/app1 slot size
// ESP32 Arduino Update.write() takes a mutable buffer even though it does not
// need to modify the received block. Keep the parsed RS485 frame const and copy
// only the OTA data bytes into this dedicated scratch buffer before writing.
static uint8_t g_fw_write_buf[HVP2PRS485::MAX_PAYLOAD - 4];
// CTRL-TS never programs its own flash while the RGB/LVGL panel is running.
// A received FW_BEGIN stages its exact target ONLY in internal no-init RAM, then
// software-reboots into a headless RS485 updater with the panel reset/backlight
// held off. The live RGB runtime therefore performs no OTA *or NVS* flash write
// during this handoff; both can suspend external-memory access on ESP32-S3.
// The handoff is accepted only after our deliberate software reset and is guarded
// by magic + format checks + checksum, so a power cycle safely returns to normal.
static bool g_fw_headless_mode = false;
static String g_fw_headless_target_version;
static String g_fw_headless_target_sha;
static uint32_t g_fw_safe_reboot_due_ms = 0;
static uint32_t g_fw_headless_entered_ms = 0;
static const uint32_t FW_HEADLESS_IDLE_RETURN_MS = 60000;
// LVGL 8.3 provides 10%% opacity steps only. Preserve the approved 35%% ramp
// appearance with an explicit 8-bit opacity value (round(0.35 * 255) = 89).
static constexpr lv_opa_t HV_OPA_35 = (lv_opa_t)89;


// Boot splash support. Put splash.jpg in the root of the Waveshare microSD card.
// WS-27078 is the ESP32-S3-Touch-LCD-7: native 800x480 panel.
static const char* SPLASH_FILENAME = "/splash.jpg";
static const uint32_t SPLASH_HOLD_MS = 10000;
static const int SPLASH_CANVAS_W = 800;
static const int SPLASH_CANVAS_H = 480;
static const int SPLASH_STATUS_H = 58;
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
static lv_obj_t *boot_progress_bar = nullptr;
static lv_obj_t *boot_canvas = nullptr;
static lv_obj_t *g_main_scr = nullptr;
static lv_obj_t *g_fw_screen = nullptr;
static lv_obj_t *g_fw_connection_lbl = nullptr;
static lv_obj_t *g_fw_row_lbl[3] = {nullptr,nullptr,nullptr};
static lv_obj_t *g_fw_row_bar[3] = {nullptr,nullptr,nullptr};
static bool g_fw_row_active[3] = {false,false,false};
static int g_fw_row_pct[3] = {0,0,0};
static String g_fw_row_phase[3] = {"Idle","Idle","Idle"};
static bool g_fw_runtime_screen = false;
static int g_fw_last_display_pct = -1;
static uint32_t g_fw_external_release_due_ms = 0;
static lv_color_t *boot_canvas_buf = nullptr;
static lv_color_t *boot_decode_buf = nullptr;
static int boot_w = 0;
static int boot_h = 0;
static int boot_decode_w = 0;
static int boot_decode_h = 0;
static JPEGDEC boot_jpeg;
static bool g_boot_ctrl_confirmed = false;
static bool g_boot_srvr_confirmed = false;
static uint32_t g_boot_last_ping_ms = 0;
static uint32_t g_boot_last_layout_req_ms = 0;
static String g_boot_rx_line;
static String g_boot_status_cache;
static String g_pending_boot_hmi_line;
static String g_pending_runtime_state_line;
static String g_pending_runtime_geometry_line;
static String g_pending_runtime_motion_line;
static String g_pending_runtime_bulk_line;


// -------------------- Framed RS485 thin-HMI link --------------------
// Waveshare is intentionally not an Ethernet node in this architecture.
// It is flashed once with this generic LVGL runtime, then receives layout/state
// from the EdgeBox CTRL over framed RS485 and returns queued touch events only when polled.
static bool g_uart_ok = false;
static bool g_ui_ready = false;
static bool g_connection_splash_active = false;
static uint32_t g_last_screen_keepalive_ms = 0;
static String g_rx_line;

static lv_obj_t *lbl_to_near,*lbl_to_far,*lbl_speed_combo,*lbl_touch_debug,*current_marker,*travel_near_marker,*travel_ref_marker,*travel_far_marker,*aux_btn[AUX_COUNT],*aux_state[AUX_COUNT];
static lv_obj_t *lbl_title,*lbl_subtitle;
static lv_obj_t *travel_panel,*travel_near_lbl,*travel_ref_lbl,*travel_far_lbl,*ramp_l,*ramp_r;
static const int RAMP_STRIP_COUNT = 10;
static lv_obj_t *ramp_l_strip[RAMP_STRIP_COUNT] = {nullptr};
static lv_obj_t *ramp_r_strip[RAMP_STRIP_COUNT] = {nullptr};
static lv_obj_t *preset_line[12], *preset_lbl[12], *preset_tri[12];
static lv_obj_t *pill_ctrl,*pill_srvr,*pill_w1p,*lbl_ctrl,*lbl_srvr,*lbl_w1p;
static lv_obj_t *dot_ctrl,*dot_w1p,*lbl_ctrl_ip,*lbl_w1p_ip;
static lv_obj_t *pill_estop,*lbl_estop;
static lv_obj_t *middle_panel,*cell_to_near,*cell_speed,*cell_to_far;
static lv_obj_t *lbl_max_speed,*lbl_current_kmh,*lbl_max_kmh,*lbl_current_pos;
static lv_obj_t *lbl_drive_mode,*lbl_accel_mode,*lbl_battery_mode,*lbl_srvr_time,*lbl_uptime,*lbl_near_value,*lbl_far_value;
static lv_obj_t *aux_text_lbl[AUX_COUNT];
static lv_obj_t *g_cal_overlay=nullptr,*g_cal_title_lbl=nullptr,*g_cal_step_lbl=nullptr,*g_cal_instruction_lbl=nullptr;
static lv_obj_t *g_cal_value_box[3]={nullptr,nullptr,nullptr};
static lv_obj_t *g_cal_value_name[3]={nullptr,nullptr,nullptr};
static lv_obj_t *g_cal_value_text[3]={nullptr,nullptr,nullptr};
static lv_obj_t *g_cal_current_lbl=nullptr,*g_cal_cancel_btn=nullptr;
static volatile bool g_cal_cancel_requested=false;
static bool g_calibration_overlay_active=false;
static String g_last_cal_overlay_title="";
static String g_last_cal_overlay_kind="";
static int g_last_cal_overlay_step=-1;
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
// Canonical SRVR-derived normalized positions. These are carried explicitly so
// the CTRL-TS travel markers cannot diverge from the SRVR Top/Side views through
// local coordinate interpretation or stale absolute/relative limits.
static float g_pos_frac=0.0f, g_ref_frac=0.5f;
// Display-only motion interpolation. Control/safety always uses verified SRVR/W1P
// telemetry; these values only make the travel marker fluid between ~10 Hz HMM1
// samples. Prediction is tightly bounded so a stale link cannot visually run away.
static float g_motion_sample_frac=0.0f;
static float g_motion_sample_speed_mps=0.0f;
static float g_progress_display_frac=0.0f;
static uint32_t g_motion_sample_ms=0;
static uint32_t g_progress_service_ms=0;
static bool g_motion_sample_valid=false;
static bool g_progress_display_valid=false;
static bool g_ref_visible = true;
static float g_speed_mps=0.0f, g_speed_kmh=0.0f, g_max_mps=0.0f, g_max_kmh=0.0f;
static float g_ramp_near=0.0f, g_ramp_far=0.0f;
static float g_ramp_near_frac=-1.0f, g_ramp_far_frac=-1.0f;
static String g_mode="Mode 1";
static String g_drive_mode="Mode A";
static String g_accel_mode="Speed";
static String g_battery_mode="Off";
static String g_srvr_time="---- -- --  --:--:--";
static String g_uptime="00:00:00";
static String g_ctrl_ip="172.20.1.101";
static String g_w1p_ip="172.20.1.102";
static String g_aux_labels[AUX_COUNT] = {"AUX 1","AUX 2","AUX 3","AUX 4","AUX 5"};
static String g_preset_names[12] = {"","","","","","","","","","","",""};
static float g_preset_pos[12] = {0,0,0,0,0,0,0,0,0,0,0,0};
static bool g_preset_visible[12] = {false,false,false,false,false,false,false,false,false,false,false,false};
static int g_preset_count = 12;

// The travel line spans the full usable width of the 780 px travel panel.
// NEAR/FAR labels sit above it and must not shorten the actual position scale.
static const int BAR_LIMIT_LEFT = 8;
static const int BAR_LIMIT_RIGHT = 772;
static const int BAR_LIMIT_WIDTH = BAR_LIMIT_RIGHT - BAR_LIMIT_LEFT;
static uint32_t g_last_aux_physical_ms[AUX_COUNT] = {0,0,0,0,0};
static uint32_t g_last_aux_touch_ms[AUX_COUNT] = {0,0,0,0,0};
static uint32_t g_selected_aux_ms = 0;
static const uint32_t AUX_PENDING_TIMEOUT_MS = 3000;
static const uint32_t AUX_TOUCH_DEBOUNCE_MS = 35;
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
// Safe v26.10.06.06 approach: no backlight/brightness writes. This page only
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
  // v26.10.06.06: no periodic full-screen or left-strip invalidation or brightness writes.
  // The Waveshare/LVGL port refreshes changed objects itself; forcing a full
  // screen refresh every second caused the visible 1-second flicker/glitch.
  if(!g_ui_ready) return;
}

static void set_label_text_if_changed(lv_obj_t *lbl, const char *txt){
  if(!lbl || !txt) return;
  const char *cur = lv_label_get_text(lbl);
  if(cur && strcmp(cur, txt) == 0) return;
  // LVGL invalidates the label as part of lv_label_set_text(). Do not issue a
  // second explicit invalidate: on the RGB panel that doubles redraw traffic and
  // materially worsens PSRAM/DMA contention during fast HMI updates.
  lv_label_set_text(lbl, txt);
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


static void boot_set_progress(int pct){
  if(!boot_progress_bar) return;
  pct = constrain(pct, 0, 100);
  lvgl_port_lock(-1);
  lv_bar_set_value(boot_progress_bar, pct, LV_ANIM_OFF);
  if(g_fw_update_active || g_fw_finalized || g_fw_reboot_due_ms) lv_obj_clear_flag(boot_progress_bar, LV_OBJ_FLAG_HIDDEN);
  else lv_obj_add_flag(boot_progress_bar, LV_OBJ_FLAG_HIDDEN);
  lv_obj_invalidate(boot_progress_bar);
  lvgl_port_unlock();
}

static void boot_set_status(const char *txt){
  String next = String(txt ? txt : "");
  // Firmware transfer owns the splash status region. Generic boot/link messages
  // must not overwrite progress between FW_BLOCK packets.
  if((g_fw_update_active || g_fw_finalized || g_fw_reboot_due_ms) &&
     !next.startsWith("Updating CTRL-TS firmware") && !next.startsWith("Firmware") &&
     !next.startsWith("Verifying CTRL-TS firmware") && !next.startsWith("CTRL Connected | SRVR")) return;
  if(next == g_boot_status_cache) return;
  g_boot_status_cache = next;
  if(!boot_status_lbl) return;
  lvgl_port_lock(-1);
  lv_label_set_text(boot_status_lbl, next.c_str());
  lv_obj_invalidate(boot_status_lbl);
  lvgl_port_unlock();
  Serial.print("[BOOT] "); Serial.println(next);
}

static String boot_get_field(const String &line, const char *key);

static bool fw_any_row_active(){
  return g_fw_row_active[0] || g_fw_row_active[1] || g_fw_row_active[2];
}

static bool fw_display_owned(){
  return bool(g_fw_update_active || g_fw_finalized || g_fw_reboot_due_ms || g_fw_safe_reboot_due_ms ||
              fw_any_row_active() || g_fw_external_release_due_ms);
}

static String fw_connection_text(){
  return String("CTRL ") + (g_boot_ctrl_confirmed ? "Connected" : "Waiting") +
         " | SRVR " + (g_boot_srvr_confirmed ? "Connected" : "Waiting");
}

static int fw_device_index(const String &device){
  String d=device; d.toUpperCase();
  if(d == "W1P") return 0;
  if(d == "CTRL") return 1;
  if(d == "CTRL-TS" || d == "CTRL_TS" || d == "CTRLTS") return 2;
  return -1;
}

static const char* fw_device_name(int idx){
  static const char *NAMES[3] = {"W1P", "CTRL", "CTRL-TS"};
  return (idx>=0 && idx<3) ? NAMES[idx] : "NODE";
}

static void fw_ensure_update_screen(){
  if(g_fw_headless_mode) return;
  if(g_fw_screen){
    if(lv_scr_act() != g_fw_screen) lv_scr_load(g_fw_screen);
    g_fw_runtime_screen = true;
    return;
  }
  lvgl_port_lock(-1);
  const int w = lv_disp_get_hor_res(NULL) > 0 ? lv_disp_get_hor_res(NULL) : 800;
  g_fw_screen = lv_obj_create(NULL);
  lv_obj_clear_flag(g_fw_screen, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_style_bg_color(g_fw_screen, lv_color_hex(0x06101c), 0);
  lv_obj_set_style_bg_opa(g_fw_screen, LV_OPA_COVER, 0);

  lv_obj_t *title = lv_label_create(g_fw_screen);
  lv_label_set_text(title, "HV P2P\nFirmware Update");
  lv_obj_set_style_text_font(title, &lv_font_montserrat_24, 0);
  lv_obj_set_style_text_color(title, lv_color_hex(0xf0f2f1), 0);
  lv_obj_set_style_text_align(title, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_width(title, w);
  lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 44);

  g_fw_connection_lbl = lv_label_create(g_fw_screen);
  lv_label_set_text(g_fw_connection_lbl, fw_connection_text().c_str());
  lv_obj_set_style_text_font(g_fw_connection_lbl, &lv_font_montserrat_14, 0);
  lv_obj_set_style_text_color(g_fw_connection_lbl, lv_color_hex(0x72ed21), 0);
  lv_obj_set_style_text_align(g_fw_connection_lbl, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_width(g_fw_connection_lbl, w);
  lv_obj_align(g_fw_connection_lbl, LV_ALIGN_TOP_MID, 0, 112);

  for(int i=0;i<3;i++){
    const int y = 170 + i*88;
    g_fw_row_lbl[i] = lv_label_create(g_fw_screen);
    String initial = String(fw_device_name(i)) + " | Waiting";
    lv_label_set_text(g_fw_row_lbl[i], initial.c_str());
    lv_obj_set_style_text_font(g_fw_row_lbl[i], &lv_font_montserrat_16, 0);
    lv_obj_set_style_text_color(g_fw_row_lbl[i], lv_color_hex(0xd8ecff), 0);
    lv_obj_set_width(g_fw_row_lbl[i], w-160);
    lv_obj_align(g_fw_row_lbl[i], LV_ALIGN_TOP_MID, 0, y);

    g_fw_row_bar[i] = lv_bar_create(g_fw_screen);
    lv_obj_set_size(g_fw_row_bar[i], w-160, 16);
    lv_obj_align(g_fw_row_bar[i], LV_ALIGN_TOP_MID, 0, y+31);
    lv_bar_set_range(g_fw_row_bar[i], 0, 100);
    lv_bar_set_value(g_fw_row_bar[i], 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(g_fw_row_bar[i], lv_color_hex(0x203142), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(g_fw_row_bar[i], LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_bg_color(g_fw_row_bar[i], lv_color_hex(0x49d8ff), LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(g_fw_row_bar[i], LV_OPA_COVER, LV_PART_INDICATOR);
  }

  lv_scr_load(g_fw_screen);
#if defined(LV_VERSION_MAJOR) && (LV_VERSION_MAJOR >= 8)
  // Render this dashboard once while the normal UI is still alive. CTRL-TS
  // self-flash does not occur in this RGB/LVGL runtime; the panel is blacked out
  // and the ESP32 reboots into the headless updater before any flash write.
  lv_refr_now(NULL);
#endif
  g_fw_runtime_screen = true;
  g_boot_status_cache = "";
  lvgl_port_unlock();
}

static void fw_set_device_status(const String &device, const String &phase, int pct, bool active){
  const int idx = fw_device_index(device);
  if(idx < 0) return;
  pct = constrain(pct, 0, 100);
  const bool wasActive = g_fw_row_active[idx];
  if(g_fw_headless_mode){
    g_fw_row_active[idx] = active;
    g_fw_row_pct[idx] = pct;
    g_fw_row_phase[idx] = phase.length() ? phase : (active ? "Updating" : "Idle");
    return;
  }
  if(!active && !fw_any_row_active() && !g_fw_update_active && !g_fw_finalized && !g_fw_reboot_due_ms && !g_fw_external_release_due_ms){
    g_fw_row_active[idx] = false;
    g_fw_row_pct[idx] = pct;
    g_fw_row_phase[idx] = phase.length() ? phase : "Idle";
    return;
  }
  fw_ensure_update_screen();
  g_fw_row_active[idx] = active;
  g_fw_row_pct[idx] = pct;
  g_fw_row_phase[idx] = phase.length() ? phase : (active ? "Updating" : "Idle");
  lvgl_port_lock(-1);
  if(g_fw_connection_lbl) set_label_text_if_changed(g_fw_connection_lbl, fw_connection_text().c_str());
  if(g_fw_row_lbl[idx]){
    String text = String(fw_device_name(idx)) + " | " + g_fw_row_phase[idx] + " | " + String(pct) + "%";
    set_label_text_if_changed(g_fw_row_lbl[idx], text.c_str());
  }
  if(g_fw_row_bar[idx] && lv_bar_get_value(g_fw_row_bar[idx]) != pct){
    lv_bar_set_value(g_fw_row_bar[idx], pct, LV_ANIM_OFF);
    lv_obj_invalidate(g_fw_row_bar[idx]);
  }
  lvgl_port_unlock();
  if(active) {
    g_fw_external_release_due_ms = 0;
  } else if(wasActive && !fw_any_row_active() && !g_fw_update_active && !g_fw_finalized && !g_fw_reboot_due_ms && !g_fw_external_release_due_ms) {
    // Schedule this once on the active->complete transition. Repeated inactive
    // HMS1/HMI1 keepalives must never keep extending firmware-screen ownership.
    g_fw_external_release_due_ms = millis() + 2000;
  }
}

static void fw_process_status_line(const String &line){
  String device = boot_get_field(line, "device");
  String phase = boot_get_field(line, "phase");
  String pctText = boot_get_field(line, "pct");
  String activeText = boot_get_field(line, "active");
  const bool active = !(activeText == "0" || activeText == "false" || activeText == "off");
  fw_set_device_status(device, phase, pctText.length() ? pctText.toInt() : 0, active);
}

static void fw_set_status_pct(const char *phase, int pct){
  pct = constrain(pct, 0, 100);
  if(pct == g_fw_last_display_pct && String(phase ? phase : "") == g_fw_row_phase[2]) return;
  g_fw_last_display_pct = pct;
  fw_set_device_status("CTRL-TS", String(phase ? phase : "Updating"), pct, true);
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

static bool queue_hmi_event(const char *line){
  if(!line || !*line) return false;
  uint8_t next = uint8_t((g_event_head + 1) % HMI_EVENT_QUEUE_SIZE);
  if(next == g_event_tail) { g_event_queue_drops++; return false; }
  HmiQueuedEvent &slot = g_event_queue[g_event_head];
  slot.id = g_next_event_id++;
  if(g_next_event_id == 0) g_next_event_id = 1;
  strlcpy(slot.text, line, sizeof(slot.text));
  g_event_head = next;
  return true;
}
static const HmiQueuedEvent* peek_hmi_event(){
  if(g_event_tail == g_event_head) return nullptr;
  return &g_event_queue[g_event_tail];
}
static bool ack_hmi_event(uint16_t eventId){
  if(g_event_tail == g_event_head) return false;
  HmiQueuedEvent &slot = g_event_queue[g_event_tail];
  if(slot.id != eventId) return false;
  slot.id = 0; slot.text[0] = '\0';
  g_event_tail = uint8_t((g_event_tail + 1) % HMI_EVENT_QUEUE_SIZE);
  return true;
}
static bool queue_aux_touch(uint8_t idx){
  if(idx >= AUX_COUNT) return false;
  // LVGL CLICKED already represents one complete press/release. Debounce only
  // pathological duplicate callbacks here, before the event enters the queue.
  // Two deliberate taps may therefore arrive back-to-back and are both kept,
  // even if the main loop services them in the same iteration.
  const uint32_t now_ms = millis();
  if(g_last_aux_touch_ms[idx] && (now_ms - g_last_aux_touch_ms[idx]) < AUX_TOUCH_DEBOUNCE_MS) return false;
  bool ok = false;
  portENTER_CRITICAL(&g_aux_touch_mux);
  uint8_t next = uint8_t((g_aux_touch_head + 1) % 8);
  if(next != g_aux_touch_tail){
    g_aux_touch_queue[g_aux_touch_head] = idx;
    g_aux_touch_head = next;
    g_last_aux_touch_ms[idx] = now_ms;
    ok = true;
  }
  portEXIT_CRITICAL(&g_aux_touch_mux);
  return ok;
}
static int pop_aux_touch(){
  int idx = -1;
  portENTER_CRITICAL(&g_aux_touch_mux);
  if(g_aux_touch_tail != g_aux_touch_head){
    idx = int(g_aux_touch_queue[g_aux_touch_tail]);
    g_aux_touch_tail = uint8_t((g_aux_touch_tail + 1) % 8);
  }
  portEXIT_CRITICAL(&g_aux_touch_mux);
  return idx;
}
static void queue_aux_cancel(){
  portENTER_CRITICAL(&g_aux_touch_mux);
  g_aux_cancel_pending = true;
  portEXIT_CRITICAL(&g_aux_touch_mux);
}
static bool pop_aux_cancel(){
  bool pending = false;
  portENTER_CRITICAL(&g_aux_touch_mux);
  pending = g_aux_cancel_pending;
  g_aux_cancel_pending = false;
  portEXIT_CRITICAL(&g_aux_touch_mux);
  return pending;
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


struct FwSafeHandoff {
  uint32_t magic;
  uint32_t checksum;
  char version[24];
  char sha[65];
};

// __NOINIT_ATTR places this tiny handoff in internal DRAM without startup
// initialisation. ESP.restart() leaves it intact; power/hardware resets are never
// accepted because fw_prepare_headless_mode() additionally requires ESP_RST_SW.
// Do not add an initializer here: that would defeat the no-init contract.
__NOINIT_ATTR FwSafeHandoff g_fw_safe_handoff;
static constexpr uint32_t FW_SAFE_HANDOFF_MAGIC = 0x48565032UL; // "HVP2"

static bool fw_safe_version_valid(const char *v){
  if(!v) return false;
  // Release authority uses the fixed vYY.MM.DD.RR form. Keep the handoff parser
  // intentionally strict because it operates on RAM retained across a restart.
  if(strnlen(v, sizeof(g_fw_safe_handoff.version)) != 12) return false;
  if(v[0] != 'v' || v[3] != '.' || v[6] != '.' || v[9] != '.') return false;
  for(int i=1; i<12; ++i){
    if(i==3 || i==6 || i==9) continue;
    if(v[i] < '0' || v[i] > '9') return false;
  }
  return true;
}

static bool fw_safe_sha_valid(const char *sha){
  if(!sha || strnlen(sha, sizeof(g_fw_safe_handoff.sha)) != 64) return false;
  for(int i=0; i<64; ++i){
    const char c = sha[i];
    const bool hex = (c>='0' && c<='9') || (c>='a' && c<='f') || (c>='A' && c<='F');
    if(!hex) return false;
  }
  return true;
}

static uint32_t fw_safe_handoff_checksum(const char *version, const char *sha){
  // FNV-1a is not an authentication primitive and does not need to be: the OTA
  // image still receives its normal SHA-256 verification. This checksum exists
  // only to reject stale/random no-init RAM before entering display-off mode.
  uint32_t h = 2166136261UL;
  const char *parts[2] = {version, sha};
  for(int p=0; p<2; ++p){
    for(const char *q=parts[p]; q && *q; ++q){ h ^= uint8_t(*q); h *= 16777619UL; }
    h ^= 0xFF; h *= 16777619UL;
  }
  return h;
}

static void fw_clear_safe_update_handoff(){
  // Clear magic first so a reset at any later instruction cannot expose a
  // half-cleared structure as a valid update request.
  g_fw_safe_handoff.magic = 0;
  __sync_synchronize();
  g_fw_safe_handoff.checksum = 0;
  g_fw_safe_handoff.version[0] = '\0';
  g_fw_safe_handoff.sha[0] = '\0';
  g_fw_headless_target_version = "";
  g_fw_headless_target_sha = "";
}

static bool fw_stage_safe_update_handoff(const String &targetVersion, const String &targetSha){
  String normalizedSha = targetSha;
  normalizedSha.toLowerCase();
  if(!fw_safe_version_valid(targetVersion.c_str()) || !fw_safe_sha_valid(normalizedSha.c_str())) return false;

  // Commit protocol: invalidate magic -> copy complete payload/checksum -> publish
  // magic last. This operation touches internal RAM only; no Preferences/NVS call
  // is permitted while the RGB/LVGL runtime is active.
  g_fw_safe_handoff.magic = 0;
  __sync_synchronize();
  memset(g_fw_safe_handoff.version, 0, sizeof(g_fw_safe_handoff.version));
  memset(g_fw_safe_handoff.sha, 0, sizeof(g_fw_safe_handoff.sha));
  targetVersion.toCharArray(g_fw_safe_handoff.version, sizeof(g_fw_safe_handoff.version));
  normalizedSha.toCharArray(g_fw_safe_handoff.sha, sizeof(g_fw_safe_handoff.sha));
  g_fw_safe_handoff.checksum = fw_safe_handoff_checksum(g_fw_safe_handoff.version, g_fw_safe_handoff.sha);
  __sync_synchronize();
  g_fw_safe_handoff.magic = FW_SAFE_HANDOFF_MAGIC;
  __sync_synchronize();
  return true;
}

static bool fw_prepare_headless_mode(){
  // A retained RAM marker is meaningful only after the deliberate ESP.restart()
  // requested by FW_BEGIN. Power-on, brownout, watchdog and external resets all
  // discard/ignore it and bring up the normal UI instead.
  if(esp_reset_reason() != ESP_RST_SW){
    fw_clear_safe_update_handoff();
    return false;
  }
  __sync_synchronize();
  if(g_fw_safe_handoff.magic != FW_SAFE_HANDOFF_MAGIC) return false;
  if(!fw_safe_version_valid(g_fw_safe_handoff.version) || !fw_safe_sha_valid(g_fw_safe_handoff.sha)){
    fw_clear_safe_update_handoff();
    return false;
  }
  const uint32_t expected = fw_safe_handoff_checksum(g_fw_safe_handoff.version, g_fw_safe_handoff.sha);
  if(expected != g_fw_safe_handoff.checksum){
    fw_clear_safe_update_handoff();
    return false;
  }

  // Copy the validated target into ordinary runtime objects, then consume the
  // no-init marker immediately. If headless update later crashes/restarts, the
  // unit returns to its known-good application rather than becoming boot-looped.
  g_fw_headless_target_version = String(g_fw_safe_handoff.version);
  g_fw_headless_target_sha = String(g_fw_safe_handoff.sha);
  g_fw_safe_handoff.magic = 0;
  __sync_synchronize();
  g_fw_headless_mode = true;
  g_fw_headless_entered_ms = millis();
  return true;
}

static void fw_clear_headless_update_state(){
  fw_clear_safe_update_handoff();
  g_fw_headless_mode = false;
  g_fw_headless_entered_ms = 0;
}

static bool fw_headless_blackout(){
  // The normal runtime already drove LCD_BL LOW and LCD_RST LOW through the
  // known-good Waveshare/CH422G instance immediately before ESP.restart().
  // Do NOT instantiate or re-initialize the CH422G here: on this board that
  // would create a second I2C/display bring-up path before the Waveshare stack
  // exists, which can itself stall/crash the safe-update boot. The CH422G is
  // external to the ESP32 and retains its output latch across a software reset.
  // Headless safety comes from *not starting* RGB/LVGL/PSRAM at all on this boot.
  Serial.println("[FW SAFE] headless boot: RGB/LVGL/PSRAM display stack remains uninitialized");
  return true;
}

static void fw_service_headless_idle_return(){
  if(!g_fw_headless_mode || g_fw_update_active || g_fw_finalized) return;
  const uint32_t now = millis();
  // Bound the display-off wait even if an incompatible/stale CTRL continues to
  // send HELLO traffic. Generic RS485 activity must not keep the panel black
  // forever; a real transfer suppresses this guard via g_fw_update_active.
  if(g_fw_headless_entered_ms && (now - g_fw_headless_entered_ms) >= FW_HEADLESS_IDLE_RETURN_MS){
    Serial.println("[FW SAFE] no firmware transfer started for 60 s; returning to normal UI");
    fw_clear_headless_update_state();
    delay(20);
    ESP.restart();
  }
}

static String fw_identity_line(){
  // safe_ota is a protocol capability LEVEL, not a boolean. Level 1 was the
  // first .03 headless-updater attempt; level 2 fixes its reboot/discovery race
  // and removes the risky second CH422G initialization on the headless boot.
  // CTRL .04+ therefore streams self-update data only to level 2 or newer.
  return String("hw=") + CTRL_TS_HW_ID + "|proto=" + String(HVP2PRS485::PROTOCOL_VERSION) +
         "|version=" + String(CTRL_TS_SEMVER) + "|hash=" + g_fw_image_hash + "|safe_ota=2" +
         "|boot_id=" + String((unsigned long)g_boot_id, HEX) +
         "|reset_reason=" + String((int)g_boot_reset_reason);
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
      else if(g_boot_ctrl_confirmed) boot_set_status("Waiting for SRVR");
      else boot_set_status("Waiting for CTRL");
    }
  } else if(line == "PONG"){
    g_boot_ctrl_confirmed = true;
    last_hmi_rx = millis();
    if(!g_boot_srvr_confirmed) boot_set_status("Waiting for SRVR");
  }
}

static void process_rs485_frame(const HVP2PRS485::Frame &frame, bool boot_phase);
static void fw_service_timeout();
static void fw_service_reboot();

static void poll_rs485(bool boot_phase){
  while(HMI.available()){
    if(g_rs485Parser.feed((uint8_t)HMI.read(), g_rs485RxFrame)) process_rs485_frame(g_rs485RxFrame, boot_phase);
  }
}

static void boot_service_uart(){
  // RS485 is deterministic master/slave: CTRL-TS never initiates traffic.
  // Firmware convergence can happen while setup() is still holding the splash,
  // so timeout and scheduled reboot servicing must run here as well as loop().
  poll_rs485(true);
  fw_service_timeout();
  fw_service_reboot();
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
  if(!boot_decode_buf || boot_decode_w <= 0 || boot_decode_h <= 0) return 0;
  const int y0 = pDraw->y;
  const int x0 = pDraw->x;
  for(int y=0; y<pDraw->iHeight; y++){
    const int dy = y0 + y;
    if(dy < 0 || dy >= boot_decode_h) continue;
    int sx = 0;
    int dx = x0;
    int w = pDraw->iWidth;
    if(dx < 0){ sx = -dx; w -= sx; dx = 0; }
    if(dx + w > boot_decode_w) w = boot_decode_w - dx;
    if(w <= 0) continue;
    memcpy(&boot_decode_buf[dy * boot_decode_w + dx], &pDraw->pPixels[y * pDraw->iWidth + sx], (size_t)w * sizeof(lv_color_t));
  }
  return 1;
}

static bool boot_render_splash_fit(){
  if(!boot_canvas_buf || !boot_decode_buf || boot_w <= 0 || boot_h <= 0 || boot_decode_w <= 0 || boot_decode_h <= 0) return false;
  memset(boot_canvas_buf, 0, (size_t)boot_w * (size_t)boot_h * sizeof(lv_color_t));
  const bool rotate = (boot_decode_h > boot_decode_w) && (boot_w > boot_h);
  const int logicalW = rotate ? boot_decode_h : boot_decode_w;
  const int logicalH = rotate ? boot_decode_w : boot_decode_h;
  const float sx = float(boot_w) / float(logicalW);
  const float sy = float(boot_h) / float(logicalH);
  const float scale = sx < sy ? sx : sy;
  const int outW = max(1, min(boot_w, int(lroundf(float(logicalW) * scale))));
  const int outH = max(1, min(boot_h, int(lroundf(float(logicalH) * scale))));
  const int xOff = (boot_w - outW) / 2;
  const int yOff = (boot_h - outH) / 2;

  for(int ty=0; ty<outH; ++ty){
    const int ry = min(logicalH - 1, (ty * logicalH) / outH);
    for(int tx=0; tx<outW; ++tx){
      const int rx = min(logicalW - 1, (tx * logicalW) / outW);
      int srcX, srcY;
      if(rotate){
        // Clockwise rotation: logical (rx,ry) maps to source (ry, H-1-rx).
        srcX = min(boot_decode_w - 1, ry);
        srcY = max(0, boot_decode_h - 1 - rx);
      } else {
        srcX = min(boot_decode_w - 1, rx);
        srcY = min(boot_decode_h - 1, ry);
      }
      boot_canvas_buf[(yOff + ty) * boot_w + (xOff + tx)] = boot_decode_buf[srcY * boot_decode_w + srcX];
    }
    if((ty & 0x0F) == 0) yield();
  }
  Serial.printf("[BOOT] splash fit src=%dx%d rotate=%d -> %dx%d at %d,%d on %dx%d\n",
                boot_decode_w, boot_decode_h, rotate ? 1 : 0, outW, outH, xOff, yOff, boot_w, boot_h);
  return true;
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
  if(!jf){ Serial.println("[BOOT] /splash.jpg not found"); return false; }
  if(!boot_jpeg.open(jf, boot_jpeg_draw)){
    Serial.print("[BOOT] JPEG open failed, error="); Serial.println(boot_jpeg.getLastError());
    jf.close();
    return false;
  }
  boot_decode_w = boot_jpeg.getWidth();
  boot_decode_h = boot_jpeg.getHeight();
  if(boot_decode_w <= 0 || boot_decode_h <= 0 || (uint64_t)boot_decode_w * (uint64_t)boot_decode_h > 2200000ULL){
    Serial.printf("[BOOT] JPEG dimensions refused %dx%d\n", boot_decode_w, boot_decode_h);
    boot_jpeg.close(); jf.close(); return false;
  }
  if(boot_decode_buf){ free(boot_decode_buf); boot_decode_buf = nullptr; }
  boot_decode_buf = (lv_color_t*)ps_malloc((size_t)boot_decode_w * (size_t)boot_decode_h * sizeof(lv_color_t));
  if(!boot_decode_buf){
    Serial.printf("[BOOT] JPEG source allocation failed %dx%d\n", boot_decode_w, boot_decode_h);
    boot_jpeg.close(); jf.close(); return false;
  }
  memset(boot_decode_buf, 0, (size_t)boot_decode_w * (size_t)boot_decode_h * sizeof(lv_color_t));
  Serial.printf("[BOOT] JPEG opened %dx%d, fitting to %dx%d without crop\n", boot_decode_w, boot_decode_h, boot_w, boot_h);
  boot_jpeg.setPixelType(RGB565_LITTLE_ENDIAN);
  const int decoded = boot_jpeg.decode(0, 0, 0);
  boot_jpeg.close();
  jf.close();
  const bool fitted = decoded == 1 && boot_render_splash_fit();
  free(boot_decode_buf); boot_decode_buf = nullptr; boot_decode_w = 0; boot_decode_h = 0;
  lvgl_port_lock(-1);
  if(boot_canvas) lv_obj_invalidate(boot_canvas);
#if defined(LV_VERSION_MAJOR) && (LV_VERSION_MAJOR >= 8)
  lv_refr_now(NULL);
#endif
  lvgl_port_unlock();
  Serial.printf("[BOOT] JPEG decode=%d fit=%d\n", decoded, fitted ? 1 : 0);
  return fitted;
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
  lv_obj_align(boot_status_lbl, LV_ALIGN_TOP_MID, 0, 8);

  boot_progress_bar = lv_bar_create(boot_status_bar);
  lv_obj_set_size(boot_progress_bar, disp_w - 80, 10);
  lv_obj_align(boot_progress_bar, LV_ALIGN_BOTTOM_MID, 0, -7);
  lv_bar_set_range(boot_progress_bar, 0, 100);
  lv_bar_set_value(boot_progress_bar, 0, LV_ANIM_OFF);
  lv_obj_set_style_bg_color(boot_progress_bar, lv_color_hex(0x203142), LV_PART_MAIN);
  lv_obj_set_style_bg_opa(boot_progress_bar, LV_OPA_COVER, LV_PART_MAIN);
  lv_obj_set_style_bg_color(boot_progress_bar, lv_color_hex(0x49d8ff), LV_PART_INDICATOR);
  lv_obj_set_style_bg_opa(boot_progress_bar, LV_OPA_COVER, LV_PART_INDICATOR);
  lv_obj_add_flag(boot_progress_bar, LV_OBJ_FLAG_HIDDEN);
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
    if(g_fw_update_active || g_fw_finalized){
      // Keep the firmware progress/result stable until updater/reboot completes.
    } else if(g_boot_ctrl_confirmed && g_boot_srvr_confirmed){
      if(min_hold_done) break;
      uint32_t remain = (SPLASH_HOLD_MS - (now - t0) + 999) / 1000;
      char msg[96];
      snprintf(msg, sizeof(msg), "CTRL OK | SRVR OK | starting in %lus", (unsigned long)remain);
      boot_set_status(msg);
    } else if(g_boot_ctrl_confirmed){
      boot_set_status("Waiting for SRVR");
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
  // The second distinct CLICKED event is the confirmation. Do not impose a
  // processing-time delay here: two fast taps can legitimately be queued before
  // the main loop runs and must still complete the deliberate two-step action.
  selected_aux = -1;
  g_selected_aux_ms = 0;
  confirmed_aux = idx;
  clear_confirm_at = now_ms + 2000;  // v26.10.06.06: confirmed AUX tile stays lit for 2 seconds
  style_aux(idx,false,true);
  snprintf(msg,sizeof(msg),"AUX %d Confirmed", idx+1);
  set_touch_debug(msg);
  if(send_command){
    char cmd[8];
    snprintf(cmd, sizeof(cmd), "AUX%u", unsigned(idx + 1));
    if(!send_hmi_command(cmd)){
      // Never present a local Confirmed state for an operator command that was
      // not actually queued for delivery. Keep the tile selected so the next
      // deliberate press retries the same AUX action without losing intent.
      confirmed_aux = -1;
      clear_confirm_at = 0;
      selected_aux = idx;
      g_selected_aux_ms = now_ms;
      style_aux(idx, true, false);
      set_touch_debug("AUX queue busy - confirm again");
      return;
    }
  }
}

static void apply_flags_to_aux(uint16_t flags){
  // AUX1..AUX5 on the current EdgeBox CTRL are touchscreen-only. The AUX bits
  // returned by CTRL are therefore acknowledgement/transport echoes of a
  // command that originated here, not a new operator press. Feeding those bits
  // back into confirm_aux_idx() created a timing race: a delayed echo could
  // become the first press of the next calibration step, making that step appear
  // to need only one touchscreen tap. Keep the flags for diagnostics/state
  // tracking, but only local CLICKED events may advance the two-step UI.
  const uint16_t masks[AUX_COUNT] = {0x0020, 0x0040, 0x0080, 0x0100, 0x0400};
  const uint32_t now_ms = millis();
  for(int i=0;i<AUX_COUNT;i++){
    const bool was = (g_last_flags & masks[i]) != 0;
    const bool now = (flags & masks[i]) != 0;
    if(now && !was && (now_ms - g_last_aux_physical_ms[i] >= AUX_PHYSICAL_DEBOUNCE_MS)){
      g_last_aux_physical_ms[i] = now_ms;
    }
  }
  g_last_flags = flags;
}
static void set_touch_debug(const char *txt){
  // AUX select/confirm is a hot operator path. Keep this diagnostic heap-free.
  static char last[64] = {0};
  const char *next = txt ? txt : "";
  if(strncmp(last, next, sizeof(last)-1) == 0 && strlen(next) < sizeof(last)) return;
  strlcpy(last, next, sizeof(last));
  set_label_text_if_changed(lbl_touch_debug, last);
  Serial.println(last);
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
  // v26.10.06.06: the middle status banner follows the SRVR-resolved state.
  // A local CTRL-TS UART/display gap must not invent "E-Stop CTRL" while SRVR
  // is still sending Status | Active. Real CTRL/W1P E-Stops are still shown
  // immediately when SRVR sends status=E-Stop... / status_level=red.
  int level = g_status_level;
  String text = g_status_text.length() ? g_status_text : "Active";
  const bool explicit_fault = (text.indexOf("Fault") >= 0) || (text.indexOf("Link Loss") >= 0);
  if(g_estop_active && !text.startsWith("E-Stop") && !explicit_fault){
    String src = g_estop_source.length() ? g_estop_source : "CTRL";
    src.replace("+", " & ");
    text = "E-Stop | " + src;
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
    if(detail.startsWith("E-Stop | ") || detail.startsWith("E-Stop / ")) detail = detail.substring(9);
    else if(detail.startsWith("E-Stop ")) detail = detail.substring(7);
    detail.trim();
    while(detail.startsWith("/")){ detail = detail.substring(1); detail.trim(); }
    shown = "E-Stop | " + detail;
  } else {
    if(text == "Active" || text == "System Ready") shown = "System | Active";
    else if(text == "Battery Change" || text == "Battery Change Mode") shown = "System | Battery Change Mode";
    else if(text.startsWith("System | ")) shown = text;
    else shown = "System | " + text;
  }
  set_label_text_if_changed(lbl_estop, shown.c_str());
}

static void refresh_status_ui(){
  style_status_pill_cached(0,pill_ctrl,lbl_ctrl,"CTRL",g_ctrl_ok);
  if(pill_srvr && lbl_srvr) style_status_pill_cached(1,pill_srvr,lbl_srvr,"SRVR",g_srvr_ok);
  style_w1p_status_pill(g_w1p_health);
  // v26.10.06.06: do not turn the main middle box red purely because the
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

static bool send_hmi_command(const char *cmd){
  if(!cmd || !*cmd) return false;
  if(!queue_hmi_event(cmd)){
    Serial.printf("[WS-HMI] event queue full; event dropped count=%lu\n", (unsigned long)g_event_queue_drops);
    return false;
  }
  Serial.printf("[WS-HMI EVENT QUEUED] %s\n", cmd);
  return true;
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
  const lv_event_code_t code = lv_event_get_code(e);
  if(code != LV_EVENT_PRESSED && code != LV_EVENT_CLICKED) return;
  lv_obj_t *target = lv_event_get_target(e);
  if(is_within_aux(target)) return;
  // Match AUX buttons: callback records intent only; main loop owns UI state.
  queue_aux_cancel();
}

static void aux_event_cb(lv_event_t *e){
  if(lv_event_get_code(e) != LV_EVENT_CLICKED) return;
  int idx=(int)(intptr_t)lv_event_get_user_data(e);
  // Never allocate String objects, mutate AUX/UI state, or queue RS485 traffic
  // inside the LVGL task callback. The main loop owns those operations.
  queue_aux_touch((uint8_t)idx);
}

static void calibration_cancel_event_cb(lv_event_t *e){
  if(lv_event_get_code(e) != LV_EVENT_CLICKED) return;
  g_cal_cancel_requested = true;
}

static void service_aux_touch_events(){
  if(pop_aux_cancel()) cancel_pending_aux();
  if(g_cal_cancel_requested){
    if(!g_calibration_overlay_active){
      g_cal_cancel_requested = false;
    } else if(send_hmi_command("CAL_CANCEL")){
      // EVENT remains in the retry/ACK queue until CTRL accepts it. Clear the
      // local touch request only after the command was successfully queued.
      g_cal_cancel_requested = false;
    }
  }
  for(int n=0; n<8; ++n){
    int idx = pop_aux_touch();
    if(idx < 0) break;
    confirm_aux_idx(idx, true);
  }
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

static void apply_external_fw_fields(const String &line){
  String v;
  v = getField(line, "fw_ctrl_active");
  if(v.length()){
    const bool active = getFieldBool(line, "fw_ctrl_active", false);
    String phase = getField(line, "fw_ctrl_phase");
    int pct = (int)getFieldFloat(line, "fw_ctrl_pct", 0);
    fw_set_device_status("CTRL", phase.length()?phase:"Updating", pct, active);
  }
  v = getField(line, "fw_w1p_active");
  if(v.length()){
    const bool active = getFieldBool(line, "fw_w1p_active", false);
    String phase = getField(line, "fw_w1p_phase");
    int pct = (int)getFieldFloat(line, "fw_w1p_pct", 0);
    fw_set_device_status("W1P", phase.length()?phase:"Updating", pct, active);
  }
}

static bool apply_calibration_overlay_fields(const String &line){
  if(!g_cal_overlay) return false;
  const bool active = getFieldBool(line, "cal_active", false);
  if(!active){
    if(g_calibration_overlay_active){
      // Hide exactly once on the active -> inactive transition. The overlay was
      // created last in the frame and therefore already owns the foreground; no
      // runtime child reordering is required.
      lv_obj_add_flag(g_cal_overlay, LV_OBJ_FLAG_HIDDEN);
      g_calibration_overlay_active = false;
      g_last_cal_overlay_title = "";
      g_last_cal_overlay_kind = "";
      g_last_cal_overlay_step = -1;
      Serial.println("[WS-HMI] calibration overlay hidden");
    }
    return false;
  }
  String kind = getField(line, "cal_kind");
  String title = getField(line, "cal_title");
  String instruction = getField(line, "cal_instruction");
  int step = (int)getFieldFloat(line, "cal_step", 0);
  if(!title.length()) title = kind.length() ? kind + " Calibration" : "Calibration";
  if(!instruction.length()) instruction = "Set the requested position, then press Confirm";
  if(kind != g_last_cal_overlay_kind || step != g_last_cal_overlay_step){
    // Every wizard step starts from a clean confirmation state. Neither a stale
    // Confirm? selection nor the previous Confirmed state may carry across a
    // Joystick / Limit / Winch step transition. This guarantees two fresh local
    // touchscreen taps for every Confirm -> Confirm? action.
    if(selected_aux >= 0){ style_aux(selected_aux, false, false); selected_aux = -1; g_selected_aux_ms = 0; }
    if(confirmed_aux >= 0){ style_aux(confirmed_aux, false, false); confirmed_aux = -1; clear_confirm_at = 0; }
    g_last_cal_overlay_kind = kind;
    g_last_cal_overlay_step = step;
  }
  g_last_cal_overlay_title = title;
  String stepText = String("Step ") + String(step + 1) + (kind == "Joystick" ? " of 3" : (kind == "Winch" ? " of 2" : " of 3"));
  set_label_text_if_changed(g_cal_title_lbl, title.c_str());
  set_label_text_if_changed(g_cal_step_lbl, stepText.c_str());
  set_label_text_if_changed(g_cal_instruction_lbl, instruction.c_str());
  const bool isLimit = (kind == "Limit");
  const bool isJoystick = (kind == "Joystick");
  if(isLimit || isJoystick){
    const char *limitNames[3] = {"NEAR", "REF", "FAR"};
    const char *joyNames[3] = {"LEFT", "CENTRE", "RIGHT"};
    const char *limitKeys[3] = {"cal_near", "cal_ref", "cal_far"};
    const char *joyKeys[3] = {"cal_left", "cal_centre", "cal_right"};
    for(int i=0;i<3;i++){
      if(g_cal_value_box[i]) lv_obj_clear_flag(g_cal_value_box[i], LV_OBJ_FLAG_HIDDEN);
      if(g_cal_value_name[i]) set_label_text_if_changed(g_cal_value_name[i], isLimit ? limitNames[i] : joyNames[i]);
      String v = getField(line, isLimit ? limitKeys[i] : joyKeys[i]);
      if(!v.length()) v = "-";
      else if(isLimit) v += " m";
      if(g_cal_value_text[i]) set_label_text_if_changed(g_cal_value_text[i], v.c_str());
    }
    String currentV = getField(line, isLimit ? "cal_pos" : "cal_joy");
    if(!currentV.length()) currentV = isLimit ? String(g_pos, 2) : "0.0000";
    String currentText = isLimit ? (String("Current Winch Position   ") + currentV + " m")
                                 : (String("Current Joystick Position   ") + currentV);
    set_label_text_if_changed(g_cal_current_lbl, currentText.c_str());
    if(g_cal_current_lbl) lv_obj_clear_flag(g_cal_current_lbl, LV_OBJ_FLAG_HIDDEN);
  } else {
    for(int i=0;i<3;i++) if(g_cal_value_box[i]) lv_obj_add_flag(g_cal_value_box[i], LV_OBJ_FLAG_HIDDEN);
    if(g_cal_current_lbl) lv_obj_add_flag(g_cal_current_lbl, LV_OBJ_FLAG_HIDDEN);
  }

  // The .01 implementation called lv_obj_move_foreground() and cleared HIDDEN
  // on every 20-40 Hz HMI packet. On real hardware that repeatedly invalidated
  // the ~780x239 calibration surface while Drive/Speed/Position widgets were
  // also being repainted underneath it. The resulting RGB/PSRAM redraw storm is
  // visible in IMG_4951/4952 as repeated vertical rows immediately before reset.
  // Show the already-foreground overlay exactly once, then only mutate labels
  // whose contents actually change.
  if(!g_calibration_overlay_active){
    lv_obj_clear_flag(g_cal_overlay, LV_OBJ_FLAG_HIDDEN);
    g_calibration_overlay_active = true;
    Serial.printf("[WS-HMI] calibration overlay shown kind=%s step=%d free_psram=%u\n",
                  kind.c_str(), step + 1, (unsigned)ESP.getFreePsram());
  }
  return true;
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
    if(lbl_settings_note) set_label_text_if_changed(lbl_settings_note, "Applied. CTRL reset requested.");
    // CTRL-TS network settings live in CTRL; an ordinary settings commit must
    // never reboot the touchscreen.
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

static void set_progress_marker_fraction(float frac){
  if(!current_marker) return;
  const int bar_left = BAR_LIMIT_LEFT;
  const int bar_right = BAR_LIMIT_RIGHT;
  const int marker_w = 5;
  frac = constrain(frac, 0.0f, 1.0f);
  const int center_x = (int)lroundf(bar_left + frac * (float)(bar_right - bar_left));
  int x = center_x - marker_w/2;
  if(x < bar_left - marker_w/2) x = bar_left - marker_w/2;
  if(x > bar_right - marker_w/2) x = bar_right - marker_w/2;
  if(x != g_current_marker_x){
    lv_obj_set_x(current_marker, x);
    g_current_marker_x = x;
  }
}

static void update_progress_marker(){
  // Cache the newest verified sample. Do not snap an already-running marker to
  // it; service_progress_marker_smooth() converges smoothly at the local 50 Hz
  // UI rate while staying anchored to these authoritative samples.
  g_motion_sample_frac = constrain(g_pos_frac, 0.0f, 1.0f);
  g_motion_sample_speed_mps = g_speed_mps;
  g_motion_sample_ms = millis();
  g_motion_sample_valid = true;
  if(!g_progress_display_valid){
    g_progress_display_frac = g_motion_sample_frac;
    g_progress_display_valid = true;
    set_progress_marker_fraction(g_progress_display_frac);
  }
}

static void service_progress_marker_smooth(){
  if(!current_marker || !g_motion_sample_valid || g_calibration_overlay_active) return;
  const uint32_t now = millis();
  if(g_progress_service_ms && (now - g_progress_service_ms) < 16) return;
  g_progress_service_ms = now;

  float target = g_motion_sample_frac;
  const float span = fabsf(g_far - g_near);
  // HMM1 normally arrives about every 100 ms. Extrapolate no more than 180 ms
  // from the latest verified sample, then hold until fresh telemetry arrives.
  // Signed measured speed preserves direction; the prediction is presentation
  // only and is continuously corrected by the next verified pos_frac sample.
  const uint32_t age_ms = now - g_motion_sample_ms;
  const float dt = min(age_ms, (uint32_t)180) / 1000.0f;
  if(span > 0.001f && fabsf(g_motion_sample_speed_mps) > 0.001f){
    target += (g_motion_sample_speed_mps / span) * dt;
  }
  target = constrain(target, 0.0f, 1.0f);

  if(!g_progress_display_valid){
    g_progress_display_frac = target;
    g_progress_display_valid = true;
  } else {
    const float err = target - g_progress_display_frac;
    if(fabsf(err) < 0.00015f) g_progress_display_frac = target;
    else g_progress_display_frac += err * 0.45f;
  }
  set_progress_marker_fraction(g_progress_display_frac);
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
  float frac = constrain(g_ref_frac, 0.0f, 1.0f);
  int center_x = (int)lroundf(bar_left + frac * (float)(bar_right - bar_left));
  int marker_x = center_x - marker_w/2;
  if(marker_x < bar_left - marker_w/2) marker_x = bar_left - marker_w/2;
  if(marker_x > bar_right - marker_w/2) marker_x = bar_right - marker_w/2;
  int label_x = center_x - 20;
  if(label_x < bar_left - 10) label_x = bar_left - 10;
  if(label_x > bar_right - 30) label_x = bar_right - 30;
  lv_obj_set_x(travel_ref_lbl, label_x);
  lv_obj_set_pos(travel_ref_marker, marker_x, 47);
  lv_obj_set_size(travel_ref_marker, marker_w, 5);
}

static void update_ramp_markers(){
  if(!ramp_l || !ramp_r) return;
  const int bar_left = BAR_LIMIT_LEFT;
  const int bar_right = BAR_LIMIT_RIGHT;
  const int bar_w = bar_right - bar_left;
  const int ramp_top = 56;
  float span = g_far - g_near;
  if(span < 0.001f) span = 0.001f;
  float frac_near = g_ramp_near_frac >= 0.0f ? constrain(g_ramp_near_frac, 0.0f, 1.0f) : constrain(g_ramp_near / span, 0.0f, 1.0f);
  float frac_far = g_ramp_far_frac >= 0.0f ? constrain(g_ramp_far_frac, 0.0f, 1.0f) : constrain(g_ramp_far / span, 0.0f, 1.0f);
  int near_w = constrain((int)lroundf(bar_w * frac_near), 0, bar_w);
  int far_w = constrain((int)lroundf(bar_w * frac_far), 0, bar_w);

  // Match the SRVR SpanDiagram semantics: each ramp begins at its hard-limit
  // endpoint and widens linearly toward the configured ramp boundary. Ten
  // one-pixel strips give a low-cost triangular wedge without a canvas buffer.
  for(int row=0; row<RAMP_STRIP_COUNT; ++row){
    const int nw = near_w > 0 ? max(1, (near_w * (row + 1)) / RAMP_STRIP_COUNT) : 0;
    const int fw = far_w > 0 ? max(1, (far_w * (row + 1)) / RAMP_STRIP_COUNT) : 0;
    if(ramp_l_strip[row]){
      lv_obj_set_pos(ramp_l_strip[row], bar_left, ramp_top + row);
      lv_obj_set_size(ramp_l_strip[row], nw, 1);
      if(nw > 0) lv_obj_clear_flag(ramp_l_strip[row], LV_OBJ_FLAG_HIDDEN);
      else lv_obj_add_flag(ramp_l_strip[row], LV_OBJ_FLAG_HIDDEN);
    }
    if(ramp_r_strip[row]){
      lv_obj_set_pos(ramp_r_strip[row], bar_right - fw, ramp_top + row);
      lv_obj_set_size(ramp_r_strip[row], fw, 1);
      if(fw > 0) lv_obj_clear_flag(ramp_r_strip[row], LV_OBJ_FLAG_HIDDEN);
      else lv_obj_add_flag(ramp_r_strip[row], LV_OBJ_FLAG_HIDDEN);
    }
  }
}

static void update_preset_markers(){
  if(!travel_panel) return;
  const int bar_left = BAR_LIMIT_LEFT;
  const int bar_right = BAR_LIMIT_RIGHT;
  const int marker_w = 5;
  const int line_w = 2;
  const int line_top_y = 47;
  const int line_h = 11;
  const int label_w = 64;
  const int label_y_top = 34;
  const int label_y_bottom = 69;

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
    // All travel markers share one canonical coordinate whose centre is exactly
    // on the Near/Far endpoint at 0/100%, matching SRVR SpanDiagram.
    int center_x = (int)lroundf(bar_left + frac * (float)(bar_right - bar_left));
    int x = center_x - (line_w / 2);
    if(x < bar_left - line_w/2) x = bar_left - line_w/2;
    if(x > bar_right - line_w/2) x = bar_right - line_w/2;
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
  const bool state_only = line.startsWith("HMS1|");
  const bool geometry_only = line.startsWith("HMG1|");
  const bool motion_only = line.startsWith("HMM1|");
  const bool bulk_packet = !state_only && !geometry_only && !motion_only;
  const bool status_packet = state_only || bulk_packet;
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
  // Prefer SRVR's canonical normalized coordinates; fall back to the legacy
  // local calculation when talking to an older SRVR packet.
  float posFallback = (g_far > g_near + 0.001f) ? ((g_pos-g_near)/(g_far-g_near)) : 0.0f;
  float refFallback = (g_far > g_near + 0.001f) ? ((g_ref-g_near)/(g_far-g_near)) : 0.0f;
  g_pos_frac = constrain(getFieldFloat(line, "pos_frac", posFallback), 0.0f, 1.0f);
  g_ref_frac = constrain(getFieldFloat(line, "ref_frac", refFallback), 0.0f, 1.0f);
  g_to_near   = getFieldFloat(line, "to_near", g_to_near);
  g_to_far    = getFieldFloat(line, "to_far", g_to_far);
  g_speed_mps = getFieldFloat(line, "speed_mps", g_speed_mps);
  g_speed_kmh = getFieldFloat(line, "speed_kmh", g_speed_kmh);
  g_ramp_near = getFieldFloat(line, "ramp_near", g_ramp_near);
  g_ramp_far = getFieldFloat(line, "ramp_far", g_ramp_far);
  g_ramp_near_frac = getFieldFloat(line, "ramp_near_frac", g_ramp_near_frac);
  g_ramp_far_frac = getFieldFloat(line, "ramp_far_frac", g_ramp_far_frac);
  g_ref_visible = getFieldBool(line, "ref_vis", g_ref_visible);
  String modeField = getField(line, "mode");
  if(modeField.length()){
    if(modeField == "Normal") modeField = "Power";
    g_mode = modeField;
  }
  if(!g_mode.length()) g_mode = "Mode 1";
  String driveField = getField(line, "drive_mode"); if(driveField.length()) g_drive_mode = driveField; else if(modeField.length()) g_drive_mode = g_mode;
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
  // The HMI wire format is pipe-delimited, so SRVR safely serializes the human
  // separator as " / ". Restore the canonical operator spelling locally.
  if(statusField.startsWith("System / ")) statusField = "System | " + statusField.substring(9);
  if(statusField.startsWith("E-Stop / ")) statusField = "E-Stop | " + statusField.substring(9);
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

  if(status_packet && statusField.length()) g_status_text = statusField;
  if(status_packet && levelField.length()){
    levelField.toLowerCase();
    if(levelField.indexOf("red") >= 0 || levelField.indexOf("stop") >= 0) g_status_level = 2;
    else if(levelField.indexOf("yellow") >= 0 || levelField.indexOf("service") >= 0) g_status_level = 1;
    else g_status_level = 0;
  } else if(status_packet && statusField.length()){
    String sf = statusField; sf.toLowerCase();
    if(sf.indexOf("e-stop") >= 0 || sf.indexOf("link loss") >= 0) g_status_level = 2;
    else if(sf.indexOf("calibr") >= 0 || sf.indexOf("battery") >= 0) g_status_level = 1;
    else g_status_level = 0;
  }

  // v26.10.06.06: if SRVR sends explicit status/status_level, trust it as
  // the authoritative display state. Do not override it locally with a CTRL
  // error just because the touchscreen/CTRL UART side saw a transient gap.
  if(status_packet){
    g_estop_active = packet_estop;
    if(srcField.length()) g_estop_source = srcField;
    else if(g_estop_active) g_estop_source = "CTRL";
    else g_estop_source = "";
    if(g_estop_active && g_estop_source.length()){
      String src = g_estop_source;
      src.replace("+", " & ");
      g_estop_source = src;
      g_status_text = "E-Stop | " + src;
      g_status_level = 2;
    }
  }

  if(status_packet && !statusField.length()){
    if(!g_ctrl_ok){
      // Do not invent a red E-Stop CTRL state from a transient display/config gap.
      // SRVR sends the authoritative status/status_level fields for real E-stops.
      g_status_text = g_status_text.length() ? g_status_text : "System | Active";
      if(g_status_text == "E-Stop CTRL") { g_status_text = "System | Active"; g_status_level = 0; g_estop_active = false; g_estop_source = ""; }
    } else if(!g_srvr_ok){
      g_estop_active = true;
      g_estop_source = "SRVR";
      g_status_text = "E-Stop | SRVR";
      g_status_level = 2;
    } else if(g_estop_active){
      String src = g_estop_source.length() ? g_estop_source : "CTRL";
      src.replace("+", " & ");
      g_status_text = "E-Stop | " + src;
      g_status_level = 2;
    } else if(mode_is_service()){
      g_status_text = "System | " + g_mode;
      g_status_level = 1;
    } else {
      g_status_text = "System | Active";
      g_status_level = 0;
    }
  }
  uint16_t flags_now = (uint16_t)getFieldFloat(line, "flags", (float)g_last_flags);

  // Apply wizard ownership before rendering the travel/info region. While the
  // opaque wizard covers that region, keep model values current but freeze the
  // hidden Drive/Speed/Position/travel widgets so they cannot create a second
  // stream of invalidations underneath the overlay. The first packet after the
  // wizard closes redraws them from the latest cached values.
  const bool calibration_was_active = g_calibration_overlay_active;
  const bool calibration_active_now = (geometry_only || motion_only) ? g_calibration_overlay_active : apply_calibration_overlay_fields(line);
  const bool calibration_just_closed = calibration_was_active && !calibration_active_now;

  String s;
  if(!calibration_active_now){
    // HMS1 is the priority state delta used immediately after AUX confirmation.
    // Keep it away from the bulk motion/position formatting and redraw path.
    if(bulk_packet || motion_only){
      s = String(g_to_near, 2); set_label_text_if_changed(lbl_to_near, s.c_str());
      s = String(g_to_far, 2); set_label_text_if_changed(lbl_to_far, s.c_str());
      s = String(fabsf(g_speed_mps), 1); set_label_text_if_changed(lbl_speed_combo, s.c_str());
      s = String(fabsf(g_speed_kmh), 1); set_label_text_if_changed(lbl_current_kmh, s.c_str());
      s = String(g_pos, 2); set_label_text_if_changed(lbl_current_pos, s.c_str());
    }
    if(bulk_packet){
      s = String(g_max_mps, 1); set_label_text_if_changed(lbl_max_speed, s.c_str());
      s = String(g_max_kmh, 1); set_label_text_if_changed(lbl_max_kmh, s.c_str());
      s = String(g_near, 2) + " m"; set_label_text_if_changed(lbl_near_value, s.c_str());
      s = String(g_far, 2) + " m"; set_label_text_if_changed(lbl_far_value, s.c_str());
    }
    set_label_text_if_changed(lbl_drive_mode, g_drive_mode.c_str());
    set_label_text_if_changed(lbl_accel_mode, g_accel_mode.c_str());
    set_label_text_if_changed(lbl_battery_mode, g_battery_mode.c_str());
  }
  // Header/footer clock/network text is bulk telemetry, not priority state.
  if(bulk_packet){
    set_label_text_if_changed(lbl_srvr_time, g_srvr_time.c_str());
    set_label_text_if_changed(lbl_uptime, g_uptime.c_str());
    set_label_text_if_changed(lbl_ctrl_ip, g_ctrl_ip.c_str());
    set_label_text_if_changed(lbl_w1p_ip, g_w1p_ip.c_str());
  }

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
  if((bulk_packet || geometry_only) && (preset_names_field.length() || preset_pos_field.length() || preset_vis_field.length()) && preset_fields_changed){
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
    if(!calibration_active_now) update_preset_markers();
  }

  apply_flags_to_aux(flags_now);
  if((bulk_packet || motion_only) && !calibration_active_now) update_progress_marker();

  // HMG1 is emitted only when geometry/presets change, so it is the explicit
  // redraw trigger for REF/ramp/preset markers. This avoids relying on the slow
  // bulk frame and also catches fraction/visibility-only changes.
  if(geometry_only && !calibration_active_now){
    g_last_ref_draw = g_ref;
    g_last_near_draw = g_near;
    g_last_far_draw = g_far;
    g_last_ramp_near_draw = g_ramp_near;
    g_last_ramp_far_draw = g_ramp_far;
    update_reference_marker();
    update_ramp_markers();
    update_preset_markers();
  } else {
    bool ref_changed = bulk_packet && !calibration_active_now && ((fabsf(g_ref - g_last_ref_draw) > 0.05f) || (fabsf(g_near - g_last_near_draw) > 0.05f) || (fabsf(g_far - g_last_far_draw) > 0.05f));
    if(ref_changed){
      g_last_ref_draw = g_ref;
      g_last_near_draw = g_near;
      g_last_far_draw = g_far;
      update_reference_marker();
      update_preset_markers();
    }
    bool ramp_changed = !calibration_active_now && (ref_changed || (fabsf(g_ramp_near - g_last_ramp_near_draw) > 0.05f) || (fabsf(g_ramp_far - g_last_ramp_far_draw) > 0.05f));
    if(ramp_changed){
      g_last_ramp_near_draw = g_ramp_near;
      g_last_ramp_far_draw = g_ramp_far;
      update_ramp_markers();
    }
  }
  if(calibration_just_closed){
    update_reference_marker();
    update_ramp_markers();
    update_preset_markers();
    update_progress_marker();
  }
  sync_service_aux_visual();
  if(mode_changed || (prev_status_text != g_status_text) || (prev_status_level != g_status_level) || (prev_estop != g_estop_active) || (prev_estop_source != g_estop_source) || (prev_ctrl != g_ctrl_ok) || (prev_srvr != g_srvr_ok) || (prev_w1p != g_w1p_ok) || (prev_w1p_health != g_w1p_health)) {
    refresh_status_ui();
  }
  // v26.10.06.06: no left-strip/full-screen invalidation on packets; progress marker animates locally.
}


static void apply_layout_packet(const String &line){
  // Keep the header fixed locally so a stored layout
  // on CTRL cannot overwrite the screen title/version or trigger header redraws.
  String hint = getField(line, "hint");
  if(lbl_title) set_label_text_if_changed(lbl_title, "HV P2P\nCTRL-TS");
  if(lbl_subtitle) set_label_text_if_changed(lbl_subtitle, "v26.10.06.06");
  if(hint.length() && hint.startsWith("ERROR")) set_touch_debug(hint.c_str());
  // UIL1 is presentation-only. AUX assignment/value ownership belongs solely to
  // live SRVR HMI state, so an old layout persisted in CTRL NVS cannot overwrite
  // current Aux 3/4/5 semantics after reconnect.
  Serial.println("[WS-HMI] layout applied from CTRL (AUX assignments ignored)");
}

static void process_text_from_ctrl(String line, bool boot_phase){
  line.trim();
  if(!line.length()) return;
  if(line.startsWith("FWSTAT|")){
    fw_process_status_line(line);
    return;
  }
  if(line.startsWith("DSP1|")) line.replace("DSP1|", "HMI1|");
  last_hmi_rx = millis();
  if(is_valid_hmi_packet(line)){
    g_boot_ctrl_confirmed = getFieldBool(line, "ctrl", g_boot_ctrl_confirmed);
    g_boot_srvr_confirmed = getFieldBool(line, "srvr", g_boot_srvr_confirmed);
    apply_external_fw_fields(line);
  } else if(line.startsWith("HMS1|")) {
    // Firmware progress and ramp/settings state ride the priority delta too.
    // Apply update rows before fw_display_owned() returns so an already-open
    // update dashboard continues to advance without bulk HMI1 traffic.
    apply_external_fw_fields(line);
  } else if(line.startsWith("HMG1|")) {
    // Change-driven geometry/preset delta; no connection or firmware semantics.
  } else if(line.startsWith("HMM1|")) {
    // Live-motion delta; display data only and never a status authority.
  }
  if(boot_phase){
    // Cache compact deltas that arrive before the main UI exists. HMI1 still
    // drives the splash connection gate, while state/geometry are replayed as
    // soon as create_ui() has constructed their widgets.
    if(line.startsWith("HMS1|")) g_pending_runtime_state_line = line;
    else if(line.startsWith("HMG1|")) g_pending_runtime_geometry_line = line;
    else if(line.startsWith("HMM1|")) g_pending_runtime_motion_line = line;
    boot_process_line(line);
    return;
  }
  if(fw_display_owned()){
    // Do not mutate the hidden main dashboard while the firmware screen owns the
    // panel, but never discard the latest operator state. Replay these snapshots
    // immediately when the update dashboard releases.
    if(line.startsWith("HMS1|")) g_pending_runtime_state_line = line;
    else if(line.startsWith("HMG1|")) g_pending_runtime_geometry_line = line;
    else if(line.startsWith("HMM1|")) g_pending_runtime_motion_line = line;
    else if(is_valid_hmi_packet(line)) g_pending_runtime_bulk_line = line;
    return;
  }
  if(line.startsWith("HMS1|")) {
    // Priority state/config delta from CTRL. apply_hmi_packet detects HMS1 and
    // touches only the small state surface instead of the bulk dashboard path.
    apply_hmi_packet(line);
  } else if(line.startsWith("HMG1|")) {
    apply_hmi_packet(line);
  } else if(line.startsWith("HMM1|")) {
    apply_hmi_packet(line);
  } else if(line.startsWith("CFG1|")) {
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
  Serial.printf("[FW RX] tx type=0x%02X seq=%u %s\n", unsigned(type), unsigned(seq), text.c_str());
}

static String sha256_hex(const uint8_t digest[32]){
  static const char HEX_DIGITS[] = "0123456789abcdef";
  char out[65];
  for(size_t i=0;i<32;i++){ out[i*2]=HEX_DIGITS[digest[i]>>4]; out[i*2+1]=HEX_DIGITS[digest[i]&0x0F]; }
  out[64]='\0';
  return String(out);
}

static bool fw_compare_release_versions(const String &candidate, const String &running, int &relation){
  int ca=0, cb=0, cc=0, cd=0;
  int ra=0, rb=0, rc=0, rd=0;
  char tail=0;
  // Release identity is intentionally strict: vYY.MM.DD.RR and no suffix.
  if(sscanf(candidate.c_str(), "v%d.%d.%d.%d%c", &ca, &cb, &cc, &cd, &tail) != 4) return false;
  if(sscanf(running.c_str(),   "v%d.%d.%d.%d%c", &ra, &rb, &rc, &rd, &tail) != 4) return false;
  const int c[4] = {ca, cb, cc, cd};
  const int r[4] = {ra, rb, rc, rd};
  relation = 0;
  for(int i=0;i<4;i++){
    if(c[i] < r[i]) { relation = -1; break; }
    if(c[i] > r[i]) { relation =  1; break; }
  }
  return true;
}

static void fw_sha_release(){
  if(g_fw_sha_active){ mbedtls_sha256_free(&g_fw_sha_ctx); g_fw_sha_active=false; }
}

static void fw_abort(const char *reason, uint16_t seq=0){
  if(g_fw_update_active) Update.abort();
  fw_sha_release();
  g_fw_update_active = false;
  g_fw_finalized = false;
  g_fw_last_display_pct = -1;
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
  fw_set_device_status("CTRL-TS", "Failed", 0, false);
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
  // A manually recovered .03+ CTRL-TS must never be pulled backwards by an
  // older CTRL that still carries a pre-.03 image. Same-version exact-image
  // repair remains allowed; only a numerically older release is rejected.
  int releaseRelation = 0;
  if(!fw_compare_release_versions(version, String(CTRL_TS_SEMVER), releaseRelation)){
    fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "fw_begin_version_invalid");
    return;
  }
  if(releaseRelation < 0){
    fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "fw_downgrade_blocked");
    return;
  }
  if(g_fw_headless_mode && (version != g_fw_headless_target_version || !sha.equalsIgnoreCase(g_fw_headless_target_sha))){
    fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "fw_begin_pending_target_mismatch");
    return;
  }
  if(g_fw_safe_reboot_due_ms){
    // CTRL may rediscover the still-running UI before this scheduled reboot has
    // fired. A duplicate FW_BEGIN must acknowledge the same transition WITHOUT
    // moving the deadline; otherwise repeated discovery can postpone the reboot
    // forever and leave the dashboard stuck at 0%.
    fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "fw_safe_reboot_retry");
    return;
  }
  if(g_fw_finalized){
    // A late duplicate FW_BEGIN must never erase an already verified inactive
    // partition while CTRL is retrying the final reboot handshake.
    fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "fw_already_finalized_reboot_pending");
    return;
  }
  if(g_fw_update_active) Update.abort();
  g_fw_finalized = false;
  g_fw_final_size = 0;
  g_fw_final_sha = "";
  // Never call Update.begin()/Update.write() while the RGB/LVGL display is
  // active. Flash programming can suspend external-memory access on ESP32-S3,
  // while this Waveshare driver scans double framebuffers from PSRAM. Reboot
  // once into a display-off/headless updater, then let CTRL retry FW_BEGIN.
  if(!g_fw_headless_mode){
    if(!fw_stage_safe_update_handoff(version, sha)){
      fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "fw_safe_handoff_failed");
      return;
    }
    // Make the transition explicit: show the coordinated dashboard and mark the
    // CTRL-TS row as preparing. The actual flash write still happens only after
    // the deliberate display-off reboot; running RGB/LVGL while programming
    // ESP32-S3 flash reintroduces the PSRAM/RGB corruption this safe updater was
    // created to eliminate. SRVR continues to show exact self-flash percentage.
    fw_set_device_status("CTRL-TS", "Preparing safe updater - SRVR shows self-flash progress", 0, true);
    Serial.printf("[FW RX] safe-update reboot requested target=%s sha=%s\n", version.c_str(), sha.c_str());
    fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "fw_safe_reboot_retry");
    g_fw_safe_reboot_due_ms = millis() + 1800;
    return;
  }

  if(!Update.begin(imageSize, U_FLASH)){
    Serial.println("[FW RX] Update.begin failed");
    fw_set_device_status("CTRL-TS", "Failed", 0, false);
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
  g_fw_last_display_pct = -1;
  g_fw_expected_size = imageSize;
  g_fw_received = 0;
  g_fw_expected_sha = sha;
  g_fw_expected_version = version;
  g_fw_last_rx_ms = millis();
  g_ctrl_fw_compatible = false;
  fw_set_status_pct("Updating CTRL-TS firmware", 0);
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
  fw_set_status_pct("Updating CTRL-TS firmware", pct);
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
  fw_set_status_pct("Verifying CTRL-TS firmware", 100);
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
  fw_set_status_pct("Firmware verified - waiting to reboot", 100);
  fw_send_text(HVP2PRS485::FW_RESULT, frame.seq, String("ok=1|size=") + String((unsigned)g_fw_final_size) + "|sha256=" + g_fw_final_sha);
  // CTRL normally follows with an explicit REBOOT and receives an ACK. If that
  // final request/ACK is lost, a verified headless updater must not stay black
  // forever. Give CTRL a generous 2.5 s handshake window, then boot the already
  // SHA-verified/selected application autonomously. An explicit REBOOT shortens
  // this deadline to 250 ms in fw_handle_reboot().
  if(g_fw_reboot_due_ms == 0) g_fw_reboot_due_ms = millis() + 2500;
}

static void fw_handle_reboot(const HVP2PRS485::Frame &frame){
  if(!g_fw_finalized){
    fw_send_text(HVP2PRS485::ERROR_MSG, frame.seq, "reboot_without_verified_image");
    return;
  }
  fw_set_status_pct("Firmware verified - restarting CTRL-TS", 100);
  if(g_fw_headless_mode) fw_clear_headless_update_state();
  fw_send_text(HVP2PRS485::ACK, frame.seq, "rebooting");
  g_fw_reboot_due_ms = millis() + 250;
}

static void fw_service_reboot(){
  const uint32_t now = millis();
  if(g_fw_safe_reboot_due_ms && now >= g_fw_safe_reboot_due_ms){
    // The CH422G survives an ESP32 software reset. Turn the backlight off and
    // hold LCD reset before reboot so the panel cannot flash random RGB data
    // while the ESP32 restarts into the headless updater.
    if(expander){
      expander->digitalWrite(LCD_BL, LOW);
      expander->digitalWrite(LCD_RST, LOW);
    }
    delay(10);
    ESP.restart();
  }
  if(g_fw_reboot_due_ms && now >= g_fw_reboot_due_ms) ESP.restart();
}

static void fw_service_timeout(){
  if(g_fw_update_active && g_fw_last_rx_ms && (millis() - g_fw_last_rx_ms) > FW_RX_TIMEOUT_MS){
    fw_abort("timeout");
  }
}

static inline void rs485_slave_turnaround_guard(){
  // Real EdgeBox/Waveshare hardware showed that the old 150 us margin could
  // lose the immediate FW_READY/FW_ACK response. Use a conservative 2.5 ms
  // half-duplex turnaround before every slave response.
  delayMicroseconds(RS485_SLAVE_TURNAROUND_US);
}

static bool frame_bool_field(const HVP2PRS485::Frame &frame, const char *key, bool &value){
  if(!key || !*key || !frame.length) return false;
  char token[24];
  const int n = snprintf(token, sizeof(token), "%s=", key);
  if(n <= 0 || n >= int(sizeof(token))) return false;
  const size_t tokenLen = size_t(n);
  for(uint16_t i=0; i + tokenLen < frame.length; ++i){
    const bool boundary = (i == 0) || frame.payload[i-1] == '|';
    if(!boundary) continue;
    if(memcmp(frame.payload + i, token, tokenLen) != 0) continue;
    const uint8_t b = frame.payload[i + tokenLen];
    if(b == '1'){ value = true; return true; }
    if(b == '0'){ value = false; return true; }
  }
  return false;
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
    if(!g_boot_srvr_confirmed){
      if(boot_phase) boot_set_status("Waiting for SRVR");
      else { lvgl_port_lock(-1); boot_set_status("Waiting for SRVR"); lvgl_port_unlock(); }
    }
    return;
  }
  if(frame.type == HVP2PRS485::TEXT){
    // Parsing and POLL/EVENT service must not depend on the LVGL render mutex.
    // Only the actual widget mutation is locked, and TEXT has no immediate slave
    // response. This keeps operator EVENT responses deterministic even when the
    // display task is busy.
    if(boot_phase) process_text_from_ctrl(HVP2PRS485::payloadString(frame), true);
    else {
      const String line = HVP2PRS485::payloadString(frame);
      lvgl_port_lock(-1);
      process_text_from_ctrl(line, false);
      lvgl_port_unlock();
    }
    return;
  }
  if(frame.type == HVP2PRS485::POLL){
    bool srvrHint = g_srvr_ok;
    const bool haveSrvrHint = frame_bool_field(frame, "srvr", srvrHint);
    // A new boot must complete HELLO/COMPATIBLE before normal operation.
    // Ignoring POLL until then forces CTRL to drop any pre-reboot session and
    // revalidate hardware/protocol/version/SHA.
    if(!g_ctrl_fw_compatible){
      rs485_slave_turnaround_guard();
      HVP2PRS485::sendText(HMI, HVP2PRS485::ERROR_MSG, frame.seq, "session_not_compatible");
      return;
    }
    // This is the only normal-operating transmit opportunity for CTRL-TS.
    // Peek rather than pop: the event remains queued until CTRL explicitly ACKs
    // its event_id, making a lost/corrupt EVENT retry-safe.
    const HmiQueuedEvent *ev = peek_hmi_event();
    char payload[HMI_EVENT_TEXT_MAX + 176];
    const uint32_t now = millis();
    const bool includeDiag = ev || !g_last_event_diag_ms || (now - g_last_event_diag_ms) >= 1000;
    if(includeDiag){
      snprintf(payload, sizeof(payload), "EV1|id=%u|drops=%lu|crc=%lu|resync=%lu|heap=%lu|minheap=%lu|psram=%lu|cmd=%s",
               ev ? unsigned(ev->id) : 0U,
               (unsigned long)g_event_queue_drops,
               (unsigned long)g_rs485Parser.crcErrors(),
               (unsigned long)g_rs485Parser.resyncs(),
               (unsigned long)ESP.getFreeHeap(),
               (unsigned long)ESP.getMinFreeHeap(),
               (unsigned long)ESP.getFreePsram(),
               ev ? ev->text : "");
      g_last_event_diag_ms = now;
    } else {
      // Most idle polls need only prove that the slave responded. Diagnostics are
      // still included on every real EVENT and at least once per second, cutting
      // normal bus occupancy without weakening observability.
      snprintf(payload, sizeof(payload), "EV1|id=0|cmd=");
    }
    rs485_slave_turnaround_guard();
    HVP2PRS485::sendFrame(HMI, HVP2PRS485::EVENT, frame.seq,
                         reinterpret_cast<const uint8_t*>(payload), uint16_t(strlen(payload)));
    // The small POLL health hint is independent of bulk display telemetry. This
    // lets CTRL-TS return to Waiting for SRVR even if the last HMI1 frame was
    // lost or delayed. Apply only after the EVENT has left the UART so UI work
    // cannot stretch the slave response time.
    if(haveSrvrHint){
      const bool changed = (g_srvr_ok != srvrHint);
      g_boot_srvr_confirmed = srvrHint;
      g_srvr_ok = srvrHint;
      if(boot_phase){
        if(!srvrHint) boot_set_status("Waiting for SRVR");
      } else if(changed || !srvrHint){
        lvgl_port_lock(-1);
        if(changed) refresh_status_ui();
        if(!srvrHint) boot_set_status("Waiting for SRVR");
        lvgl_port_unlock();
      }
    }
    return;
  }
  if(frame.type == HVP2PRS485::ACK){
    String text = HVP2PRS485::payloadString(frame);
    String idText = boot_get_field(text, "event_id");
    if(idText.length()) ack_hmi_event((uint16_t)idText.toInt());
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
  const int SX=10, SW=780, GAP=7;
  const int HEADER_Y=8, HEADER_H=45;
  const int BANNER_Y=HEADER_Y+HEADER_H+GAP, BANNER_H=34;
  const int AUX_Y=BANNER_Y+BANNER_H+GAP, AUX_H=74;
  const int TRAVEL_Y=AUX_Y+AUX_H+GAP, TRAVEL_H=100;
  const int INFO_Y=TRAVEL_Y+TRAVEL_H+GAP, INFO_H=141;
  const int FOOT_Y=INFO_Y+INFO_H+GAP, FOOT_H=35;

  // Header: locked logo, CTRL/W1P link cards, version.
  lv_obj_t *brand=make_panel(frame,SX,HEADER_Y,70,HEADER_H,C_BG,0x63d84e,7);
  lbl_title=make_label(brand,"HV P2P\nCTRL-TS",0,6,&lv_font_montserrat_12,lv_color_hex(C_FG),70);
  lv_obj_set_style_text_line_space(lbl_title,-2,0);
  lbl_subtitle=make_label(frame,"v26.10.06.06",690,21,&lv_font_montserrat_10,lv_color_hex(C_MUTED),92);

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
  lbl_estop=make_label(pill_estop,"E-STOP | CTRL & W1P",0,8,&lv_font_montserrat_14,lv_color_hex(0xef5757),SW);

  // Five AUX cards: same grey/cyan/green visual language as SRVR.
  const int AUX_GAP=6, AUX_W=(SW-(AUX_COUNT-1)*AUX_GAP)/AUX_COUNT;
  const char *aux_heads[AUX_COUNT]={"AUX 1","AUX 2","AUX 3","AUX 4","AUX 5"};
  for(int i=0;i<AUX_COUNT;i++){
    aux_btn[i]=make_button(frame,SX+i*(AUX_W+AUX_GAP),AUX_Y,AUX_W,AUX_H);
    lv_obj_add_event_cb(aux_btn[i],aux_event_cb,LV_EVENT_CLICKED,(void*)(intptr_t)i);
    make_label(aux_btn[i],aux_heads[i],8,8,&lv_font_montserrat_10,lv_color_hex(C_CYAN),AUX_W-16);
    aux_text_lbl[i]=make_label(aux_btn[i],aux_action_part(g_aux_labels[i]).c_str(),8,28,&lv_font_montserrat_12,lv_color_hex(C_FG),AUX_W-16);
    // Value names can be longer than the action (for example "Practice Mode").
    // Give the value line almost the full card width and keep it explicitly on
    // one line so LVGL cannot wrap the final characters below the 83 px tile.
    aux_state[i]=make_label(aux_btn[i],aux_value_part(g_aux_labels[i]).c_str(),4,48,&lv_font_montserrat_10,lv_color_hex(C_GREEN),AUX_W-8);
    lv_label_set_long_mode(aux_state[i], LV_LABEL_LONG_CLIP);
  }

  // Cable/travel panel. Presets green, Ref blue, current skate white/green.
  travel_panel=make_panel(frame,SX,TRAVEL_Y,SW,TRAVEL_H,C_PANEL,C_BORDER,4);
  lv_obj_add_event_cb(travel_panel,bg_event_cb,LV_EVENT_PRESSED,nullptr);
  travel_near_lbl=make_label(travel_panel,"NEAR",8,6,&lv_font_montserrat_10,lv_color_hex(C_MUTED),60);
  lbl_near_value=make_label(travel_panel,"0.00 m",8,19,&lv_font_montserrat_10,lv_color_hex(C_FG),72);
  travel_far_lbl=make_label(travel_panel,"FAR",712,6,&lv_font_montserrat_10,lv_color_hex(C_MUTED),60);
  lbl_far_value=make_label(travel_panel,"100.00 m",700,19,&lv_font_montserrat_10,lv_color_hex(C_FG),74);
  travel_ref_lbl=make_label(travel_panel,"REF",370,7,&lv_font_montserrat_10,lv_color_hex(C_GREEN),40);

  // horizontal travel line
  lv_obj_t *track=lv_obj_create(travel_panel); lv_obj_set_pos(track,BAR_LIMIT_LEFT,52); lv_obj_set_size(track,BAR_LIMIT_WIDTH,1); lv_obj_set_style_bg_color(track,lv_color_hex(0xd7dad8),0); lv_obj_set_style_border_width(track,0,0); lv_obj_clear_flag(track,LV_OBJ_FLAG_SCROLLABLE);
  // ramp zones below the line
  // Ramping zones use the same triangular Near/Far semantics as SRVR's
  // SpanDiagram instead of the old thin rectangular bands.
  for(int r=0; r<RAMP_STRIP_COUNT; ++r){
    ramp_l_strip[r]=make_panel(travel_panel,BAR_LIMIT_LEFT,56+r,1,1,0x687074,0x687074,0,HV_OPA_35);
    ramp_r_strip[r]=make_panel(travel_panel,BAR_LIMIT_RIGHT-1,56+r,1,1,0x687074,0x687074,0,HV_OPA_35);
    lv_obj_set_style_border_width(ramp_l_strip[r],0,0);
    lv_obj_set_style_border_width(ramp_r_strip[r],0,0);
    lv_obj_add_flag(ramp_l_strip[r], LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(ramp_r_strip[r], LV_OBJ_FLAG_HIDDEN);
  }
  ramp_l=ramp_l_strip[RAMP_STRIP_COUNT-1];
  ramp_r=ramp_r_strip[RAMP_STRIP_COUNT-1];

  travel_near_marker=lv_obj_create(travel_panel); lv_obj_set_pos(travel_near_marker,BAR_LIMIT_LEFT,46); lv_obj_set_size(travel_near_marker,2,14); lv_obj_set_style_bg_color(travel_near_marker,lv_color_hex(0xd7dad8),0); lv_obj_set_style_border_width(travel_near_marker,0,0); lv_obj_clear_flag(travel_near_marker,LV_OBJ_FLAG_SCROLLABLE);
  travel_ref_marker=lv_obj_create(travel_panel); lv_obj_set_pos(travel_ref_marker,360,47); lv_obj_set_size(travel_ref_marker,5,5); lv_obj_set_style_radius(travel_ref_marker,1,0); lv_obj_set_style_bg_color(travel_ref_marker,lv_color_hex(C_GREEN),0); lv_obj_set_style_border_width(travel_ref_marker,0,0); lv_obj_clear_flag(travel_ref_marker,LV_OBJ_FLAG_SCROLLABLE);
  travel_far_marker=lv_obj_create(travel_panel); lv_obj_set_pos(travel_far_marker,BAR_LIMIT_RIGHT,46); lv_obj_set_size(travel_far_marker,2,14); lv_obj_set_style_bg_color(travel_far_marker,lv_color_hex(0xd7dad8),0); lv_obj_set_style_border_width(travel_far_marker,0,0); lv_obj_clear_flag(travel_far_marker,LV_OBJ_FLAG_SCROLLABLE);
  current_marker=lv_obj_create(travel_panel); lv_obj_set_pos(current_marker,BAR_LIMIT_LEFT,44); lv_obj_set_size(current_marker,6,18); lv_obj_set_style_bg_color(current_marker,lv_color_hex(0xf0f2f1),0); lv_obj_set_style_border_color(current_marker,lv_color_hex(0x697074),0); lv_obj_set_style_border_width(current_marker,1,0); lv_obj_clear_flag(current_marker,LV_OBJ_FLAG_SCROLLABLE);

  for(int i=0;i<12;i++){
    preset_line[i]=lv_obj_create(travel_panel); lv_obj_set_size(preset_line[i],1,9); lv_obj_set_style_bg_color(preset_line[i],lv_color_hex(C_GREEN),0); lv_obj_set_style_border_width(preset_line[i],0,0); lv_obj_clear_flag(preset_line[i],LV_OBJ_FLAG_SCROLLABLE); lv_obj_add_flag(preset_line[i],LV_OBJ_FLAG_HIDDEN);
    preset_tri[i]=lv_obj_create(travel_panel); lv_obj_set_size(preset_tri[i],1,1); lv_obj_set_style_bg_opa(preset_tri[i],LV_OPA_TRANSP,0); lv_obj_set_style_border_width(preset_tri[i],0,0); lv_obj_add_flag(preset_tri[i],LV_OBJ_FLAG_HIDDEN);
    preset_lbl[i]=make_label(travel_panel,"",0,35,&lv_font_montserrat_10,lv_color_hex(C_MUTED),64); lv_obj_add_flag(preset_lbl[i],LV_OBJ_FLAG_HIDDEN);
  }

  // Bottom row: Drive / Speed / Position.
  const int DRIVE_W=232, SPEED_W=264, POS_W=272;
  lv_obj_t *drive=make_panel(frame,SX,INFO_Y,DRIVE_W,INFO_H,C_PANEL,C_BORDER,4);
  make_label(drive,"DRIVE",10,10,&lv_font_montserrat_12,lv_color_hex(C_CYAN),90);
  make_label(drive,"Drive Mode",10,40,&lv_font_montserrat_10,lv_color_hex(C_FG),105); lbl_drive_mode=make_label(drive,g_drive_mode.c_str(),125,40,&lv_font_montserrat_10,lv_color_hex(C_FG),95);
  make_label(drive,"Acceleration Mode",10,68,&lv_font_montserrat_10,lv_color_hex(C_FG),105); lbl_accel_mode=make_label(drive,g_accel_mode.c_str(),125,68,&lv_font_montserrat_10,lv_color_hex(C_FG),95);
  make_label(drive,"Battery Change Mode",10,96,&lv_font_montserrat_10,lv_color_hex(C_FG),105); lbl_battery_mode=make_label(drive,g_battery_mode.c_str(),125,96,&lv_font_montserrat_10,lv_color_hex(C_FG),95);

  lv_obj_t *speed=make_panel(frame,SX+DRIVE_W+GAP,INFO_Y,SPEED_W,INFO_H,C_PANEL,C_BORDER,4);
  make_label(speed,"SPEED",10,10,&lv_font_montserrat_12,lv_color_hex(C_CYAN),90);
  make_label(speed,"CURRENT SPEED",10,39,&lv_font_montserrat_10,lv_color_hex(C_MUTED),110);
  lbl_speed_combo=make_label(speed,"0.0",8,55,&lv_font_montserrat_24,lv_color_hex(C_FG),92); make_label(speed,"m/s",88,68,&lv_font_montserrat_10,lv_color_hex(C_MUTED),36);
  lbl_current_kmh=make_label(speed,"0.0",8,92,&lv_font_montserrat_16,lv_color_hex(C_GREEN),75); make_label(speed,"km/h",80,97,&lv_font_montserrat_10,lv_color_hex(C_MUTED),42);
  make_label(speed,"MAX SPEED",144,39,&lv_font_montserrat_10,lv_color_hex(C_MUTED),100);
  lbl_max_speed=make_label(speed,"0.0",140,55,&lv_font_montserrat_24,lv_color_hex(C_FG),78); make_label(speed,"m/s",211,68,&lv_font_montserrat_10,lv_color_hex(C_MUTED),36);
  lbl_max_kmh=make_label(speed,"0.0",140,92,&lv_font_montserrat_16,lv_color_hex(C_GREEN),75); make_label(speed,"km/h",208,97,&lv_font_montserrat_10,lv_color_hex(C_MUTED),42);

  lv_obj_t *position=make_panel(frame,SX+DRIVE_W+GAP+SPEED_W+GAP,INFO_Y,POS_W,INFO_H,C_PANEL,C_BORDER,4);
  make_label(position,"POSITION",10,10,&lv_font_montserrat_12,lv_color_hex(C_CYAN),100);
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

  // Calibration wizard occupies the travel/info area only, leaving all five AUX
  // cards visible and touchable so the assigned AUX remains the step Confirm
  // control. It is created last, so it is permanently the top child and never
  // needs lv_obj_move_foreground() at runtime. Keep the wizard intentionally
  // simple: title, step and one operator instruction row only.
  g_cal_overlay=make_panel(frame,SX,TRAVEL_Y,SW,TRAVEL_H+GAP+INFO_H,0x11191f,0x26d5ff,6);
  g_cal_title_lbl=make_label(g_cal_overlay,"Calibration",28,18,&lv_font_montserrat_24,lv_color_hex(C_CYAN),SW-56);
  g_cal_step_lbl=make_label(g_cal_overlay,"Step 1",28,55,&lv_font_montserrat_16,lv_color_hex(C_GREEN),SW-56);
  g_cal_instruction_lbl=make_label(g_cal_overlay,"Set the requested position, then press Confirm",28,88,&lv_font_montserrat_16,lv_color_hex(C_FG),SW-56);
  lv_label_set_long_mode(g_cal_instruction_lbl,LV_LABEL_LONG_WRAP);
  const int CAL_BOX_Y=145, CAL_BOX_H=52, CAL_BOX_GAP=12, CAL_BOX_W=(SW-56-(2*CAL_BOX_GAP))/3;
  for(int i=0;i<3;i++){
    const int bx=28+i*(CAL_BOX_W+CAL_BOX_GAP);
    g_cal_value_box[i]=make_panel(g_cal_overlay,bx,CAL_BOX_Y,CAL_BOX_W,CAL_BOX_H,0x171f25,0x3f535d,4);
    g_cal_value_name[i]=make_label(g_cal_value_box[i],i==0?"NEAR":(i==1?"REF":"FAR"),8,5,&lv_font_montserrat_10,lv_color_hex(C_CYAN),CAL_BOX_W-16);
    g_cal_value_text[i]=make_label(g_cal_value_box[i],"-",8,23,&lv_font_montserrat_16,lv_color_hex(C_GREEN),CAL_BOX_W-16);
    lv_obj_add_flag(g_cal_value_box[i],LV_OBJ_FLAG_HIDDEN);
  }
  g_cal_current_lbl=make_label(g_cal_overlay,"Current Winch Position   0.00 m",28,209,&lv_font_montserrat_14,lv_color_hex(C_GREEN),SW-190);
  lv_obj_set_style_text_align(g_cal_current_lbl,LV_TEXT_ALIGN_LEFT,0);
  lv_obj_add_flag(g_cal_current_lbl,LV_OBJ_FLAG_HIDDEN);
  g_cal_cancel_btn=make_button(g_cal_overlay,SW-142,201,112,32);
  lv_obj_add_event_cb(g_cal_cancel_btn,calibration_cancel_event_cb,LV_EVENT_CLICKED,nullptr);
  make_label(g_cal_cancel_btn,"Cancel",0,8,&lv_font_montserrat_12,lv_color_hex(C_FG),112);
  lv_obj_add_flag(g_cal_overlay,LV_OBJ_FLAG_HIDDEN);

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


static void service_runtime_connection_screen(){
  if(!g_ui_ready || !g_main_scr || !boot_scr || fw_display_owned()) return;
  const bool ctrl_link_alive = last_hmi_rx && ((millis() - last_hmi_rx) <= HMI_TIMEOUT_MS) && g_ctrl_ok;
  const bool need_splash = (!ctrl_link_alive) || (!g_srvr_ok);
  if(need_splash){
    const char *msg = ctrl_link_alive ? "Waiting for SRVR" : "Waiting for CTRL";
    boot_set_status(msg);
    if(!g_connection_splash_active || lv_scr_act() != boot_scr){
      lv_scr_load(boot_scr);
      g_connection_splash_active = true;
    }
    return;
  }
  if(g_connection_splash_active || lv_scr_act() != g_main_scr){
    lv_scr_load(g_main_scr);
    g_connection_splash_active = false;
    refresh_status_ui();
  }
}

static void service_fw_screen_release(){
  if(!g_fw_external_release_due_ms || millis() < g_fw_external_release_due_ms) return;
  if(g_fw_update_active || g_fw_finalized || g_fw_reboot_due_ms || fw_any_row_active()) return;
  g_fw_external_release_due_ms = 0;
  g_fw_runtime_screen = false;
  if(g_ui_ready && g_main_scr) {
    lv_scr_load(g_main_scr);
    // Restore the freshest complete model first, then overlay the newest compact
    // state/geometry deltas. This makes AUX labels, live speed/position, ramps,
    // REF and presets converge immediately after any update dashboard.
    if(g_pending_runtime_bulk_line.length()) apply_hmi_packet(g_pending_runtime_bulk_line);
    if(g_pending_runtime_state_line.length()) apply_hmi_packet(g_pending_runtime_state_line);
    if(g_pending_runtime_geometry_line.length()) apply_hmi_packet(g_pending_runtime_geometry_line);
    if(g_pending_runtime_motion_line.length()) apply_hmi_packet(g_pending_runtime_motion_line);
    g_pending_runtime_bulk_line = "";
    g_pending_runtime_state_line = "";
    g_pending_runtime_geometry_line = "";
    g_pending_runtime_motion_line = "";
    update_progress_marker();
    update_reference_marker();
    update_ramp_markers();
    update_preset_markers();
    refresh_status_ui();
  }
}

static void service_link_state(){
  if(selected_aux >= 0 && g_selected_aux_ms && (millis() - g_selected_aux_ms > AUX_PENDING_TIMEOUT_MS)){
    cancel_pending_aux();
  }
  if(confirmed_aux>=0 && millis()>clear_confirm_at) {
    style_aux(confirmed_aux,false,false);
    confirmed_aux=-1;
    // Production UI deliberately has no debug label (lbl_touch_debug=nullptr).
    // Route this through the null-safe helper instead of dereferencing the absent
    // LVGL object. The old direct lv_label_set_text(nullptr, ...) caused the
    // post-confirm panic/reboot seen ~2 seconds after AUX actions completed.
    set_touch_debug("Ready");
  }

  bool link_alive = last_hmi_rx && ((millis() - last_hmi_rx) <= HMI_TIMEOUT_MS);
  if(!link_alive) {
    // v26.10.06.06: local UART/display timeout is a CTRL-TS link warning, not
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

  // Detect the internal-RAM safe-update handoff before touching NVS or starting
  // any RGB/PSRAM display resource. The CH422G is external to the ESP32 and can
  // retain LCD_BL=HIGH across ESP.restart(), so assert blackout first on the
  // deliberate headless boot. No flash access is required to decide this mode.
  const esp_reset_reason_t earlyResetReason = esp_reset_reason();
  g_boot_reset_reason = earlyResetReason;
  g_boot_id = esp_random();
  if(g_boot_id == 0) g_boot_id = 1;
  delay(20);
  Serial.printf("[WS-HMI] early reset_reason=%d boot_id=%08lX\n", (int)earlyResetReason, (unsigned long)g_boot_id);
  bool safeHeadlessBoot = fw_prepare_headless_mode();
  if(safeHeadlessBoot && !fw_headless_blackout()){
    Serial.println("[FW SAFE] blackout setup failed; abandoning headless update");
    fw_clear_headless_update_state();
    delay(20);
    ESP.restart();
  }
  // Firmware identity NVS reads are now safe: either no display has ever been
  // started (headless path), or this is an ordinary boot before lcd_init().
  load_fw_identity();

  delay(safeHeadlessBoot ? 20 : 200);
  Serial.println(CTRL_TS_VERSION);
  Serial.printf("[WS-HMI] reset_reason=%d\n", (int)esp_reset_reason());
  Serial.printf("[FW RX] identity hash=%s\n", g_fw_image_hash.c_str());
  Serial.println("[WS-HMI] boot: starting framed RS485 thin-HMI runtime");
  HMI.setRxBufferSize(4096);
  HMI.begin(HMI_BAUD, SERIAL_8N1, HMI_UART_RX, HMI_UART_TX);
  g_uart_ok = true;
  Serial.printf("[WS-HMI] onboard RS485 RX=%d TX=%d baud=%d (auto direction)\n", HMI_UART_RX, HMI_UART_TX, HMI_BAUD);

  if(safeHeadlessBoot){
    Serial.printf("[FW SAFE] headless updater target=%s sha=%s\n", g_fw_headless_target_version.c_str(), g_fw_headless_target_sha.c_str());
    while(true){
      // boot_service_uart() polls framed RS485 and services both updater timeout
      // and scheduled/autonomous reboot paths. Keep the display headless/black
      // while self-flash is active, including when upgrading from older builds.
      boot_service_uart();
      fw_service_headless_idle_return();
      delay(20);
    }
  }

  Serial.printf("[WS-HMI] PSRAM found=%d total=%u free=%u bytes\n", psramFound() ? 1 : 0, (unsigned)ESP.getPsramSize(), (unsigned)ESP.getFreePsram());
  if(!psramFound() || ESP.getPsramSize() < (4U * 1024U * 1024U)){
    Serial.println("[WS-HMI] FATAL DISPLAY: PSRAM unavailable/too small; entering RS485 firmware recovery mode");
    while(true){ boot_service_uart(); fw_service_reboot(); fw_service_timeout(); delay(20); }
  }
  Serial.println("[WS-HMI] boot: lcd_init()");
  lcd_init();
  if(lv_disp_get_default() == nullptr){
    Serial.println("[WS-HMI] FATAL DISPLAY: RGB/LVGL display unavailable; entering RS485 firmware recovery mode");
    while(true){ boot_service_uart(); fw_service_reboot(); fw_service_timeout(); delay(20); }
  }
  const int panel_w = lv_disp_get_hor_res(NULL);
  const int panel_h = lv_disp_get_ver_res(NULL);
  Serial.printf("[WS-HMI] LCD ready %dx%d free_psram=%u bytes\n", panel_w, panel_h, (unsigned)ESP.getFreePsram());
  if(panel_w != 800 || panel_h != 480){
    Serial.printf("[WS-HMI] FATAL DISPLAY: expected 800x480, got %dx%d; entering RS485 firmware recovery mode\n", panel_w, panel_h);
    while(true){ boot_service_uart(); fw_service_reboot(); fw_service_timeout(); delay(20); }
  }
  Serial.println("[WS-HMI] boot: splash");
  show_boot_splash();
  Serial.println("[WS-HMI] boot: create main UI");
  lvgl_port_lock(-1);
  // Keep the original JPEG splash resident after startup so a runtime SRVR
  // disconnect can return to exactly the same loading screen without rebooting.
  // The framebuffer lives in PSRAM. CTRL-TS self-update never programs flash
  // with this RGB/LVGL runtime active; it first reboots into the headless updater.
  lv_obj_t *main_scr = lv_obj_create(NULL);
  g_main_scr = main_scr;
  lv_obj_clear_flag(main_scr, LV_OBJ_FLAG_SCROLLABLE);
  lv_scr_load(main_scr);
  g_fw_connection_lbl = nullptr;
  g_fw_runtime_screen = false;
  g_connection_splash_active = false;
  create_ui();
  if(g_pending_boot_hmi_line.length() && is_valid_hmi_packet(g_pending_boot_hmi_line)){
    apply_hmi_packet(g_pending_boot_hmi_line);
  }
  if(g_pending_runtime_state_line.length()) apply_hmi_packet(g_pending_runtime_state_line);
  if(g_pending_runtime_geometry_line.length()) apply_hmi_packet(g_pending_runtime_geometry_line);
  if(g_pending_runtime_motion_line.length()) apply_hmi_packet(g_pending_runtime_motion_line);
  g_pending_runtime_state_line = "";
  g_pending_runtime_geometry_line = "";
  g_pending_runtime_motion_line = "";
  lvgl_port_unlock();
  delay(50);
  Serial.println("[WS-HMI] boot: UI ready after CTRL and SRVR confirmed");

}

void loop(){
  fw_service_reboot();

  // Always drain and answer RS485 before entering the LVGL critical section.
  // POLL/EVENT timing is therefore independent of display rendering. TEXT frames
  // take the LVGL mutex internally only for the widget update they require.
  handle_hmi_rx();
  if(fw_display_owned()){
    // External W1P/CTRL update rows may own the dashboard. CTRL-TS self-flash
    // never reaches this runtime loop: it reboots into the display-off headless
    // updater before Update.begin()/Update.write() are allowed.
    lvgl_port_lock(-1);
    service_fw_screen_release();
    lvgl_port_unlock();
  } else {
    lvgl_port_lock(-1);
    service_aux_touch_events();
    if(!fw_display_owned()){
      service_runtime_connection_screen();
      service_link_state();
      service_progress_marker_smooth();
      screen_keepalive();
    }
    lvgl_port_unlock();
  }
  fw_service_timeout();
  delay(20);
}
