#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / 'SRVR_GitHub_v26.10.06.09' / 'tools' / 'test_backend_logic.py'
text = TEST.read_text()

active_assert = 'assert b.systemStatusLevel == 0 and b.systemReady and b.bannerText == "System | Active"'
pos = text.find(active_assert)
assert pos >= 0, 'primary System | Active runtime assertion missing'
window = text[max(0, pos - 900):pos]
for required in (
    'b.state.near_limit.position_m = 0.0',
    'b.state.far_limit.position_m = 100.0',
    'b.state.pos_m = 50.0',
    'b.current_speed_mps = 0.0',
    'b.last_sent_vel = 0.0',
):
    assert required in window, f'Active runtime fixture does not explicitly reset {required}'

print('BACKEND_STATUS_FIXTURE_CONTRACT_0606_PASS')
