#!/usr/bin/env python3
"""v26.10.06.07 contracts for joystick drift, preset naming and predictive stops."""
from __future__ import annotations
from pathlib import Path
import math
import re

ROOT = Path(__file__).resolve().parents[1]
SR = ROOT / 'SRVR_GitHub_v26.10.06.07'
BACKEND = (SR / 'backend.py').read_text(encoding='utf-8')
MAIN = (SR / 'qml' / 'Main.qml').read_text(encoding='utf-8')
SETUP = (SR / 'qml' / 'pages' / 'SetupPage.qml').read_text(encoding='utf-8')
SPAN = (SR / 'qml' / 'components' / 'SpanDiagram.qml').read_text(encoding='utf-8')
W1P = (ROOT / 'HV_P2P_W1P_EDGEBOX_v26.10.06.07' / 'HV_P2P_W1P_EDGEBOX_v26.10.06.07.ino').read_text(encoding='utf-8')


def py_const(name: str) -> float:
    m = re.search(rf'(?m)^{re.escape(name)}\s*=\s*([0-9.]+)\s*$', BACKEND)
    assert m, f'missing backend constant {name}'
    return float(m.group(1))


def cpp_const(name: str) -> float:
    m = re.search(rf'static const float\s+{re.escape(name)}\s*=\s*([0-9.]+)f?\s*;', W1P)
    assert m, f'missing W1P constant {name}'
    return float(m.group(1))


def py_method(name: str) -> str:
    m = re.search(rf'(?m)^    def {re.escape(name)}\([^\n]*\)[^:\n]*:\n', BACKEND)
    assert m, f'missing backend method {name}'
    start = m.start()
    nxt = re.search(r'(?m)^    (?:def|@Property|@Slot|@staticmethod|@classmethod)\b', BACKEND[m.end():])
    end = len(BACKEND) if not nxt else m.end() + nxt.start()
    return BACKEND[start:end]


# 1) Requested SRVR joystick readout labels + exact common value column.
assert 'text:"Value"' in SETUP and 'text:"Percentage"' in SETUP
assert 'Current Value' not in SETUP and 'Current Percentage' not in SETUP
assert 'text:Number(backend.setupJoystickValue).toFixed(2);horizontalAlignment:Text.AlignRight' in SETUP
assert 'text:Number(backend.setupJoystickPercentage).toFixed(1)+" %";horizontalAlignment:Text.AlignRight' in SETUP
assert 'def setupJoystickPercentage' in BACKEND and 'def _setup_preview_joystick' in BACKEND
assert SETUP.count('width:root.f(72);anchors.verticalCenter:parent.verticalCenter') >= 2

# 2) Short/Long preset name selection is global and reaches both SRVR diagrams and CTRL-TS packet.
for token in ('text:"Preset Names"', 'text:"Short Names"', 'text:"Long Names"',
              'backend.setPresetNameMode("Short Names")', 'backend.setPresetNameMode("Long Names")'):
    assert token in MAIN, f'missing preset-mode QML token: {token}'
for token in ('self.preset_name_mode = "Short Names"', '"preset_name_mode": self.preset_name_mode',
              'def setPresetNameMode', '"shortName": f"P{i+1}"', '"longName":', '"displayName": self._preset_display_name(i)'):
    assert token in BACKEND, f'missing preset-mode backend token: {token}'
assert 'item.displayName' in SPAN
assert 'preset_names.append(self._display_field(self._preset_display_name(i), 24))' in BACKEND
assert 'f"preset_names={\',\'.join(preset_names)}"' in BACKEND

# 3) Centre drift is conservative, runtime-only and bounded.
for token in ('JOY_CENTRE_DRIFT_IDLE_S', 'JOY_CENTRE_DRIFT_SAMPLE_WINDOW_S',
              'JOY_CENTRE_DRIFT_CAPTURE_FRAC', 'JOY_CENTRE_DRIFT_STABILITY_FRAC',
              'JOY_CENTRE_DRIFT_MAX_FRAC', 'JOY_CENTRE_DRIFT_TAU_S',
              'def _update_joystick_centre_drift', 'def _effective_joystick_centre',
              'self._update_joystick_centre_drift()', 'joystickCentreTrimPercentage'):
    assert token in BACKEND, f'missing centre-drift token: {token}'
