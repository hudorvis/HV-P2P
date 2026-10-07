#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, sys, tempfile, urllib.request
ROOT=Path(__file__).resolve().parents[1]
SRVR=ROOT/'SRVR_GitHub_v26.10.06.11'
sys.path.insert(0,str(SRVR))
from firmware_authority import FirmwareBundle, FirmwareAuthorityError, FirmwareAuthorityServer, SCHEMA, AUTHORITY

REL='v26.10.06.11'
def sha(b): return hashlib.sha256(b).hexdigest()
def make_bundle(root:Path):
    ctrl=b'\xe9CTRL_TEST_IMAGE'; w1p=b'\xe9W1P_TEST_IMAGE'
    (root/'ctrl.bin').write_bytes(ctrl); (root/'w1p.bin').write_bytes(w1p)
    bid=hashlib.sha256(f'{REL}\nCTRL={sha(ctrl)}\nW1P={sha(w1p)}\n'.encode()).hexdigest()
    doc={'schema':SCHEMA,'authority':AUTHORITY,'bundle_id':bid,'release':REL,'images':{
      'ctrl':{'file':'ctrl.bin','role':'CTRL','target':'EDGEBOX_ESP100','version':REL,'size':len(ctrl),'sha256':sha(ctrl)},
      'w1p':{'file':'w1p.bin','role':'W1P','target':'EDGEBOX_ESP100','version':REL,'size':len(w1p),'sha256':sha(w1p)}}}
    (root/'manifest.json').write_text(json.dumps(doc))
    return ctrl,w1p
with tempfile.TemporaryDirectory() as td:
    d=Path(td); ctrl,w1p=make_bundle(d)
    b=FirmwareBundle(d,REL); assert b.images['ctrl'].sha256==sha(ctrl)
    srv=FirmwareAuthorityServer(REL,host='127.0.0.1',port=0,bundle_dir=d); srv.start()
    try:
      base=f'http://127.0.0.1:{srv.port}'
      m=json.loads(urllib.request.urlopen(base+'/firmware/ctrl/manifest',timeout=2).read())
      assert m['schema']==SCHEMA and m['role']=='CTRL' and m['target']=='EDGEBOX_ESP100' and m['version']==REL
      assert urllib.request.urlopen(base+'/firmware/ctrl/image',timeout=2).read()==ctrl
      assert urllib.request.urlopen(base+'/firmware/w1p/image',timeout=2).read()==w1p
    finally: srv.close(); srv.close()
    (d/'ctrl.bin').write_bytes(ctrl+b'X')
    try: FirmwareBundle(d,REL)
    except FirmwareAuthorityError: pass
    else: raise AssertionError('tampered CTRL image accepted')
print('SRVR_AUTHORITY_SERVER_PASS')
