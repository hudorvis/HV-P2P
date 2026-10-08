#!/usr/bin/env python3
"""Source contract for the startup safety vs. uncalibrated runtime regression."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
backend = (ROOT / 'SRVR_GitHub_v26.10.08.02' / 'backend.py').read_text()
test = (ROOT / 'SRVR_GitHub_v26.10.08.02' / 'tools' / 'test_backend_logic.py').read_text()
# Production must remain fail-safe until live safety evaluation runs.
assert 'estop_active: bool = True' in backend
# E-stop/fault status must retain priority over yellow service/unreferenced states.
resolver = backend[backend.index('def _resolved_system_status'):backend.index('def _ctrl_ts_update_allowed')]
assert 'if self.state.estop_active:' in resolver
assert resolver.index('if self.state.estop_active:') < resolver.index('if self._not_calibrated:')
# The fresh-backend persistence regression must isolate the synthetic startup
# safety latch before asking for the yellow Uncalibrated banner.
needle = 'b2 = HVP2PBackend(version="26.10.08.02", smoke_test=True)'
start = test.index(needle)
block = test[start:start+900]
assert 'assert b2._not_calibrated' in block
assert 'b2.state.estop_active = False' in block
assert 'assert b2.bannerText == "System | Uncalibrated"' in block
assert block.index('b2.state.estop_active = False') < block.index('assert b2.bannerText == "System | Uncalibrated"')
print('BACKEND_STATUS_RUNTIME_CONTRACT_0502_PASS')
