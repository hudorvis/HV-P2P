#!/usr/bin/env python3
"""Exercise the SRVR link log as real Python without requiring PySide in CI.

The two exact production method bodies are extracted from backend AST, so this
also runs on headless source-audit runners that cannot import PySide6.
"""
import ast
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "SRVR_GitHub_v26.10.16.02" / "backend.py"
source = BACKEND.read_text(encoding="utf-8")
module = ast.parse(source)
cls = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "HVP2PBackend")
methods = {}
for name in ("_connection_log_snapshot", "_service_connection_log", "_log_link_batch"):
    node = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
    methods[name] = textwrap.dedent(ast.get_source_segment(source, node))

class Clock:
    t = 0.0
    def time(self): return self.t
    def monotonic(self): return self.t

clock = Clock()
namespace = {"time": clock}
for body in methods.values():
    exec(compile(body, str(BACKEND), "exec"), namespace)

class Fake:
    _connection_log_snapshot = namespace["_connection_log_snapshot"]
    _service_connection_log = namespace["_service_connection_log"]
    def __init__(self):
        self.version = "26.10.16.02"
        self.ctrl_ip = "172.20.1.101"
        self.w1p_ip = "172.20.1.102"
        self.w1p_port = 5000
        self.ctrl = False
        self.w1p = type("W", (), {"connected": False})()
        self.w1p_fresh = False
        self.rs485Connected = False
        self.ctrlTsConnected = False
        self.ctrlTsRs485Active = False
        self._ctrl_fw_match = False
        self._ctrl_fw_version = ""
        self._ctrl_fw_authority = "unknown"
        self._w1p_fw_match = False
        self._w1p_fw_version = ""
        self._w1p_fw_authority = "unknown"
        self.joystick = False
        self.hmi = False
        self.freed_input_enabled = False
        self.freed_input_last_rx = 0.0
        self.lines = []
        self.batch_count = 0
        self._link_log_started_at = clock.monotonic()
        self._link_log_last_poll = 0.0
        self._link_log_observed = {}
        self._link_log_published = {}
        self._link_log_boot_done = False
        self._link_log_startup_grace_s = 3.0
        self._link_log_transition_debounce_s = 0.75
    def _ctrl_connected(self): return self.ctrl
    def _w1p_status_fresh(self): return self.w1p_fresh
    def _ctrl_authority_fresh(self): return self.hmi
    def _joystick_input_connected(self): return self.joystick
    def _log(self, line): self.lines.append(line)
    def _log_link_batch(self, lines):
        if not lines: return
        self.batch_count += 1
        self.lines.extend(lines)

# Frozen-app smoke uses force=True before the normal 3s discovery grace;
# it must produce a concrete link entry rather than silently skipping.
smoke = Fake()
clock.t = 0.1
smoke._service_connection_log(force=True)
assert any("CTRL UDP: FAULT" in l for l in smoke.lines)

b = Fake()
clock.t = 0.26
b._service_connection_log()
assert not b.lines, b.lines  # no false boot-time red lights
clock.t = 3.4
b._service_connection_log()
assert any("CTRL UDP: FAULT" in l for l in b.lines)
assert any("W1P UDP: FAULT" in l for l in b.lines)
assert any("EL7 RS485: UNVERIFIED" in l for l in b.lines)
assert any("CTRL-TS: OFFLINE" in l and "optional HMI" in l for l in b.lines)
assert any("Startup discovery complete" in l for l in b.lines)
initial_count = len(b.lines)
clock.t = 10.0
b._service_connection_log()
assert len(b.lines) == initial_count, "Steady offline status should not flood logs"
assert b.batch_count == 1, "Entire startup snapshot should cause one Log-page refresh"

