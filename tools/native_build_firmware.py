#!/usr/bin/env python3
"""Build the three HV P2P device firmwares in dependency order.

This script does not install Arduino cores/libraries.  The GitHub Actions workflow
in this release installs the pinned toolchain, then calls this script.

Order is important:
  1. Compile CTRL-TS native application.
  2. Embed that exact .ino.bin + SHA-256 in a *staged copy* of CTRL source.
  3. Compile CTRL, which is impossible from the checked-in source build guard.
  4. Compile W1P.
  5. Package native build products and a SHA-256 manifest.

The checked-in source tree is never mutated by a successful build.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

VER = "26.08.31.06"
SEMVER = f"v{VER}"
CTRL_SLOT = 0x600000
HMI_SLOT = 0x380000

# Espressif Arduino core 3.3.8 exposes the EdgeBox board but defaults it to 4 MB.
# The physical EdgeBox-ESP-100 is 16 MB, so FlashSize=16M is mandatory here.
EDGEBOX_FQBN = (
    "esp32:esp32:Edgebox-ESP-100:"
    "FlashSize=16M,FlashMode=qio,PSRAM=disabled,CPUFreq=240,"
    "CDCOnBoot=default,USBMode=default,UploadMode=default,UploadSpeed=921600"
)
# The Waveshare board is ESP32-S3N16R8.  The project uses a local dual-OTA
# partitions.csv and OPI PSRAM for the 800x480 LVGL display stack.
HMI_FQBN = (
    "esp32:esp32:esp32s3:"
    "FlashSize=16M,FlashMode=qio,PSRAM=opi,CPUFreq=240,"
    "CDCOnBoot=cdc,USBMode=hwcdc,UploadMode=default,UploadSpeed=921600,"
    "PartitionScheme=custom"
)


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(str(x) for x in cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_app_bin(build_dir: Path, sketch_stem: str) -> Path:
    candidates = []
    for p in build_dir.rglob("*.bin"):
        name = p.name.lower()
        if any(x in name for x in ("bootloader", "partitions", "merged")):
            continue
        if name.endswith(".ino.bin") or name == f"{sketch_stem.lower()}.bin":
            candidates.append(p)
    if not candidates:
        # Some arduino-cli versions name the app simply <sketch>.bin.
        candidates = [
            p for p in build_dir.rglob("*.bin")
            if not any(x in p.name.lower() for x in ("bootloader", "partitions", "merged"))
        ]
    if len(candidates) != 1:
        raise RuntimeError(f"expected one application binary in {build_dir}, got: {candidates}")
    return candidates[0]


def copy_build_products(build_dir: Path, out_dir: Path, prefix: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in sorted(build_dir.rglob("*.bin")):
        suffix = src.name
        dest = out_dir / f"{prefix}__{suffix}"
        shutil.copy2(src, dest)
        copied.append(dest)
    return copied


def compile_sketch(cli: str, sketch_dir: Path, fqbn: str, build_dir: Path, max_size: int | None = None) -> Path:
    build_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        cli, "compile", "--fqbn", fqbn,
        "--warnings", "all",
        "--export-binaries",
        "--output-dir", str(build_dir),
    ]
    if max_size is not None:
        cmd += ["--build-property", f"upload.maximum_size={max_size}"]
    cmd += [str(sketch_dir)]
    run(cmd)
    app = find_app_bin(build_dir, sketch_dir.name)
    return app


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--arduino-cli", default=os.environ.get("ARDUINO_CLI", "arduino-cli"))
    args = ap.parse_args()

    root = args.root.resolve()
    output = (args.output or (root / "NATIVE_BUILD_ARTIFACTS")).resolve()
    if shutil.which(args.arduino_cli) is None:
        raise SystemExit("ERROR: arduino-cli is not installed or not on PATH")

    ctrl_name = f"HV_P2P_CTRL_EDGEBOX_v{VER}"
    hmi_name = f"HV_P2P_CTRL_TS_v{VER}"
    w1p_name = f"HV_P2P_W1P_EDGEBOX_v{VER}"
    for d in (ctrl_name, hmi_name, w1p_name):
        if not (root / d / f"{d}.ino").is_file():
            raise SystemExit(f"ERROR: source sketch missing: {d}")

    guard = (root / ctrl_name / "HV_P2P_CTRL_TS_Firmware_Image.h").read_text(errors="replace")
    if '#error "CTRL-TS firmware image has not been staged.' not in guard:
        raise SystemExit("ERROR: source CTRL carrier is not the expected clean build-guard state")

    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hvp2p_native_") as td:
        stage = Path(td) / "source"
        build = Path(td) / "build"
        for d in (ctrl_name, hmi_name, w1p_name):
            shutil.copytree(root / d, stage / d)

        # 1. Native Waveshare image.
        hmi_app = compile_sketch(args.arduino_cli, stage / hmi_name, HMI_FQBN, build / "ctrl_ts")
        if not 0 < hmi_app.stat().st_size <= HMI_SLOT:
            raise SystemExit(f"ERROR: CTRL-TS app {hmi_app.stat().st_size} exceeds 0x{HMI_SLOT:X} OTA slot")
        if hmi_app.read_bytes()[:1] != b"\xE9":
            raise SystemExit("ERROR: native CTRL-TS output is not an ESP application image")

        # 2. Embed the exact native HMI into staged CTRL source.
        staged_header = stage / ctrl_name / "HV_P2P_CTRL_TS_Firmware_Image.h"
        run([sys.executable, str(root / "tools" / "embed_ctrl_ts_firmware.py"), str(hmi_app), SEMVER, str(staged_header)])
        run([sys.executable, str(root / "tools" / "verify_staged_hmi_header.py"), str(staged_header), str(hmi_app)])

        # 3. Build the actual CTRL carrier.  Override the board's stock maximum
        # sketch size because our local partition CSV deliberately provides 6 MB.
        ctrl_app = compile_sketch(args.arduino_cli, stage / ctrl_name, EDGEBOX_FQBN, build / "ctrl", CTRL_SLOT)
        if not 0 < ctrl_app.stat().st_size <= CTRL_SLOT:
            raise SystemExit(f"ERROR: CTRL app {ctrl_app.stat().st_size} exceeds 0x{CTRL_SLOT:X} app slot")

        # 4. W1P uses the same 16 MB dual-OTA partition map.
        w1p_app = compile_sketch(args.arduino_cli, stage / w1p_name, EDGEBOX_FQBN, build / "w1p", CTRL_SLOT)
        if not 0 < w1p_app.stat().st_size <= CTRL_SLOT:
            raise SystemExit(f"ERROR: W1P app {w1p_app.stat().st_size} exceeds 0x{CTRL_SLOT:X} app slot")

        # 5. Preserve the fully staged CTRL source used to produce the binary.
        staged_src = output / "STAGED_SOURCE"
        if staged_src.exists():
            shutil.rmtree(staged_src)
        staged_src.mkdir(parents=True)
        for d in (ctrl_name, hmi_name, w1p_name):
            shutil.copytree(stage / d, staged_src / d)

        bins_dir = output / "BINARIES"
        if bins_dir.exists():
            shutil.rmtree(bins_dir)
        products = []
        products += copy_build_products(build / "ctrl_ts", bins_dir / "CTRL_TS", hmi_name)
        products += copy_build_products(build / "ctrl", bins_dir / "CTRL", ctrl_name)
        products += copy_build_products(build / "w1p", bins_dir / "W1P", w1p_name)

        # Canonical app filenames for straightforward use/verification.
        canonical = {
            "CTRL_TS": bins_dir / f"{hmi_name}.ino.bin",
            "CTRL": bins_dir / f"{ctrl_name}.ino.bin",
            "W1P": bins_dir / f"{w1p_name}.ino.bin",
        }
        for src, dst in ((hmi_app, canonical["CTRL_TS"]), (ctrl_app, canonical["CTRL"]), (w1p_app, canonical["W1P"])):
            shutil.copy2(src, dst)
            products.append(dst)

        manifest = {
            "release": SEMVER,
            "arduino_core": "esp32:esp32@3.3.8",
            "fqbn": {"CTRL_TS": HMI_FQBN, "CTRL": EDGEBOX_FQBN, "W1P": EDGEBOX_FQBN},
            "slot_limits": {"CTRL_TS": HMI_SLOT, "CTRL": CTRL_SLOT, "W1P": CTRL_SLOT},
            "applications": {
                role: {"file": str(path.relative_to(output)), "size": path.stat().st_size, "sha256": sha256(path)}
                for role, path in canonical.items()
            },
        }
        (output / "NATIVE_BUILD_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")

        manifest_lines = []
        for p in sorted(set(products + [output / "NATIVE_BUILD_MANIFEST.json"])):
            manifest_lines.append(f"{sha256(p)}  {p.relative_to(output)}")
        (output / "SHA256SUMS.txt").write_text("\n".join(manifest_lines) + "\n")

        # Re-run source checks on the clean source tree. Staged-header byte-level
        # verification above is the native carrier gate for the staged copy.
        run([sys.executable, str(root / "tools" / "run_all_source_checks.py")], cwd=root)

    print("NATIVE_FIRMWARE_BUILD_PASS")
    print(f"Artifacts: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
