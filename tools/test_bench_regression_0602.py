#!/usr/bin/env python3
"""v26.10.08.03 locked-scope bench regressions for the five requested fixes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VER = '26.10.08.03'
B = (ROOT / f'SRVR_GitHub_v{VER}' / 'backend.py').read_text(encoding='utf-8')
M = (ROOT / f'SRVR_GitHub_v{VER}' / 'qml' / 'Main.qml').read_text(encoding='utf-8')
S = (ROOT / f'SRVR_GitHub_v{VER}' / 'qml' / 'pages' / 'SetupPage.qml').read_text(encoding='utf-8')
BTN = (ROOT / f'SRVR_GitHub_v{VER}' / 'qml' / 'components' / 'HVButton.qml').read_text(encoding='utf-8')
FIELD = (ROOT / f'SRVR_GitHub_v{VER}' / 'qml' / 'components' / 'HVField.qml').read_text(encoding='utf-8')
W = next((ROOT / f'HV_P2P_W1P_EDGEBOX_v{VER}').glob('*.ino')).read_text(encoding='utf-8')
T = next((ROOT / f'HV_P2P_CTRL_TS_v{VER}').glob('*.ino')).read_text(encoding='utf-8')

# 1) Limit Calibration random stops: keep the proven cadence/watchdog values
# unchanged, but renew the short background VEL lease from fresh CTRL packets
# only while the physical raw stick remains coherent with the command producer.
assert 'VEL_KEEPALIVE_S = 0.15' in B
assert 'VEL_BACKGROUND_REFRESH_S = 0.18' in B
assert 'VEL_REFRESH_LEASE_S = 0.22' in B
assert 'VEL_REFRESH_AXIS_TOL = 0.035' in B
assert 'static const uint32_t W1P_VEL_COMMAND_TIMEOUT_MS = 500;' in W
assert 'def renew_velocity_refresh_from_controller(self, source_axis, unsafe: bool = False):' in B
renew = B[B.index('    def renew_velocity_refresh_from_controller'):B.index('    def clear_velocity_refresh', B.index('    def renew_velocity_refresh_from_controller'))]
for token in ('self._vel_refresh_source_axis', 'VEL_REFRESH_AXIS_TOL', 'self._vel_refresh_until = time.monotonic() + VEL_REFRESH_LEASE_S'):
    assert token in renew, f'CTRL-coherent VEL lease renewal missing {token}'
assert 'self._vel_refresh_text = ""' in renew and 'self._vel_refresh_source_axis = None' in renew
worker = B[B.index('    def _controller_worker'):B.index('    @staticmethod\n    def _parse_control_packet')]
for token in ('FLAG_ESTOP_PRESSED', 'FLAG_ADS1115_FAULT', 'FLAG_CTRL_HMI_FAULT', 'FLAG_CTRL_FW_FAULT'):
    assert token in worker, f'CTRL refresh safety mask missing {token}'
assert 'self.w1p.renew_velocity_refresh_from_controller(msg[1], unsafe=refresh_unsafe)' in worker
assert 'self.w1p.arm_velocity_refresh(cmd, source_axis=self._ctrl_axis)' in B

# 2/5) Run > Shortcuts > System uses the same locked 31 px row grid/component
# fonts as Preset/Limits, and the three calibration buttons use the requested
# compact operator labels without changing backend action names.
sys_start = M.index('// Keep System controls on the same locked visual grid')
sys_end = M.index('                                }\n                            }', sys_start)
system = M[sys_start:sys_end]
assert 'spacing:f(3)' in system
assert system.count('height:f(31)') >= 5
assert system.count('spacing:f(5)') >= 5
assert 'height:f(32)' not in system
assert 'font.pixelSize:f(11)' not in system
for label in ('Joystick', 'Limit', 'Winch'):
    assert f'text:"{label}"' in system
for old in ('text:"Joystick Calibration"', 'text:"Limit Calibration"', 'text:"Winch Calibration"'):
    assert old not in system
assert 'backend.openJoystickCalibration()' in system
assert 'backend.openLimitCalibration()' in system
assert 'backend.openWinchCalibration()' in system
assert 'implicitHeight: 32' in BTN and 'font.pixelSize: 14' in BTN
assert 'implicitHeight: 31' in FIELD and 'font.pixelSize: 13' in FIELD

# 3) AUX assignment dropdown starts with None; all existing action strings remain.
choices_start = S.index('property var auxChoices:')
choices_end = S.index('    ]', choices_start)
choices = S[choices_start:choices_end]
assert choices.index('"None"') < choices.index('"Acceleration Mode"')
for value in ('Acceleration Mode','Battery Change Mode','Drive Mode','Joystick Calibration','Limit Calibration','Winch Calibration'):
    assert f'"{value}"' in choices

# 4) CTRL-TS progress marker remains display-only and locally interpolated at
# the LVGL service rate. The current implementation must not predict ahead of
# verified HMM1 samples because that can overshoot and visibly correct backwards.
for token in ('g_motion_sample_frac', 'g_progress_display_frac', 'g_progress_segment_start_frac', 'g_progress_segment_duration_ms'):
    assert token in T
smooth = T[T.index('static void service_progress_marker_smooth()'):T.index('static void update_reference_marker()', T.index('static void service_progress_marker_smooth()'))]
assert 'g_progress_segment_start_frac +' in smooth
assert 'g_motion_sample_frac - g_progress_segment_start_frac' in smooth
assert 'set_progress_marker_fraction(g_progress_display_frac)' in smooth
assert 'g_motion_sample_speed_mps' not in T
assert 'min(age_ms, (uint32_t)180)' not in T
loop = T[T.index('void loop()'):]
assert 'service_progress_marker_smooth();' in loop
apply = T[T.index('static void apply_hmi_packet'):T.index('static inline void rs485_slave_turnaround_guard', T.index('static void apply_hmi_packet'))]
assert 's = String(g_pos, 2); set_label_text_if_changed(lbl_current_pos, s.c_str());' in apply
assert 'float next_frac = constrain(g_pos_frac' in T

print('BENCH_REGRESSION_0602_PASS')
