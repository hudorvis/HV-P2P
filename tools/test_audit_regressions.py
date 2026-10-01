#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VER="26.10.01.02"
W=(ROOT/f"HV_P2P_W1P_EDGEBOX_v{VER}/HV_P2P_W1P_EDGEBOX_v{VER}.ino").read_text()
C=(ROOT/f"HV_P2P_CTRL_EDGEBOX_v{VER}/HV_P2P_CTRL_EDGEBOX_v{VER}.ino").read_text()
T=(ROOT/f"HV_P2P_CTRL_TS_v{VER}/HV_P2P_CTRL_TS_v{VER}.ino").read_text()
B=(ROOT/f"SRVR_GitHub_v{VER}/backend.py").read_text()
N=(ROOT/"tools/native_build_firmware.py").read_text()
assert '"DO1_CFG"' not in B[B.index('required_status'):B.index('if not required_status')]
for k in ('"DO2_CFG"','"DO3_CFG"','"DO4_CFG"','"DO5_CFG"'): assert k in B
assert 'if (!modbusWriteSingleRegister(DRIVE_MODBUS_ID, REG_PR0_VELOCITY' in W
assert 'if (!modbusWriteSingleRegister(DRIVE_MODBUS_ID, REG_PR_CONTROL, PR_TRIGGER_PATH0' in W
assert 'if (!g.drive_writes_enabled) return false;' in W
assert '0x06 | 0x80' in W and '0x10 | 0x80' in W
assert 'g_hmiReportedVersion = "";' in C and 'g_hmiPollOutstanding' in C
assert 'stale/unexpected EVENT' in C
assert 'session_not_compatible' in T and 'if(!g_ctrl_fw_compatible)' in T
assert 'boot_progress_bar' in T and 'Firmware transfer owns the splash status region' in T
assert 'FATAL DISPLAY: PSRAM unavailable/too small' in T and 'expected 800x480' in T
assert 'HEADER_H=45' in T and 'FOOT_H=35' in T and 'SW=780, GAP=7' in T
edgebox_fqbn = N[N.index('EDGEBOX_FQBN'):N.index('HMI_FQBN')]
assert 'PartitionScheme=app3M_fat9M_16MB' in edgebox_fqbn
assert 'PartitionScheme=custom' not in edgebox_fqbn

# v26.10.01.02 operator input / safety refinements.
assert 'self.reverse_joystick = False' in B
assert 'VEL_KEEPALIVE_S = 0.15' in B
assert 'def joystickPercentage' in B
assert 'W1P_VEL_COMMAND_TIMEOUT_MS = 500' in W
assert 'JOY_SAMPLES = 8' in C and 'trimmedSum' in C
assert 'SGM_CONFIG_AI1_CONT_800SPS_6V144 = 0x50E3' in C
assert 'sampleCtrlEstopAI0' in C
assert 'AI0 carries the CTRL E-stop status' in C and 'AI1 carries the APEM 0-5 V joystick signal' in C
assert 'sgmSelectChannelVerified(SGM_CONFIG_AI0_CONT_800SPS_6V144, "AI0 E-stop")' in C
assert 'sgmSelectChannelVerified(SGM_CONFIG_AI1_CONT_800SPS_6V144, "AI1 joystick")' in C
assert 'Always restore and verify AI1' in C
assert 'CTRL_ESTOP_HEALTHY_MIN_V = 3.5f' in C and 'CTRL_ESTOP_HEALTHY_CONFIRM_SAMPLES = 3' in C
# v26.10.01.02 direction-regression guard: CTRL normalises physical Left/Right
# before SRVR, so the default backend direction is Normal and sign is preserved.
BT=(ROOT/'SRVR_GitHub_v26.10.01.02/tools/test_backend_logic.py').read_text()
assert 'assert b.reverse_joystick is False' in BT
assert 'physical Left=-1' in B
assert 'b.requested_speed_mps < 0.0' in BT
assert 'b.requested_speed_mps > 0.0' in BT
# AI0/AI1 identity, status priority, session calibration, and OTA display ownership.
assert 'float axis = 1.0f - (2.0f * (float(raw) / EDGEBOX_JOY_5V_COUNTS))' in C
assert 'FLAG_CTRL_HMI_FAULT' in C and 'FLAG_CTRL_FW_FAULT' in C
assert 'if(estop_active) flags_out |= FLAG_ESTOP_PRESSED;' in C
assert 'if(hmi_safety) flags_out |= FLAG_CTRL_HMI_FAULT;' in C
assert 'position_reference_persistent' in B and 'self._not_calibrated = True' in B
assert 'def systemStatusLevel' in B and 'System Un-Calibrated' in B
assert 'g_boot_session_id' in W and 'BOOT_ID=' in W
assert 'fw_ensure_update_screen' in T and 'fw_display_owned' in T
assert 'if(!fw_display_owned())' in T and 'Firmware transfer owns the screen' in T

# v26.10.01.02 field-feedback regressions: a newer SRVR must be noticed without
# power-cycling field nodes, SRVR must not trust a stale old-session match, the
# CTRL-TS updater must replace the JPEG splash even when FW_BEGIN arrives during
# boot, and E-stop source formatting must never render "| / W1P".
for node in (C, W):
    assert 'if(g_srvrFirmwareMatched) return;' not in node
    assert 'FW_AUTH_MATCHED_RECHECK_MS = 2000' in node
    assert 'authorityUnchanged' in node and 'previousVersion' in node
assert 'previousSha' in C and 'previousSha' in W
assert 'stale_release_report' in B
assert 'reported_match and version_current and authority_current' in B
assert 'reported_w1p_match and self._firmware_version_matches_current' in B
assert 'return self._current_firmware_version()' in B
assert '"Update required"' in B
assert 'if(g_fw_runtime_screen && boot_scr) return;' in T
assert 'lv_obj_t *previous_scr = boot_scr;' in T
assert 'lv_obj_del(previous_scr)' in T
assert 'if(pct != g_fw_last_display_pct)' in T
assert 'g_status_text = "E-Stop " + src;' in T
assert 'detail.startsWith("E-Stop / ")' in T

print('AUDIT_REGRESSIONS_PASS')
