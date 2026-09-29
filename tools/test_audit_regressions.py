#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VER="26.09.29.02"
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
print('AUDIT_REGRESSIONS_PASS')
