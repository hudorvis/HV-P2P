#!/usr/bin/env python3
"""Regression contract for HV P2P Power/Speed acceleration-mode semantics.

This intentionally does not retune the controller.  It proves that SRVR maps the
operator's Speed choice to W1P DYNAMIC mode, W1P keeps the EL7 in velocity mode,
and the DYNAMIC outer loop varies its velocity command in the direction required
to correct measured cable-speed error. Power/TRADITIONAL remains the uncorrected
profile response.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SRVR = (ROOT / 'SRVR_GitHub_v26.09.04.02' / 'backend.py').read_text(encoding='utf-8')
W1P = (ROOT / 'HV_P2P_W1P_EDGEBOX_v26.09.04.02' / 'HV_P2P_W1P_EDGEBOX_v26.09.04.02.ino').read_text(encoding='utf-8')


def const(name: str) -> float:
    m = re.search(rf'static const float\s+{re.escape(name)}\s*=\s*([0-9.]+)f?\s*;', W1P)
    assert m, f'missing {name}'
    return float(m.group(1))


# End-to-end mode mapping and the EL7 command path are locked.
assert "SET_ACCEL_MODE {'DYNAMIC' if self.acceleration_mode == 'Speed' else 'TRADITIONAL'}" in SRVR
assert 'ACCEL_MODE_DYNAMIC' in W1P and 'ACCEL_MODE_TRADITIONAL' in W1P
assert 'mode == "DYNAMIC" || mode == "SPEED"' in W1P
assert 'mode == "TRADITIONAL" || mode == "NORMAL" || mode == "POWER"' in W1P
assert 'REG_PR0_MODE, PR_MODE_VELOCITY' in W1P
assert 'REG_PR0_VELOCITY' in W1P and 'PR_TRIGGER_PATH0' in W1P
assert 'MOTION_PROFILE_INTERVAL_MS = 20' in W1P, 'Speed/profile loop must remain 50 Hz'
assert 'g_dynamic_feedback_mps = (0.30f * raw_mps) + (0.70f * g_dynamic_feedback_mps);' in W1P, 'Speed mode must use smoothed measured cable velocity'

# Speed mode must use real measured cable-speed feedback and PI correction.
for token in (
    'g_acceleration_mode == ACCEL_MODE_DYNAMIC',
    'g.drive_feedback_ok',
    'g_dynamic_feedback_mps',
    'float speedErr = g.vel_profile_mps - g_dynamic_feedback_mps;',
    'DYNAMIC_SPEED_KP * speedErr + DYNAMIC_SPEED_KI * g_dynamic_speed_i_mps',
    'g_dynamic_speed_i_mps += speedErr * dt;',
    'corr = constrain(corr, -corrLimit, corrLimit);',
    'cmdOut = constrain(g.vel_profile_mps + corr, -MAX_CMD_VEL_MPS, MAX_CMD_VEL_MPS);',
):
    assert token in W1P, f'missing Speed-mode controller token: {token}'

# Power mode must not inherit a stale Speed-mode integral correction.
assert 'else {\n    g_dynamic_speed_i_mps = 0.0f;' in W1P

KP = const('DYNAMIC_SPEED_KP')
KI = const('DYNAMIC_SPEED_KI')
BASE = const('DYNAMIC_CORR_BASE_MPS')
FRAC = const('DYNAMIC_CORR_FRAC')
MAX_CORR = const('DYNAMIC_CORR_MAX_MPS')
DEADBAND = const('DYNAMIC_CORR_DEADBAND_MPS')
assert KP > 0 and KI > 0 and BASE > 0 and FRAC > 0 and MAX_CORR > BASE and DEADBAND > 0


def dynamic_command(profile: float, measured: float, dt: float = 0.02, integral: float = 0.0):
    err = profile - measured
    if abs(err) < DEADBAND:
        err = 0.0
    limit = min(MAX_CORR, max(BASE, abs(profile) * FRAC + BASE))
    integral += err * dt
    integral_limit = limit / max(0.05, KI)
    integral = max(-integral_limit, min(integral_limit, integral))
    corr = KP * err + KI * integral
    corr = max(-limit, min(limit, corr))
    cmd = profile + corr
    if profile > 0 and cmd < 0:
        cmd = 0.0
    elif profile < 0 and cmd > 0:
        cmd = 0.0
    return cmd, corr, integral, limit

# Under-speed increases requested velocity so the EL7's internal velocity loop
# demands additional torque/current; over-speed reduces it. The same is true in
# reverse, and correction is always bounded.
cmd, corr, _, limit = dynamic_command(10.0, 8.0)
assert cmd > 10.0 and 0.0 < corr <= limit
cmd, corr, _, limit = dynamic_command(10.0, 12.0)
assert cmd < 10.0 and -limit <= corr < 0.0
cmd, corr, _, limit = dynamic_command(-10.0, -8.0)
assert cmd < -10.0 and -limit <= corr < 0.0
cmd, corr, _, limit = dynamic_command(-10.0, -12.0)
assert cmd > -10.0 and 0.0 < corr <= limit
cmd, corr, _, limit = dynamic_command(10.0, 0.0, dt=5.0)
assert abs(corr) <= limit + 1e-9 and cmd >= 0.0

# At zero/no target the source explicitly clears the integrator and command.
assert 'fabsf(target) <= MOTION_ZERO_EPS_MPS' in W1P
assert 'g_dynamic_speed_i_mps = 0.0f;\n    cmdOut = 0.0f;' in W1P

print('SPEED_MODE_CONTRACT_PASS')
print(f'KP={KP:.3f} KI={KI:.3f} deadband={DEADBAND:.3f} max_correction={MAX_CORR:.3f} m/s')
