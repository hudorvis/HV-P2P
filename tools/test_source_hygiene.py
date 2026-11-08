#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
forbidden_ext={'.bin','.exe','.pyc'}
forbidden_dir={'__pycache__','NATIVE_BUILD_ARTIFACTS','HVP2P_NATIVE_BUILD_ARTIFACTS','build','dist','PREVIEWS','REFERENCE_ONLY'}
bad=[]
for p in ROOT.rglob('*'):
    rel=p.relative_to(ROOT)
    if any(part in forbidden_dir for part in rel.parts): bad.append(str(rel)); continue
    if p.is_file() and (p.suffix.lower() in forbidden_ext or p.name.endswith('.app')): bad.append(str(rel))
assert not bad, f'generated/forbidden source artifacts: {bad[:30]}'
print('SOURCE_HYGIENE_PASS')
