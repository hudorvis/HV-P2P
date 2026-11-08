#!/usr/bin/env python3
"""Run the production W1P poll with a host clock and simulated Modbus replies."""
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
source = next(ROOT.glob('HV_P2P_W1P_EDGEBOX_v*/*.ino')).read_text()


def extract_function(name):
    match = re.search(rf'^static [^\n;]+\b{name}\([^\n;]*\) *\{{\n.*?^\}}', source, re.M | re.S)
    assert match, name
    return match.group()


constants = (
    'MODBUS_POLL_MS MODBUS_FAULT_POLL_MS DRIVE_MODBUS_ID RS485_BAUD RS485_LINK_TIMEOUT_MS '
    'RS485_RECOVER_CONFIRM_COUNT RS485_FAIL_CONFIRM_COUNT MOTION_ZERO_EPS_MPS '
    'LEADSHINE_SRVON_DISABLED_VALUE LEADSHINE_SRVON_EXTERNAL_VALUE LEADSHINE_SRVON_INTERNAL_VALUE '
    'LEGACY_BAD_SRVON_DECIMAL_VALUE INPUT_DI1_MASK '
    'OUTPUT_DO2_MASK OUTPUT_DO3_MASK OUTPUT_DO4_MASK OUTPUT_DO5_MASK '
    'EDGEBOX_BRAKE_FEEDBACK_STALE_MS EDGEBOX_BRAKE_STATUS_STALE_MS'
).split()
constants += re.findall(r'^static const \w+\s+((?:EXPECTED|REG)_\w+)\s*=', source, re.M)
declarations = []
for name in constants:
    match = re.search(rf'^static const \w+\s+{name}\s*=[^;]+;', source, re.M)
    assert match, name
    declarations.append(match.group())

