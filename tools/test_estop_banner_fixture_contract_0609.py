#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / 'SRVR_GitHub_v26.10.08.03' / 'tools' / 'test_backend_logic.py'
text = TEST.read_text()

ctrl_assert = 'assert b.bannerText == "E-Stop | CTRL", b.bannerText'
w1p_assert = 'assert b.bannerText == "E-Stop | W1P", b.bannerText'
both_assert = 'assert b.bannerText == "E-Stop | CTRL & W1P", b.bannerText'
for marker in (ctrl_assert, w1p_assert, both_assert):
    assert marker in text, f'missing canonical E-stop runtime assertion: {marker}'

pos = text.index(ctrl_assert)
window = text[max(0, pos - 1200):pos]
assert 'healthy_ctrl_status(); healthy_w1p_status()' in window, \
    'CTRL-only E-stop fixture must begin from fully healthy validated CTRL/W1P state'
assert 'b._ctrl_rx_times.clear()' in window, \
    'CTRL-only E-stop fixture must explicitly simulate CTRL link loss'

wpos = text.index(w1p_assert)
w1p_window = text[max(0, wpos - 700):wpos]
assert 'healthy_ctrl_status()' in w1p_window, \
    'W1P-only E-stop fixture must explicitly restore healthy CTRL state'
assert 'b.w1p.last_seen = 0.0' in w1p_window, \
    'W1P-only E-stop fixture must explicitly simulate W1P loss'

print('ESTOP_BANNER_FIXTURE_CONTRACT_0609_PASS')
