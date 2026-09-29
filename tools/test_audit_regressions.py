#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VER="26.09.29.05"
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

# v26.09.29.05 operator input / safety refinements.
assert 'self.reverse_joystick = True' in B
assert 'VEL_KEEPALIVE_S = 0.15' in B
assert 'def joystickPercentage' in B
assert 'W1P_VEL_COMMAND_TIMEOUT_MS = 500' in W
assert 'JOY_SAMPLES = 8' in C and 'trimmedSum' in C
assert 'SGM_CONFIG_AI1_CONT_800SPS_6V144 = 0x50E3' in C
assert 'sampleCtrlEstopAI0' in C
assert 'AI0 carries the CTRL E-stop status' in C and 'AI1 carries the APEM 0-5 V joystick signal' in C
assert 'Failed selecting AI0 E-stop channel' in C and 'Failed restoring AI1 joystick channel' in C
assert 'CTRL_ESTOP_HEALTHY_MIN_V = 3.5f' in C and 'CTRL_ESTOP_HEALTHY_CONFIRM_SAMPLES = 3' in C
# v26.09.29.05 CI direction-regression guard: backend tests must not assume
# positive raw CTRL axis implies positive requested motor speed when the default
# commissioned joystick direction is inverted.
BT=(ROOT/'SRVR_GitHub_v26.09.29.05/tools/test_backend_logic.py').read_text()
assert 'assert b.reverse_joystick is True' in BT
assert '0.0 < abs(b.requested_speed_mps)' in BT
assert '1.0 if b.reverse_joystick else -1.0' in BT
print('AUDIT_REGRESSIONS_PASS')
