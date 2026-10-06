#!/usr/bin/env python3
"""v26.10.06.05 locked-scope regressions: calibration AUX confirmation + motion status."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VER = '26.10.06.05'
T = next((ROOT / f'HV_P2P_CTRL_TS_v{VER}').glob('*.ino')).read_text(encoding='utf-8')
B = (ROOT / f'SRVR_GitHub_v{VER}' / 'backend.py').read_text(encoding='utf-8')

# 1) Every calibration step must start from Ready and need two fresh local taps.
cal = T[T.index('static bool apply_calibration_overlay_fields'):T.index('static int split_csv', T.index('static bool apply_calibration_overlay_fields'))]
assert 'if(selected_aux >= 0)' in cal
assert 'selected_aux = -1; g_selected_aux_ms = 0;' in cal
assert 'if(confirmed_aux >= 0)' in cal
assert 'confirmed_aux = -1; clear_confirm_at = 0;' in cal
assert 'two fresh local' in cal

# CTRL AUX flags are touchscreen transport echoes in this architecture; they may
# be tracked but must never feed the local select/confirm state machine.
flags = T[T.index('static void apply_flags_to_aux'):T.index('static void set_touch_debug', T.index('static void apply_flags_to_aux'))]
assert 'confirm_aux_idx(i, false);' not in flags
assert 'touchscreen-only' in flags and 'transport echoes' in flags

# 2) Fast deliberate taps: no 250 ms select->confirm gate remains. Duplicate
# callback debounce happens at LVGL event capture so two queued taps can both run.
assert 'AUX_TOUCH_CONFIRM_GAP_MS' not in T
assert 'AUX_TOUCH_DEBOUNCE_MS = 35' in T
assert 'g_aux_suppress_until_ms' not in T
queue = T[T.index('static bool queue_aux_touch'):T.index('static int pop_aux_touch', T.index('static bool queue_aux_touch'))]
assert 'g_last_aux_touch_ms[idx]' in queue
assert 'AUX_TOUCH_DEBOUNCE_MS' in queue
confirm = T[T.index('static void confirm_aux_idx'):T.index('static void apply_flags_to_aux', T.index('static void confirm_aux_idx'))]
assert 'processing-time delay' in confirm
assert '(now_ms - g_selected_aux_ms)' not in confirm

# 3) Canonical backend status is shared by SRVR + CTRL-TS. E-stop/service/
# uncalibrated states retain priority, then Near/Far (within 1 m), then Ramping.
assert 'LIMIT_STATUS_DISTANCE_M = 1.0' in B
assert 'RAMP_STATUS_SPEED_EPS_MPS = 0.03' in B
zone = B[B.index('    def _normal_motion_zone_status'):B.index('    def _resolved_system_status', B.index('    def _normal_motion_zone_status'))]
for text in ('System | Near Limit', 'System | Far Limit', 'System | Ramping'):
    assert text in zone
assert 'motion < 0.0' in zone and 'near_ramp > 0.0' in zone
assert 'motion > 0.0' in zone and 'far_ramp > 0.0' in zone
resolved = B[B.index('    def _resolved_system_status'):B.index('    def _set_ctrl_ts_gate_reason', B.index('    def _resolved_system_status'))]
order = [resolved.index(x) for x in (
    'if self.state.estop_active:',
    'if self.joystick_calibration_open:',
    'if self.calibration_open:',
    'if self.battery_change_mode:',
    'if self._not_calibrated:',
    'zone_status = self._normal_motion_zone_status()',
)]
assert order == sorted(order), 'new motion states must not outrank safety/service/calibration states'
assert 'return zone_status, "yellow", "", 0' in resolved

print('BENCH_REGRESSION_0605_PASS')
