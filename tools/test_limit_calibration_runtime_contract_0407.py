#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
B = (ROOT / 'SRVR_GitHub_v26.10.06.05' / 'backend.py').read_text()
T = (ROOT / 'SRVR_GitHub_v26.10.06.05' / 'tools' / 'test_backend_logic.py').read_text()

# Backend must refuse delayed/duplicate confirmation after any wizard closes.
needle = '''    def calibrationNext(self):\n        # Calibration confirmation is edge/event driven from both SRVR and\n'''
assert needle in B, 'calibrationNext post-close guard/comment missing'
block = B[B.index('    def calibrationNext(self):'):B.index('    @Slot()\n    def calibrationBack', B.index('    def calibrationNext(self):'))]
assert 'if not self.calibration_open:\n            return' in block, 'closed calibration can still consume a late Confirm'

# Limit Calibration is zero-based 0/1/2 and completes on Ref. The PySide6
# runtime regression must not resurrect the obsolete fourth Done step.
assert 'assert b.calibration_step == 3' not in T, 'runtime test still expects obsolete Limit step 3'
assert 'b.calibrationNext()  # Done\n    assert not b.calibration_open' not in T, 'runtime test still sends obsolete fourth Limit Done confirmation'
assert T.count('b.calibrationNext()  # Ref & Done') >= 2, 'runtime test does not cover three-step Ref completion in both scenarios'
assert T.count('assert b.calibration_step == 2 and not b.calibration_open') >= 2, 'runtime test does not assert terminal step 2/closed state'
assert 'Duplicate/late confirmation must not recapture Ref.' in T, 'runtime test lacks late-confirm reference immutability check'

print('LIMIT_CALIBRATION_RUNTIME_CONTRACT_0407_PASS')
