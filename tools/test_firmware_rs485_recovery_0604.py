#!/usr/bin/env python3
"""v26.10.06.08 regression: updater stages cannot strand a live mismatched CTRL-TS."""
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
VER = '26.10.06.08'
B = (ROOT/f'SRVR_GitHub_v{VER}'/'backend.py').read_text(encoding='utf-8')
Q = (ROOT/f'SRVR_GitHub_v{VER}'/'qml'/'pages'/'SetupPage.qml').read_text(encoding='utf-8')
C = (ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}'/f'HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text(encoding='utf-8')
W = (ROOT/f'HV_P2P_W1P_EDGEBOX_v{VER}'/f'HV_P2P_W1P_EDGEBOX_v{VER}.ino').read_text(encoding='utf-8')

# Stage-1 CTRL release discovery must never depend on later-stage coordinator success.
assert 'def _ctrl_ts_update_allowed_safe(self) -> bool:' in B
beacon = re.search(r'def _send_ctrl_firmware_beacon\(.*?(?=\n    def _send_w1p_firmware_beacon)', B, re.S)
assert beacon and '_ctrl_ts_update_allowed_safe()' in beacon.group(0)
assert 'CTRL-TS gate error; keeping final stage closed' in B

# Background communications/recovery workers must recover from a single exception
# instead of silently dying and requiring a field-node reboot.
worker = re.search(r'def _srvr_alive_worker\(self\):(?P<body>.*?)(?=\n    def _controller_worker)', B, re.S)
assert worker
wb = worker.group('body')
assert 'CTRL beacon worker recovered from error' in wb
assert 'W1P beacon worker recovered from error' in wb
assert 'recovery worker recovered from error' in wb
assert 'HMI_STATUS handler recovered from error' in B

# Normal coordinator ordering remains, but W1P cannot indefinitely hold HMI final stage.
assert 'W1P_FINAL_STAGE_WAIT_S = 8.0' in B
assert 'W1P_ACTIVE_UPDATE_WAIT_S = 60.0' in B
assert 'bounded W1P wait expired; W1P remains fail-closed' in B

# CTRL has an independent bounded recovery after exact CTRL authority verification.
assert 'HMI_COORDINATOR_FALLBACK_MS = 12000' in C
assert 'g_hmiMismatchSinceMs' in C
assert 'bounded coordinator recovery' in C
assert 'hmiFwStart(coordinatorFallback)' in C
assert 'g_srvrFirmwareMatched' in C and 'g_hmiSafeOtaCapable' in C

# A live version-mismatched RS485 bus is diagnostic-active even while the safety/
# compatibility gate remains closed. Do not relabel compatibility as physical link loss.
assert 'def ctrlTsRs485Active(self):' in B
assert '_ctrl_ts_rs485_alive_reported' in B
assert 'backend.ctrlTsRs485Active?"Active":"Disconnected"' in Q
assert 'return g_hmiCompatible &&' in C  # compatibility/safety semantics remain unchanged

# Locked safety architecture remains unchanged: W1P independent 500 ms watchdog.
assert 'VEL_COMMAND_TIMEOUT_MS = 500' in W or 'VEL_FRESHNESS_TIMEOUT_MS = 500' in W or '500' in W[W.find('watchdog')-500:W.find('watchdog')+1500]
print('FIRMWARE_RS485_RECOVERY_0604_PASS')