b.ctrl = True
b.hmi = True
b.joystick = True
b._ctrl_fw_match = True
b._ctrl_fw_version = "v26.10.16.02"
b.w1p.connected = True
b.w1p_fresh = True
b._w1p_fw_match = True
b._w1p_fw_version = "v26.10.16.02"
b.rs485Connected = True
b.ctrlTsRs485Active = True
clock.t = 10.3
b._service_connection_log()
assert any("CTRL UDP: ACTIVE" in l for l in b.lines)
assert any("W1P UDP: ACTIVE" in l for l in b.lines)
assert any("EL7 RS485: ACTIVE" in l for l in b.lines)
clock.t = 11.1
b._service_connection_log()
assert any("CTRL-TS: DEGRADED" in l for l in b.lines)
assert not b.ctrlTsConnected
assert any("CTRL firmware: MATCHED" in l for l in b.lines)
assert any("W1P firmware: MATCHED" in l for l in b.lines)

# A drive alarm/configuration mismatch must NOT make the transport go red.
b._w1p_fw_match = False
b._w1p_fw_version = "v26.10.11.02"
clock.t = 11.5
b._service_connection_log()
clock.t = 12.5
b._service_connection_log()
assert any("W1P firmware: MISMATCH" in l for l in b.lines)
assert b._link_log_published["EL7 RS485"] == "ACTIVE"

# One short transport dropout should not be logged; a sustained outage should.
b.rs485Connected = False
clock.t = 13.0
b._service_connection_log()
clock.t = 13.3
b._service_connection_log()
assert b._link_log_published["EL7 RS485"] == "ACTIVE"
b.rs485Connected = True
clock.t = 13.6
b._service_connection_log()
clock.t = 14.2
b._service_connection_log()
assert b._link_log_published["EL7 RS485"] == "ACTIVE"
b.rs485Connected = False
clock.t = 15.0
b._service_connection_log()
clock.t = 16.0
b._service_connection_log()
assert b._link_log_published["EL7 RS485"] == "FAULT"
b.rs485Connected = True
clock.t = 16.3
b._service_connection_log()
assert b._link_log_published["EL7 RS485"] == "ACTIVE"

# The feature must remain presentation-only, on Qt after display-build stage.
tick = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_tick")
tick_src = ast.get_source_segment(source, tick)
assert tick_src.index("self._send_controller_display_packet()") < tick_src.index("self._service_connection_log()")
for method in ("_motion_tick", "_estop_status_text", "_send_velocity"):
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method)
    txt = ast.get_source_segment(source, fn)
    assert "_link_log_" not in txt and "_service_connection_log" not in txt
assert "self.logChanged.emit()" not in methods["_connection_log_snapshot"]
assert "self._service_connection_log()" not in methods["_connection_log_snapshot"]
assert len(b.lines) < 45, "Transition monitoring must remain bounded"
assert b.batch_count <= 9, "Steady connection state must not generate repeated UI signals"

# Exercise the ACTUAL production batch implementation with a lightweight Qt
# signal substitute. One startup burst must produce one logChanged emission,
# retaining both saved-text lines and structured Log filters.
from collections import deque
from datetime import datetime
import threading
import time as real_time
namespace.update({"datetime": datetime, "time": real_time})
exec(compile(methods["_log_link_batch"], str(BACKEND), "exec"), namespace)
class SignalStub:
    def __init__(self): self.emits = 0
    def emit(self): self.emits += 1
class LogStub:
    _log_link_batch = namespace["_log_link_batch"]
    def __init__(self):
        self._lock = threading.RLock()
        self._logs = deque(maxlen=1200)
        self._log_entries = deque(maxlen=1200)
        self._log_revision = 0
        self.logChanged = SignalStub()
    def _classify_log_message(self, message):
        return ("FAULT" if "FAULT" in message else "INFO", "SYSTEM", "Network", message)
logger = LogStub()
logger._log_link_batch(["[LINK] CTRL UDP: FAULT", "[LINK] W1P UDP: ACTIVE"])
assert len(logger._logs) == 2 and len(logger._log_entries) == 2
assert logger._log_revision == 2 and logger.logChanged.emits == 1
assert logger._log_entries[0]["view"] == "Network"
logger._log_link_batch([])
assert logger.logChanged.emits == 1, "No notification for empty transition batch"
print("SRVR STARTUP CONNECTION / TRANSITION LOGGING PASS", len(b.lines), "messages")
