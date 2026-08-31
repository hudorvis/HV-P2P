// ============================================================
// HV P2P W1P EdgeBox v26.08.31.04
// Seeed EdgeBox-ESP-100 Leadshine EL7-RS2000P commissioning interface
//
// Purpose:
//   - Appear on the network over Ethernet
//   - Accept UDP commands from HV P2P SRVR
//   - Return STATUS lines compatible with the current SRVR branch over UDP
//   - Provide a local winch E-Stop input
//   - Initialise the EdgeBox onboard isolated RS485 link for
//     Leadshine EL7-RS2000P Modbus RTU position and velocity control
//
// Current state of this build:
//   - Network + SRVR UDP interface: implemented
//   - Local E-Stop input: implemented
//   - Simulated position / velocity model for SRVR integration testing: implemented
//   - EL7-RS2000P readback: implemented using the documented PR/Modbus register map
//   - EL7-RS2000P velocity control: implemented with local accel/decel/cross-over profiling
//   - Dynamic acceleration mode: feedback-assisted speed regulation using live drive velocity
//   - EL7 outputs verified/configured as DO2=Ready/SRDY, DO3=Enabled/SRV-ST,
//     DO4=Brake/BRK-OFF and DO5=Fault/ALARM before normal motion can arm
//   - Existing software SRV-ON is dropped before any EL7 output-map migration
//
// Notes:
//   - This sketch is intended for first powered RS485 commissioning. It starts with
//     drive writes locked OFF, reads the EL7 position and communication settings,
//     and reports them to SRVR. Drive writes must be explicitly enabled after checks.
//   - The SRVR expects a line-oriented UDP protocol on the configured winch
//     host/port with STATUS lines and commands such as VEL, STOP, SET_SPAN,
//     SET_LIMIT_NEAR, SET_LIMIT_FAR, and SYNC_POS.
// ============================================================

// EdgeBox-ESP-100 hardware port: onboard W5500 Ethernet and isolated RS485.
#include <ETH.h>
#include <SPI.h>
#include "hal/uart_types.h"
#include <NetworkUdp.h>
#include <WebServer.h>
#include <Update.h>
#include <nvs_flash.h>
#include <Preferences.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdlib.h>

// -------------------- Version / identity --------------------
static const char* FW_NAME    = "HV P2P W1P";
static const char* FW_VERSION = "v26.08.31.04";
static const char* NODE_BANNER = "HV_P2P_W1P";

// -------------------- Network defaults --------------------
static IPAddress LOCAL_IP(172, 20, 1, 102);
static IPAddress GATEWAY(172, 20, 1, 1);
static IPAddress SUBNET(255, 255, 0, 0);
static IPAddress DNS1(8, 8, 8, 8);
static IPAddress DNS2(1, 1, 1, 1);
static IPAddress SRVR_IP(172, 20, 1, 100);

// Seeed EdgeBox-ESP-100 fixed peripheral mapping.
static const int EDGEBOX_ETH_CS = 10;
static const int EDGEBOX_ETH_MISO = 11;
static const int EDGEBOX_ETH_MOSI = 12;
static const int EDGEBOX_ETH_SCLK = 13;
static const int EDGEBOX_ETH_INT = 14;
static const int EDGEBOX_ETH_RST = 15;
static const int EDGEBOX_RS485_TX = 17;
static const int EDGEBOX_RS485_RX = 18;
static const int EDGEBOX_RS485_RTS = 8;

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

static void loadNetworkConfig(){
  Preferences np;
  np.begin("w1p-netcfg", true);
  IPAddress ip;
  String s;
  s = np.getString("w1p_ip", ""); if(s.length() && parseIpString(s, ip)) LOCAL_IP = ip;
  s = np.getString("srvr_ip", ""); if(s.length() && parseIpString(s, ip)) SRVR_IP = ip;
  s = np.getString("subnet",  ""); if(s.length() && parseIpString(s, ip)) SUBNET = ip;
  s = np.getString("gateway", ""); if(s.length() && parseIpString(s, ip)) GATEWAY = ip;
  np.end();
}

static bool saveNetworkConfigFromHmi(const String &line, String &note){
  IPAddress next_w1p = LOCAL_IP;
  IPAddress next_srvr = SRVR_IP;
  IPAddress next_subnet = SUBNET;
  IPAddress next_gateway = GATEWAY;
  String v;
  v = hvGetPipeField(line, "w1p_ip"); if(!v.length()) v = hvGetPipeField(line, "ctrl_ip"); if(v.length() && !parseIpString(v, next_w1p)){ note = "Bad W1P IP"; return false; }
  v = hvGetPipeField(line, "srvr_ip"); if(v.length() && !parseIpString(v, next_srvr)){ note = "Bad SRVR IP"; return false; }
  v = hvGetPipeField(line, "subnet");  if(v.length() && !parseIpString(v, next_subnet)){ note = "Bad Subnet"; return false; }
  v = hvGetPipeField(line, "gateway"); if(v.length() && !parseIpString(v, next_gateway)){ note = "Bad Gateway"; return false; }
  LOCAL_IP = next_w1p; SRVR_IP = next_srvr; SUBNET = next_subnet; GATEWAY = next_gateway;
  Preferences np;
  np.begin("w1p-netcfg", false);
  np.putString("w1p_ip", ipToString(LOCAL_IP));
  np.putString("srvr_ip", ipToString(SRVR_IP));
  np.putString("subnet", ipToString(SUBNET));
  np.putString("gateway", ipToString(GATEWAY));
  np.end();
  note = "W1P saved settings";
  return true;
}


static const uint16_t TCP_PORT = 5000;

// -------------------- Local I/O --------------------
// Local W1P E-stop status on EdgeBox isolated DI0. Wire a 24 V NC loop:
// field voltage present -> optocoupler GPIO HIGH -> healthy; open/pressed -> LOW -> unsafe.
static const int PIN_LOCAL_ESTOP = 4;
static const int LOCAL_ESTOP_HEALTHY_LEVEL = HIGH;

// Do not consume an EdgeBox industrial output just for a firmware heartbeat.
static const int PIN_STATUS_LED = -1;

// -------------------- Leadshine Servo Enable strategy --------------------
// v26.08.31.04: EdgeBox W5500 + isolated native RS485; corrected EL7 SRV-ON configuration to PA4.00 / P04.00
// Input Selection DI1. MotionStudio confirmed the usable no-extra-wire setup
// is DI1 = Servo ON Input (SRV-ON), Normally Closed, which reads/writes as
// 0x83. Do not use the old DI5 / P04.04 path; do not use Normally Open
// unless a physical 24 V SRV-ON input is wired.
//
// IMPORTANT: this enables the drive logic only. It is not STO, does not remove
// main power, and does not release the motor brake. Keep the W1P E-stop, brake
// wiring and power isolation strategy independent of this setting.
static const bool LEADSHINE_SOFTWARE_SRVON_ENABLED = true;
static const uint16_t LEADSHINE_SRVON_EXTERNAL_VALUE = 3;   // Physical DI SRV-ON, Normally Open - not used by default
static const uint16_t LEADSHINE_SRVON_INTERNAL_VALUE = 0x0083;  // DI1 SRV-ON, Normally Closed - no physical SRV-ON wire (0x83 = decimal 131)
static const uint16_t LEADSHINE_SRVON_DISABLED_VALUE = 0x0003;  // DI1 SRV-ON, Normally Open - with no DI wire this drops Servo Enable
static const bool     LEADSHINE_DROP_SW_SRVON_ON_ESTOP = true; // best-effort software drop; physical SRV-ON/STO remains recommended
static const uint32_t SOFTWARE_SRVON_SETTLE_MS = 700;

// Optional legacy GPIO SRV-ON output path. Disabled by default from v26.08.19.01.
// Leave disconnected unless you intentionally want a physical isolated SRV-ON DI circuit.
static const bool LEADSHINE_SRVON_OUTPUT_ENABLED = false;
static const int  PIN_LEADSHINE_SRVON = -1;
static const bool LEADSHINE_SRVON_ACTIVE_HIGH = true;
static const uint32_t SRVON_SETTLE_MS = 500;

// -------------------- EdgeBox isolated RS485 --------------------
// Onboard transceiver: UART1 TX=GPIO17, RX=GPIO18, RTS=GPIO8. The ESP32 UART
// half-duplex mode asserts RTS while transmitting and releases it after the final
// bit, matching the EdgeBox DE direction input. Keep the existing Modbus timing,
// CRC/retry and EL7 register logic unchanged.
static const int RS485_RX_PIN = EDGEBOX_RS485_RX;
static const int RS485_TX_PIN = EDGEBOX_RS485_TX;
static const int RS485_RTS_PIN = EDGEBOX_RS485_RTS;
static const uint32_t RS485_BAUD = 115200;
HardwareSerial DriveSerial(1);

// -------------------- W1P-TS disabled for this integration round --------------------
#define ENABLE_W1P_TS 0
// Legacy W1P-TS definitions are retained only so the older helper code still compiles.
// ENABLE_W1P_TS is fixed to 0 for this integration round; these pins are not used.
#ifndef W1PTS_UART_RX
#define W1PTS_UART_RX 36   // W1P receives from W1P-TS TXD; same as CTRL-TS wiring
#endif
#ifndef W1PTS_UART_TX
#define W1PTS_UART_TX 4    // W1P transmits to W1P-TS RXD; same as CTRL-TS wiring
#endif
static const uint32_t W1PTS_BAUD = 115200;
HardwareSerial HMI(2);
static const uint32_t HMI_LINK_TIMEOUT_MS = 30000;
static const uint32_t DISPLAY_FORWARD_MIN_MS = 100;
static const uint32_t DISPLAY_KEEPALIVE_MS = 3000;
static const uint32_t SRVR_DISPLAY_TIMEOUT_MS = 5000;
static uint32_t g_lastHmiRxMs = 0;
static uint32_t g_lastHmiStatusTxMs = 0;
static String g_latestDisplayPacket;
static String g_lastForwardedDisplayPacket;
static uint32_t g_lastSrvrDisplayMs = 0;
static uint32_t g_lastHmiDisplayForwardMs = 0;
static uint32_t g_lastHmiDisplayKeepaliveMs = 0;


// -------------------- Leadshine EL7-RS2000P Modbus --------------------
// Exact EL7-RS P-series register map from Leadshine User Manual V2.0.1.
// The drive must be configured in PR mode (P00.01 = 6), Modbus RTU 8N1,
// 115200 baud, slave address 1. Position is 10,000 pulses per motor revolution.
static const uint8_t  DRIVE_MODBUS_ID = 1;
static const uint16_t REG_CONTROL_MODE = 0x0003;        // P00.01, expected 6 = PR mode
static const uint16_t REG_DI1_ASSIGN = 0x0401;           // P04.00 / PA4.00, DI1 Input Selection
static const uint16_t REG_LEGACY_DI5_ASSIGN = 0x0409;    // Legacy v26.06.26.04 target: P04.04 / DI5 assignment. Read/clear only if old SRV-ON value remains.
static const uint16_t REG_DO1_ASSIGN = 0x0415;           // P04.10 / DO1. Left operator-defined/spare; not used as a safety prerequisite.
static const uint16_t REG_DO2_ASSIGN = 0x0417;           // P04.11, expected 2 = Servo Ready (SRDY)
static const uint16_t REG_DO3_ASSIGN = 0x0419;           // P04.12, expected 0x12 = Servo Status / Enabled (SRV-ST)
static const uint16_t REG_DO4_ASSIGN = 0x041B;           // P04.13, expected 3 = External brake released (BRK-OFF)
static const uint16_t REG_DO5_ASSIGN = 0x041D;           // P04.14, expected 1 = Alarm / Fault (ALARM, NO)
static const uint16_t REG_RS485_MODE = 0x053B;          // P05.29, expected 4 = 8N1
static const uint16_t REG_RS485_BAUD = 0x053D;          // P05.30, expected 6 = 115200
static const uint16_t REG_RS485_ADDRESS = 0x053F;       // P05.31, expected 1
static const uint16_t REG_PR_CONTROL = 0x6002;          // P08.02 trigger/reset/E-stop
static const uint16_t REG_MOTOR_POSITION_H = 0x602C;    // P08.44 high word
static const uint16_t REG_MOTOR_POSITION_L = 0x602D;    // P08.45 low word
static const uint16_t REG_INPUT_IO_STATUS = 0x602E;     // P08.46
static const uint16_t REG_OUTPUT_IO_STATUS = 0x602F;    // P08.47
static const uint16_t REG_PR0_MODE = 0x6200;            // P09.00
static const uint16_t REG_PR0_VELOCITY = 0x6203;        // P09.03, signed rpm
static const uint16_t REG_PR0_ACCEL = 0x6204;           // P09.04, ms/1000rpm
static const uint16_t REG_PR0_DECEL = 0x6205;           // P09.05, ms/1000rpm

static const uint16_t EXPECTED_CONTROL_MODE = 6;
static const uint16_t EXPECTED_DI1_ASSIGN_EXTERNAL = LEADSHINE_SRVON_EXTERNAL_VALUE; // P04.00 = SRV-ON, Normally Open (physical DI wiring only)
static const uint16_t EXPECTED_DI1_ASSIGN_INTERNAL = LEADSHINE_SRVON_INTERNAL_VALUE; // P04.00 = SRV-ON, Normally Closed (no physical SRV-ON wire)
static const uint16_t LEGACY_BAD_SRVON_DECIMAL_VALUE = 83; // v26.06.26.04 wrote decimal 83 to DI5; 0x83 should be decimal 131.
static const uint16_t DI_DISABLED_VALUE = 0;              // Leadshine input allocation 0x0 = invalid/no assigned input function.
// The operator-facing five-state plan uses a direct hardwired Power indication.
// Leadshine programmable outputs therefore carry Ready / Enabled / Brake / Fault on DO2..DO5.
static const uint16_t EXPECTED_DO2_READY_ASSIGN = 2;     // P04.11 = SRDY (NO)
static const uint16_t EXPECTED_DO3_ENABLED_ASSIGN = 0x12;// P04.12 = SRV-ST (NO)
static const uint16_t EXPECTED_DO4_BRAKE_ASSIGN = 3;     // P04.13 = BRK-OFF (NO)
static const uint16_t EXPECTED_DO5_FAULT_ASSIGN = 1;     // P04.14 = ALARM (NO; active when drive alarm occurs)
static const uint16_t INPUT_DI1_MASK = 0x0001;           // P08.46 bit 0 = DI1 state, assuming DI1..DI8 map to bits 0..7
static const uint16_t OUTPUT_DO2_MASK = 0x0002;          // P08.47 bit 1 = DO2 / configured SRDY
static const uint16_t OUTPUT_DO3_MASK = 0x0004;          // P08.47 bit 2 = DO3 / configured SRV-ST
static const uint16_t OUTPUT_DO4_MASK = 0x0008;          // P08.47 bit 3 = DO4 / configured BRK-OFF
static const uint16_t OUTPUT_DO5_MASK = 0x0010;          // P08.47 bit 4 = DO5 / configured ALARM
static const uint16_t EXPECTED_RS485_MODE = 4;
static const uint16_t EXPECTED_RS485_BAUD_CODE = 6;
static const uint16_t EXPECTED_RS485_ADDRESS = 1;
static const uint16_t PR_MODE_VELOCITY = 0x0002;
static const uint16_t PR_TRIGGER_PATH0 = 0x0010;
static const uint16_t PR_RESET = 0x0020;
static const uint16_t PR_EMERGENCY_STOP = 0x0040;
static const float    EL7_POSITION_PULSES_PER_REV = 10000.0f;
static const float    EL7_RATED_MAX_RPM = 2500.0f;
static const bool     MODBUS_WORD_SWAP = false;
static const uint32_t MODBUS_POLL_MS = 100;
static const uint32_t MODBUS_FAULT_POLL_MS = 150;
static const uint32_t MODBUS_REPLY_TIMEOUT_MS = 50;
static const uint8_t  MODBUS_READ_RETRIES = 3;
static const uint32_t MODBUS_INTERFRAME_GAP_US = 1500;
// v26.08.31.04: EdgeBox W5500 + isolated native RS485; fail the physical link after two consecutive invalid/no-reply
// transactions, with a 250 ms stale-reply backstop. Require two valid replies
// before recovering. The 50 ms reply timeout is still generous at 115200 baud,
// while reducing the time for a removed CN3 lead to become a safety fault.
static const uint8_t  RS485_FAIL_CONFIRM_COUNT = 2;
static const uint8_t  RS485_RECOVER_CONFIRM_COUNT = 2;
static const uint32_t RS485_LINK_TIMEOUT_MS = 250;
// Fenner SPA150 starting value: 10,000 pulses / (pi * 0.150m).
static const float    COMMAND_UNITS_PER_METRE_DEFAULT = 21220.7f;
static float          g_command_units_per_m = COMMAND_UNITS_PER_METRE_DEFAULT;
static float          g_drive_accel_mps2 = 2.0f;
static float          g_drive_decel_mps2 = 2.0f;
static float          g_drive_crossover_mps2 = 4.0f;
static float          g_drive_stop_decel_mps2 = 4.0f; // joystick-release stop response; higher = less coast

