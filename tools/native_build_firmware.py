#!/usr/bin/env python3
"""Build native HV P2P firmware in dependency order without mutating source.

GitHub Actions is the authoritative native compiler. Order:
  1. CTRL-TS native application.
  2. Embed that exact CTRL-TS app/hash into an isolated CTRL source copy.
  3. Compile CTRL.
  4. Compile W1P.
  5. Verify retained role/target/version identity tokens.
  6. Build immutable SRVR_FIRMWARE_BUNDLE for CTRL and W1P.
  7. Preserve only clean staged Arduino source and native outputs outside checkout.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

VER = "26.10.06.10"
SEMVER = f"v{VER}"
CTRL_SLOT = 0x600000
HMI_SLOT = 0x380000
BUNDLE_SCHEMA = "hv-p2p-firmware-manifest-v1"
BUNDLE_AUTHORITY = "HV_P2P_SRVR"
EDGEBOX_TARGET = "EDGEBOX_ESP100"
WAVESHARE_ST7262_LVGL_COMMIT = os.environ.get(
    "WAVESHARE_ST7262_LVGL_COMMIT", "593775b89ebfd2d411df3eadba7bc382767ed4a4"
)
EDGEBOX_FQBN = (
    "esp32:esp32:Edgebox-ESP-100:"
    "FlashSize=16M,FlashMode=qio,PSRAM=disabled,CPUFreq=240,"
    "CDCOnBoot=default,USBMode=default,UploadMode=default,UploadSpeed=921600,"
    "PartitionScheme=app3M_fat9M_16MB"
)
HMI_FQBN = (
    "esp32:esp32:esp32s3:"
    "FlashSize=16M,FlashMode=qio,PSRAM=opi,CPUFreq=240,"
    "CDCOnBoot=cdc,USBMode=hwcdc,UploadMode=default,UploadSpeed=921600,"
    "PartitionScheme=custom"
)


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(str(x) for x in cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, env=_clean_env())


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_snapshot(root: Path) -> dict[str, str]:
    """Hash all checkout files so native compilation cannot silently dirty source."""
    ignored_parts = {".git", "__pycache__"}
    snap: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or any(part in ignored_parts for part in p.parts):
            continue
        rel = p.relative_to(root).as_posix()
        snap[rel] = sha256(p)
    return snap


def require_binary_token(path: Path, token: str, role: str) -> None:
    if token.encode("ascii") not in path.read_bytes():
        raise SystemExit(f"ERROR: {role} application missing retained identity token: {token}")


def find_app_bin(build_dir: Path, sketch_stem: str) -> Path:
    candidates = []
    for p in build_dir.rglob("*.bin"):
        name = p.name.lower()
        if any(x in name for x in ("bootloader", "partitions", "merged")):
            continue
        if name.endswith(".ino.bin") or name == f"{sketch_stem.lower()}.bin":
            candidates.append(p)
    if not candidates:
        candidates = [p for p in build_dir.rglob("*.bin")
                      if not any(x in p.name.lower() for x in ("bootloader", "partitions", "merged"))]
    if len(candidates) != 1:
        raise RuntimeError(f"expected one application binary in {build_dir}, got: {candidates}")
    return candidates[0]


def copy_build_products(build_dir: Path, out_dir: Path, prefix: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in sorted(build_dir.rglob("*.bin")):
        dest = out_dir / f"{prefix}__{src.name}"
        shutil.copy2(src, dest)
        copied.append(dest)
    return copied


def compile_sketch(cli: str, sketch_dir: Path, fqbn: str, build_dir: Path, max_size: int | None = None) -> Path:
    build_dir.mkdir(parents=True, exist_ok=True)
    cmd = [cli, "compile", "--fqbn", fqbn, "--warnings", "all",
           "--export-binaries", "--output-dir", str(build_dir)]
    if max_size is not None:
        cmd += ["--build-property", f"upload.maximum_size={max_size}"]
    cmd += [str(sketch_dir)]
    run(cmd)
    return find_app_bin(build_dir, sketch_dir.name)


def bundle_id_for(release: str, ctrl_sha: str, w1p_sha: str) -> str:
    return hashlib.sha256(f"{release}\nCTRL={ctrl_sha}\nW1P={w1p_sha}\n".encode("ascii")).hexdigest()


def make_firmware_bundle(ctrl_app: Path, w1p_app: Path, out_dir: Path) -> dict:
    """Create the immutable SRVR authority payload from verified native apps."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ctrl_dst = out_dir / "ctrl.bin"
    w1p_dst = out_dir / "w1p.bin"
    shutil.copy2(ctrl_app, ctrl_dst)
    shutil.copy2(w1p_app, w1p_dst)
    ctrl_sha, w1p_sha = sha256(ctrl_dst), sha256(w1p_dst)
    bundle_id = bundle_id_for(SEMVER, ctrl_sha, w1p_sha)
    manifest = {
        "schema": BUNDLE_SCHEMA,
        "authority": BUNDLE_AUTHORITY,
        "bundle_id": bundle_id,
        "release": SEMVER,
        "images": {
            "ctrl": {"file": "ctrl.bin", "role": "CTRL", "target": EDGEBOX_TARGET,
                     "version": SEMVER, "size": ctrl_dst.stat().st_size, "sha256": ctrl_sha},
            "w1p": {"file": "w1p.bin", "role": "W1P", "target": EDGEBOX_TARGET,
                    "version": SEMVER, "size": w1p_dst.stat().st_size, "sha256": w1p_sha},
        },
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sums = [
        f"{sha256(ctrl_dst)}  ctrl.bin",
        f"{sha256(w1p_dst)}  w1p.bin",
        f"{sha256(manifest_path)}  manifest.json",
    ]
    (out_dir / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return manifest


def _default_output() -> Path:
    base = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir())
    return base / "HVP2P_NATIVE_BUILD_ARTIFACTS"


def _strip_generated_tree(stage: Path) -> None:
    for p in list(stage.rglob("*")):
        if p.is_dir() and (p.name in {"build", "dist", "__pycache__"} or p.name.startswith("cmake-build")):
            shutil.rmtree(p, ignore_errors=True)
    for p in list(stage.rglob("*.pyc")):
        p.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--arduino-cli", default=os.environ.get("ARDUINO_CLI", "arduino-cli"))
    args = ap.parse_args()

    root = args.root.resolve()
    output = (args.output or _default_output()).resolve()
    if output == root or root in output.parents:
        raise SystemExit("ERROR: native output must be outside the source checkout")
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

    before = source_snapshot(root)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="hvp2p_native_") as td:
        td = Path(td)
        stage, build = td / "source", td / "build"
        for d in (ctrl_name, hmi_name, w1p_name):
            shutil.copytree(root / d, stage / d)

        hmi_app = compile_sketch(args.arduino_cli, stage / hmi_name, HMI_FQBN, build / "ctrl_ts")
        if not 0 < hmi_app.stat().st_size <= HMI_SLOT or hmi_app.read_bytes()[:1] != b"\xE9":
            raise SystemExit("ERROR: invalid/oversize native CTRL-TS application")

        staged_header = stage / ctrl_name / "HV_P2P_CTRL_TS_Firmware_Image.h"
        run([sys.executable, str(root / "tools" / "embed_ctrl_ts_firmware.py"), str(hmi_app), SEMVER, str(staged_header)])
        run([sys.executable, str(root / "tools" / "verify_staged_hmi_header.py"), str(staged_header), str(hmi_app)])

        ctrl_app = compile_sketch(args.arduino_cli, stage / ctrl_name, EDGEBOX_FQBN, build / "ctrl", CTRL_SLOT)
        w1p_app = compile_sketch(args.arduino_cli, stage / w1p_name, EDGEBOX_FQBN, build / "w1p", CTRL_SLOT)
        for role, app in (("CTRL", ctrl_app), ("W1P", w1p_app)):
            if not 0 < app.stat().st_size <= CTRL_SLOT or app.read_bytes()[:1] != b"\xE9":
                raise SystemExit(f"ERROR: invalid/oversize {role} application")
            require_binary_token(app, f"HV_P2P_FW_ROLE={role};", role)
            require_binary_token(app, f"HV_P2P_FW_TARGET={EDGEBOX_TARGET};", role)
            require_binary_token(app, f"HV_P2P_FW_VERSION={SEMVER};", role)

        staged_src = output / "STAGED_SOURCE"
        staged_src.mkdir(parents=True)
        for d in (ctrl_name, hmi_name, w1p_name):
            shutil.copytree(stage / d, staged_src / d)
        _strip_generated_tree(staged_src)

        bins_dir = output / "BINARIES"
        products = []
        products += copy_build_products(build / "ctrl_ts", bins_dir / "CTRL_TS", hmi_name)
        products += copy_build_products(build / "ctrl", bins_dir / "CTRL", ctrl_name)
        products += copy_build_products(build / "w1p", bins_dir / "W1P", w1p_name)
        canonical = {
            "CTRL_TS": bins_dir / f"{hmi_name}.ino.bin",
            "CTRL": bins_dir / f"{ctrl_name}.ino.bin",
            "W1P": bins_dir / f"{w1p_name}.ino.bin",
        }
        for src, dst in ((hmi_app, canonical["CTRL_TS"]), (ctrl_app, canonical["CTRL"]), (w1p_app, canonical["W1P"])):
            shutil.copy2(src, dst)
            products.append(dst)

        fw_bundle = output / "SRVR_FIRMWARE_BUNDLE"
        bundle_manifest = make_firmware_bundle(ctrl_app, w1p_app, fw_bundle)

        native_manifest = {
            "release": SEMVER,
            "arduino_core": "esp32:esp32@3.3.8",
            "dependencies": {
                "Waveshare_ST7262_LVGL": {"repository": "https://github.com/iamfaraz/Waveshare_ST7262_LVGL.git", "commit": WAVESHARE_ST7262_LVGL_COMMIT},
                "lvgl": "8.3.11", "ESP32_Display_Panel": "0.1.6", "ESP32_IO_Expander": "0.0.3", "JPEGDEC": "1.8.4",
            },
            "fqbn": {"CTRL_TS": HMI_FQBN, "CTRL": EDGEBOX_FQBN, "W1P": EDGEBOX_FQBN},
            "slot_limits": {"CTRL_TS": HMI_SLOT, "CTRL": CTRL_SLOT, "W1P": CTRL_SLOT},
            "applications": {role: {"file": str(path.relative_to(output)), "size": path.stat().st_size, "sha256": sha256(path)} for role, path in canonical.items()},
            "firmware_bundle": {"directory": "SRVR_FIRMWARE_BUNDLE", "bundle_id": bundle_manifest["bundle_id"]},
        }
        native_manifest_path = output / "NATIVE_BUILD_MANIFEST.json"
        native_manifest_path.write_text(json.dumps(native_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        checksum_targets = [p for p in output.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt"]
        (output / "SHA256SUMS.txt").write_text("".join(
            f"{sha256(p)}  {p.relative_to(output).as_posix()}\n" for p in sorted(checksum_targets)
        ), encoding="utf-8")

    after = source_snapshot(root)
    if after != before:
        changed = sorted(set(before) ^ set(after) | {k for k in set(before) & set(after) if before[k] != after[k]})
        raise SystemExit(f"ERROR: native build mutated source checkout: {changed[:30]}")

    print("NATIVE_FIRMWARE_BUILD_PASS")
    print(f"Artifacts: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
