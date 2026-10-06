#!/usr/bin/env python3
from pathlib import Path
import importlib.util, tempfile, hashlib, json
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'tools/native_build_firmware.py'
spec=importlib.util.spec_from_file_location('nbf',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
text=p.read_text()
for tok in ('source_snapshot(root)','source checkout','SRVR_FIRMWARE_BUNDLE','make_firmware_bundle','HV_P2P_FW_TARGET={EDGEBOX_TARGET}','STAGED_SOURCE','PYTHONDONTWRITEBYTECODE'):
    assert tok in text,tok
with tempfile.TemporaryDirectory() as td:
    d=Path(td); c=d/'c.bin'; w=d/'w.bin'; out=d/'bundle'
    c.write_bytes(b'\xe9CTRL'); w.write_bytes(b'\xe9W1P')
    doc=m.make_firmware_bundle(c,w,out)
    assert set(doc['images'])=={'ctrl','w1p'} and doc['release']=='v26.10.06.03'
    assert (out/'ctrl.bin').read_bytes()==b'\xe9CTRL' and (out/'w1p.bin').read_bytes()==b'\xe9W1P'
    for key in ('ctrl','w1p'):
        meta=doc['images'][key]; data=(out/meta['file']).read_bytes()
        assert meta['size']==len(data) and meta['sha256']==hashlib.sha256(data).hexdigest()
print('NATIVE_BUILD_ORCHESTRATION_PASS')
