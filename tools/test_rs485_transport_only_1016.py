"""RS485 UI indicator is physical Modbus link, without motion gate regression."""
import ast
from pathlib import Path
root = Path(__file__).resolve().parents[1]
src = (root / "SRVR_GitHub_v26.10.16.02" / "backend.py").read_text()
mod = ast.parse(src)
cls = next(n for n in mod.body if isinstance(n, ast.ClassDef) and n.name == "HVP2PBackend")
prop = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "rs485Connected")
body = ast.get_source_segment(src, prop)
assert "_w1p_rs485_transport_active" in body
assert "_w1p_status_fresh()" in body
assert "winch_rs_status" not in body and "_w1p_fw_match" not in body
assert "self._w1p_rs485_transport_active = rs in" in src
assert 'self._w1p_rs485_transport_active = False' in src
for method in ("_motion_tick", "_estop_status_text"):
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method)
    text = ast.get_source_segment(src, fn)
    assert 'winch_rs_status != "Connected"' in text
    assert '_w1p_rs485_transport_active' not in text
qml = (root / "SRVR_GitHub_v26.10.16.02" / "qml/pages/SetupPage.qml").read_text()
assert 'backend.rs485Connected?"Active":"Disconnected"' in qml
print('RS485 TRANSPORT-ONLY DISPLAY CONTRACT PASS')
