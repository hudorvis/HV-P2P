#!/usr/bin/env python3
"""Regression guard for v26.10.11.02 frozen desktop runtime hardening."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
SRVR = ROOT / "SRVR_GitHub_v26.10.11.02"
BACKEND_PATH = SRVR / "backend.py"
MAIN_PATH = SRVR / "main.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "complete-build.yml"

backend = BACKEND_PATH.read_text(encoding="utf-8")
main = MAIN_PATH.read_text(encoding="utf-8")
workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
requirements = (SRVR / "requirements.txt").read_text(encoding="utf-8")

# Reproducible compiler/runtime line. The .08.05 job proved that allowing
# pyside6-deploy to silently fetch a newer Nuitka can turn a source-clean build
# into a native SIGSEGV.
assert requirements.splitlines() == ["PySide6==6.11.1", "Nuitka==4.2.2"]
assert workflow.count("python-version: '3.12.10'") >= 3
assert "assert importlib.metadata.version('Nuitka') == '4.2.2'" in workflow
assert "Pinned Nuitka survived macOS freeze" in workflow
assert "pysidedeploy.spec did not retain pinned Nuitka 4.2.2" in workflow

# Smoke tests exercise persistence aggressively; they must use a private temp
# directory rather than the operator's real Application Support/config path.
assert 'tempfile.mkdtemp(prefix="hvp2p-srvr-smoke-")' in backend
assert '_process_smoke_data_dir()' in backend
assert 'atexit.register(shutil.rmtree, _SMOKE_DATA_DIR, ignore_errors=True)' in backend
assert 'shutil.rmtree(self._smoke_config_dir, ignore_errors=True)' not in backend

# The Apple crash stack was in the huge DSP1 builder. No function/lambda may be
# created inside another backend function; this keeps closure-generated compiled
# frames out of all hot Qt/network/property paths, not just the first crash site.
tree = ast.parse(backend, filename=str(BACKEND_PATH))
parents = {}
for node in ast.walk(tree):
    for child in ast.iter_child_nodes(node):
        parents[child] = node

nested = []
for node in ast.walk(tree):
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        continue
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            nested.append((getattr(node, "lineno", -1), getattr(node, "name", "<lambda>")))
            break
        cur = parents.get(cur)
assert not nested, f"nested backend callables reintroduced: {nested}"

builder = backend.split("def _build_controller_display_packet", 1)[1].split("\n    def ", 1)[0]
assert "def _cal_value" not in builder
assert "def _joy_cal_value" not in builder
assert "_cal_value(" not in builder
assert "_joy_cal_value(" not in builder

# Frozen smoke must report native phase progress, stress the exact DSP1 path,
# and make Apple crash reports visible in Actions if a native failure returns.
assert "faulthandler.enable(all_threads=True)" in main
assert "for index in range(200):" in main
assert 'SMOKE PHASE:' in main
assert 'backend._log_w1p_rs485_diagnostics(rs485_fixture)' in main
assert 'backend._build_controller_display_packet()' in main
assert "PYTHONFAULTHANDLER=1" in workflow
assert "recent Apple crash reports" in workflow
assert "SMOKE_RC=${PIPESTATUS[0]}" in workflow
assert "ROUNDTRIP_SMOKE_RC=${PIPESTATUS[0]}" in workflow

print("MACOS_FROZEN_RUNTIME_HARDENING_101102_PASS")
