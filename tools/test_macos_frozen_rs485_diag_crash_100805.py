#!/usr/bin/env python3
"""Source/frozen-smoke contract for the v26.10.08.04 macOS Intel crash."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = (ROOT / 'SRVR_GitHub_v26.10.11.02' / 'backend.py').read_text()
MAIN = (ROOT / 'SRVR_GitHub_v26.10.11.02' / 'main.py').read_text()

# The .08.04 diagnostic signature used direct bool.__str__ special-method calls
# immediately before the huge compiled DSP1 builder. Keep the frozen path to
# primitive literals and defer Qt logging until after DSP1 construction.
assert 'fb_ok.__str__()' not in BACKEND
assert 'pos_ok.__str__()' not in BACKEND
assert 'io_ok.__str__()' not in BACKEND
assert 'ready.__str__()' not in BACKEND
assert 'srdy.__str__()' not in BACKEND
assert 'self._pending_w1p_rs485_log = ""' in BACKEND
assert 'pending_rs485_log = self._pending_w1p_rs485_log' in BACKEND
assert BACKEND.index('self._send_controller_display_packet()') < BACKEND.index('pending_rs485_log = self._pending_w1p_rs485_log')

# The packaged PySide/Nuitka smoke test must execute the exact sequence that was
# missing from .08.04 CI: RS485 diagnostic reduction -> repeated DSP1 builds.
assert 'Frozen-runtime regression for the macOS Intel v26.10.08.04/.08.05' in MAIN
assert 'backend._log_w1p_rs485_diagnostics(rs485_fixture)' in MAIN
assert 'for index in range(200):' in MAIN
assert 'packet = backend._build_controller_display_packet()' in MAIN
assert 'DSP1 frozen-runtime regression packet invalid' in MAIN

assert 'faulthandler.enable(all_threads=True)' in MAIN
assert 'SMOKE PHASE:' in MAIN
print('MACOS_FROZEN_RS485_DIAG_CRASH_100805_PASS')
