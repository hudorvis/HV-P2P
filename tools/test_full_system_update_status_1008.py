#!/usr/bin/env python3
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.08.03'
C=(ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}'/f'HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text()
W=(ROOT/f'HV_P2P_W1P_EDGEBOX_v{VER}'/f'HV_P2P_W1P_EDGEBOX_v{VER}.ino').read_text()
T=(ROOT/f'HV_P2P_CTRL_TS_v{VER}'/f'HV_P2P_CTRL_TS_v{VER}.ino').read_text()
B=(ROOT/f'SRVR_GitHub_v{VER}'/'backend.py').read_text()

# Both field controllers report real authority-OTA progress to SRVR.
assert 'FW_PROGRESS|device=CTRL|active=' in C
assert 'FW_PROGRESS|device=W1P|active=' in W
# CTRL additionally gives CTRL-TS direct progress while the CTRL loop is blocked.
assert 'FWSTAT|device=CTRL|active=' in C
assert 'hmiSendFirmwareStatusText(msg)' in C

# SRVR tracks both devices and carries their phase/percentage in DSP1.
for tok in ("_set_fw_progress(\"ctrl\"", "_set_fw_progress(\"w1p\"", "fw_ctrl_active=", "fw_ctrl_phase=", "fw_ctrl_pct=", "fw_w1p_active=", "fw_w1p_phase=", "fw_w1p_pct="):
    assert tok in B, tok

# CTRL forwards the compact firmware state to CTRL-TS as priority HMS1 traffic.
state_fn=B  # placeholder only for clearer failures below
assert '"fw_ctrl_active", "fw_ctrl_phase", "fw_ctrl_pct"' in C
assert '"fw_w1p_active", "fw_w1p_phase", "fw_w1p_pct", "fw_ts_allowed"' in C
assert 'String out = "HMS1";' in C

# CTRL-TS consumes and renders both external update rows.
assert 'getField(line, "fw_ctrl_active")' in T
assert 'fw_set_device_status("CTRL"' in T
assert 'getField(line, "fw_w1p_active")' in T
assert 'fw_set_device_status("W1P"' in T
assert 'apply_external_fw_fields(line);' in T

# Ordered coordinator remains CTRL -> W1P -> CTRL-TS, keeping the touchscreen
# available to display CTRL/W1P progress before its own final-stage self-flash.
coord=B[B.index('def _ctrl_ts_update_allowed'):B.index('def _ctrl_ts_update_allowed_safe')]
assert 'waiting for CTRL authority' in coord
assert 'waiting for W1P update' in coord
assert '_grant_ctrl_ts_update("CTRL and W1P verified")' in coord
assert 'fw_ts_allowed=' in B

# All three target firmwares advertise this release so a full SRVR release causes
# normal authority convergence on CTRL and W1P and the final CTRL-TS stage.
for src in (C,W,T):
    assert f'v{VER}' in src
print('FULL_SYSTEM_UPDATE_STATUS_1008_PASS')
