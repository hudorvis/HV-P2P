#!/usr/bin/env python3
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.05.08'; SEM='v'+VER
must=[
 ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}/HV_P2P_CTRL_EDGEBOX_v{VER}.ino',
 ROOT/f'HV_P2P_CTRL_TS_v{VER}/HV_P2P_CTRL_TS_v{VER}.ino',
 ROOT/f'HV_P2P_W1P_EDGEBOX_v{VER}/HV_P2P_W1P_EDGEBOX_v{VER}.ino',
 ROOT/f'SRVR_GitHub_v{VER}/main.py', ROOT/'.github/workflows/complete-build.yml']
for p in must: assert p.is_file(),p
texts='\n'.join(p.read_text(errors='replace') for p in must)
assert VER in texts and SEM in texts
# No active source path should claim a later/earlier release as its current APP/FW version.
for p in ROOT.rglob('*'):
    if not p.is_file() or p.suffix.lower() in {'.png','.ico','.zip'}: continue
    t=p.read_text(errors='ignore')
    if 'APP_VERSION =' in t or 'FW_VERSION =' in t or 'VER = ' in t:
        # permit historical prose only outside executable source/tools
        if p.suffix in {'.py','.ino'}:
            assert VER in t, f'active version mismatch {p}'
print('RELEASE_CONSISTENCY_PASS')
