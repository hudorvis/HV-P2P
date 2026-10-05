#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VER = '26.10.05.06'
B = (ROOT / f'SRVR_GitHub_v{VER}' / 'backend.py').read_text()
M = (ROOT / f'SRVR_GitHub_v{VER}' / 'qml' / 'Main.qml').read_text()
S = (ROOT / f'SRVR_GitHub_v{VER}' / 'qml' / 'pages' / 'SetupPage.qml').read_text()
C = (ROOT / f'HV_P2P_CTRL_EDGEBOX_v{VER}' / f'HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text()
T = (ROOT / f'HV_P2P_CTRL_TS_v{VER}' / f'HV_P2P_CTRL_TS_v{VER}.ino').read_text()

# Limit/Winch calibration service bypass is an immediate priority transaction,
# while the existing convergent settings loop remains armed for confirmation.
assert 'if force and self.w1p.connected:' in B
assert 'self.w1p.send(f"SERVICE_MODE {enabled}")' in B
assert 'self._mark_w1p_settings_pending(("SERVICE",))' in B

# Operator-facing current speed is magnitude-only; signed internal velocity is retained.
assert 'speed = float(self.current_speed_mps or 0.0)' in B
assert 'def currentSpeed(self): return abs(float(self.current_speed_mps))' in B
assert 'String(fabsf(g_speed_mps), 1)' in T
assert 'String(fabsf(g_speed_kmh), 1)' in T

# Both calibration wizards carry their three captures plus a live current value to CTRL-TS.
for field in ('cal_joy', 'cal_left', 'cal_centre', 'cal_right'):
    assert field in B and field in C and field in T
assert 'Current Winch Position' in M and 'Current Joystick Position' in M
assert 'Current Winch Position' in T and 'Current Joystick Position' in T
assert 'g_cal_value_box[3]' in T and 'g_cal_value_text[3]' in T

# A verified headless self-update cannot remain black forever if the final CTRL
# REBOOT/ACK exchange is lost. Explicit REBOOT still shortens the deadline.
assert 'g_fw_reboot_due_ms = millis() + 2500' in T
assert 'g_fw_reboot_due_ms = millis() + 250;' in T

# CTRL-TS travel scale uses the full usable 780px panel width, independent of labels.
assert 'BAR_LIMIT_LEFT = 8' in T
assert 'BAR_LIMIT_RIGHT = 772' in T

# Run Shortcuts: paired mode rows use full available width and calibration exposes all three wizards.
assert 'text:"Joystick Calibration";onClicked:{window.cancelShortcutConfirm();backend.openJoystickCalibration()}' in M
assert 'text:"Limit Calibration";onClicked:{window.cancelShortcutConfirm();backend.openLimitCalibration()}' in M
assert 'text:"Winch Calibration";onClicked:{window.cancelShortcutConfirm();backend.openWinchCalibration()}' in M
assert M.count('width:(parent.width-f(7))/2') >= 6

# Settings calibration buttons are alphabetical top-to-bottom.
j = S.index('text:"JOYSTICK CALIBRATION"')
l = S.index('text:"LIMIT CALIBRATION"')
w = S.index('text:"WINCH CALIBRATION"')
assert j < l < w

# AUX order: general actions alphabetically, then Near, Ref, Far, followed by
# Preset Recall, Preset Save and Preset Slip groups.
choices_start = S.index('property var auxChoices:')
choices_end = S.index('    ]', choices_start)
choices = S[choices_start:choices_end]
expected = [
    'Acceleration Mode','Battery Change Mode','Drive Mode',
    'Joystick Calibration','Limit Calibration','None','Winch Calibration',
    'Near Limit Recall','Near Limit Save','Near Limit Slip',
    'Ref Point Recall','Ref Point Save','Ref Point Slip',
    'Far Limit Recall','Far Limit Save','Far Limit Slip',
    'Preset 1 Recall','Preset 1 Save','Preset 1 Slip'
]
positions = [choices.index(f'"{x}"') for x in expected]
assert positions == sorted(positions)
assert choices.index('"Preset 10 Recall"') < choices.index('"Preset 1 Save"')
assert choices.index('"Preset 10 Save"') < choices.index('"Preset 1 Slip"')

print('BENCH_REGRESSION_0504_PASS')