enum AccelerationMode : uint8_t {
  ACCEL_MODE_TRADITIONAL = 0,
  ACCEL_MODE_DYNAMIC = 1,
};
static AccelerationMode g_acceleration_mode = ACCEL_MODE_DYNAMIC;
static bool g_crossover_active = false;
static int8_t g_crossover_target_sign = 0;

// Local motion shaping runs independently from SRVR/display refresh. The EL7
// remains the fast inner motor-speed loop; W1P supplies the outer cable-speed
// target and rate limits. Dynamic mode adds a deliberately small, bounded
// correction from measured motor velocity so uphill/downhill load changes do
// not make the cable-speed response feel different.
static const uint32_t MOTION_PROFILE_INTERVAL_MS = 20; // 50 Hz local profile loop
static const uint32_t DRIVE_COMMAND_MIN_INTERVAL_MS = 50; // 20 Hz Modbus command ceiling
static const float DRIVE_COMMAND_MIN_DELTA_MPS = 0.01f;
static const float MAX_PROFILE_ACCEL_MPS2 = 20.0f;
static const float MOTION_ZERO_EPS_MPS = 0.005f;
static const float DYNAMIC_LEAD_TIME_S = 0.50f;
static const float DYNAMIC_MIN_LEAD_MPS = 0.05f;
// v26.08.31.04: EdgeBox W5500 + isolated native RS485; Dynamic mode is a closed cable-speed hold. Joystick sets
// target line speed; this PI trim lets the command nudge above/below the shaped
// target to hold measured feedback speed more precisely under changing load.
static const float DYNAMIC_SPEED_KP = 0.14f;
static const float DYNAMIC_SPEED_KI = 0.20f;
static const float DYNAMIC_CORR_BASE_MPS = 0.08f;
static const float DYNAMIC_CORR_FRAC = 0.08f;
static const float DYNAMIC_CORR_MAX_MPS = 0.85f;
static const float DYNAMIC_CORR_DEADBAND_MPS = 0.035f;
static float g_dynamic_speed_i_mps = 0.0f;
static float g_dynamic_feedback_mps = 0.0f;

// W1P link-loss timing remains independent from display refresh timing.
static const uint32_t W1P_STATUS_INTERVAL_MS = 50;
static const uint32_t W1P_PEER_TIMEOUT_MS = 750;
static const float    MAX_CMD_VEL_MPS = 20.0f;
static const float    LIMIT_STOP_GUARD_BASE_M = 0.03f;
static const float    LIMIT_STOP_GUARD_PER_MPS = 0.12f;
static const float    LIMIT_STOP_GUARD_MAX_M = 0.35f;
static const float    AUTO_DRIVE_ARM_MIN_REQUEST_MPS = 0.02f; // do not arm/trigger PR0 at idle
static const uint32_t AUTO_DRIVE_ARM_REQUEST_FRESH_MS = 450; // command must be recent before arming from WAIT
static const float    AUTO_DRIVE_DISABLE_ZERO_REQUEST_MPS = 0.01f; // release writes only after commanded stop is settled
static const float    AUTO_DRIVE_MOVING_GATE_MPS = 0.05f; // used only to block initial arming, never to disable active motion

// -------------------- Simulation / state --------------------
struct WinchState {
  float pos_m = 0.0f;
  float vel_request_mps = 0.0f;   // target requested by SRVR
  float vel_profile_mps = 0.0f;   // accel/decel/cross-over limited target
  float vel_cmd_mps = 0.0f;       // final command sent to EL7
  float vel_actual_mps = 0.0f;    // measured from EL7 position feedback
  float span_m = 100.0f;
  float limit_near_m = 0.0f;
  float limit_far_m = 100.0f;
  bool local_estop = false;
  bool ethernet_up = false;
  bool client_connected = false;
  bool drive_ready = false;
  bool drive_fault = false;
  bool simulation_enabled = false;
  bool service_mode = false;
  bool motor_reverse = false;  // reverses physical motor sign while preserving operator/UI direction
  bool feedback_from_drive = false;
  bool position_feedback_read_ok = false;
  bool output_io_read_ok = false;
  bool di1_assignment_read_ok = false;
  bool di1_srvon_assignment_ok = false;
  bool legacy_di5_assignment_read_ok = false;
  bool legacy_di5_srvon_conflict = false;
  bool legacy_di5_cleanup_attempted = false;
  bool legacy_di5_cleanup_ok = false;
  bool do1_assignment_read_ok = false;
  bool do2_assignment_read_ok = false;
  bool do2_ready_assignment_ok = false;
  bool do3_assignment_read_ok = false;
  bool do3_enabled_assignment_ok = false;
  bool do4_assignment_read_ok = false;
  bool do4_brake_assignment_ok = false;
  bool do5_assignment_read_ok = false;
  bool do5_fault_assignment_ok = false;
  bool servo_enabled_output = false;
  bool brake_output_released = false;
  bool fault_output_active = false;
  uint32_t output_config_last_attempt_ms = 0;
  bool srvon_output_asserted = false;
  bool srvon_output_ready = false;
  bool srvon_input_valid = false;
  uint32_t srvon_asserted_ms = 0;
  bool software_srvon_configured = false;
  bool software_srvon_ready = false;
  bool software_srvon_write_ok = false;
  bool software_srvon_write_attempted = false;
  bool software_srvon_inhibit = false;
  bool software_srvon_disable_attempted = false;
  uint32_t software_srvon_configured_ms = 0;
  bool servo_ready = false;
  bool drive_feedback_ok = false;      // strict: position read + output status + verified DO2/SRDY
  bool drive_writes_enabled = false;   // automatic motion-enable once SRVR/RS485/drive-ready safety gate is healthy
  bool pr_estop_latched = false;
  bool communication_config_read_ok = false;
  bool communication_config_ok = false;
  bool control_mode_read_ok = false;
  bool rs485_mode_read_ok = false;
  bool rs485_baud_read_ok = false;
  bool rs485_address_read_ok = false;
  uint8_t last_modbus_exception = 0;
  int32_t raw_pos_units = 0;
  int32_t raw_vel_units_s = 0;
  float drive_position_offset_m = 0.0f;
  uint16_t drive_status_word = 0;
  uint16_t input_io_status = 0;
  uint16_t output_io_status = 0;
  uint16_t di1_assignment = 0xFFFF;
  uint16_t legacy_di5_assignment = 0xFFFF;
  uint16_t do1_assignment = 0xFFFF;
  uint16_t do2_assignment = 0xFFFF;
  uint16_t do3_assignment = 0xFFFF;
  uint16_t do4_assignment = 0xFFFF;
  uint16_t do5_assignment = 0xFFFF;
  uint16_t control_mode = 0xFFFF;
  uint16_t rs485_mode = 0xFFFF;
  uint16_t rs485_baud_code = 0xFFFF;
  uint16_t rs485_address = 0xFFFF;
  bool drive_enabled = false;
  bool no_motion_feedback_fault = false;
  unsigned long no_motion_feedback_since_ms = 0;
  bool drive_mode_ok = false;
  bool rs_link_ok = false;
  uint8_t rs_consecutive_successes = 0;
  uint8_t rs_consecutive_failures = 0;
  uint32_t rs_last_ok_ms = 0;
  uint32_t rs_last_err_ms = 0;
};

WinchState g;

static float motorDirectionSign() {
  return g.motor_reverse ? -1.0f : 1.0f;
}

static float rawUnitsToDisplayPositionM(int32_t rawUnits) {
  return motorDirectionSign() * (float(rawUnits) / g_command_units_per_m) + g.drive_position_offset_m;
}

static float rawUnitsDeltaToDisplayMps(int64_t deltaUnits, float dt_s) {
  if (dt_s <= 0.0f) return 0.0f;
  return motorDirectionSign() * (float(deltaUnits) / g_command_units_per_m) / dt_s;
}

static void preserveDisplayedPositionForMotorDirectionChange(float displayedPositionM) {
  g.drive_position_offset_m = displayedPositionM - motorDirectionSign() * (float(g.raw_pos_units) / g_command_units_per_m);
  g.pos_m = displayedPositionM;
}

Preferences prefs;
NetworkUDP udp;


// -------------------- HV P2P browser update / service page --------------------
// After the first USB flash, open http://172.20.1.102/ in a browser on the control LAN.
// Supported web actions:
//   1) Main App firmware OTA (.ino.bin)
//   2) Web/UI filesystem partition upload (.littlefs.bin / .spiffs.bin / fs .bin)
//   3) Saved Config / NVS reset
//
// Safety model:
//   - This updater deliberately does NOT overwrite bootloader or partition table.
//   - File validation is role/filename based on both browser-side and ESP32-side checks.
//   - Do not rename binaries to bypass the role check.
static WebServer hvWebOta(80);

static const char* HV_UPDATE_NODE_NAME = "HV P2P W1P";
static const char* HV_UPDATE_ROLE = "W1P";
static const char* HV_UPDATE_APP_TOKEN = "HV_P2P_W1P";
static const char* HV_UPDATE_FS_TOKEN = "HV_P2P_W1P";
static const char* HV_UPDATE_REJECT_TOKENS = "CTRL,CTRL_TS";
static const char* HV_UPDATE_WARNING = "Upload only HV_P2P_W1P_v*.ino.bin firmware. CTRL/CTRL-TS files are rejected.";
static const char* HV_UPDATE_BUILD_TOKEN = "HV_P2P_FW_ROLE=W1P;HV_P2P_FW_VERSION=v26.08.31.04";

static bool hvUploadAllowed = false;
static bool hvUploadIsFs = false;
static bool hvUploadFinished = false;
static String hvUploadError;

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
  html += "<div class='card'><h2>Main App Firmware</h2><p class='muted'>Drag and drop the exported Arduino <code>.ino.bin</code> here. This updates the running application only.</p>";
  html += "<div id='appDrop' class='drop'>Drop app firmware here<br><span class='muted'>or click to select</span><input id='appFile' type='file' accept='.bin'></div>";
  html += "<div class='bar'><div id='appFill' class='fill'></div></div><p id='appMsg' class='muted'></p></div>";
  html += "<div class='card'><h2>Web/UI Filesystem Partition</h2><p class='muted'>Optional. Use only if this device build includes a LittleFS/SPIFFS web/UI partition. Filename should include <code>LITTLEFS</code>, <code>SPIFFS</code>, <code>FILESYSTEM</code>, or <code>_FS</code>.</p>";
  html += "<div id='fsDrop' class='drop'>Drop filesystem image here<br><span class='muted'>or click to select</span><input id='fsFile' type='file' accept='.bin'></div>";
  html += "<div class='bar'><div id='fsFill' class='fill'></div></div><p id='fsMsg' class='muted'></p></div>";
  html += "<div class='card'><h2>Service Actions</h2><div class='row'><button onclick='postAction(\"/reboot\",\"svcMsg\")'>Reboot Device</button>";
  html += "<button class='danger' onclick='confirmReset()'>Reset Saved Config / NVS</button></div><p id='svcMsg' class='muted'></p>";
  html += "<p class='bad'>NVS reset clears saved device settings/preferences and restarts the ESP32. It does not change bootloader or partition table.</p></div>";
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
  html += "wire('appDrop','appFile','/update/app','appFill','appMsg',validApp);wire('fsDrop','fsFile','/update/fs','fsFill','fsMsg',validFs);</script>";
  html += "</div></body></html>";
  return html;
}

