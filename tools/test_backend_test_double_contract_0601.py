#!/usr/bin/env python3
"""Guard production/test-double interface parity for updater-order W1P calls."""
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VER = '26.10.06.06'
backend_path = ROOT / f'SRVR_GitHub_v{VER}' / 'backend.py'
test_path = ROOT / f'SRVR_GitHub_v{VER}' / 'tools' / 'test_backend_logic.py'
backend = backend_path.read_text(encoding='utf-8')
test_src = test_path.read_text(encoding='utf-8')

# The production gate relies on this interface. If it changes, the regression
# test double must change in the same revision so PySide CI cannot fail later.
required = {'firmware_snapshot', 'send', 'arm_velocity_refresh', 'renew_velocity_refresh_from_controller', 'clear_velocity_refresh', 'reconfigure', 'close'}
assert 'self.w1p.firmware_snapshot()' in backend, 'production W1P snapshot gate missing'

tree = ast.parse(test_src, filename=str(test_path))
fakes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == 'FakeW1P']
assert len(fakes) == 1, f'expected exactly one FakeW1P, found {len(fakes)}'
fake = fakes[0]
methods = {n.name for n in fake.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
missing = required - methods
assert not missing, f'FakeW1P missing production interface: {sorted(missing)}'

# Ensure the fake snapshot is deliberately current/matched rather than an
# arbitrary stub, because the surrounding test is about DSP/AUX transport and
# must not accidentally exercise the update-order denial path.
seg = ast.get_source_segment(test_src, fake) or ''
for token in ('self.last_seen', 'self.host', 'self.port', '_fw_snapshot', 'matched', 'time.monotonic()', 'def firmware_snapshot'):
    assert token in seg, f'FakeW1P firmware snapshot contract missing {token!r}'

print('BACKEND_TEST_DOUBLE_CONTRACT_0601_PASS')
