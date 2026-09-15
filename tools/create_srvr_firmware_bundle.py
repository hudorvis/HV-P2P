#!/usr/bin/env python3
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil

VER = "26.09.15.01"
SEMVER = f"v{VER}"


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit("ERROR: " + message)


def create_bundle(native: Path, output: Path) -> None:
    native = native.resolve()
    source_manifest = native / "NATIVE_BUILD_MANIFEST.json"
    require(source_manifest.is_file(), f"native manifest missing: {source_manifest}")
    meta = json.loads(source_manifest.read_text(encoding="utf-8"))
    require(meta.get("release") == SEMVER, f"native release must be {SEMVER}")
    apps = meta.get("applications")
    require(isinstance(apps, dict), "native applications map missing")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    roles: dict[str, dict] = {}
    for role, dest_name in (("CTRL", "ctrl.bin"), ("W1P", "w1p.bin")):
        entry = apps.get(role)
        require(isinstance(entry, dict), f"native {role} application metadata missing")
        src = (native / str(entry.get("file", ""))).resolve()
        require(src.is_file() and native in src.parents, f"native {role} application path invalid")
        require(src.read_bytes()[:1] == b"\xE9", f"native {role} is not an ESP app image")
        size = src.stat().st_size
        require(size == int(entry.get("size", -1)), f"native {role} size mismatch")
        image_sha = digest(src)
        require(image_sha == entry.get("sha256"), f"native {role} SHA-256 mismatch")
        identity = f"HV_P2P_FW_ROLE={role};HV_P2P_FW_VERSION={SEMVER}"
        target_token = "HV_P2P_FW_TARGET=EDGEBOX_ESP100;"
        raw = src.read_bytes()
        require(identity.encode("ascii") in raw, f"native {role} identity token missing")
        require(target_token.encode("ascii") in raw, f"native {role} EdgeBox target token missing")
        dest = output / dest_name
        shutil.copy2(src, dest)
        require(digest(dest) == image_sha, f"copied {role} image changed")
        roles[role] = {
            "role": role,
            "target": "EDGEBOX_ESP100",
            "hardware": "Seeed EdgeBox-ESP-100",
            "version": SEMVER,
            "file": dest_name,
            "size": size,
            "sha256": image_sha,
            "identity_token": identity,
            "target_token": target_token,
        }

    bundle_id = sha256((SEMVER + "\n" + roles["CTRL"]["sha256"] + "\n" + roles["W1P"]["sha256"] + "\n").encode("ascii")).hexdigest()
    manifest = {
        "schema": 1,
        "authority": "HV_P2P_SRVR",
        "release": SEMVER,
        "bundle_id": bundle_id,
        "source_native_manifest_sha256": digest(source_manifest),
        "roles": roles,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    sums = []
    for name in ("manifest.json", "ctrl.bin", "w1p.bin"):
        p = output / name
        sums.append(f"{digest(p)}  {name}")
    (output / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(f"SRVR_FIRMWARE_BUNDLE_CREATED release={SEMVER} bundle_id={bundle_id}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--native-output", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    create_bundle(args.native_output, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
