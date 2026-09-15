#!/usr/bin/env python3
"""Exercise native-build staging/cleanup/bundle orchestration with a fake compiler.

The fake compiler creates test-only ESP-shaped bytes and deliberately simulates
arduino-cli --export-binaries pollution inside staged sketch build/ directories.
This validates orchestration only; GitHub Actions remains the real compiler gate.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ctrl_dirs = [p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith("HV_P2P_CTRL_EDGEBOX_v")]
if len(ctrl_dirs) != 1:
    raise SystemExit("NATIVE_ORCHESTRATION_TEST_FAIL: active CTRL source directory ambiguous")
VER = ctrl_dirs[0].name.split("_v", 1)[1]
SEMVER = "v" + VER

fake_template = r'''#!/usr/bin/env python3
import sys
from pathlib import Path
args=sys.argv[1:]
out=Path(args[args.index('--output-dir')+1])
sketch=Path(args[-1])
out.mkdir(parents=True,exist_ok=True)
name=sketch.name
ver='__SEMVER__'
raw=bytearray(b'\xE9FAKE_NATIVE_ORCHESTRATION_TEST_ONLY\0')
if 'CTRL_EDGEBOX' in name:
    raw += f'HV_P2P_FW_ROLE=CTRL;HV_P2P_FW_VERSION={ver}\0'.encode()+b'HV_P2P_FW_TARGET=EDGEBOX_ESP100;\0'
elif 'W1P_EDGEBOX' in name:
    raw += f'HV_P2P_FW_ROLE=W1P;HV_P2P_FW_VERSION={ver}\0'.encode()+b'HV_P2P_FW_TARGET=EDGEBOX_ESP100;\0'
raw += bytes(max(0,4096-len(raw)))
(out/f'{name}.ino.bin').write_bytes(raw)
(out/f'{name}.ino.bootloader.bin').write_bytes(b'boot')
(out/f'{name}.ino.partitions.bin').write_bytes(b'part')
(out/f'{name}.ino.merged.bin').write_bytes(b'merged')
pollute=sketch/'build'/'esp32.fake.board'
pollute.mkdir(parents=True,exist_ok=True)
(pollute/f'{name}.ino.merged.bin').write_bytes(b'polluted duplicate')
'''.replace("__SEMVER__", SEMVER)

with tempfile.TemporaryDirectory(prefix="hvp2p_native_orch_") as td_s:
    td = Path(td_s)
    fake = td / "arduino-cli"
    fake.write_text(fake_template, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    out = td / "native-output"
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run([
        sys.executable, str(ROOT / "tools/native_build_firmware.py"),
        "--skip-source-preflight", "--arduino-cli", str(fake), "--output", str(out),
    ], cwd=ROOT, check=True, env=env, stdout=subprocess.DEVNULL)

    staged = out / "STAGED_SOURCE"
    if any(p.is_dir() for p in staged.rglob("build")):
        raise SystemExit("NATIVE_ORCHESTRATION_TEST_FAIL: generated build directory survived STAGED_SOURCE cleanup")
    if any(staged.rglob("*.bin")):
        raise SystemExit("NATIVE_ORCHESTRATION_TEST_FAIL: generated .bin survived STAGED_SOURCE cleanup")
    for rel in (
        "SRVR_FIRMWARE_BUNDLE/ctrl.bin",
        "SRVR_FIRMWARE_BUNDLE/w1p.bin",
        "SRVR_FIRMWARE_BUNDLE/manifest.json",
        "NATIVE_BUILD_MANIFEST.json",
        "SHA256SUMS.txt",
    ):
        q = out / rel
        if not q.is_file() or q.stat().st_size <= 0:
            raise SystemExit(f"NATIVE_ORCHESTRATION_TEST_FAIL: missing output {rel}")

subprocess.run(
    [sys.executable, str(ROOT / "tools/test_source_package_hygiene.py")],
    cwd=ROOT,
    check=True,
    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    stdout=subprocess.DEVNULL,
)
print("NATIVE_BUILD_ORCHESTRATION_PASS")
