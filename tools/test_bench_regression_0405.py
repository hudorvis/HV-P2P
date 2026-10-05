#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.05.10'
B=(ROOT/f'SRVR_GitHub_v{VER}/backend.py').read_text()
Q=(ROOT/f'SRVR_GitHub_v{VER}/qml/Main.qml').read_text()
C=(ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}/HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text()
T=(ROOT/f'HV_P2P_CTRL_TS_v{VER}/HV_P2P_CTRL_TS_v{VER}.ino').read_text()

# Operator status/readout consistency.
assert 'System | Uncalibrated' in B
assert 'System Un-Calibrated' not in B
assert 'shown = "System | Active";' in T
assert 'shown = "STATE | " + text;' not in T  # SRVR owns canonical System | ... status wording
assert 'def _operator_joystick_axis' in B
assert 'neutral_pct = max(0.5' in B
assert 'setupJoystickPercentage' in B and '_operator_joystick_axis(self._setup_preview_joystick())' in B

# Limit wizard exposes live/captured Near/Ref/Far values in SRVR and CTRL-TS.
assert 'self._limit_cal_pending = {"near": None, "ref": None, "far": None}' in B
for key in ('cal_pos=', 'cal_near=', 'cal_ref=', 'cal_far='):
    assert key in B, key
assert 'limitCalibrationCaptures' in B and 'Current Winch Position' in Q
assert 'g_cal_value_box[3]' in T and 'g_cal_value_text[3]' in T and 'g_cal_current_lbl' in T
assert 'Current Winch Position' in T and 'Current Joystick Position' in T
assert 'kind == "Limit"' in T and 'kind == "Joystick"' in T

# Virtual calibration starts from a defined local coordinate and does not require W1P.
open_limit=B[B.index('def openLimitCalibration'):B.index('def openWinchCalibration')]
assert 'self.position_source == "Virtual"' in open_limit and 'self.state.pos_m = 0.0' in open_limit
assert 'self._virtual_motion_step()' in B and 'self._virtual_output_inhibit()' in B

# AUX assignment semantics are SRVR-owned; persisted UIL1 cannot overwrite them.
layout=T[T.index('static void apply_layout_packet'):T.index('static void process_text_from_ctrl')]
assert 'AUX assignments ignored' in layout
for forbidden in ('g_aux_labels[i] = v', 'String key = String("aux")'):
    assert forbidden not in layout, forbidden
for i in range(1,6):
    assert f'f"aux{i}={{labels[{i-1}]}}"' in B
assert '|aux3=AUX 3' in C and '|aux4=AUX 4' in C

# Sparse HMG1 geometry/preset delta is serialized ahead of bulk telemetry.
assert 'buildHmiGeometryPacketFromSrvr' in C and 'String out = "HMG1"' in C
for field in ('ramp_near_frac','ramp_far_frac','preset_names','preset_abs','preset_vis'):
    assert f'"{field}"' in C
assert 'g_hmiGeometryPacketPending' in C
assert 'if(!hmiPriorityPacketSent && g_hmiGeometryPacketPending' in C
assert 'line.startsWith("HMG1|")' in T and 'geometry_only' in T
assert 'update_reference_marker();' in T and 'update_ramp_markers();' in T and 'update_preset_markers();' in T

# Only genuinely pre-authority field nodes use the blocking legacy browser bridge.
assert 'def _try_start_legacy_firmware_push' in B
assert 'def _legacy_firmware_push_required' in B and 'parts <= (26, 10, 1, 1)' in B
hmi=B[B.index('def _handle_ctrl_hmi_status'):B.index('def _joystick_min_cal_span')]
assert '_legacy_firmware_push_required(self._ctrl_fw_version)' in hmi
assert '< 3.0' in B

# Safe self-flash remains headless. Give the operator a longer explicit handoff,
# and keep CTRL quiet longer than that handoff so rediscovery cannot race reboot.
assert 'Preparing safe updater - SRVR shows self-flash progress' in T
assert 'g_fw_safe_reboot_due_ms = millis() + 1800;' in T
assert 'g_hmiSafeRebootHoldUntilMs = millis() + 3000;' in C
begin=T[T.index('static void fw_handle_begin'):T.index('static void fw_handle_block')]
assert begin.index('if(!g_fw_headless_mode)') < begin.index('Update.begin(imageSize, U_FLASH)')

print('BENCH_REGRESSION_0405_PASS')
