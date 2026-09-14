#!/usr/bin/env python3
"""Fail fast on mixed active release paths/version tokens before native CI."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("HV_P2P_CTRL_EDGEBOX_v", "HV_P2P_CTRL_TS_v", "HV_P2P_W1P_EDGEBOX_v", "SRVR_GitHub_v")

found = {}
for prefix in KINDS:
    dirs = sorted(p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith(prefix))
    if len(dirs) != 1:
        raise SystemExit(f"RELEASE_CONSISTENCY_FAIL: expected exactly one active {prefix} directory, got {[p.name for p in dirs]}")
    version = dirs[0].name[len(prefix):]
    found[prefix] = (version, dirs[0])
versions = {v for v, _ in found.values()}
if len(versions) != 1:
    raise SystemExit(f"RELEASE_CONSISTENCY_FAIL: active directory versions disagree: {found}")
VER = versions.pop()
SEMVER = f"v{VER}"

ctrl = found["HV_P2P_CTRL_EDGEBOX_v"][1] / f"HV_P2P_CTRL_EDGEBOX_v{VER}.ino"
hmi = found["HV_P2P_CTRL_TS_v"][1] / f"HV_P2P_CTRL_TS_v{VER}.ino"
w1p = found["HV_P2P_W1P_EDGEBOX_v"][1] / f"HV_P2P_W1P_EDGEBOX_v{VER}.ino"
srvr = found["SRVR_GitHub_v"][1]
for p in (ctrl, hmi, w1p, srvr / "main.py", srvr / "backend.py", ROOT / ".github/workflows/complete-build.yml"):
    if not p.is_file():
        raise SystemExit(f"RELEASE_CONSISTENCY_FAIL: missing active file {p.relative_to(ROOT)}")

expectations = {
    ctrl: [f'CTRL_VERSION "HV P2P CTRL EdgeBox {SEMVER}"', f'HV_CTRL_SEMVER = "{SEMVER}"', f'HV_P2P_FW_VERSION={SEMVER}'],
    hmi: [f'CTRL_TS_SEMVER "{SEMVER}"'],
    w1p: [f'FW_VERSION = "{SEMVER}"', f'HV_P2P_FW_VERSION={SEMVER}'],
    srvr / "main.py": [f'APP_VERSION = "{VER}"'],
    srvr / "backend.py": [f'def __init__(self, version="{VER}"'],
}
for path, tokens in expectations.items():
    text = path.read_text(encoding="utf-8", errors="replace")
    missing = [token for token in tokens if token not in text]
    if missing:
        raise SystemExit(f"RELEASE_CONSISTENCY_FAIL: {path.relative_to(ROOT)} missing {missing}")

workflow = (ROOT / ".github/workflows/complete-build.yml").read_text(encoding="utf-8")
for token in (f"HV P2P Complete Build {SEMVER}", f"APP_VERSION: '{VER}'", f"HV-P2P-v{VER}-Native-Firmware",
              f"HV-P2P-v{VER}-Complete-Release", f"SRVR_GitHub_v{VER}"):
    if token not in workflow:
        raise SystemExit(f"RELEASE_CONSISTENCY_FAIL: workflow missing {token!r}")

# Path-bearing active code must never accidentally point at a previous release.
path_re = re.compile(r"(?:SRVR_GitHub|HV_P2P_(?:CTRL_EDGEBOX|CTRL_TS|W1P_EDGEBOX))_v(\d+\.\d+\.\d+\.\d+)")
active = list((ROOT / "tools").glob("*.py")) + list((srvr / "tools").glob("*.py")) + [ROOT / ".github/workflows/complete-build.yml"]
for path in active:
    text = path.read_text(encoding="utf-8", errors="replace")
    bad = sorted({m.group(1) for m in path_re.finditer(text) if m.group(1) != VER})
    if bad:
        raise SystemExit(f"RELEASE_CONSISTENCY_FAIL: {path.relative_to(ROOT)} references stale active release path(s): {bad}")

print(f"RELEASE_CONSISTENCY_PASS version={SEMVER}")
