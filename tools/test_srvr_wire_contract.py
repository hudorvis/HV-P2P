#!/usr/bin/env python3
from pathlib import Path
import ast, struct
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'SRVR_GitHub_v26.08.31.10'/'backend.py'
src=path.read_text()
tree=ast.parse(src)
func=None
for n in ast.walk(tree):
    if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='_parse_control_packet':
        func=n; break
if func is None: raise SystemExit('FAIL: _parse_control_packet not found')
# Remove decorators/indent context and execute the actual function body standalone.
func.decorator_list=[]
mod=ast.Module(body=[ast.Import(names=[ast.alias(name='struct')]),func],type_ignores=[])
ast.fix_missing_locations(mod)
ns={'CONTROL_PACKET_CODE':0xA6}
exec(compile(mod,str(path),'exec'),ns,ns)
parse=ns['_parse_control_packet']
for axis,flags in [(-1.0,0x0010),(0.0,0x0000),(0.375,0x0410),(1.0,0x0400)]:
    pkt=bytes([0xA7,(flags>>8)&255,flags&255])+struct.pack('!f',axis)+b'\x00\x00\x00'
    got=parse(pkt)
    assert got is not None
    gf,ga=got
    assert gf==flags,(gf,flags)
    assert abs(ga-axis)<1e-6,(ga,axis)
# Clamp test is part of existing safety contract.
pkt=bytes([0xA7,0,0])+struct.pack('!f',5.0)+b'\x00\x00\x00'
assert parse(pkt)==(0,1.0)
# Malformed packets must fail closed at parser level.
assert parse(b'') is None
assert parse(b'\xA7\x00') is None
print('SRVR_WIRE_CONTRACT_PASS: actual _parse_control_packet accepts EdgeBox A7 16-bit flags / network-order float')
