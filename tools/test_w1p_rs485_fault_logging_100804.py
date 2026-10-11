#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B=(ROOT/'SRVR_GitHub_v26.10.08.04'/'backend.py').read_text()
W=(ROOT/'HV_P2P_W1P_EDGEBOX_v26.10.08.04'/'HV_P2P_W1P_EDGEBOX_v26.10.08.04.ino').read_text()

# Established project framing is restored, while the factory framing remains a
# read-only stopped diagnostic probe only.
for tok in (
    'RS485_BAUD = 115200',
    'DriveSerial.begin(RS485_BAUD, SERIAL_8N1',
    'probing EL7 factory 38400 8N2 read-only',
    'startDriveSerialConfig(38400, SERIAL_8N2)',
    'startDriveSerialConfig(RS485_BAUD, SERIAL_8N1)',
    'EXPECTED_RS485_MODE = 4',
    'EXPECTED_RS485_BAUD_CODE = 6',
    'g_factoryCommsDetected = false;',
):
    assert tok in W, tok

# SRVR must turn W1P evidence into operator/saved-log diagnostics, not merely a
# generic red Disconnected state. Logging is transition keyed to avoid 20 Hz spam.
for tok in (
    'self._w1p_rs485_diag_signature = ""',
    'def _log_w1p_rs485_diagnostics(self, fields: dict)',
    'if signature == self._w1p_rs485_diag_signature:',
    'self._log_w1p_rs485_diagnostics(fields)',
    '[W1P RS485] FAULT: no valid EL7 Modbus reply at 115200 8N1',
    'W1P DID receive a valid ',
    'read-only reply at the EL7 factory 38400 8N2 setting',
    '[W1P RS485] FAULT: physical Modbus link is connected, but EL7 configuration mismatch',
    '[W1P RS485] FAULT: Modbus link/configuration are valid but drive ',
    'feedback is not ready:',
    '[W1P RS485] Connected: EL7 verified at 115200 8N1 / slave 1',
):
    assert tok in B, tok

# Ensure the detailed messages are classified into the existing W1P/network log
# path by using the [W1P ...] tag and the word FAULT where appropriate.
assert 'elif "W1P" in tag_u:' in B
print('W1P_RS485_FAULT_LOGGING_100804_PASS')

# Exercise the exact helper without importing PySide6: extract the method AST and
# bind it to a tiny dummy object exposing only _log + the signature state.
import ast
module = ast.parse(B)
backend_cls = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == 'HVP2PBackend')
method = next(n for n in backend_cls.body if isinstance(n, ast.FunctionDef) and n.name == '_log_w1p_rs485_diagnostics')
method_module = ast.Module(body=[method], type_ignores=[])
ast.fix_missing_locations(method_module)
ns = {}
exec(compile(method_module, '<w1p-rs485-diag>', 'exec'), ns)

class Dummy:
    _w1p_rs485_diag_signature = ''
    def __init__(self): self.logs = []
    def _log(self, msg): self.logs.append(msg)
Dummy._log_w1p_rs485_diagnostics = ns['_log_w1p_rs485_diagnostics']

def sample(**kw):
    d = {
        'RS_STAT':'FAULT','LEAD_CFG':'READ_FAULT','FACTORY_COMMS':'0',
        'MODBUS':'0','POS_READ':'0','IO_READ':'0','READY':'0','SRDY':'0',
        'MB_EX':'0','RS_FAIL_SEQ':'2','RS_FMT':'65535','RS_BAUD':'65535',
        'RS_ID':'65535','CTRL_MODE':'65535','DI1_ASSIGN':'65535',
        'DO2_ASSIGN':'65535','DO3_ASSIGN':'65535','DO4_ASSIGN':'65535','DO5_ASSIGN':'65535',
    }
    d.update({k:str(v) for k,v in kw.items()})
    return d

d = Dummy()
d._log_w1p_rs485_diagnostics(sample())
d._log_w1p_rs485_diagnostics(sample())  # identical 20 Hz status must not spam
d._log_w1p_rs485_diagnostics(sample(FACTORY_COMMS=1))
d._log_w1p_rs485_diagnostics(sample(RS_STAT='CONNECTED',LEAD_CFG='MISMATCH',MODBUS=1,POS_READ=1,IO_READ=1,READY=1,SRDY=1,RS_FMT=5,RS_BAUD=4,RS_ID=1,CTRL_MODE=6,DI1_ASSIGN=131,DO2_ASSIGN=2,DO3_ASSIGN=18,DO4_ASSIGN=3,DO5_ASSIGN=1))
d._log_w1p_rs485_diagnostics(sample(RS_STAT='CONNECTED',LEAD_CFG='OK',MODBUS=1,POS_READ=1,IO_READ=1,READY=1,SRDY=1,RS_FMT=4,RS_BAUD=6,RS_ID=1,CTRL_MODE=6,DI1_ASSIGN=131,DO2_ASSIGN=2,DO3_ASSIGN=18,DO4_ASSIGN=3,DO5_ASSIGN=1))
assert len(d.logs) == 4, d.logs
assert 'no valid EL7 Modbus reply at 115200 8N1' in d.logs[0]
assert 'factory 38400 8N2' in d.logs[1]
assert 'P05.29=4 / 8N1 (reported 5)' in d.logs[2]
assert 'P05.30=6 / 115200 (reported 4)' in d.logs[2]
assert '[W1P RS485] Connected:' in d.logs[3]
print('W1P_RS485_FAULT_LOGGING_RUNTIME_PASS')
