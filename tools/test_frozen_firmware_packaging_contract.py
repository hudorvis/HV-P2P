#!/usr/bin/env python3
"""Source-level guard for the frozen SRVR firmware bundle packaging contract."""
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WF = (ROOT / ".github/workflows/complete-build.yml").read_text(encoding="utf-8")
PATCH = (ROOT / "tools/patch_pyside_deploy_spec.py").read_text(encoding="utf-8")
AUTH = (ROOT / "SRVR_GitHub_v26.09.15.02/firmware_authority.py").read_text(encoding="utf-8")

flags = (
    "--include-data-files=firmware_bundle/ctrl.bin=firmware_bundle/ctrl.bin",
    "--include-data-files=firmware_bundle/w1p.bin=firmware_bundle/w1p.bin",
)
checks = {
    "patcher forces ctrl.bin": flags[0] in PATCH,
    "patcher forces w1p.bin": flags[1] in PATCH,
    "legacy include-data-dir removed by patcher": "LEGACY_FW_DIR_FLAG" in PATCH and "args = [a for a in args if a != LEGACY_FW_DIR_FLAG]" in PATCH,
    "mac workflow uses common patcher": 'patch_pyside_deploy_spec.py" pysidedeploy.spec' in WF,
    "windows workflow uses common patcher": "patch_pyside_deploy_spec.py\" pysidedeploy.spec --windows" in WF,
    "mac dry run proves ctrl": flags[0] in WF,
    "mac dry run proves w1p": flags[1] in WF,
    "mac app asserts packaged ctrl": "PACKAGED_CTRL" in WF and "firmware_bundle/ctrl.bin" in WF,
    "mac app asserts packaged w1p": "PACKAGED_W1P" in WF and "firmware_bundle/w1p.bin" in WF,
    "mac release zip asserts firmware images": "missing packaged firmware data" in WF,
    "runtime checks module data": 'module_dir / "firmware_bundle"' in AUTH,
    "runtime checks exe data": 'exe_dir / "firmware_bundle"' in AUTH,
    "runtime checks mac Resources": 'exe_dir.parent / "Resources" / "firmware_bundle"' in AUTH,
    "windows frozen smoke remains mandatory": "Frozen Windows smoke test failed" in WF,
}

# Exercise the spec patcher on a representative generated spec to prove it is
# idempotent and that the obsolete directory flag is removed.
import importlib.util
specmod = importlib.util.spec_from_file_location("patcher", ROOT / "tools/patch_pyside_deploy_spec.py")
mod = importlib.util.module_from_spec(specmod)
specmod.loader.exec_module(mod)
with tempfile.TemporaryDirectory() as td:
    t = Path(td)
    (t / "firmware_bundle").mkdir()
    for n in ("manifest.json", "SHA256SUMS.txt", "ctrl.bin", "w1p.bin"):
        (t / "firmware_bundle" / n).write_bytes(b"x")
    (t / "HV_P2P_SRVR_icon.ico").write_bytes(b"x" * 2048)
    sp = t / "pysidedeploy.spec"
    sp.write_text("[app]\nicon = old.ico\n[nuitka]\nextra_args = --include-data-dir=firmware_bundle=firmware_bundle\n", encoding="utf-8")
    old = Path.cwd()
    try:
        import os
        os.chdir(t)
        mod.patch_spec(sp, windows=True)
        once = sp.read_text(encoding="utf-8")
        mod.patch_spec(sp, windows=True)
        twice = sp.read_text(encoding="utf-8")
    finally:
        os.chdir(old)
    checks["patcher is idempotent"] = once == twice
    checks["patched spec drops legacy dir"] = mod.LEGACY_FW_DIR_FLAG not in twice
    checks["patched spec contains both forced bins"] = all(f in twice for f in flags)
    checks["patched spec keeps noninteractive windows flag"] = "--assume-yes-for-downloads" in twice

failed = [k for k, v in checks.items() if not v]
for k, v in checks.items():
    print(("OK  " if v else "FAIL") + k)
if failed:
    raise SystemExit("FROZEN_FIRMWARE_PACKAGING_CONTRACT_FAIL: " + ", ".join(failed))
print(f"FROZEN_FIRMWARE_PACKAGING_CONTRACT_PASS ({len(checks)} checks)")