prefix = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>
using std::isfinite;
static uint32_t nowMs = 0;
static uint32_t millis() { return nowMs; }
static float g_command_units_per_m = 1000.0f;
static float g_dynamic_feedback_mps = 0.0f, filteredDriveVelocityMps = 0.0f;
static uint32_t lastDriveConfigPollMs = 0, lastModbusPollMs = 0;
static uint32_t lastDriveFeedbackMs = 0, lastBrakeStatusMs = 0;
static uint32_t g_lastFactoryProbeMs = 0;
static bool g_srvrFirmwareMatched = true, hvServiceOperationActive = false;
static bool g_factoryCommsDetected = false;
static uint16_t g_factoryFmt = 0, g_factoryBaud = 0, g_factoryAddr = 0;
static constexpr uint32_t SERIAL_8N1 = 1, SERIAL_8N2 = 2;
static std::string diagnostic;
static struct {
  void println(const char* message) { diagnostic = message; }
  template<typename... Args>
  void printf(const char* message, Args...) { diagnostic = message; }
} Serial;
'''

transport = r'''
static bool replyOk = true;
static uint32_t replyDelay = 10;
static int32_t replyCounts = 0;
static uint16_t outputBits = OUTPUT_DO2_MASK;
static std::vector<uint32_t> uartConfigs;
static void startDriveSerialConfig(uint32_t baud, uint32_t config) {
  assert((baud == 38400 && config == SERIAL_8N2) || (baud == RS485_BAUD && config == SERIAL_8N1));
  uartConfigs.push_back(config);
}
static bool modbusReadHoldingRegisters(uint8_t, uint16_t, uint16_t, uint16_t* out) {
  assert(uartConfigs.back() == SERIAL_8N2);
  *out = 1;
  noteRsOk();
  return true;
}
static bool modbusReadFeedbackBlock(uint8_t, int32_t& pos, uint16_t& in, uint16_t& out) {
  nowMs += replyDelay;
  if (!replyOk) {
    noteRsErr();
    return false;
  }
  pos = replyCounts;
  in = 0;
  out = outputBits;
  noteRsOk();
  return true;
}
static bool configReadContinue(uint16_t reg, uint16_t& value, bool& ok, bool&) {
  nowMs += 7;
  switch (reg) {
    case REG_CONTROL_MODE: value = EXPECTED_CONTROL_MODE; break;
    case REG_DI1_ASSIGN: value = EXPECTED_DI1_ASSIGN_INTERNAL; break;
    case REG_DO2_ASSIGN: value = EXPECTED_DO2_READY_ASSIGN; break;
    case REG_DO3_ASSIGN: value = EXPECTED_DO3_ENABLED_ASSIGN; break;
    case REG_DO4_ASSIGN: value = EXPECTED_DO4_BRAKE_ASSIGN; break;
    case REG_DO5_ASSIGN: value = EXPECTED_DO5_FAULT_ASSIGN; break;
    case REG_RS485_MODE: value = EXPECTED_RS485_MODE; break;
    case REG_RS485_BAUD: value = EXPECTED_RS485_BAUD_CODE; break;
    case REG_RS485_ADDRESS: value = EXPECTED_RS485_ADDRESS; break;
    default: value = 0; break;
  }
  noteRsOk();
  return ok = true;
}
'''

test = r'''
int main() {
  // An untried operational UART and its first good reply are both discovery.
  g.software_srvon_inhibit = true;
  serviceLeadshineFactoryCommsProbe();
  assert(uartConfigs.empty() && diagnostic.empty());
  nowMs = MODBUS_FAULT_POLL_MS;
  pollLeadshineFeedback();
  assert(lastDriveFeedbackMs == nowMs && lastBrakeStatusMs == nowMs);
  assert(g.rs_consecutive_successes == 1 && !g.rs_link_ok);
  serviceLeadshineFactoryCommsProbe();
  assert(uartConfigs.empty() && diagnostic.empty());

  // Configuration has an artificial 77 ms sweep, then the read blocks for
  // another 33 ms. The full reply owns the sample and the verified startup log.
  nowMs = 2000;
  replyDelay = 33;
  pollLeadshineFeedback();
  assert(nowMs == 2110 && lastDriveFeedbackMs == 2110 && lastBrakeStatusMs == 2110);
  assert(g_drive_position_sequence == 2 && g.drive_feedback_ok);
  assert(diagnostic.find("position feedback are verified") != std::string::npos);

  // VEL uses elapsed reply time (100 ms), not the 200 ms poll-start interval.
  nowMs = 2200;
  replyDelay = 10;
  replyCounts = 100;
  pollLeadshineFeedback();
  assert(lastDriveFeedbackMs == 2210 && g_drive_position_sequence == 3);
  assert(std::fabs(g.vel_actual_mps - 0.88f) < 0.001f);

  // A timeout crosses the existing 500 ms stale threshold during the read.
  nowMs = 2700;
  replyDelay = 50;
  replyOk = false;
  pollLeadshineFeedback();
  assert(lastDriveFeedbackMs == 2210 && g_drive_position_sequence == 3);
  assert(!g.position_feedback_read_ok && !g.output_io_read_ok && !g.drive_feedback_ok);
  serviceLeadshineFactoryCommsProbe();
  assert(uartConfigs.empty());  // one failed operational transaction
  noteRsErr();
  serviceLeadshineFactoryCommsProbe();
  assert((uartConfigs == std::vector<uint32_t>{SERIAL_8N2, SERIAL_8N1}));
  assert(g_factoryCommsDetected && !g.rs_link_ok && g.rs_consecutive_failures == 2);

  // The validated reply and sequence can both roll over to exactly zero.
  nowMs = UINT32_MAX - 39;
  lastDriveConfigPollMs = nowMs;
  lastModbusPollMs = nowMs - MODBUS_FAULT_POLL_MS;
  recordDrivePositionSample(100, UINT32_MAX - 99);
  g_drive_position_sequence = UINT32_MAX;
  filteredDriveVelocityMps = 0.0f;
  replyOk = true;
  replyDelay = 40;
  outputBits = OUTPUT_DO2_MASK | OUTPUT_DO3_MASK | OUTPUT_DO4_MASK;
  replyCounts = 200;
  pollLeadshineFeedback();
  assert(lastDriveFeedbackMs == 0 && lastBrakeStatusMs == 0 && g_drive_position_sequence == 0);
  assert(std::fabs(g.vel_actual_mps - 0.88f) < 0.001f);
  g.rs_link_ok = true;
  g.edgebox_brake_released = true;
  assert(edgeboxBrakeReleaseHoldAllowed());
  nowMs = 1;
  noteRsErr();
  assert(g.rs_link_ok);  // a valid response at millisecond zero stays fresh
  nowMs = EDGEBOX_BRAKE_STATUS_STALE_MS + EDGEBOX_BRAKE_FEEDBACK_STALE_MS + 1;
  assert(!edgeboxBrakeReleaseHoldAllowed());
  nowMs = 100;
  replyDelay = 0;
  replyCounts = 200;
  pollLeadshineFeedback();
  assert(lastDriveFeedbackMs == 100 && g_drive_position_sequence == 1 && g.vel_actual_mps == 0.0f);
}
'''

winch_state = source[source.index('struct WinchState {'):source.index('static float motorDirectionSign()')]
count_state = source[source.index('static int64_t g_drive_unwrapped_units'):source.index('static int64_t wrappedPositionDelta')]
before_transport = (
    'motorDirectionSign', 'wrappedPositionDelta', 'unwrapDrivePosition',
    'rawUnitsToDisplayPositionM', 'rawUnitsDeltaToDisplayMps', 'recordDrivePositionSample',
    'noteRsOk', 'noteRsErr',
)
after_transport = (
    'isLegacyDi5SrvonConflict', 'leadshineFactoryProbeSafe', 'serviceLeadshineFactoryCommsProbe',
    'pollLeadshineFeedback', 'edgeboxBrakeShutdownSequencingRequested', 'edgeboxBrakeReleaseHoldAllowed',
)
cpp = '\n'.join((
    prefix, *declarations, winch_state, count_state,
    *(extract_function(name) for name in before_transport),
    transport, *(extract_function(name) for name in after_transport), test,
))
with tempfile.TemporaryDirectory(prefix='hvp2p-feedback-timing-') as tmp:
    src = Path(tmp) / 'feedback.cpp'
    binary = src.with_suffix('')
    src.write_text(cpp)
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(src), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

service = extract_function('hvPrepareSafeServiceState')
assert service.index('const unsigned long now = millis();') < service.index('recordDrivePositionSample(pos, now);')
status = extract_function('sendStatusLine')
assert 'POS_T_MS=" + String(lastDriveFeedbackMs)' in status
assert 'g_drive_unwrapped_valid ? now - lastDriveFeedbackMs : UINT32_MAX' in status
print('W1P_FEEDBACK_TIMING_AND_STARTUP_PASS')
