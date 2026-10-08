#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.08.02'
B=(ROOT/f'SRVR_GitHub_v{VER}/backend.py').read_text()
Q=(ROOT/f'SRVR_GitHub_v{VER}/qml/Main.qml').read_text()
C=(ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}/HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text()
T=(ROOT/f'HV_P2P_CTRL_TS_v{VER}/HV_P2P_CTRL_TS_v{VER}.ino').read_text()

# Update startup must retry quickly when SRVR beacon beats HTTP authority readiness.
assert 'g_fwAuthorityFastRetryUntilMs' in C
assert 'g_fwAuthorityRetryDelayMs = (g_fwAuthorityFastRetryUntilMs' in C
assert '? 500 : 5000' in C
assert 'if(releaseChanged || newSession)' in C
assert 'g_fwAuthorityFastRetryUntilMs = millis() + 15000' in C

# Compact state/geometry must self-heal instead of one-shot delivery.
assert '#define HMI_STATE_KEEPALIVE_MS  1000' in C
assert '#define HMI_GEOMETRY_KEEPALIVE_MS 2500' in C
assert 'g_lastHmiStateTxMs' in C and 'g_lastHmiGeometryTxMs' in C
assert 'g_hmiStatePacketPending = true' in C and 'g_hmiGeometryPacketPending = true' in C

# CTRL-TS must cache packets while firmware dashboard owns the panel, then replay.
for token in ('g_pending_runtime_state_line','g_pending_runtime_geometry_line','g_pending_runtime_bulk_line'):
    assert token in T, token
proc=T[T.index('static void process_text_from_ctrl'):T.index('static inline void rs485_slave_turnaround_guard', T.index('static void process_text_from_ctrl'))]
assert 'if(fw_display_owned()){' in proc
assert 'g_pending_runtime_state_line = line' in proc
assert 'g_pending_runtime_geometry_line = line' in proc
assert 'g_pending_runtime_bulk_line = line' in proc
release=T[T.index('static void service_fw_screen_release'):T.index('static void service_link_state')]
assert 'apply_hmi_packet(g_pending_runtime_bulk_line)' in release
assert 'apply_hmi_packet(g_pending_runtime_state_line)' in release
assert 'apply_hmi_packet(g_pending_runtime_geometry_line)' in release
assert 'update_progress_marker();' in release
assert 'update_ramp_markers();' in release and 'update_preset_markers();' in release

# Repeated inactive firmware keepalives cannot postpone UI release forever.
fw=T[T.index('static void fw_set_device_status'):T.index('static void fw_process_status_line')]
assert 'const bool wasActive = g_fw_row_active[idx];' in fw
assert 'else if(wasActive && !fw_any_row_active()' in fw
assert 'g_fw_external_release_due_ms = millis() + 2000;' in fw
assert 'millis() + 8000' not in fw

# Limit Calibration mirrors the three-step Joystick wizard and closes on Ref.
assert 'model:["Set Near","Set Far","Set Ref"]' in Q
assert 'title:"Cable Position"; subtitle:"Side View"; sideView:true' in Q
assert 'model:[{label:"NEAR",key:"near"},{label:"REF",key:"ref"},{label:"FAR",key:"far"}]' in Q
assert '"Set Ref & Done"' in Q
limit=B[B.index('def calibrationNext'):B.index('def calibrationBack')]
assert 'self.calibration_open = False' in limit
assert 'self.calibration_step = 2' in limit
assert 'self.battery_change_mode = False' in limit
assert 'self._battery_change_went_outside_limits = False' in limit
assert 'self._sync_service_mode_to_winch(force=True)' in limit
assert 'self.calibration_step = 3' not in limit

# Safe CTRL-TS self flash remains headless; do not regress display corruption fix.
assert 'headless boot: RGB/LVGL/PSRAM display stack remains uninitialized' in T
assert 'Update.begin(imageSize, U_FLASH)' in T

print('BENCH_REGRESSION_0406_PASS')
