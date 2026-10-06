#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.06.03'
p=ROOT/f'HV_P2P_CTRL_TS_v{VER}/HV_P2P_CTRL_TS_v{VER}.ino'
s=p.read_text(errors='replace')
assert 'static HVP2PRS485::Parser g_rs485Parser;' in s
assert 'g_rs485Parser.crcErrors()' in s
assert 'g_rs485Parser.resyncs()' in s
assert 'g_hmiParser.crcErrors()' not in s
assert 'g_hmiParser.resyncs()' not in s
print('CTRL_TS_PARSER_DIAGNOSTICS_CONTRACT_PASS')
