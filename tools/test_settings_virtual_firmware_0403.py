#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B=(ROOT/'SRVR_GitHub_v26.10.08.03'/'backend.py').read_text()
Q=(ROOT/'SRVR_GitHub_v26.10.08.03'/'qml'/'pages'/'SetupPage.qml').read_text()
C=(ROOT/'HV_P2P_CTRL_EDGEBOX_v26.10.08.03'/'HV_P2P_CTRL_EDGEBOX_v26.10.08.03.ino').read_text()
W=(ROOT/'HV_P2P_W1P_EDGEBOX_v26.10.08.03'/'HV_P2P_W1P_EDGEBOX_v26.10.08.03.ino').read_text()

# External/AUX changes must refresh the Settings mirror and the visible controls
# bind to live state, not a stale draft snapshot.
assert 'self._save_config(); self._refresh_setup_mirror(); self._notify_config()' in B
assert 'id:batteryChangeModeCombo' in Q and 'value:backend.batteryChange?1:0' in Q
assert 'id:accelerationModeCombo' in Q and 'value:root.idx(accelerationModeCombo.model,backend.accelerationMode)' in Q
assert 'Battery Change auto-cancelled' in B and 'self._refresh_setup_mirror()' in B[B.index('def _update_battery_change_auto_cancel'):B.index('def _predictive_speed_cap')]

# Battery Change/service motion must be speed-limited but allowed outside limits
# on both SRVR and W1P, with signed distance telemetry preserved.
assert 'return 5.0 / 3.6' in B
motion=B[B.index('def _motion_tick'):B.index('# --- Free-D ---')]
assert 'if not service:' in motion and '_hard_limit_velocity' in motion
assert 'if (g.service_mode) return requestedVel;' in W
assert 'to_near = pos_abs - near_abs' in B and 'to_far = far_abs - pos_abs' in B
assert 'def toNear(self): return self.position-float' in B
assert 'def toFar(self): return float(self.state.far_limit.position_m or 100.0)-self.position' in B
assert 'if (g.service_mode)' in W and 'line += "|to_near=" + String(g.pos_m - g.limit_near_m, 3);' in W

# Virtual must be a local simulation that can run with no W1P while still
# positively inhibiting any W1P that is present.
assert 'virtual_demo = (self.position_source == "Virtual")' in B
assert '((not virtual_demo) and w1p_safety)' in B
assert 'self.w1p.send("STOP")' in B and 'self.w1p.send("SW_SRVON 0")' in B
assert 'if self.position_source == "Virtual":' in B and 'self._virtual_velocity_mps = vel' in B

# CTRL and W1P firmware value fields show live progress during updates, otherwise
# the reported running firmware version. CTRL must report update progress back to
# SRVR, not only to CTRL-TS.
assert 'def ctrlFirmwareDisplay' in B and 'def w1pFirmwareDisplay' in B
assert 'text:backend.ctrlFirmwareDisplay' in Q and 'text:backend.w1pFirmwareDisplay' in Q
assert 'FW_PROGRESS|device=CTRL|active=' in C
ctrl_worker=B[B.index('def _controller_worker'):B.index('@staticmethod\n    def _parse_control_packet')]
assert 'line_text.startswith("FW_PROGRESS|")' in ctrl_worker and '_set_fw_progress("ctrl"' in ctrl_worker
assert 'FW_PROGRESS|device=W1P|active=' in W

# CTRL-TS Settings panel is now one Firmware row with version-or-progress text.
assert 'def ctrlTsFirmwareDisplay' in B
panel=Q[Q.index('Text{text:"▣  CTRL-TS"'):Q.index('Panel {', Q.index('Text{text:"▣  CTRL-TS"')+1)]
assert 'text:"Firmware"' in panel and 'backend.ctrlTsFirmwareDisplay' in panel
assert 'text:"Detected"' not in panel and 'text:"Required"' not in panel and 'text:"Update"' not in panel

print('SETTINGS_VIRTUAL_FIRMWARE_0403_PASS')
