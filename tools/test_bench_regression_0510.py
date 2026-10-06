#!/usr/bin/env python3
"""v26.10.06.04 bench regressions: calibration origin, System layout, AUX label width."""
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
BE = (ROOT / "SRVR_GitHub_v26.10.06.04" / "backend.py").read_text()
QML = (ROOT / "SRVR_GitHub_v26.10.06.04" / "qml" / "Main.qml").read_text()
TS = (ROOT / "HV_P2P_CTRL_TS_v26.10.06.04" / "HV_P2P_CTRL_TS_v26.10.06.04.ino").read_text()

# Limit Calibration must re-zero its operator-facing coordinate after staged Near.
helper = BE[BE.index("def _limit_calibration_display_position"):BE.index("def _build_controller_display_packet")]
assert "self._limit_cal_pending.get(\"near\") is None" in helper
assert "near_raw = cap.get(\"near_raw\")" in helper
assert "abs(float(int(raw_now) - int(near_raw))" in helper
assert "abs(pos_now - float(near_pos))" in helper
assert "cal_pos = self._limit_calibration_display_position()" in BE
assert '"current": f"{self._limit_calibration_display_position():.2f} m"' in BE
assert "currentPosition:backend.limitCalibrationPosition" in QML

# System shortcut controls must use the same 31 px control height as Limits and
# fit inside the panel instead of overflowing its bottom edge.
sys_start = QML.index("// Keep System controls on the same locked visual grid")
sys_end = QML.index("                                }\n                            }", sys_start)
system = QML[sys_start:sys_end]
assert "spacing:f(3)" in system
assert system.count("height:f(31)") >= 4
assert "height:f(32)" not in system
for label in ("Power", "Speed", "Off", "On", "Joystick", "Limit", "Winch", "Short Names", "Long Names"):
    assert f'text:"{label}"' in system

# Practice Mode was source-truncated by the 24-character display-field default;
# the AUX field now has enough bounded payload for action + full value/name.
assert 'labels = [self._display_field(self._aux_action_label(i, source="ctrl"), 40) for i in range(5)]' in BE
assert 'aux_state[i]=make_label' in TS and 'AUX_W-8' in TS
assert 'lv_label_set_long_mode(aux_state[i], LV_LABEL_LONG_CLIP);' in TS

print("BENCH_REGRESSION_0510_PASS")