static void hvHandleUpload(bool filesystem) {
  HTTPUpload& upload = hvWebOta.upload();
  if(upload.status == UPLOAD_FILE_START) {
    hvUploadIsFs = filesystem;
    hvUploadAllowed = false;
    hvUploadFinished = false;
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
    if(Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
      hvUploadError = "Update.write failed.";
      Update.printError(Serial);
    }
  } else if(upload.status == UPLOAD_FILE_END) {
    if(!hvUploadAllowed) return;
    if(Update.end(true)) {
      hvUploadFinished = true;
      Serial.printf("[OTA] %s update success: %u bytes\n", filesystem ? "FS" : "APP", upload.totalSize);
    } else {
      hvUploadError = "Update.end failed.";
      Update.printError(Serial);
    }
  } else if(upload.status == UPLOAD_FILE_ABORTED) {
    hvUploadError = "Upload aborted.";
    Update.end();
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

static void hvBeginWebUpdater() {
  hvWebOta.on("/", HTTP_GET, [](){
    hvWebOta.send(200, "text/html", hvOtaIndexHtml(HV_UPDATE_NODE_NAME, FW_VERSION, ETH.localIP().toString()));
  });
  hvWebOta.on("/update", HTTP_GET, [](){
    hvWebOta.send(200, "text/html", hvOtaIndexHtml(HV_UPDATE_NODE_NAME, FW_VERSION, ETH.localIP().toString()));
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
  hvWebOta.onNotFound([](){
    hvWebOta.send(404, "text/plain", "Not found");
  });
  hvWebOta.begin();
  Serial.printf("[OTA] Browser service page ready: http://%s/ role=%s\n", ETH.localIP().toString().c_str(), HV_UPDATE_ROLE);
}

static void hvHandleWebUpdater() {
  hvWebOta.handleClient();
}
IPAddress peerIP(0,0,0,0);
uint16_t peerPort = 0;
bool peerValid = false;
unsigned long lastStatusMs = 0;
unsigned long lastMotionMs = 0;
unsigned long lastBlinkMs = 0;
unsigned long lastPeerPacketMs = 0;
unsigned long lastModbusPollMs = 0;
unsigned long lastDriveFeedbackMs = 0;
unsigned long lastDriveConfigPollMs = 0;
int32_t lastRawDrivePosition = 0;
unsigned long lastRawDrivePositionMs = 0;
float filteredDriveVelocityMps = 0.0f;
float lastDriveCommandMps = 999999.0f;
unsigned long lastDriveCommandMs = 0;
unsigned long lastMotionProfileMs = 0;
unsigned long lastUnexpectedPeerLogMs = 0;
uint32_t lastModbusTransactionEndUs = 0;
unsigned long lastStopStatusMs = 0;
unsigned long lastVelocityCommandMs = 0;
unsigned long lastNonZeroVelocityCommandMs = 0;
float lastConfiguredAccelMps2 = -1.0f;
float lastConfiguredDecelMps2 = -1.0f;
float lastConfiguredCrossMps2 = -1.0f;


// -------------------- Helpers --------------------
static String trimCopy(String s) {
  s.trim();
  return s;
}

static bool modbusReadHoldingRegisters(uint8_t slave, uint16_t reg, uint16_t count, uint16_t* outRegs);
static bool modbusReadU16(uint8_t slave, uint16_t reg, uint16_t& outVal);
static bool modbusReadI32(uint8_t slave, uint16_t reg, int32_t& outVal);
static bool modbusWriteSingleRegister(uint8_t slave, uint16_t reg, uint16_t value);
static bool modbusWriteMultipleRegisters(uint8_t slave, uint16_t reg, uint16_t count, const uint16_t* regs);
static bool modbusWriteI32(uint8_t slave, uint16_t reg, int32_t value);
static void modbusWaitForSilentGap();
static void modbusTransactionFinished();
static bool driveResetPrEmergencyStop();
static bool driveWriteVelocityCommandMps(float vel_mps);
static bool driveConfigureMotionProfile();
static void serviceMotionProfile();
static bool driveSendEmergencyStop();
static void updateLocalInputs();
static void servicePeerTimeout();
static void sendStatusLine(bool force = false);
static void requestSoftwareSrvonInhibit(bool inhibit, const char* reason);

// Keep the W1P Ethernet/status heartbeat alive while a disconnected EL7 makes
// a Modbus transaction wait for its reply timeout. This must not service UDP
// commands here because a command could start a nested Modbus transaction.
static inline void serviceStatusHeartbeatDuringModbusWait() {
  sendStatusLine(false);
  yield();
}

static bool parseFloatArg(const String& line, const char* cmd, float& outVal) {
  if (!line.startsWith(cmd)) return false;
  String rest = line.substring(strlen(cmd));
  rest.trim();
  if (!rest.length()) return false;
  char* end = nullptr;
  const float value = strtof(rest.c_str(), &end);
  while (end && *end && isspace((unsigned char)*end)) ++end;
  if (!end || end == rest.c_str() || *end != '\0' || !isfinite(value)) return false;
  outVal = value;
  return true;
}

static uint16_t modbusCRC16(const uint8_t* data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (uint8_t b = 0; b < 8; ++b) {
      if (crc & 0x0001) crc = (crc >> 1) ^ 0xA001;
      else crc >>= 1;
    }
  }
  return crc;
}

static void modbusWaitForSilentGap() {
  if (lastModbusTransactionEndUs == 0) return;
  while ((uint32_t)(micros() - lastModbusTransactionEndUs) < MODBUS_INTERFRAME_GAP_US) {
    delayMicroseconds(50);
  }
}

static void modbusTransactionFinished() {
  lastModbusTransactionEndUs = micros();
}

static void noteRsOk() {
  g.rs_last_ok_ms = millis();
  g.rs_consecutive_failures = 0;
  if (g.rs_consecutive_successes < 0xFF) ++g.rs_consecutive_successes;
  if (g.rs_link_ok || g.rs_consecutive_successes >= RS485_RECOVER_CONFIRM_COUNT) {
    g.rs_link_ok = true;
    g.rs_consecutive_successes = RS485_RECOVER_CONFIRM_COUNT;
  }
}

static void noteRsErr() {
  const uint32_t now = millis();
  g.rs_last_err_ms = now;
  g.rs_consecutive_successes = 0;
  if (g.rs_consecutive_failures < 0xFF) ++g.rs_consecutive_failures;
  const bool stale = (g.rs_last_ok_ms == 0) || ((now - g.rs_last_ok_ms) > RS485_LINK_TIMEOUT_MS);
  if (g.rs_consecutive_failures >= RS485_FAIL_CONFIRM_COUNT || stale) {
    g.rs_link_ok = false;
  }
}

static bool modbusWriteSingleRegister(uint8_t slave, uint16_t reg, uint16_t value) {
  modbusWaitForSilentGap();
  while (DriveSerial.available()) DriveSerial.read();
  uint8_t req[8];
  req[0] = slave;
  req[1] = 0x06;
  req[2] = uint8_t((reg >> 8) & 0xFF);
  req[3] = uint8_t(reg & 0xFF);
  req[4] = uint8_t((value >> 8) & 0xFF);
  req[5] = uint8_t(value & 0xFF);
  uint16_t crc = modbusCRC16(req, 6);
  req[6] = uint8_t(crc & 0xFF);
  req[7] = uint8_t((crc >> 8) & 0xFF);
  DriveSerial.write(req, sizeof(req));
  DriveSerial.flush();

  uint8_t resp[8];
  size_t got = 0;
  unsigned long t0 = millis();
  while ((millis() - t0) < MODBUS_REPLY_TIMEOUT_MS && got < sizeof(resp)) {
    while (DriveSerial.available() && got < sizeof(resp)) resp[got++] = uint8_t(DriveSerial.read());
    serviceStatusHeartbeatDuringModbusWait();
  }
  modbusTransactionFinished();
  if (got != sizeof(resp)) { noteRsErr(); return false; }
  uint16_t respCrc = uint16_t(resp[6]) | (uint16_t(resp[7]) << 8);
  if (modbusCRC16(resp, 6) != respCrc) { noteRsErr(); return false; }
  if (memcmp(req, resp, 6) != 0) { noteRsErr(); return false; }
  noteRsOk();
  return true;
}

static bool modbusWriteMultipleRegisters(uint8_t slave, uint16_t reg, uint16_t count, const uint16_t* regs) {
  modbusWaitForSilentGap();
  while (DriveSerial.available()) DriveSerial.read();
  if (count == 0 || count > 8) return false;
  uint8_t req[64];
  size_t idx = 0;
  req[idx++] = slave;
  req[idx++] = 0x10;
  req[idx++] = uint8_t((reg >> 8) & 0xFF);
  req[idx++] = uint8_t(reg & 0xFF);
  req[idx++] = uint8_t((count >> 8) & 0xFF);
  req[idx++] = uint8_t(count & 0xFF);
  req[idx++] = uint8_t(count * 2);
  for (uint16_t i = 0; i < count; ++i) {
    req[idx++] = uint8_t((regs[i] >> 8) & 0xFF);
    req[idx++] = uint8_t(regs[i] & 0xFF);
  }
  uint16_t crc = modbusCRC16(req, idx);
  req[idx++] = uint8_t(crc & 0xFF);
  req[idx++] = uint8_t((crc >> 8) & 0xFF);
  DriveSerial.write(req, idx);
  DriveSerial.flush();

  uint8_t resp[8];
  size_t got = 0;
  unsigned long t0 = millis();
  while ((millis() - t0) < MODBUS_REPLY_TIMEOUT_MS && got < sizeof(resp)) {
    while (DriveSerial.available() && got < sizeof(resp)) resp[got++] = uint8_t(DriveSerial.read());
    serviceStatusHeartbeatDuringModbusWait();
  }
  modbusTransactionFinished();
  if (got != sizeof(resp)) { noteRsErr(); return false; }
  uint16_t respCrc = uint16_t(resp[6]) | (uint16_t(resp[7]) << 8);
  if (modbusCRC16(resp, 6) != respCrc) { noteRsErr(); return false; }
  if (resp[0] != slave || resp[1] != 0x10 || resp[2] != req[2] || resp[3] != req[3] || resp[4] != req[4] || resp[5] != req[5]) { noteRsErr(); return false; }
  noteRsOk();
  return true;
}

static bool modbusReadU16(uint8_t slave, uint16_t reg, uint16_t& outVal) {
  for (uint8_t attempt = 0; attempt < MODBUS_READ_RETRIES; ++attempt) {
    uint16_t v = 0;
    if (modbusReadHoldingRegisters(slave, reg, 1, &v)) {
      outVal = v;
      return true;
    }
    delay(2 + (attempt * 2));
  }
  return false;
}

static bool modbusWriteI32(uint8_t slave, uint16_t reg, int32_t value) {
  uint16_t regs[2];
  regs[0] = uint16_t((uint32_t(value) >> 16) & 0xFFFF);
  regs[1] = uint16_t(uint32_t(value) & 0xFFFF);
  if (MODBUS_WORD_SWAP) { uint16_t t = regs[0]; regs[0] = regs[1]; regs[1] = t; }
  return modbusWriteMultipleRegisters(slave, reg, 2, regs);
}

static uint16_t accelMsPer1000Rpm(float accel_mps2) {
  float rpm_per_s = max(0.01f, accel_mps2) * g_command_units_per_m * 60.0f / EL7_POSITION_PULSES_PER_REV;
  long value = lroundf(1000000.0f / rpm_per_s);
  return uint16_t(constrain(value, 1L, 32767L));
}

static bool driveResetPrEmergencyStop() {
  if (!g.pr_estop_latched) return true;
  if (!modbusWriteSingleRegister(DRIVE_MODBUS_ID, REG_PR_CONTROL, PR_RESET)) return false;
  delay(5);
  g.pr_estop_latched = false;
  return true;
}

static bool driveSendEmergencyStop() {
  if (!g.drive_writes_enabled || !g.rs_link_ok) return false;
  bool ok = modbusWriteSingleRegister(DRIVE_MODBUS_ID, REG_PR_CONTROL, PR_EMERGENCY_STOP);
  if (ok) g.pr_estop_latched = true;
  return ok;
}

static bool driveConfigureMotionProfile() {
  if (!g.drive_writes_enabled) return false;
  // W1P performs the exact cable-speed profile. Program the EL7's internal
  // ramps as equal-or-faster backup limits so they do not fight the W1P
  // cross-over profile while still preventing an abrupt internal command.
  const float driveAccelLimit = max(g_drive_accel_mps2, g_drive_crossover_mps2);
  const float driveDecelLimit = max(max(g_drive_decel_mps2, g_drive_stop_decel_mps2), g_drive_crossover_mps2);
  const bool unchanged = fabsf(driveAccelLimit - lastConfiguredAccelMps2) < 0.001f &&
                         fabsf(driveDecelLimit - lastConfiguredDecelMps2) < 0.001f &&
                         fabsf(g_drive_crossover_mps2 - lastConfiguredCrossMps2) < 0.001f;
  if (unchanged && g.drive_mode_ok) return true;

  const uint16_t accel = accelMsPer1000Rpm(driveAccelLimit);
  const uint16_t decel = accelMsPer1000Rpm(driveDecelLimit);
  bool ok = true;
  ok &= modbusWriteSingleRegister(DRIVE_MODBUS_ID, REG_PR0_MODE, PR_MODE_VELOCITY);
  ok &= modbusWriteSingleRegister(DRIVE_MODBUS_ID, REG_PR0_ACCEL, accel);
  ok &= modbusWriteSingleRegister(DRIVE_MODBUS_ID, REG_PR0_DECEL, decel);
  if (ok) {
    lastConfiguredAccelMps2 = driveAccelLimit;
    lastConfiguredDecelMps2 = driveDecelLimit;
    lastConfiguredCrossMps2 = g_drive_crossover_mps2;
    g.drive_mode_ok = true;
    noteRsOk();
  } else {
    g.drive_mode_ok = false;
    noteRsErr();
  }
  return ok;
}

static bool driveWriteVelocityCommandMps(float vel_mps) {
  if (!g.drive_writes_enabled) return false;
  if (!g.drive_feedback_ok || !g.communication_config_ok || g.local_estop) return false;
  if (!driveResetPrEmergencyStop()) return false;
  if (!driveConfigureMotionProfile()) return false;

  float rpm_f = vel_mps * motorDirectionSign() * g_command_units_per_m * 60.0f / EL7_POSITION_PULSES_PER_REV;
  rpm_f = constrain(rpm_f, -EL7_RATED_MAX_RPM, EL7_RATED_MAX_RPM);
  const int16_t rpm = int16_t(lroundf(rpm_f));

  bool ok = true;
  ok &= modbusWriteSingleRegister(DRIVE_MODBUS_ID, REG_PR0_VELOCITY, uint16_t(rpm));
  ok &= modbusWriteSingleRegister(DRIVE_MODBUS_ID, REG_PR_CONTROL, PR_TRIGGER_PATH0);
  if (!ok) {
    g.drive_mode_ok = false;
    noteRsErr();
    return false;
  }
  g.drive_mode_ok = true;
  g.drive_enabled = true; // command path is active; software/internal SRV-ON or physical SON controls torque enable
  noteRsOk();
  return true;
}

static const char* rsStatusText() {
  // RS_STAT reports the physical Modbus reply path only. LEAD_CFG reports the
  // parameter match and MODBUS reports valid motor-position feedback. SRVR then
  // keeps Connected strict while distinguishing wiring, configuration and encoder faults.
  if (g.rs_link_ok && (millis() - g.rs_last_ok_ms) <= RS485_LINK_TIMEOUT_MS) return "CONNECTED";
  if (g.rs_last_err_ms > 0) return "FAULT";
  return "WAITING";
}

static bool modbusReadHoldingRegisters(uint8_t slave, uint16_t reg, uint16_t count, uint16_t* outRegs) {
  modbusWaitForSilentGap();
  while (DriveSerial.available()) DriveSerial.read();

  uint8_t req[8];
  req[0] = slave;
  req[1] = 0x03;
  req[2] = uint8_t((reg >> 8) & 0xFF);
  req[3] = uint8_t(reg & 0xFF);
  req[4] = uint8_t((count >> 8) & 0xFF);
  req[5] = uint8_t(count & 0xFF);
  uint16_t crc = modbusCRC16(req, 6);
  req[6] = uint8_t(crc & 0xFF);
  req[7] = uint8_t((crc >> 8) & 0xFF);

  DriveSerial.write(req, sizeof(req));
  DriveSerial.flush();

  const size_t normalRespLen = 5 + (2 * count);
  uint8_t resp[64];
  if (normalRespLen > sizeof(resp)) {
    modbusTransactionFinished();
    return false;
  }

  size_t got = 0;
  size_t targetLen = normalRespLen;
  unsigned long t0 = millis();
  while ((millis() - t0) < MODBUS_REPLY_TIMEOUT_MS && got < targetLen) {
    while (DriveSerial.available() && got < targetLen) {
      resp[got++] = uint8_t(DriveSerial.read());
      if (got >= 2 && resp[1] == uint8_t(0x03 | 0x80)) targetLen = 5;
    }
    serviceStatusHeartbeatDuringModbusWait();
    delayMicroseconds(50);
  }
  modbusTransactionFinished();

  if (got != targetLen) { noteRsErr(); return false; }

  uint16_t respCrc = uint16_t(resp[targetLen - 2]) | (uint16_t(resp[targetLen - 1]) << 8);
  if (modbusCRC16(resp, targetLen - 2) != respCrc) { noteRsErr(); return false; }
  if (resp[0] != slave) { noteRsErr(); return false; }

  if (resp[1] == uint8_t(0x03 | 0x80)) {
    // A CRC-valid Modbus exception still proves that the slave and physical
    // RS485 path replied. Keep the physical link healthy while reporting the
    // individual register/configuration read as failed.
    g.last_modbus_exception = resp[2];
    noteRsOk();
    return false;
  }
  if (resp[1] != 0x03 || resp[2] != (2 * count)) { noteRsErr(); return false; }

  g.last_modbus_exception = 0;
  for (uint16_t i = 0; i < count; ++i) {
    outRegs[i] = (uint16_t(resp[3 + (2 * i)]) << 8) | uint16_t(resp[4 + (2 * i)]);
  }
  noteRsOk();
  return true;
}

static bool modbusReadI32(uint8_t slave, uint16_t reg, int32_t& outVal) {
  // Position is polled continuously, so do not multiply a missing-encoder
  // timeout by the configuration retry count. The next poll is the retry.
  uint16_t regs[2] = {0, 0};
  if (!modbusReadHoldingRegisters(slave, reg, 2, regs)) return false;
  uint16_t hi = regs[0];
  uint16_t lo = regs[1];
  if (MODBUS_WORD_SWAP) {
    hi = regs[1];
    lo = regs[0];
  }
  outVal = (int32_t(uint32_t(hi) << 16) | uint32_t(lo));
  return true;
}

static bool modbusReadFeedbackBlock(uint8_t slave, int32_t& outPos, uint16_t& outInputIo, uint16_t& outOutputIo) {
  // P08.44..P08.47 are contiguous: motor position high/low, input I/O and
  // output I/O. Reading all four in one transaction gives a position sample
  // and the current DO2..DO5 output states from the same successful Modbus reply.
  uint16_t regs[4] = {0, 0, 0, 0};
  if (!modbusReadHoldingRegisters(slave, REG_MOTOR_POSITION_H, 4, regs)) return false;
  uint16_t hi = regs[0];
  uint16_t lo = regs[1];
  if (MODBUS_WORD_SWAP) {
    hi = regs[1];
    lo = regs[0];
  }
  outPos = (int32_t(uint32_t(hi) << 16) | uint32_t(lo));
  outInputIo = regs[2];
  outOutputIo = regs[3];
  return true;
}

static bool isLegacyDi5SrvonConflict(uint16_t value) {
  // v26.06.26.04 could write the wrong old DI5 target. Leadshine Er-211 is
  // an input interface function assignment error, so do not allow a stale DI5
  // SRV-ON assignment to coexist with the corrected DI1=0x83 setup.
  return value == LEADSHINE_SRVON_EXTERNAL_VALUE ||
         value == LEGACY_BAD_SRVON_DECIMAL_VALUE ||
         value == LEADSHINE_SRVON_INTERNAL_VALUE;
}

static void pollLeadshineFeedback() {
  unsigned long now = millis();
  const uint32_t feedbackPollIntervalMs = g.drive_feedback_ok ? MODBUS_POLL_MS : MODBUS_FAULT_POLL_MS;
  if ((now - lastModbusPollMs) < feedbackPollIntervalMs) return;
  lastModbusPollMs = now;

  // Read configuration first when due. In v26.06.15.01 the failed encoder/
  // position transaction happened immediately before P00.01, so P00.01 was
  // repeatedly the only read stored as 0xFFFF even though the other parameters
  // proved the link was alive.
  if ((now - lastDriveConfigPollMs) >= 2000) {
    lastDriveConfigPollMs = now;
    uint16_t ctrl=0xFFFF, di1Assign=0xFFFF, legacyDi5Assign=0xFFFF,
             do1Assign=0xFFFF, do2Assign=0xFFFF, do3Assign=0xFFFF, do4Assign=0xFFFF, do5Assign=0xFFFF,
             fmt=0xFFFF, baud=0xFFFF, addr=0xFFFF;
    bool okCtrl = modbusReadU16(DRIVE_MODBUS_ID, REG_CONTROL_MODE, ctrl);
    updateLocalInputs();
    bool okDi1Assign = modbusReadU16(DRIVE_MODBUS_ID, REG_DI1_ASSIGN, di1Assign);
    updateLocalInputs();
    bool okLegacyDi5Assign = modbusReadU16(DRIVE_MODBUS_ID, REG_LEGACY_DI5_ASSIGN, legacyDi5Assign);
    updateLocalInputs();
    bool okDo1Assign = modbusReadU16(DRIVE_MODBUS_ID, REG_DO1_ASSIGN, do1Assign);
    updateLocalInputs();
    bool okDo2Assign = modbusReadU16(DRIVE_MODBUS_ID, REG_DO2_ASSIGN, do2Assign);
    updateLocalInputs();
    bool okDo3Assign = modbusReadU16(DRIVE_MODBUS_ID, REG_DO3_ASSIGN, do3Assign);
    updateLocalInputs();
    bool okDo4Assign = modbusReadU16(DRIVE_MODBUS_ID, REG_DO4_ASSIGN, do4Assign);
    updateLocalInputs();
    bool okDo5Assign = modbusReadU16(DRIVE_MODBUS_ID, REG_DO5_ASSIGN, do5Assign);
    updateLocalInputs();
    bool okFmt = modbusReadU16(DRIVE_MODBUS_ID, REG_RS485_MODE, fmt);
    updateLocalInputs();
    bool okBaud = modbusReadU16(DRIVE_MODBUS_ID, REG_RS485_BAUD, baud);
    updateLocalInputs();
    bool okAddr = modbusReadU16(DRIVE_MODBUS_ID, REG_RS485_ADDRESS, addr);
    updateLocalInputs();

    g.control_mode_read_ok = okCtrl;
    g.di1_assignment_read_ok = okDi1Assign;
    g.legacy_di5_assignment_read_ok = okLegacyDi5Assign;
    g.do1_assignment_read_ok = okDo1Assign;
    g.do2_assignment_read_ok = okDo2Assign;
    g.do3_assignment_read_ok = okDo3Assign;
    g.do4_assignment_read_ok = okDo4Assign;
    g.do5_assignment_read_ok = okDo5Assign;
    g.rs485_mode_read_ok = okFmt;
    g.rs485_baud_read_ok = okBaud;
    g.rs485_address_read_ok = okAddr;
    g.communication_config_read_ok = okCtrl && okDi1Assign && okDo2Assign && okDo3Assign && okDo4Assign && okDo5Assign && okFmt && okBaud && okAddr;

    if (okCtrl) g.control_mode = ctrl;
    if (okDi1Assign) g.di1_assignment = di1Assign;
    if (okLegacyDi5Assign) g.legacy_di5_assignment = legacyDi5Assign;
    if (okDo1Assign) g.do1_assignment = do1Assign;
    if (okDo2Assign) g.do2_assignment = do2Assign;
    if (okDo3Assign) g.do3_assignment = do3Assign;
    if (okDo4Assign) g.do4_assignment = do4Assign;
    if (okDo5Assign) g.do5_assignment = do5Assign;
    if (okFmt) g.rs485_mode = fmt;
    if (okBaud) g.rs485_baud_code = baud;
    if (okAddr) g.rs485_address = addr;

    const bool di1EnabledOk = okDi1Assign && (di1Assign == EXPECTED_DI1_ASSIGN_INTERNAL);
    const bool di1DisabledForInhibitOk = okDi1Assign && (di1Assign == LEADSHINE_SRVON_DISABLED_VALUE) && (g.local_estop || g.software_srvon_inhibit);
    g.di1_srvon_assignment_ok = di1EnabledOk || di1DisabledForInhibitOk;
    g.legacy_di5_srvon_conflict = okLegacyDi5Assign && isLegacyDi5SrvonConflict(legacyDi5Assign);
    g.do2_ready_assignment_ok = okDo2Assign && (do2Assign == EXPECTED_DO2_READY_ASSIGN);
    g.do3_enabled_assignment_ok = okDo3Assign && (do3Assign == EXPECTED_DO3_ENABLED_ASSIGN);
    g.do4_brake_assignment_ok = okDo4Assign && (do4Assign == EXPECTED_DO4_BRAKE_ASSIGN);
    g.do5_fault_assignment_ok = okDo5Assign && (do5Assign == EXPECTED_DO5_FAULT_ASSIGN);
    g.communication_config_ok = g.communication_config_read_ok &&
      (ctrl == EXPECTED_CONTROL_MODE) &&
      g.di1_srvon_assignment_ok &&
      !g.legacy_di5_srvon_conflict &&
      g.do2_ready_assignment_ok &&
      g.do3_enabled_assignment_ok &&
      g.do4_brake_assignment_ok &&
      g.do5_fault_assignment_ok &&
      (fmt == EXPECTED_RS485_MODE) &&
      (baud == EXPECTED_RS485_BAUD_CODE) &&
      (addr == EXPECTED_RS485_ADDRESS);

    static int lastDiagState = -1;
    const bool physicalLink = g.rs_link_ok && (millis() - g.rs_last_ok_ms) <= RS485_LINK_TIMEOUT_MS;
    const int diagState = !physicalLink ? 0 :
      (!g.communication_config_read_ok ? 1 :
      (!g.communication_config_ok ? 2 :
      (!g.drive_feedback_ok ? 3 : 4)));

    if (diagState != lastDiagState) {
      lastDiagState = diagState;
      if (diagState == 0) {
        Serial.printf("[RS485] No valid Modbus reply at 115200 8N1, slave ID %u. Check tested T/R harness, A/B/GND and EL7 P05.29/P05.30/P05.31.\n", (unsigned)DRIVE_MODBUS_ID);
      } else if (diagState == 1) {
        Serial.printf("[RS485] Configuration read fault: P00.01=%s, P04.00=%s, P04.11=%s, P04.12=%s, P04.13=%s, P04.14=%s, P05.29=%s, P05.30=%s, P05.31=%s; last Modbus exception=0x%02X.\n",
                      okCtrl ? "OK" : "NO REPLY",
                      okDi1Assign ? "OK" : "NO REPLY",
                      okDo2Assign ? "OK" : "NO REPLY",
                      okDo3Assign ? "OK" : "NO REPLY",
                      okDo4Assign ? "OK" : "NO REPLY",
                      okDo5Assign ? "OK" : "NO REPLY",
                      okFmt ? "OK" : "NO REPLY",
                      okBaud ? "OK" : "NO REPLY",
                      okAddr ? "OK" : "NO REPLY",
                      (unsigned)g.last_modbus_exception);
      } else if (diagState == 2) {
        Serial.printf("[RS485] Link OK but configuration value mismatch: P00.01=%u (need 6), P04.00=%u (need 0x83/131=DI1 SRV-ON NC), legacy P04.04/DI5=%u (must not be SRV-ON), P04.11/DO2=%u (need 2=SRDY), P04.12/DO3=%u (need 0x12=SRV-ST), P04.13/DO4=%u (need 3=BRK-OFF), P04.14/DO5=%u (need 1=ALARM), P05.29=%u (need 4/8N1), P05.30=%u (need 6/115200), P05.31=%u (need 1).\n",
                      (unsigned)g.control_mode, (unsigned)g.di1_assignment, (unsigned)g.legacy_di5_assignment,
                      (unsigned)g.do2_assignment, (unsigned)g.do3_assignment, (unsigned)g.do4_assignment, (unsigned)g.do5_assignment,
                      (unsigned)g.rs485_mode, (unsigned)g.rs485_baud_code, (unsigned)g.rs485_address);
      } else if (diagState == 3) {
        Serial.printf("[RS485] Link/config OK but drive feedback is not safe: POS_READ=%u IO_READ=%u P04.11/DO2=%u%s SRDY=%u OUT_IO=0x%04X. Active requires a valid position read and asserted DO2/SRDY.\n",
                      g.position_feedback_read_ok ? 1u : 0u,
                      g.output_io_read_ok ? 1u : 0u,
                      (unsigned)g.do2_assignment,
                      g.do2_ready_assignment_ok ? "" : " (need 2=SRDY)",
                      g.servo_ready ? 1u : 0u,
                      (unsigned)g.output_io_status);
      } else {
        Serial.println("[RS485] Leadshine Modbus link, DO2/SRDY, DO3/SRV-ST, DO4/BRK-OFF, DO5/ALARM assignments and position feedback are verified.");
      }
    }
  }

  int32_t rawPos = 0;
  uint16_t inio = 0;
  uint16_t outio = 0;
  bool okFeedbackBlock = modbusReadFeedbackBlock(DRIVE_MODBUS_ID, rawPos, inio, outio);
  if (okFeedbackBlock) {
    if (lastRawDrivePositionMs > 0) {
      unsigned long dt_ms = now - lastRawDrivePositionMs;
      if (dt_ms > 0 && dt_ms < 1000) {
        int64_t delta = int64_t(rawPos) - int64_t(lastRawDrivePosition);
        float raw_mps = rawUnitsDeltaToDisplayMps(delta, float(dt_ms) / 1000.0f);
        if (isfinite(raw_mps) && fabsf(raw_mps) <= 30.0f) {
          // v16: display/control feedback follows the real drive velocity much
          // more closely and snaps to zero quickly. This removes the visual tail
          // where SRVR/CTRL-TS still showed movement after the motor stopped.
          if (fabsf(raw_mps) < 0.030f) {
            filteredDriveVelocityMps = 0.0f;
            g_dynamic_feedback_mps = 0.0f;
          } else {
            filteredDriveVelocityMps = (0.88f * raw_mps) + (0.12f * filteredDriveVelocityMps);
            // Separate smoother feedback for Dynamic speed-hold. The display path
            // follows raw velocity closely so the readout stops fast; the control
            // correction must not chase one-sample encoder/Modbus spikes.
            g_dynamic_feedback_mps = (0.30f * raw_mps) + (0.70f * g_dynamic_feedback_mps);
          }
        }
      }
    }
    lastRawDrivePosition = rawPos;
    lastRawDrivePositionMs = now;
    g.raw_pos_units = rawPos;
    g.raw_vel_units_s = int32_t(filteredDriveVelocityMps * g_command_units_per_m);
    g.pos_m = rawUnitsToDisplayPositionM(rawPos);
    g.vel_actual_mps = filteredDriveVelocityMps;
    g.input_io_status = inio;
    g.output_io_status = outio;
    g.srvon_input_valid = ((inio & INPUT_DI1_MASK) != 0);
    g.position_feedback_read_ok = true;
    g.output_io_read_ok = true;
    g.servo_ready = g.do2_ready_assignment_ok && ((outio & OUTPUT_DO2_MASK) != 0);
    g.servo_enabled_output = g.do3_enabled_assignment_ok && ((outio & OUTPUT_DO3_MASK) != 0);
    g.brake_output_released = g.do4_brake_assignment_ok && ((outio & OUTPUT_DO4_MASK) != 0);
    g.fault_output_active = g.do5_fault_assignment_ok && ((outio & OUTPUT_DO5_MASK) != 0);
    g.feedback_from_drive = true;
    lastDriveFeedbackMs = now;
  } else if ((now - lastDriveFeedbackMs) > 500) {
    g.position_feedback_read_ok = false;
    g.output_io_read_ok = false;
    g.servo_ready = false;
    g.servo_enabled_output = false;
    g.brake_output_released = false;
    g.fault_output_active = false;
    g.srvon_input_valid = false;
    g.feedback_from_drive = false;
    g.vel_actual_mps = 0.0f;
    g_dynamic_feedback_mps = 0.0f;
  }

  // A readable position register is not enough: the EL7 can return P08.44/45
  // while CN2/main power are unavailable. Treat feedback as safe only when
  // the same reply includes output status and the verified DO2/SRDY signal is on.
  g.drive_feedback_ok = g.position_feedback_read_ok &&
                        g.output_io_read_ok &&
                        g.do2_ready_assignment_ok &&
                        g.servo_ready &&
                        !g.fault_output_active;
  g.drive_ready = g.drive_feedback_ok && g.communication_config_ok;
  g.drive_fault = !g.drive_ready;
}

static void saveConfig() {
  prefs.begin("hv-p2p-w1p", false);
  prefs.putFloat("span_m", g.span_m);
  prefs.putFloat("limit_near", g.limit_near_m);
  prefs.putFloat("limit_far", g.limit_far_m);
  prefs.putFloat("pos_m", g.pos_m);
  prefs.putBool("sim", g.simulation_enabled);
  prefs.putBool("service", g.service_mode);
  prefs.putBool("motor_rev", g.motor_reverse);
  prefs.putFloat("units_per_m", g_command_units_per_m);
  prefs.putFloat("drv_offset", g.drive_position_offset_m);
  prefs.putFloat("accel", g_drive_accel_mps2);
  prefs.putFloat("decel", g_drive_decel_mps2);
  prefs.putFloat("cross", g_drive_crossover_mps2);
  prefs.putFloat("stop_dec", g_drive_stop_decel_mps2);
  prefs.putUChar("acc_mode", uint8_t(g_acceleration_mode));
  prefs.end();
}

static void loadConfig() {
  prefs.begin("hv-p2p-w1p", true);
  g.span_m = prefs.getFloat("span_m", g.span_m);
  g.limit_near_m = prefs.getFloat("limit_near", g.limit_near_m);
  g.limit_far_m = prefs.getFloat("limit_far", g.limit_far_m);
  g.pos_m = prefs.getFloat("pos_m", g.pos_m);
  g.simulation_enabled = prefs.getBool("sim", g.simulation_enabled);
  g.service_mode = prefs.getBool("service", g.service_mode);
  g.motor_reverse = prefs.getBool("motor_rev", g.motor_reverse);
  g_command_units_per_m = prefs.getFloat("units_per_m", g_command_units_per_m);
  g.drive_position_offset_m = prefs.getFloat("drv_offset", g.drive_position_offset_m);
  g_drive_accel_mps2 = max(0.05f, prefs.getFloat("accel", g_drive_accel_mps2));
  g_drive_decel_mps2 = max(0.05f, prefs.getFloat("decel", g_drive_decel_mps2));
  g_drive_crossover_mps2 = max(0.05f, prefs.getFloat("cross", g_drive_crossover_mps2));
  g_drive_stop_decel_mps2 = max(0.05f, prefs.getFloat("stop_dec", g_drive_stop_decel_mps2));
  g_acceleration_mode = prefs.getUChar("acc_mode", uint8_t(g_acceleration_mode)) == uint8_t(ACCEL_MODE_TRADITIONAL)
      ? ACCEL_MODE_TRADITIONAL : ACCEL_MODE_DYNAMIC;
  bool leadMigrationDone = prefs.getBool("el7p_v1", false);
  prefs.end();

  // One-time migration from the old placeholder simulation/CiA402 build.
  if (!leadMigrationDone) {
    g.simulation_enabled = false;
    g_command_units_per_m = COMMAND_UNITS_PER_METRE_DEFAULT;
    Preferences mp;
    mp.begin("hv-p2p-w1p", false);
    mp.putBool("sim", false);
    mp.putFloat("units_per_m", g_command_units_per_m);
    mp.putBool("el7p_v1", true);
    mp.end();
  }
  // Drive writes are not persisted. They auto-enable only while SRVR is online and the strict safety gate is healthy.
  g.drive_writes_enabled = false;

  if (g.limit_far_m < g.limit_near_m) {
    float t = g.limit_far_m;
    g.limit_far_m = g.limit_near_m;
    g.limit_near_m = t;
  }
  g.span_m = max(g.span_m, 0.1f);
}

static void driveStopNow() {
  g.vel_request_mps = 0.0f;
  g.vel_profile_mps = 0.0f;
  g_crossover_active = false;
  g_crossover_target_sign = 0;
  g.vel_cmd_mps = 0.0f;
  if (!g.feedback_from_drive) g.vel_actual_mps = 0.0f;
  if (g.drive_writes_enabled) {
    (void)driveSendEmergencyStop();
  }
  g.drive_enabled = false;
}

static void updateLocalInputs() {
  int raw = digitalRead(PIN_LOCAL_ESTOP);
  bool active = (raw != LOCAL_ESTOP_HEALTHY_LEVEL);
  if (active != g.local_estop) {
    g.local_estop = active;
    Serial.printf("[IO] Local E-Stop -> %s\n", g.local_estop ? "ACTIVE" : "CLEAR");
    if (g.local_estop) {
      driveStopNow();
      g.drive_writes_enabled = false;
      requestSoftwareSrvonInhibit(true, "W1P_ESTOP");
    } else {
      requestSoftwareSrvonInhibit(false, "W1P_ESTOP_CLEAR");
    }
  }
}

static void setLeadshineSrvonOutput(bool enable) {
  if (!LEADSHINE_SRVON_OUTPUT_ENABLED || PIN_LEADSHINE_SRVON < 0) {
    g.srvon_output_asserted = false;
    g.srvon_output_ready = false;
    g.srvon_asserted_ms = 0;
    return;
  }
  if (enable != g.srvon_output_asserted) {
    const int level = (enable == LEADSHINE_SRVON_ACTIVE_HIGH) ? HIGH : LOW;
    digitalWrite(PIN_LEADSHINE_SRVON, level);
    g.srvon_output_asserted = enable;
    g.srvon_asserted_ms = enable ? millis() : 0;
    g.srvon_output_ready = false;
    Serial.printf("[SRVON] W1P GPIO%d -> %s. This must drive an external isolated interface into the EL7 SRV-ON DI; RS485 PR commands alone do not assert SRV-ON.\n",
                  PIN_LEADSHINE_SRVON, enable ? "ON" : "OFF");
    sendLine(String("OK SRVON_OUT ") + (enable ? "ON" : "OFF"));
  }
  if (g.srvon_output_asserted && g.srvon_asserted_ms && (millis() - g.srvon_asserted_ms >= SRVON_SETTLE_MS)) {
    g.srvon_output_ready = true;
  }
}

static bool servoEnableCommonPreconditions() {
  if (g.local_estop) return false;
  if (!g.client_connected) return false;
  if (!g.rs_link_ok) return false;
  if (!g.communication_config_read_ok) return false;
  if (!g.position_feedback_read_ok || !g.output_io_read_ok) return false;
  if (fabsf(g.vel_actual_mps) > 0.05f) return false;
  if (g.no_motion_feedback_fault) return false;
  return true;
}

static bool servoEnableOutputPreconditions() {
  if (!LEADSHINE_SRVON_OUTPUT_ENABLED || PIN_LEADSHINE_SRVON < 0) return false;
  if (!servoEnableCommonPreconditions()) return false;
  if (!g.communication_config_ok) return false;
  return true;
}

static bool softwareServoEnableReady() {
  if (!LEADSHINE_SOFTWARE_SRVON_ENABLED) return true;
  if (g.local_estop || g.software_srvon_inhibit) return false;
  return g.software_srvon_configured && g.software_srvon_ready;
}

static bool softwareSrvonConfigPreconditions() {
  if (g.local_estop || g.software_srvon_inhibit) return false;
  if (!g.client_connected) return false;
  if (!g.rs_link_ok) return false;
  if (!g.communication_config_read_ok) return false;
  // Do not torque-enable the servo while the output map is still being migrated.
  // In particular, BRK-OFF must already be verified on DO4 so the EL7 can own
  // its configured brake release/engage sequence before SRV-ON is restored.
  if (!g.do2_ready_assignment_ok || !g.do3_enabled_assignment_ok ||
      !g.do4_brake_assignment_ok || !g.do5_fault_assignment_ok) return false;
  return true;
}

static bool writeLeadshineSoftwareSrvonAssignment(bool enable, const char* reason) {
  if (!LEADSHINE_SOFTWARE_SRVON_ENABLED) return true;
  const uint16_t target = enable ? LEADSHINE_SRVON_INTERNAL_VALUE : LEADSHINE_SRVON_DISABLED_VALUE;
  if (!g.rs_link_ok) return false;
  bool ok = modbusWriteSingleRegister(DRIVE_MODBUS_ID, REG_DI1_ASSIGN, target);
  g.software_srvon_write_ok = ok;
  if (ok) {
    g.di1_assignment = target;
    g.di1_srvon_assignment_ok = enable;
    g.software_srvon_configured = enable;
    g.software_srvon_ready = false;
    g.software_srvon_configured_ms = enable ? millis() : 0;
    if (enable) {
      g.software_srvon_disable_attempted = false;
      Serial.printf("[SRVON] PA4.00/P04.00 -> 0x83 DI1 SRV-ON NC (%s).\n", reason ? reason : "enable");
      sendLine("OK SW_SRVON ON P04.00=0x83");
    } else {
      Serial.printf("[SRVON] PA4.00/P04.00 -> 0x03 DI1 SRV-ON NO, no physical DI wire = Servo Enable OFF (%s).\n", reason ? reason : "disable");
      sendLine("OK SW_SRVON OFF P04.00=0x03");
    }
  } else {
    Serial.printf("[SRVON] Failed to write PA4.00/P04.00 -> 0x%02X (%s).\n", (unsigned)target, reason ? reason : "sw_srvon");
    sendLine(enable ? "ERR SW_SRVON_ON WRITE_FAILED" : "ERR SW_SRVON_OFF WRITE_FAILED");
  }
  return ok;
}

static void requestSoftwareSrvonInhibit(bool inhibit, const char* reason) {
  if (!LEADSHINE_SOFTWARE_SRVON_ENABLED) return;
  g.software_srvon_inhibit = inhibit;
  if (inhibit) {
    g.software_srvon_ready = false;
    g.software_srvon_configured = false;
    g.software_srvon_configured_ms = 0;
    if (LEADSHINE_DROP_SW_SRVON_ON_ESTOP && !g.software_srvon_disable_attempted) {
      if (g.di1_assignment == LEADSHINE_SRVON_DISABLED_VALUE) {
        g.software_srvon_disable_attempted = true;
      } else if (g.di1_assignment == LEADSHINE_SRVON_INTERNAL_VALUE || g.di1_assignment == 0xFFFF) {
        g.software_srvon_disable_attempted = writeLeadshineSoftwareSrvonAssignment(false, reason);
      }
    }
  } else {
    g.software_srvon_disable_attempted = false;
    g.software_srvon_write_attempted = false;
    g.software_srvon_ready = false;
    g.software_srvon_configured = (g.di1_assignment == LEADSHINE_SRVON_INTERNAL_VALUE);
    g.software_srvon_configured_ms = g.software_srvon_configured ? millis() : 0;
  }
}

static bool configureLeadshineOutputAssignment(uint16_t reg, uint16_t expected, uint16_t &current,
                                               bool &readOk, bool &assignmentOk, const char* label) {
  Serial.printf("[EL7 DO] Configuring %s register 0x%04X from 0x%02X to 0x%02X.\n",
                label, (unsigned)reg, (unsigned)current, (unsigned)expected);
  bool ok = modbusWriteSingleRegister(DRIVE_MODBUS_ID, reg, expected);
  if (!ok) {
    sendLine(String("ERR EL7_DO_MAP ") + label + " WRITE_FAILED");
    return false;
  }
  uint16_t verify = 0xFFFF;
  delay(3);
  bool verifyOk = modbusReadU16(DRIVE_MODBUS_ID, reg, verify);
  readOk = verifyOk;
  if (verifyOk) current = verify;
  assignmentOk = verifyOk && (verify == expected);
  sendLine(String(assignmentOk ? "OK EL7_DO_MAP " : "ERR EL7_DO_MAP ") + label +
           (assignmentOk ? " VERIFIED" : " VERIFY_FAILED"));
  return assignmentOk;
}

static void serviceLeadshineOutputAssignments() {
  // HV P2P output plan:
  //   Power   = direct hardwired indication (not a programmable EL7 DO)
  //   DO2     = Ready / SRDY
  //   DO3     = Enabled / SRV-ST
  //   DO4     = Brake release / BRK-OFF
  //   DO5     = Fault / ALARM
  // EL7 owns brake release/engage timing. W1P only verifies/configures the
  // assignment map while stopped, before normal motion can arm.
  if (g.do2_ready_assignment_ok && g.do3_enabled_assignment_ok &&
      g.do4_brake_assignment_ok && g.do5_fault_assignment_ok) return;
  if (g.local_estop || !g.client_connected || !g.rs_link_ok || !g.communication_config_read_ok) return;
  if (g.drive_writes_enabled || fabsf(g.vel_actual_mps) > 0.05f) return;
  const uint32_t now = millis();
  if (g.output_config_last_attempt_ms && (now - g.output_config_last_attempt_ms) < 3000) return;
  g.output_config_last_attempt_ms = now;

  // If this drive was previously commissioned with software SRV-ON already
  // active, torque-inhibit it before altering any programmable output mapping.
  // This is especially important for DO4 because BRK-OFF owns the external
  // motor-brake release path. The normal software SRV-ON service will restore
  // P04.00=0x83 only after the complete DO2..DO5 map has been re-read/verified.
  if (g.di1_assignment == LEADSHINE_SRVON_INTERNAL_VALUE) {
    (void)writeLeadshineSoftwareSrvonAssignment(false, "EL7_DO_MAP_MIGRATION");
    return;
  }

  // Change at most one output assignment per service interval. Motion remains
  // locked until a later configuration poll verifies the complete map.
  if (!g.do2_ready_assignment_ok) {
    configureLeadshineOutputAssignment(REG_DO2_ASSIGN, EXPECTED_DO2_READY_ASSIGN,
                                       g.do2_assignment, g.do2_assignment_read_ok,
                                       g.do2_ready_assignment_ok, "DO2=SRDY");
    return;
  }
  if (!g.do3_enabled_assignment_ok) {
    configureLeadshineOutputAssignment(REG_DO3_ASSIGN, EXPECTED_DO3_ENABLED_ASSIGN,
                                       g.do3_assignment, g.do3_assignment_read_ok,
                                       g.do3_enabled_assignment_ok, "DO3=SRV-ST");
    return;
  }
  if (!g.do4_brake_assignment_ok) {
    configureLeadshineOutputAssignment(REG_DO4_ASSIGN, EXPECTED_DO4_BRAKE_ASSIGN,
                                       g.do4_assignment, g.do4_assignment_read_ok,
                                       g.do4_brake_assignment_ok, "DO4=BRK-OFF");
    return;
  }
  if (!g.do5_fault_assignment_ok) {
    configureLeadshineOutputAssignment(REG_DO5_ASSIGN, EXPECTED_DO5_FAULT_ASSIGN,
                                       g.do5_assignment, g.do5_assignment_read_ok,
                                       g.do5_fault_assignment_ok, "DO5=ALARM");
    return;
  }
}

static void serviceLeadshineSoftwareServoEnable() {
  if (!LEADSHINE_SOFTWARE_SRVON_ENABLED) {
    g.software_srvon_configured = true;
    g.software_srvon_ready = true;
    return;
  }

  if (g.local_estop || g.software_srvon_inhibit) {
    requestSoftwareSrvonInhibit(true, g.local_estop ? "E-STOP" : "REMOTE_INHIBIT");
    return;
  }

  if (!softwareSrvonConfigPreconditions()) {
    // Do not clear software_srvon_ready just because the motor is moving. PA4.00 is a persistent
    // drive input assignment, not a per-motion readiness latch. Clearing it during movement caused
    // AUTO_DRIVE_ENABLE/AUTO_DRIVE_DISABLE SRVON_NOT_READY loops.
    return;
  }

  if (g.legacy_di5_srvon_conflict) {
    if (!g.legacy_di5_cleanup_attempted) {
      g.legacy_di5_cleanup_attempted = true;
      Serial.printf("[SRVON] Legacy DI5/P04.04 has old SRV-ON value %u. Clearing DI5 to 0x00 to remove possible Er-211 input assignment conflict.\n", (unsigned)g.legacy_di5_assignment);
      bool ok = modbusWriteSingleRegister(DRIVE_MODBUS_ID, REG_LEGACY_DI5_ASSIGN, DI_DISABLED_VALUE);
      g.legacy_di5_cleanup_ok = ok;
      if (ok) {
        g.legacy_di5_assignment = DI_DISABLED_VALUE;
        g.legacy_di5_srvon_conflict = false;
        Serial.println("[SRVON] Legacy DI5/P04.04 cleared to 0x00. Power-cycle or alarm-reset the EL7 if Er-211 remains latched.");
        sendLine("OK CLEAR_DI5 P04.04=0x00");
      } else {
        Serial.println("[SRVON] Failed to clear legacy DI5/P04.04 SRV-ON assignment. Check MotionStudio PA4.04 manually.");
        sendLine("ERR CLEAR_DI5 WRITE_FAILED");
      }
    }
    return;
  }

  if (g.di1_assignment == LEADSHINE_SRVON_INTERNAL_VALUE) {
    if (!g.software_srvon_configured) {
      g.software_srvon_configured = true;
      g.software_srvon_configured_ms = millis();
      Serial.println("[SRVON] EL7 PA4.00/P04.00 already set to 0x83: DI1 SRV-ON Normally Closed selected.");
      sendLine("OK SW_SRVON DI1_NC");
    }
    if (g.software_srvon_configured_ms && (millis() - g.software_srvon_configured_ms >= SOFTWARE_SRVON_SETTLE_MS)) {
      g.software_srvon_ready = true;
    }
    return;
  }

  if (!g.software_srvon_write_attempted || g.di1_assignment == LEADSHINE_SRVON_DISABLED_VALUE) {
    g.software_srvon_write_attempted = true;
    Serial.printf("[SRVON] Writing EL7 PA4.00/P04.00 from %u to 0x83: DI1 Servo ON Input (SRV-ON), Normally Closed.\n", (unsigned)g.di1_assignment);
    (void)writeLeadshineSoftwareSrvonAssignment(true, "AUTO_RESTORE");
  }
}

static void serviceLeadshineServoEnableOutput() {
  serviceLeadshineOutputAssignments();
  serviceLeadshineSoftwareServoEnable();
  setLeadshineSrvonOutput(servoEnableOutputPreconditions());
}

static float moveToward(float current, float target, float maxDelta) {
  if (target > current) return min(current + maxDelta, target);
  if (target < current) return max(current - maxDelta, target);
  return target;
}

static float selectedProfileRate(float current, float target) {
  const bool currentZero = fabsf(current) <= MOTION_ZERO_EPS_MPS;
  const bool targetZero = fabsf(target) <= MOTION_ZERO_EPS_MPS;
  const int8_t currentSign = current > MOTION_ZERO_EPS_MPS ? 1 : (current < -MOTION_ZERO_EPS_MPS ? -1 : 0);
  const int8_t targetSign = target > MOTION_ZERO_EPS_MPS ? 1 : (target < -MOTION_ZERO_EPS_MPS ? -1 : 0);

  if (targetZero) {
    g_crossover_active = false;
    g_crossover_target_sign = 0;
    return g_drive_stop_decel_mps2;
  }
  if (!g_crossover_active && currentSign != 0 && targetSign != 0 && currentSign != targetSign) {
    g_crossover_active = true;
    g_crossover_target_sign = targetSign;
  }
  if (g_crossover_active) {
    if (targetSign != g_crossover_target_sign) {
      g_crossover_active = false;
      g_crossover_target_sign = 0;
    } else if (fabsf(target - current) <= MOTION_ZERO_EPS_MPS) {
      g_crossover_active = false;
      g_crossover_target_sign = 0;
    } else {
      return g_drive_crossover_mps2;
    }
  }
  if (currentZero) return g_drive_accel_mps2;
  if (fabsf(target) > fabsf(current)) return g_drive_accel_mps2;
  return g_drive_decel_mps2;
}


static float limitVelocityForSoftLimits(float pos, float requestedVel) {
  if (g.service_mode) return requestedVel;
  if (fabsf(requestedVel) <= MOTION_ZERO_EPS_MPS) return 0.0f;

  float nl = g.limit_near_m;
  float fl = g.limit_far_m;
  if (fl < nl) { float t = fl; fl = nl; nl = t; }

  const float stopDecel = max(0.10f, g_drive_stop_decel_mps2);
  const float fbSpeed = fabsf(g.vel_actual_mps);
  const float guard = min(LIMIT_STOP_GUARD_MAX_M, max(LIMIT_STOP_GUARD_BASE_M, LIMIT_STOP_GUARD_BASE_M + LIMIT_STOP_GUARD_PER_MPS * fbSpeed));

  if (requestedVel < 0.0f) {
    const float remaining = pos - nl;
    if (remaining <= guard) return 0.0f;
    const float effective = max(0.0f, remaining - guard);
    const float allowed = sqrtf(max(0.0f, 2.0f * stopDecel * effective));
    return -min(fabsf(requestedVel), allowed);
  }
  if (requestedVel > 0.0f) {
    const float remaining = fl - pos;
    if (remaining <= guard) return 0.0f;
    const float effective = max(0.0f, remaining - guard);
    const float allowed = sqrtf(max(0.0f, 2.0f * stopDecel * effective));
    return min(fabsf(requestedVel), allowed);
  }
  return 0.0f;
}

static bool driveAutoEnableReady() {
  const unsigned long now = millis();
  const bool requestingMotion = fabsf(g.vel_request_mps) >= AUTO_DRIVE_ARM_MIN_REQUEST_MPS;
  const bool requestFresh = (lastNonZeroVelocityCommandMs > 0) && ((now - lastNonZeroVelocityCommandMs) <= AUTO_DRIVE_ARM_REQUEST_FRESH_MS);

  if (g.local_estop) return false;
  if (!g.client_connected) return false;
  if (!g.drive_feedback_ok) return false;
  if (!g.communication_config_ok) return false;
  if (!g.rs_link_ok) return false;
  if (!softwareServoEnableReady()) return false;
  if (LEADSHINE_SRVON_OUTPUT_ENABLED && !g.srvon_output_ready) return false;
  if (g.no_motion_feedback_fault && requestingMotion) return false;

  if (!g.drive_writes_enabled) {
    // v26.08.31.04: EdgeBox W5500 + isolated native RS485; only arm from WAIT on a fresh, non-zero joystick command.
    // Do not re-arm from stale VEL state, and do not arm while the motor is still
    // coasting from a previous PR stop. Once armed, do not drop writes just because
    // feedback velocity becomes non-zero; that caused the observed step/pulse motion.
    if (!requestingMotion || !requestFresh) return false;
    if (fabsf(g.vel_actual_mps) > AUTO_DRIVE_MOVING_GATE_MPS) return false;
  }
  return true;
}



static void serviceNoMotionFeedbackFault() {
  const unsigned long now = millis();
  const bool requesting_motion = g.drive_writes_enabled && fabsf(g.vel_cmd_mps) >= 0.08f;
  const bool no_feedback_motion = fabsf(g.vel_actual_mps) < 0.025f;
  if (requesting_motion && no_feedback_motion) {
    if (g.no_motion_feedback_since_ms == 0) g.no_motion_feedback_since_ms = now;
    if ((now - g.no_motion_feedback_since_ms) >= 900) {
      if (!g.no_motion_feedback_fault) {
        Serial.println("[DRIVE] Commanded velocity but no motor feedback. Servo Enable/SRV-ON, brake release or main power is not active.");
      }
      g.no_motion_feedback_fault = true;
    }
  } else {
    g.no_motion_feedback_since_ms = 0;
    if (fabsf(g.vel_request_mps) < 0.02f && fabsf(g.vel_cmd_mps) < 0.02f) {
      g.no_motion_feedback_fault = false;
    }
  }
}

static const char* driveAutoEnableBlockReason() {
  const unsigned long now = millis();
  if (g.local_estop) return "W1P_ESTOP";
  if (!g.client_connected) return "SRVR_MISSING";
  if (!g.drive_feedback_ok) return "FEEDBACK_NOT_READY";
  if (!g.communication_config_ok) return "CONFIG_NOT_READY";
  if (!g.rs_link_ok) return "RS485_NOT_READY";
  if (!softwareServoEnableReady()) return "SRVON_NOT_READY";
  if (LEADSHINE_SRVON_OUTPUT_ENABLED && !g.srvon_output_ready) return "SRVON_OUTPUT_SETTLING";
  if (!g.drive_writes_enabled && fabsf(g.vel_request_mps) < AUTO_DRIVE_ARM_MIN_REQUEST_MPS) return "WAITING_JOYSTICK";
  if (!g.drive_writes_enabled && (lastNonZeroVelocityCommandMs == 0 || (now - lastNonZeroVelocityCommandMs) > AUTO_DRIVE_ARM_REQUEST_FRESH_MS)) return "STALE_JOYSTICK";
  if (!g.drive_writes_enabled && fabsf(g.vel_actual_mps) > AUTO_DRIVE_MOVING_GATE_MPS) return "MOTOR_STILL_MOVING";
  if (g.no_motion_feedback_fault && fabsf(g.vel_request_mps) >= 0.02f) return "NO_MOTION_FEEDBACK";
  return "OK";
}


static void serviceAutomaticDriveEnable() {
  const bool ready = driveAutoEnableReady();
  const unsigned long now = millis();

  if (ready && !g.drive_writes_enabled) {
    g.simulation_enabled = false;
    g.drive_writes_enabled = true;
    // Arm the command path only after a fresh real joystick request. Preserve the
    // request and let the 50 Hz W1P profile ramp from zero. Do not trigger PR0 at idle.
    g.vel_profile_mps = 0.0f;
    g.vel_cmd_mps = 0.0f;
    g_crossover_active = false;
    g_crossover_target_sign = 0;
    lastConfiguredAccelMps2 = -1.0f;
    lastConfiguredDecelMps2 = -1.0f;
    lastConfiguredCrossMps2 = -1.0f;
    lastDriveCommandMps = 0.0f;      // no initial zero PR0 trigger on arm
    lastDriveCommandMs = now;
    g.drive_enabled = false;
    Serial.println("[DRIVE] Automatic drive command enable: fresh joystick command; continuous write mode stays armed during motion.");
    sendLine("OK AUTO_DRIVE_ENABLE");
    sendStatusLine(true);
    return;
  }

  if (!ready && g.drive_writes_enabled) {
    const char* reason = driveAutoEnableBlockReason();
    // Do not disable the command path merely because the motor is moving. That
    // was the source of the one-second step/pulse motion. Only disable for real
    // safety/config faults, or once the joystick command, W1P profile and drive
    // feedback have all settled at zero.
    const bool commandSettledZero =
      fabsf(g.vel_request_mps) <= AUTO_DRIVE_DISABLE_ZERO_REQUEST_MPS &&
      fabsf(g.vel_profile_mps) <= MOTION_ZERO_EPS_MPS &&
      fabsf(g.vel_cmd_mps) <= MOTION_ZERO_EPS_MPS &&
      fabsf(g.vel_actual_mps) <= AUTO_DRIVE_MOVING_GATE_MPS &&
      (lastVelocityCommandMs > 0) && ((now - lastVelocityCommandMs) > 350);
    const bool safetyLost =
      g.local_estop || !g.client_connected || !g.drive_feedback_ok || !g.communication_config_ok ||
      !g.rs_link_ok || !softwareServoEnableReady() ||
      (LEADSHINE_SRVON_OUTPUT_ENABLED && !g.srvon_output_ready) ||
      (g.no_motion_feedback_fault && fabsf(g.vel_request_mps) >= 0.02f);

    if (commandSettledZero || safetyLost) {
      driveStopNow();
      g.drive_writes_enabled = false;
      Serial.printf("[DRIVE] Automatic drive command disable: %s.\n", commandSettledZero ? "command settled at zero" : reason);
      sendLine(String("OK AUTO_DRIVE_DISABLE REASON=") + (commandSettledZero ? "COMMAND_ZERO" : reason));
      sendStatusLine(true);
    }
  }
}


static void serviceMotionProfile() {
  const unsigned long now = millis();
  if (lastMotionProfileMs == 0) {
    lastMotionProfileMs = now;
    return;
  }
  if ((now - lastMotionProfileMs) < MOTION_PROFILE_INTERVAL_MS) return;
  float dt = float(now - lastMotionProfileMs) / 1000.0f;
  lastMotionProfileMs = now;
  if (dt <= 0.0f || dt > 0.25f) dt = float(MOTION_PROFILE_INTERVAL_MS) / 1000.0f;

  if (g.local_estop || !g.client_connected) {
    g.vel_request_mps = 0.0f;
  }
  float target = constrain(g.vel_request_mps, -MAX_CMD_VEL_MPS, MAX_CMD_VEL_MPS);
  // v26.08.31.04: EdgeBox W5500 + isolated native RS485; predictive hard-limit guard.  SRVR also tapers before
  // Near/Far, but W1P applies the same stopping-distance rule locally so a
  // delayed network packet cannot keep driving past an end limit.
  target = limitVelocityForSoftLimits(g.pos_m, target);

  // Traditional mode advances the command-only velocity profile at the selected rate.
  // Dynamic mode treats joystick position as a constant cable-speed request and
  // keeps the outer command tied to measured winch speed. The EL7's internal
  // velocity loop then supplies whatever torque is required to hold the target
  // RPM/cable speed on uphill/downhill cable slopes.
  const float profileReference = g.vel_profile_mps;
  const float rate = max(0.05f, selectedProfileRate(profileReference, target));
  float nextProfile = moveToward(profileReference, target, rate * dt);
  if (g_acceleration_mode == ACCEL_MODE_DYNAMIC && g.drive_feedback_ok && isfinite(g.vel_actual_mps) &&
      fabsf(target - profileReference) > MOTION_ZERO_EPS_MPS) {
    const float lead = max(DYNAMIC_MIN_LEAD_MPS, rate * DYNAMIC_LEAD_TIME_S);
    if (target > profileReference) {
      nextProfile = max(profileReference, min(nextProfile, g.vel_actual_mps + lead));
    } else if (target < profileReference) {
      nextProfile = min(profileReference, max(nextProfile, g.vel_actual_mps - lead));
    }
  }
  g.vel_profile_mps = nextProfile;
  if (fabsf(g.vel_profile_mps) <= MOTION_ZERO_EPS_MPS && fabsf(target) <= MOTION_ZERO_EPS_MPS) {
    g.vel_profile_mps = 0.0f;
  }

  float cmdOut = g.vel_profile_mps;
  if (g_acceleration_mode == ACCEL_MODE_DYNAMIC && g.drive_feedback_ok && isfinite(g_dynamic_feedback_mps) &&
      fabsf(g.vel_profile_mps) > MOTION_ZERO_EPS_MPS && fabsf(target) > MOTION_ZERO_EPS_MPS) {
    float speedErr = g.vel_profile_mps - g_dynamic_feedback_mps;
    if (fabsf(speedErr) < DYNAMIC_CORR_DEADBAND_MPS) speedErr = 0.0f;
    const float corrLimit = min(DYNAMIC_CORR_MAX_MPS, max(DYNAMIC_CORR_BASE_MPS, fabsf(g.vel_profile_mps) * DYNAMIC_CORR_FRAC + DYNAMIC_CORR_BASE_MPS));
    g_dynamic_speed_i_mps += speedErr * dt;
    g_dynamic_speed_i_mps = constrain(g_dynamic_speed_i_mps, -corrLimit / max(0.05f, DYNAMIC_SPEED_KI), corrLimit / max(0.05f, DYNAMIC_SPEED_KI));
    float corr = DYNAMIC_SPEED_KP * speedErr + DYNAMIC_SPEED_KI * g_dynamic_speed_i_mps;
    corr = constrain(corr, -corrLimit, corrLimit);
    cmdOut = constrain(g.vel_profile_mps + corr, -MAX_CMD_VEL_MPS, MAX_CMD_VEL_MPS);
    // Never let a correction reverse the commanded direction while a target exists.
    if ((g.vel_profile_mps > 0.0f && cmdOut < 0.0f) || (g.vel_profile_mps < 0.0f && cmdOut > 0.0f)) cmdOut = 0.0f;
  } else {
    g_dynamic_speed_i_mps = 0.0f;
    g_dynamic_feedback_mps = g.vel_actual_mps;
  }
  if (fabsf(target) <= MOTION_ZERO_EPS_MPS && fabsf(g.vel_profile_mps) <= MOTION_ZERO_EPS_MPS) {
    g_dynamic_speed_i_mps = 0.0f;
    cmdOut = 0.0f;
  }
  g.vel_cmd_mps = cmdOut;

  serviceNoMotionFeedbackFault();

  // Assert W1P-controlled SRV-ON output first, then allow PR/RS485 command writes only after it has settled.
  serviceLeadshineServoEnableOutput();

  // Keep the command path enabled automatically whenever the full safety gate is healthy.
  serviceAutomaticDriveEnable();

  if (g.drive_writes_enabled && g.no_motion_feedback_fault) {
    driveStopNow();
    g.drive_writes_enabled = false;
    return;
  }

  if (g.drive_writes_enabled && (!g.drive_feedback_ok || !g.communication_config_ok)) {
    // Loss of verified Leadshine feedback/config is a control-path fault. Stop immediately.
    driveStopNow();
    g.drive_writes_enabled = false;
    return;
  }

  if (g.drive_writes_enabled) {
    const bool intervalDue = (now - lastDriveCommandMs) >= DRIVE_COMMAND_MIN_INTERVAL_MS;
    const bool changedEnough = fabsf(g.vel_cmd_mps - lastDriveCommandMps) >= DRIVE_COMMAND_MIN_DELTA_MPS;
    const bool zeroCommand = fabsf(g.vel_cmd_mps) <= MOTION_ZERO_EPS_MPS;
    const bool lastZeroCommand = fabsf(lastDriveCommandMps) <= MOTION_ZERO_EPS_MPS;
    // Do not keep re-triggering PR0 at 0 m/s. The EL7 stays armed, and repeated
    // zero triggers can mask the real command path while commissioning. Send
    // one zero after arming or after a nonzero move, then only keep alive while
    // an actual nonzero motion command is active.
    const bool keepaliveDue = (!zeroCommand) && ((now - lastDriveCommandMs) >= 250);
    const bool needInitialZero = zeroCommand && !lastZeroCommand;
    if (intervalDue && (changedEnough || keepaliveDue || needInitialZero)) {
      if (driveWriteVelocityCommandMps(g.vel_cmd_mps)) {
        lastDriveCommandMps = g.vel_cmd_mps;
        lastDriveCommandMs = now;
      }
    }
    return;
  }

  if (g.feedback_from_drive) {
    // Read-only commissioning mode: continue reporting encoder speed/position,
    // but never retain a motion request.
    g.vel_request_mps = 0.0f;
    g.vel_profile_mps = 0.0f;
    g.vel_cmd_mps = 0.0f;
    return;
  }

  // Simulation follows the same local profile so both acceleration modes can be
  // tested without a powered drive.
  g.vel_actual_mps = g.vel_cmd_mps;
  if (g.simulation_enabled) {
    g.pos_m += g.vel_actual_mps * dt;
    if (!g.service_mode) {
      if (g.pos_m <= g.limit_near_m) {
        g.pos_m = g.limit_near_m;
        if (g.vel_actual_mps < 0.0f) {
          g.vel_actual_mps = 0.0f;
          g.vel_profile_mps = 0.0f;
          g.vel_cmd_mps = 0.0f;
        }
      }
      if (g.pos_m >= g.limit_far_m) {
        g.pos_m = g.limit_far_m;
        if (g.vel_actual_mps > 0.0f) {
          g.vel_actual_mps = 0.0f;
          g.vel_profile_mps = 0.0f;
          g.vel_cmd_mps = 0.0f;
        }
      }
    }
  }
}

static void updateMotionModel() {
  serviceMotionProfile();
}

static void sendLine(const String& s) {
  if (!peerValid) return;
  udp.beginPacket(peerIP, peerPort);
  udp.print(s);
  udp.print("\n");
  udp.endPacket();
}

static bool hmiLinkConnected(){
  uint32_t now = millis();
  return (g_lastHmiRxMs > 0) && ((now - g_lastHmiRxMs) <= HMI_LINK_TIMEOUT_MS);
}

static void sendNetworkConfigToHmi(){
  String line = "CFG1|w1p_ip=" + ipToString(LOCAL_IP) + "|ctrl_ip=" + ipToString(LOCAL_IP) + "|srvr_ip=" + ipToString(SRVR_IP) + "|subnet=" + ipToString(SUBNET) + "|gateway=" + ipToString(GATEWAY);
  HMI.println(line);
}

static void sendW1pHmiStatusToSrvr(){
  uint32_t now = millis();
  if((now - g_lastHmiStatusTxMs) < 1000) return;
  g_lastHmiStatusTxMs = now;
  uint32_t age = g_lastHmiRxMs ? (now - g_lastHmiRxMs) : 999999;
  String line = "W1P_HMI_STATUS|w1p_ts=" + String(hmiLinkConnected() ? 1 : 0) + "|age_ms=" + String((unsigned long)age) + "|version=" + String(FW_VERSION);
  sendLine(line);
}

static String buildFallbackDisplayPacket(){
  String line = "HMI1";
  line += "|pos=" + String(g.pos_m, 3);
  if (g.service_mode) {
    line += "|to_near=" + String(g.pos_m - g.limit_near_m, 3);
    line += "|to_far=" + String(g.limit_far_m - g.pos_m, 3);
  } else {
    line += "|to_near=" + String(max(0.0f, g.pos_m - g.limit_near_m), 3);
    line += "|to_far=" + String(max(0.0f, g.limit_far_m - g.pos_m), 3);
  }
  line += "|speed_mps=" + String(g.vel_actual_mps, 2);
  line += "|speed_kmh=" + String(g.vel_actual_mps * 3.6f, 2);
  line += "|near=" + String(g.limit_near_m, 2);
  line += "|ref=0.00";
  line += "|far=" + String(g.limit_far_m, 2);
  line += "|ramp_near=0.00|ramp_far=0.00|ref_vis=0";
  const bool srvr_missing = !g.client_connected;
  const bool rs485_link_fault = (strcmp(rsStatusText(), "CONNECTED") != 0);
  const bool rs485_config_fault = !g.communication_config_ok;
  const bool rs485_feedback_fault = !g.drive_feedback_ok;
  const bool any_rs485_fault = rs485_link_fault || rs485_config_fault || rs485_feedback_fault;
  const bool fallback_fault = g.local_estop || srvr_missing || any_rs485_fault;
  // Keep the physical E-stop input distinct from derived fail-safe faults.
  // SAFETY remains asserted for RS485/SRVR faults so downstream diagnostics
  // can show that motion is inhibited without calling it E-Stop W1P.
  line += "|estop=" + String(g.local_estop ? 1 : 0);
  line += "|estop_src=" + String(g.local_estop ? "W1P" : "");
  line += "|safety=" + String(fallback_fault ? 1 : 0);
  line += "|safety_src=" + String(g.local_estop ? "W1P" : (srvr_missing ? "SRVR" : (any_rs485_fault ? "RS485" : "")));
  if (g.local_estop) line += "|status=E-Stop W1P|status_level=red";
  else if (srvr_missing) line += "|status=E-Stop SRVR|status_level=red";
  else if (rs485_link_fault || rs485_config_fault) line += "|status=RS485 Fault|status_level=red";
  else if (rs485_feedback_fault) line += "|status=RS485 Feedback Fault|status_level=red";
  else line += "|status=Active|status_level=blue";
  line += "|ctrl=0|srvr=" + String(g.client_connected ? 1 : 0) + "|w1p=1|w1p_state=" + String(any_rs485_fault ? "fault" : "ok") + "|service=" + String(g.service_mode ? 1 : 0);
  line += "|flags=0";
  line += "|aux1=AUX 1|aux2=AUX 2|aux3=AUX 3|aux4=AUX 4";
  line += "|max_mps=0.00|max_kmh=0.00|mode=Mode A";
  line += "|preset_names=|preset_pos=|preset_vis=0,0,0,0,0,0";
  return line;
}

static void serviceHmiUart(){
  static String line;
  while(HMI.available()) {
    char ch = (char)HMI.read();
    if(ch == '\r') continue;
    if(ch == '\n') {
      line.trim();
      if(line.length()) {
        g_lastHmiRxMs = millis();
        if(line == "PING") {
          HMI.println("PONG");
          if(!g_latestDisplayPacket.length() || ((millis() - g_lastSrvrDisplayMs) > SRVR_DISPLAY_TIMEOUT_MS)) HMI.println(buildFallbackDisplayPacket());
        } else if(line == "CFG?") {
          sendNetworkConfigToHmi();
        } else if(line.startsWith("CFG1|")) {
          String note;
          bool ok = saveNetworkConfigFromHmi(line, note);
          HMI.println(String("CFG_ACK|ok=") + (ok ? "1" : "0") + "|note=" + note);
          sendNetworkConfigToHmi();
          if(ok && hvGetPipeField(line, "reset") == "1") { delay(250); ESP.restart(); }
        } else if(line == "AUX1" || line == "AUX2" || line == "AUX3" || line == "AUX4") {
          sendLine(String("W1PTS_") + line);
        } else if(line == "LAYOUT?") {
          HMI.println(String("UIL1|title=HV P2P W1P-TS|subtitle=") + FW_VERSION + "|layout=main4|theme=hv|aux1=AUX 1|aux2=AUX 2|aux3=AUX 3|aux4=AUX 4|hint=Ready");
        }
      }
      line = "";
    } else if(line.length() < 511) {
      line += ch;
    }
  }
}

static void serviceHmiDisplay(){
  uint32_t now = millis();
  if((now - g_lastHmiDisplayForwardMs) < DISPLAY_FORWARD_MIN_MS) return;
  String nextDisplay;
  if(g_latestDisplayPacket.length() && ((now - g_lastSrvrDisplayMs) <= SRVR_DISPLAY_TIMEOUT_MS)) nextDisplay = g_latestDisplayPacket;
  else nextDisplay = buildFallbackDisplayPacket();
  const bool changed = (nextDisplay != g_lastForwardedDisplayPacket);
  const bool keepalive_due = ((now - g_lastHmiDisplayKeepaliveMs) >= DISPLAY_KEEPALIVE_MS);
  if(changed || keepalive_due) {
    g_lastHmiDisplayForwardMs = now;
    g_lastHmiDisplayKeepaliveMs = now;
    g_lastForwardedDisplayPacket = nextDisplay;
    HMI.println(nextDisplay);
  } else {
    g_lastHmiDisplayForwardMs = now;
  }
}

static void sendStatusLine(bool force) {
  unsigned long now = millis();
  if (!force && (now - lastStatusMs) < W1P_STATUS_INTERVAL_MS) return;
  lastStatusMs = now;

  String line = "STATUS";
  line += " POS_M=" + String(g.pos_m, 3);
  line += " SPAN_M=" + String(g.span_m, 3);
  line += " NL=" + String(g.limit_near_m, 3);
  line += " FL=" + String(g.limit_far_m, 3);
  line += " VEL_MPS=" + String(g.vel_actual_mps, 3);
  line += " REQ_VEL_MPS=" + String(g.vel_request_mps, 3);
  line += " PROFILE_VEL_MPS=" + String(g.vel_profile_mps, 3);
  line += " CMD_VEL_MPS=" + String(g.vel_cmd_mps, 3);
  line += " ACC_MODE=" + String(g_acceleration_mode == ACCEL_MODE_DYNAMIC ? "Speed" : "Power");
  line += " ACCEL=" + String(g_drive_accel_mps2, 3);
  line += " DECEL=" + String(g_drive_decel_mps2, 3);
  line += " CROSS=" + String(g_drive_crossover_mps2, 3);
  line += " STOP_DECEL=" + String(g_drive_stop_decel_mps2, 3);
  const bool status_srvr_missing = !g.client_connected;
  const bool status_rs485_link_fault = (strcmp(rsStatusText(), "CONNECTED") != 0);
  const bool status_rs485_config_fault = !g.communication_config_ok;
  const bool status_rs485_feedback_fault = !g.drive_feedback_ok;
  const bool status_any_rs485_fault = status_rs485_link_fault || status_rs485_config_fault || status_rs485_feedback_fault;
  const bool status_safety = g.local_estop || status_srvr_missing || status_any_rs485_fault;
  line += " ESTOP=" + String(g.local_estop ? 1 : 0);
  line += " ESTOP_SRC=" + String(g.local_estop ? "W1P" : "NONE");
  line += " SAFETY=" + String(status_safety ? 1 : 0);
  line += " SAFETY_SRC=" + String(g.local_estop ? "W1P" : (status_srvr_missing ? "SRVR" : (status_any_rs485_fault ? "RS485" : "NONE")));
  line += " ETH=" + String(g.ethernet_up ? 1 : 0);
  line += " READY=" + String(g.drive_ready ? 1 : 0);
  line += " FAULT=" + String(g.drive_fault ? 1 : 0);
  line += " SIM=" + String(g.simulation_enabled ? 1 : 0);
  line += " WRITE_EN=" + String(g.drive_writes_enabled ? 1 : 0);
  line += " LEAD_CFG=" + String(!g.communication_config_read_ok ? "READ_FAULT" : (g.communication_config_ok ? "OK" : "MISMATCH"));
  line += " CFG_CTRL=" + String(g.control_mode_read_ok ? 1 : 0);
  line += " CFG_FMT=" + String(g.rs485_mode_read_ok ? 1 : 0);
  line += " CFG_BAUD=" + String(g.rs485_baud_read_ok ? 1 : 0);
  line += " CFG_ID=" + String(g.rs485_address_read_ok ? 1 : 0);
  line += " MB_EX=" + String(g.last_modbus_exception);
  line += " CTRL_MODE=" + String(g.control_mode);
  line += " RS_FMT=" + String(g.rs485_mode);
  line += " RS_BAUD=" + String(g.rs485_baud_code);
  line += " RS_ID=" + String(g.rs485_address);
  line += " IN_IO=" + String(g.input_io_status);
  line += " OUT_IO=" + String(g.output_io_status);
  line += " DI1_ASSIGN=" + String(g.di1_assignment);
  line += " DI1_CFG=" + String(g.di1_srvon_assignment_ok ? 1 : 0);
  line += " LEGACY_DI5_ASSIGN=" + String(g.legacy_di5_assignment);
  line += " LEGACY_DI5_CONFLICT=" + String(g.legacy_di5_srvon_conflict ? 1 : 0);
  line += " LEGACY_DI5_CLEAR=" + String(g.legacy_di5_cleanup_ok ? 1 : 0);
  line += " SRVON_IN=" + String(g.srvon_input_valid ? 1 : 0);
  line += " SRVON_OUT=" + String(g.srvon_output_asserted ? 1 : 0);
  line += " SRVON_READY=" + String(g.srvon_output_ready ? 1 : 0);
  line += " SRVON_PIN=" + String(PIN_LEADSHINE_SRVON);
  line += " SW_SRVON=" + String(g.software_srvon_configured ? 1 : 0);
  line += " SW_SRVON_READY=" + String(g.software_srvon_ready ? 1 : 0);
  line += " SW_SRVON_OK=" + String(g.software_srvon_write_ok ? 1 : 0);
  line += " SW_SRVON_INHIBIT=" + String(g.software_srvon_inhibit ? 1 : 0);
  line += " POS_READ=" + String(g.position_feedback_read_ok ? 1 : 0);
  line += " IO_READ=" + String(g.output_io_read_ok ? 1 : 0);
  line += " DO1_ASSIGN=" + String(g.do1_assignment);
  line += " DO2_CFG=" + String(g.do2_ready_assignment_ok ? 1 : 0);
  line += " DO2_ASSIGN=" + String(g.do2_assignment);
  line += " READY_OUT=" + String(g.servo_ready ? 1 : 0);
  line += " DO3_CFG=" + String(g.do3_enabled_assignment_ok ? 1 : 0);
  line += " DO3_ASSIGN=" + String(g.do3_assignment);
  line += " ENABLED_OUT=" + String(g.servo_enabled_output ? 1 : 0);
  line += " DO4_CFG=" + String(g.do4_brake_assignment_ok ? 1 : 0);
  line += " DO4_ASSIGN=" + String(g.do4_assignment);
  line += " BRAKE_OUT=" + String(g.brake_output_released ? 1 : 0);
  line += " DO5_CFG=" + String(g.do5_fault_assignment_ok ? 1 : 0);
  line += " DO5_ASSIGN=" + String(g.do5_assignment);
  line += " FAULT_OUT=" + String(g.fault_output_active ? 1 : 0);
  line += " SRDY=" + String(g.servo_ready ? 1 : 0);
  line += " SERVICE=" + String(g.service_mode ? 1 : 0);
  line += " MOTOR_REV=" + String(g.motor_reverse ? 1 : 0);
  line += " POS_SRC=" + String(g.feedback_from_drive ? "DRIVE" : (g.simulation_enabled ? "SIM" : "NONE"));
  line += " RAW_POS=" + String(g.raw_pos_units);
  line += " RAW_VEL=" + String(g.raw_vel_units_s);
  line += " MODBUS=" + String(g.drive_feedback_ok ? 1 : 0);
  line += " UPM=" + String(g_command_units_per_m, 1);
  line += " RS_STAT=" + String(rsStatusText());
  line += " RS_OK_SEQ=" + String(g.rs_consecutive_successes);
  line += " RS_FAIL_SEQ=" + String(g.rs_consecutive_failures);
  line += " DRV_EN=" + String(g.drive_enabled ? 1 : 0);
  line += " NO_MOTION=" + String(g.no_motion_feedback_fault ? 1 : 0);
  sendLine(line);
}

static void sendHello() {
  String hello = String("HELLO NAME=") + NODE_BANNER + " VER=" + FW_VERSION;
  sendLine(hello);
  sendStatusLine(true);
}

static bool applyVelocity(float v) {
  const unsigned long now = millis();
  if (g.local_estop) {
    driveStopNow();
    return false;
  }
  g.vel_request_mps = constrain(v, -MAX_CMD_VEL_MPS, MAX_CMD_VEL_MPS);
  lastVelocityCommandMs = now;
  if (fabsf(g.vel_request_mps) >= AUTO_DRIVE_ARM_MIN_REQUEST_MPS) {
    lastNonZeroVelocityCommandMs = now;
  }
  // The local 50 Hz profile loop applies the three motion limits and sends the
  // resulting command. Accepting the target here keeps Ethernet/display timing
  // out of the acceleration behaviour.
  return g.drive_writes_enabled || g.simulation_enabled;
}


static void handleCommand(const String& rawLine) {
  String line = trimCopy(rawLine);
  if (!line.length()) return;

  Serial.print("[UDP RX] ");
  Serial.println(line);

  float val = 0.0f;

  if (line.startsWith("DSP1|")) {
    g.client_connected = true;
    g_lastSrvrDisplayMs = millis();
    g_latestDisplayPacket = line;
    g_latestDisplayPacket.replace("DSP1|", "HMI1|");
    return;
  }

  if (line == "STOP") {
    const bool wasAlreadyStopped =
      fabsf(g.vel_request_mps) < MOTION_ZERO_EPS_MPS &&
      fabsf(g.vel_profile_mps) < MOTION_ZERO_EPS_MPS &&
      fabsf(g.vel_cmd_mps) < MOTION_ZERO_EPS_MPS &&
      !g.drive_enabled;
    driveStopNow();
    g.drive_writes_enabled = false;
    sendLine("OK STOP");
    const unsigned long nowStop = millis();
    if (!wasAlreadyStopped || (nowStop - lastStopStatusMs) >= 1000) {
      lastStopStatusMs = nowStop;
      sendStatusLine(true);
    }
    return;
  }

  if (line == "PING") {
    sendLine("PONG");
    return;
  }

  if (line == "STATUS") {
    sendStatusLine(true);
    return;
  }

  if (parseFloatArg(line, "SW_SRVON", val)) {
    if (val >= 0.5f) {
      requestSoftwareSrvonInhibit(false, "REMOTE_SW_SRVON_ON");
      serviceLeadshineSoftwareServoEnable();
      sendLine("OK SW_SRVON REQUEST_ON");
    } else {
      driveStopNow();
      g.drive_writes_enabled = false;
      requestSoftwareSrvonInhibit(true, "REMOTE_SW_SRVON_OFF");
      sendLine("OK SW_SRVON REQUEST_OFF");
    }
    sendStatusLine(true);
    return;
  }

  if (line == "ENABLE_SIM") {
    // Simulation is retained only for workshop UI testing; it never writes to the drive.
    g.simulation_enabled = true;
    g.drive_writes_enabled = false;
    saveConfig();
    sendLine("OK ENABLE_SIM");
    sendStatusLine(true);
    return;
  }

  if (line == "DISABLE_SIM") {
    g.simulation_enabled = false;
    driveStopNow();
    saveConfig();
    sendLine("OK DISABLE_SIM");
    sendStatusLine(true);
    return;
  }

  if (line == "ENABLE_DRIVE_WRITES") {
    // Compatibility command only. Drive command writes are now automatically controlled by the safety gate.
    serviceAutomaticDriveEnable();
    sendLine(g.drive_writes_enabled ? "OK ENABLE_DRIVE_WRITES AUTO" : "ERR ENABLE_DRIVE_WRITES SAFETY_OR_CONFIG");
    sendStatusLine(true);
    return;
  }

  if (line == "DISABLE_DRIVE_WRITES") {
    // Compatibility command only. A STOP is honoured, but the safety gate may re-enable command writes once healthy.
    driveStopNow();
    sendLine("OK DISABLE_DRIVE_WRITES AUTO_CONTROLLED");
    sendStatusLine(true);
    return;
  }

  if (parseFloatArg(line, "SET_ACCEL", val)) {
    g_drive_accel_mps2 = constrain(val, 0.05f, MAX_PROFILE_ACCEL_MPS2);
    lastConfiguredAccelMps2 = -1.0f;
    saveConfig();
    sendLine("OK SET_ACCEL");
    return;
  }

  if (parseFloatArg(line, "SET_DECEL", val)) {
    g_drive_decel_mps2 = constrain(val, 0.05f, MAX_PROFILE_ACCEL_MPS2);
    lastConfiguredDecelMps2 = -1.0f;
    saveConfig();
    sendLine("OK SET_DECEL");
    return;
  }

  if (parseFloatArg(line, "SET_CROSSOVER", val)) {
    g_drive_crossover_mps2 = constrain(val, 0.05f, MAX_PROFILE_ACCEL_MPS2);
    lastConfiguredCrossMps2 = -1.0f;
    saveConfig();
    sendLine("OK SET_CROSSOVER");
    return;
  }

  if (parseFloatArg(line, "SET_STOP_DECEL", val)) {
    g_drive_stop_decel_mps2 = constrain(val, 0.05f, MAX_PROFILE_ACCEL_MPS2);
    lastConfiguredDecelMps2 = -1.0f;
    saveConfig();
    sendLine("OK SET_STOP_DECEL");
    return;
  }

  if (line.startsWith("SET_ACCEL_MODE")) {
    String mode = line.substring(strlen("SET_ACCEL_MODE"));
    mode.trim();
    mode.toUpperCase();
    if (mode == "DYNAMIC" || mode == "SPEED") {
      g_acceleration_mode = ACCEL_MODE_DYNAMIC;
    } else if (mode == "TRADITIONAL" || mode == "NORMAL" || mode == "POWER") {
      g_acceleration_mode = ACCEL_MODE_TRADITIONAL;
    } else {
      sendLine("ERR SET_ACCEL_MODE");
      return;
    }
    g.vel_profile_mps = g.drive_feedback_ok ? g.vel_actual_mps : g.vel_cmd_mps;
    saveConfig();
    sendLine("OK SET_ACCEL_MODE");
    sendStatusLine(true);
    return;
  }

  if (parseFloatArg(line, "SET_MOTOR_REVERSE", val) || parseFloatArg(line, "SET_MOTOR_DIR", val)) {
    const float displayedPosition = g.pos_m;
    g.motor_reverse = (val >= 0.5f);
    if (g.feedback_from_drive) {
      preserveDisplayedPositionForMotorDirectionChange(displayedPosition);
    }
    saveConfig();
    sendLine(String("OK SET_MOTOR_REVERSE ") + (g.motor_reverse ? "1" : "0"));
    sendStatusLine(true);
    return;
  }

  if (parseFloatArg(line, "VEL", val)) {
    bool ok = applyVelocity(val);
    // Velocity commands are intentionally silent while read-only to avoid UDP log traffic.
    if (g.drive_writes_enabled) sendLine(ok ? "OK VEL" : "ERR VEL DRIVE_NOT_READY");
    return;
  }

  if (parseFloatArg(line, "SERVICE_MODE", val)) {
    g.service_mode = (val >= 0.5f);
    if (!g.service_mode) {
      if (!g.feedback_from_drive) {
        g.pos_m = constrain(g.pos_m, g.limit_near_m, g.limit_far_m);
        if (g.pos_m <= g.limit_near_m && g.vel_actual_mps < 0.0f) g.vel_actual_mps = 0.0f;
        if (g.pos_m >= g.limit_far_m && g.vel_actual_mps > 0.0f) g.vel_actual_mps = 0.0f;
      }
    }
    saveConfig();
    sendLine("OK SERVICE_MODE");
    sendStatusLine(true);
    return;
  }

  if (parseFloatArg(line, "SET_SPAN", val)) {
    g.span_m = constrain(val, 0.1f, 10000.0f);
    saveConfig();
    sendLine("OK SET_SPAN");
    sendStatusLine(true);
    return;
  }

  if (parseFloatArg(line, "SET_LIMIT_NEAR", val)) {
    g.limit_near_m = val;
    if (g.limit_far_m < g.limit_near_m) g.limit_far_m = g.limit_near_m;
    if (!g.service_mode && !g.feedback_from_drive) g.pos_m = constrain(g.pos_m, g.limit_near_m, g.limit_far_m);
    saveConfig();
    sendLine("OK SET_LIMIT_NEAR");
    sendStatusLine(true);
    return;
  }

  if (parseFloatArg(line, "SET_LIMIT_FAR", val)) {
    g.limit_far_m = val;
    if (g.limit_far_m < g.limit_near_m) g.limit_near_m = g.limit_far_m;
    if (!g.service_mode && !g.feedback_from_drive) g.pos_m = constrain(g.pos_m, g.limit_near_m, g.limit_far_m);
    saveConfig();
    sendLine("OK SET_LIMIT_FAR");
    sendStatusLine(true);
    return;
  }

  if (parseFloatArg(line, "SYNC_POS", val)) {
    if (fabsf(g.vel_actual_mps) > 0.05f || fabsf(g.vel_request_mps) > MOTION_ZERO_EPS_MPS) {
      sendLine("ERR SYNC_POS MOTOR_MOVING");
      return;
    }
    if (g.feedback_from_drive) {
      g.drive_position_offset_m = val - motorDirectionSign() * (float(g.raw_pos_units) / g_command_units_per_m);
      g.pos_m = val;
    } else {
      g.pos_m = g.service_mode ? val : constrain(val, g.limit_near_m, g.limit_far_m);
    }
    saveConfig();
    sendLine("OK SYNC_POS");
    sendStatusLine(true);
    return;
  }

  if (parseFloatArg(line, "SET_UNITS_PER_M", val)) {
    val = constrain(val, 1.0f, 100000000.0f);
    const float displayedPosition = g.pos_m;
    g_command_units_per_m = val;
    if (g.feedback_from_drive) {
      preserveDisplayedPositionForMotorDirectionChange(displayedPosition);
    }
    saveConfig();
    sendLine("OK SET_UNITS_PER_M");
    sendStatusLine(true);
    return;
  }

  sendLine("ERR UNKNOWN_CMD");
}

static void serviceUdp() {
  if (!g.ethernet_up) return;

  int packetSize = udp.parsePacket();
  if (packetSize <= 0) return;

  const IPAddress remoteIp = udp.remoteIP();
  if (remoteIp != SRVR_IP) {
    while (udp.available()) udp.read();
    if ((millis() - lastUnexpectedPeerLogMs) >= 5000) {
      lastUnexpectedPeerLogMs = millis();
      Serial.printf("[UDP] Ignored packet from unexpected host %s\n", remoteIp.toString().c_str());
    }
    return;
  }
  if (packetSize > 2048) {
    while (udp.available()) udp.read();
    Serial.printf("[UDP] Dropped oversized packet (%d bytes)\n", packetSize);
    return;
  }
  bool wasDisconnected = !g.client_connected;
  bool newPeer = (!peerValid) || (peerIP != remoteIp) || (peerPort != udp.remotePort());
  peerIP = remoteIp;
  peerPort = udp.remotePort();
  peerValid = true;
  g.client_connected = true;
  lastPeerPacketMs = millis();

  if ((newPeer || wasDisconnected) && g.software_srvon_inhibit && !g.local_estop) {
    requestSoftwareSrvonInhibit(false, "SRVR_HEARTBEAT_RESTORED");
  }

  if (newPeer) {
    Serial.printf("[UDP] Peer %s:%u connected\n", peerIP.toString().c_str(), (unsigned)peerPort);
    sendHello();
  }

  String payload;
  payload.reserve(packetSize + 1);
  while (udp.available()) {
    char c = (char)udp.read();
    if (c != '\r') payload += c;
  }

  int startIdx = 0;
  while (startIdx < (int)payload.length()) {
    int nl = payload.indexOf('\n', startIdx);
    String line;
    if (nl < 0) {
      line = payload.substring(startIdx);
      startIdx = payload.length();
    } else {
      line = payload.substring(startIdx, nl);
      startIdx = nl + 1;
    }
    line.trim();
    if (line.length()) handleCommand(line);
  }
}

static void startDriveSerial() {
  DriveSerial.begin(RS485_BAUD, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);
  if(!DriveSerial.setPins(RS485_RX_PIN, RS485_TX_PIN, -1, RS485_RTS_PIN))
    Serial.println("[RS485] ERROR assigning EdgeBox UART1 RTS pin");
  if(!DriveSerial.setMode(UART_MODE_RS485_HALF_DUPLEX))
    Serial.println("[RS485] ERROR enabling UART_MODE_RS485_HALF_DUPLEX");
  Serial.printf("[RS485] EdgeBox isolated UART1 started @ %lu 8N1 (RX=%d TX=%d RTS=%d)\n",
                (unsigned long)RS485_BAUD, RS485_RX_PIN, RS485_TX_PIN, RS485_RTS_PIN);
}


static void servicePeerTimeout() {
  if (peerValid && (millis() - lastPeerPacketMs) > W1P_PEER_TIMEOUT_MS) {
    if (g.client_connected || g.drive_writes_enabled || !g.software_srvon_inhibit) {
      Serial.println("[UDP] SRVR peer timeout - stopping drive, locking writes and dropping software Servo Enable");
      driveStopNow();
      g.drive_writes_enabled = false;
      requestSoftwareSrvonInhibit(true, "SRVR_TIMEOUT");
      sendStatusLine(true);
    }
    g.client_connected = false;
  }
}

static bool initEthernetStatic()
{
  bool ok = ETH.begin(ETH_PHY_W5500, 1, EDGEBOX_ETH_CS, EDGEBOX_ETH_INT, EDGEBOX_ETH_RST,
                      SPI2_HOST, EDGEBOX_ETH_SCLK, EDGEBOX_ETH_MISO, EDGEBOX_ETH_MOSI);
  if(!ok) { Serial.println("[ETH] EdgeBox W5500 begin failed"); return false; }
  if(!ETH.config(LOCAL_IP, GATEWAY, SUBNET, DNS1, DNS2)) {
    Serial.println("[ETH] static config failed"); return false;
  }
  uint32_t t0 = millis();
  while(millis() - t0 < 2000 && ETH.localIP() == IPAddress(0,0,0,0)) delay(10);
  Serial.print("[ETH] EdgeBox W5500 IP: "); Serial.println(ETH.localIP());
  return (ETH.localIP() != IPAddress(0,0,0,0));
}

void setup() {
  Serial.begin(115200);
  delay(400);
  Serial.println();
  Serial.println("============================================================");
  Serial.printf("%s %s\n", FW_NAME, FW_VERSION);
  Serial.println("Leadshine EL7-RS2000P command interface (auto-enable under SRVR safety gate)");
  Serial.println("v26.08.31.04: EdgeBox W5500 + isolated native RS485; SRVR/safety fail-safe + joystick-neutral re-arm; EL7 DO2/DO3/DO4/DO5 map verification enabled");
  Serial.println("============================================================");

  pinMode(PIN_LOCAL_ESTOP, INPUT);
  Serial.printf("[IO] EdgeBox DI0 GPIO%d: 24V NC loop HIGH=healthy, LOW/open=E-Stop\n", PIN_LOCAL_ESTOP);
  if(PIN_STATUS_LED >= 0) { pinMode(PIN_STATUS_LED, OUTPUT); digitalWrite(PIN_STATUS_LED, LOW); }
  if (LEADSHINE_SRVON_OUTPUT_ENABLED && PIN_LEADSHINE_SRVON >= 0) {
    pinMode(PIN_LEADSHINE_SRVON, OUTPUT);
    digitalWrite(PIN_LEADSHINE_SRVON, LEADSHINE_SRVON_ACTIVE_HIGH ? LOW : HIGH);
  }

  loadNetworkConfig();
  loadConfig();
  startDriveSerial();
#if ENABLE_W1P_TS
  HMI.begin(W1PTS_BAUD, SERIAL_8N1, W1PTS_UART_RX, W1PTS_UART_TX);
#endif
  Serial.println("[W1P-TS] disabled for EdgeBox SYS Update 4 integration");
  bool eth_ok = initEthernetStatic();
  g.ethernet_up = eth_ok;
  udp.begin(TCP_PORT);
  Serial.printf("[UDP] Listening on %s:%u\n", ETH.localIP().toString().c_str(), (unsigned)TCP_PORT);
  hvBeginWebUpdater();

  Serial.printf("[CFG] IP=%s UDP=%u ETH=%s\n", ETH.localIP().toString().c_str(), (unsigned)TCP_PORT, eth_ok ? "OK" : "FAILED");
  Serial.printf("[CFG] ESTOP_DI0=%d RS485_RX=%d RS485_TX=%d RTS=%d ID=%u\n", PIN_LOCAL_ESTOP, RS485_RX_PIN, RS485_TX_PIN, RS485_RTS_PIN, (unsigned)DRIVE_MODBUS_ID);
  Serial.printf("[CFG] POS=%.3f SPAN=%.3f NL=%.3f FL=%.3f SIM=%s UPM=%.1f WRITES=LOCKED\n",
                g.pos_m, g.span_m, g.limit_near_m, g.limit_far_m,
                g.simulation_enabled ? "ON" : "OFF", g_command_units_per_m);
  Serial.printf("[MOTION] MODE=%s ACCEL=%.3f DECEL=%.3f CROSS=%.3f STOP_DECEL=%.3f m/s^2\n",
                g_acceleration_mode == ACCEL_MODE_DYNAMIC ? "Speed" : "Power",
                g_drive_accel_mps2, g_drive_decel_mps2, g_drive_crossover_mps2, g_drive_stop_decel_mps2);
}

void loop() {
  // Keep link state fresh even when using the simpler CTRL-style ETH init path.
  g.ethernet_up = (ETH.localIP() != IPAddress(0,0,0,0)) && ETH.linkUp();
  updateLocalInputs();
  servicePeerTimeout();
  pollLeadshineFeedback();
  updateMotionModel();
  serviceUdp();
#if ENABLE_W1P_TS
  serviceHmiUart();
  serviceHmiDisplay();
  sendW1pHmiStatusToSrvr();
#endif
  hvHandleWebUpdater();
  servicePeerTimeout();
  sendStatusLine(false);

  // No EdgeBox field DO is consumed for a heartbeat indicator.
  unsigned long now = millis();
  if(PIN_STATUS_LED >= 0) {
    if (g.client_connected) digitalWrite(PIN_STATUS_LED, HIGH);
    else if (g.ethernet_up && (now - lastBlinkMs) >= 500) { lastBlinkMs = now; digitalWrite(PIN_STATUS_LED, !digitalRead(PIN_STATUS_LED)); }
    else if (!g.ethernet_up) digitalWrite(PIN_STATUS_LED, LOW);
  }

  delay(5);
}
