#!/usr/bin/env python3
"""v26.10.06.09 locked-scope regression: marker smoothing, persistent ramp status, W1P encoder path."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.06.09'
T=(ROOT/f'HV_P2P_CTRL_TS_v{VER}/HV_P2P_CTRL_TS_v{VER}.ino').read_text()
B=(ROOT/f'SRVR_GitHub_v{VER}/backend.py').read_text()
W=(ROOT/f'HV_P2P_W1P_EDGEBOX_v{VER}/HV_P2P_W1P_EDGEBOX_v{VER}.ino').read_text()

# 1) Progress marker uses verified sample-to-sample interpolation, never velocity prediction.
update=T[T.index('static void update_progress_marker()'):T.index('static void service_progress_marker_smooth()')]
smooth=T[T.index('static void service_progress_marker_smooth()'):T.index('static void update_reference_marker()')]
for tok in ('g_progress_segment_start_frac', 'g_progress_segment_start_ms', 'g_progress_segment_duration_ms', 'sample_interval_ms'):
    assert tok in update, tok
assert 'g_motion_sample_speed_mps' not in T
assert 'target +=' not in smooth
assert 'float t = constrain(float(elapsed) / float(duration)' in smooth
assert '(g_motion_sample_frac - g_progress_segment_start_frac) * t' in smooth
assert 'g_speed_mps > 0.03f && next_frac < g_progress_segment_start_frac' in update
assert 'g_speed_mps < -0.03f && next_frac > g_progress_segment_start_frac' in update

# 2) Ramping is based on zone occupancy even at zero speed; Near/Far remain more specific.
zone=B[B.index('def _normal_motion_zone_status'):B.index('def _resolved_system_status')]
assert 'near_d <= LIMIT_STATUS_DISTANCE_M' in zone and 'far_d <= LIMIT_STATUS_DISTANCE_M' in zone
assert 'in_near_ramp' in zone and 'in_far_ramp' in zone
assert 'if in_near_ramp or in_far_ramp:' in zone
assert 'abs(motion)' not in zone and 'last_sent_vel' not in zone
assert 'return "System | Ramping"' in zone

# 3) Encoder mode remains the physical default and the W1P/EL7 Modbus path stays fully armed only through safety gates.
assert 'self.position_source = "Encoder"' in B
assert 'if "POS_M" in fields and self.position_source != "Virtual"' in B
assert 'if "VEL_MPS" in fields and self.position_source != "Virtual"' in B
for tok in (
    'EDGEBOX_RS485_TX = 17', 'EDGEBOX_RS485_RX = 18', 'EDGEBOX_RS485_RTS = 8',
    'RS485_BAUD = 115200', 'SERIAL_8N1', 'UART_MODE_RS485_HALF_DUPLEX',
    'DRIVE_MODBUS_ID = 1', 'REG_CONTROL_MODE = 0x0003', 'EXPECTED_CONTROL_MODE = 6',
    'REG_PR_CONTROL = 0x6002', 'REG_MOTOR_POSITION_H = 0x602C',
    'REG_INPUT_IO_STATUS = 0x602E', 'REG_OUTPUT_IO_STATUS = 0x602F',
    'REG_PR0_MODE = 0x6200', 'REG_PR0_VELOCITY = 0x6203',
    'REG_PR0_ACCEL = 0x6204', 'REG_PR0_DECEL = 0x6205',
    'PR_MODE_VELOCITY = 0x0002', 'PR_TRIGGER_PATH0 = 0x0010',
    'W1P_VEL_COMMAND_TIMEOUT_MS = 500', 'serviceAutomaticDriveEnable()',
    'driveWriteVelocityCommandMps(g.vel_cmd_mps)'):
    assert tok in W, tok
assert 'g.drive_feedback_ok' in W and 'g.communication_config_ok' in W and 'g.rs_link_ok' in W
assert 'SET_UNITS_PER_M' in B and 'SET_MOTOR_REVERSE' in B and 'SET_LIMIT_NEAR' in B and 'SET_LIMIT_FAR' in B
print('BENCH_REGRESSION_0608_PASS')
