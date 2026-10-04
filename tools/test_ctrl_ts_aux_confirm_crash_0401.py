#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TS = (ROOT / 'HV_P2P_CTRL_TS_v26.10.04.04' / 'HV_P2P_CTRL_TS_v26.10.04.04.ino').read_text()
CTRL = (ROOT / 'HV_P2P_CTRL_EDGEBOX_v26.10.04.04' / 'HV_P2P_CTRL_EDGEBOX_v26.10.04.04.ino').read_text()
SRVR = (ROOT / 'SRVR_GitHub_v26.10.04.04' / 'backend.py').read_text()

# Production face deliberately has no debug label. Any direct LVGL call through
# that pointer is therefore a crash bug; diagnostic helper must remain null-safe.
assert 'lbl_touch_debug=nullptr' in TS
assert 'lv_label_set_text(lbl_touch_debug' not in TS
assert 'set_touch_debug("Ready")' in TS
assert 'if(!lbl || !txt) return;' in TS

# Confirmation must not claim success unless the command entered the retry-safe
# event queue. A full queue leaves the AUX selected for an explicit retry.
assert 'static bool send_hmi_command(const char *cmd)' in TS
assert 'if(!send_hmi_command(cmd))' in TS
assert 'AUX queue busy - confirm again' in TS

# Keep low-rate end-to-end diagnostics so bench can prove whether a particular
# AUX command reached CTRL and what resulting SRVR state was applied.
assert '|last_event_id=' in CTRL and '|last_event_cmd=' in CTRL
assert 'g_hmiLastAcceptedEventCmd = cmd.startsWith("AUX") ? cmd : String("OTHER")' in CTRL
assert '[CTRL-TS EVENT] CTRL accepted id=' in SRVR
assert "[AUX] {label}: {action}{result}" in SRVR

print('CTRL_TS_AUX_CONFIRM_CRASH_0401_PASS')