drift = py_method('_update_joystick_centre_drift')
assert 'self.joystick_cal_centre =' not in drift, 'runtime drift must never rewrite saved calibration centre'
for token in ('not self.state.estop_active', 'not self.joystick_calibration_open',
              'self.goto_target_m is None', 'not self._service_override_active()',
              'abs(float(self.requested_speed_mps or 0.0)) <= 0.001',
              'abs(float(self.current_speed_mps or 0.0)) <= 0.03'):
    assert token in drift, f'centre drift missing idle/safety gate: {token}'
max_frac = py_const('JOY_CENTRE_DRIFT_MAX_FRAC')
assert 0.0 < max_frac <= 0.03, max_frac
assert 'recalibration recommended' in drift

# 4) Predictive stop envelope exists in SRVR and independently in W1P.
for token in ('PREDICTIVE_LIMIT_REACTION_S', 'PREDICTIVE_LIMIT_MARGIN_M',
              'PREDICTIVE_LIMIT_DECEL_FACTOR', 'def _predictive_speed_cap',
              'self._predictive_speed_cap(rem, decel)'):
    assert token in BACKEND, f'missing SRVR predictive-stop token: {token}'
for token in ('LIMIT_PREDICT_REACTION_S', 'LIMIT_PREDICT_MARGIN_M',
              'LIMIT_PREDICT_DECEL_FACTOR', 'predictiveLimitSpeedCap',
              'target = limitVelocityForSoftLimits(g.pos_m, target);'):
    assert token in W1P, f'missing W1P predictive-stop token: {token}'

sr_t = py_const('PREDICTIVE_LIMIT_REACTION_S')
sr_margin = py_const('PREDICTIVE_LIMIT_MARGIN_M')
sr_factor = py_const('PREDICTIVE_LIMIT_DECEL_FACTOR')
w_t = cpp_const('LIMIT_PREDICT_REACTION_S')
w_margin = cpp_const('LIMIT_PREDICT_MARGIN_M')
w_factor = cpp_const('LIMIT_PREDICT_DECEL_FACTOR')
assert sr_t >= w_t > 0.0, (sr_t, w_t)  # SRVR may taper slightly earlier than local W1P.
assert abs(sr_margin - w_margin) < 1e-9 and sr_margin >= 0.05
assert 0.0 < sr_factor <= 0.75 and 0.0 < w_factor <= 0.75


def cap(remaining: float, decel: float, reaction: float, margin: float, factor: float) -> float:
    d = max(0.0, remaining - margin)
    a = max(0.10, decel * factor)
    if d <= 0.0:
        return 0.0
    at = a * reaction
    return max(0.0, math.sqrt(at*at + 2.0*a*d) - at)

# Cap must monotonically fall as distance closes, reaching zero at the safety margin.
far = cap(10.0, 5.0, sr_t, sr_margin, sr_factor)
mid = cap(2.0, 5.0, sr_t, sr_margin, sr_factor)
near = cap(0.5, 5.0, sr_t, sr_margin, sr_factor)
stop = cap(sr_margin, 5.0, sr_t, sr_margin, sr_factor)
assert far > mid > near > 0.0 and stop == 0.0, (far, mid, near, stop)

# 5) Speed mode retains a velocity-command architecture for slope/load changes.
# The EL7 is the inner velocity loop. W1P's bounded PI nudges the setpoint in the
# correction direction but must never reverse requested motion merely to brake.
for token in ('REG_PR0_MODE, PR_MODE_VELOCITY',
              'float speedErr = g.vel_profile_mps - g_dynamic_feedback_mps;',
              'DYNAMIC_SPEED_KP * speedErr + DYNAMIC_SPEED_KI * g_dynamic_speed_i_mps',
              'corr = constrain(corr, -corrLimit, corrLimit);',
              'Never let a correction reverse the commanded direction while a target exists'):
    assert token in W1P, f'missing slope/speed-mode contract: {token}'
assert 'downhill over-speed is resisted by negative/regenerative motor' in W1P
assert 'W1P deliberately never reverses the velocity command merely to brake' in W1P

print('MOTION_INNOVATIONS_CONTRACT_PASS')
print(f'centre_trim_max={max_frac*100:.1f}% srvr_reaction={sr_t:.2f}s w1p_reaction={w_t:.2f}s margin={sr_margin:.2f}m')
