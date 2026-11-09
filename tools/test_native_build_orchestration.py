#!/usr/bin/env python3
from pathlib import Path
import importlib.util, tempfile, hashlib, json
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'tools/native_build_firmware.py'
spec=importlib.util.spec_from_file_location('nbf',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
text=p.read_text()
for tok in ('source_snapshot(root)','source checkout','SRVR_FIRMWARE_BUNDLE','make_firmware_bundle','HV_P2P_FW_TARGET={target}','STAGED_SOURCE','PYTHONDONTWRITEBYTECODE'):
    assert tok in text,tok
with tempfile.TemporaryDirectory() as td:
    d=Path(td); c=d/'c.bin'; w=d/'w.bin'; p=d/'p.bin'; out=d/'bundle'
    c.write_bytes(b'\xe9CTRL'); w.write_bytes(b'\xe9W1P'); p.write_bytes(b'\xe9PDM')
    doc=m.make_firmware_bundle(c,w,p,out)
    assert set(doc['images'])=={'ctrl','w1p','pdm'} and doc['release']=='v26.11.09.04'
    assert (out/'ctrl.bin').read_bytes()==b'\xe9CTRL' and (out/'w1p.bin').read_bytes()==b'\xe9W1P'
    assert (out/'pdm.bin').read_bytes()==b'\xe9PDM'
    assert doc['images']['pdm']['target']=='OLIMEX_ESP32_POE_ISO'
    assert doc['bundle_id']==m.bundle_id_for(doc['release'], doc['images']['ctrl']['sha256'], doc['images']['w1p']['sha256'])
    for key in ('ctrl','w1p','pdm'):
        meta=doc['images'][key]; data=(out/meta['file']).read_bytes()
        assert meta['size']==len(data) and meta['sha256']==hashlib.sha256(data).hexdigest()
print('NATIVE_BUILD_ORCHESTRATION_PASS')
