#!/usr/bin/env python3
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VER = "26.09.15.02"
SEMVER = f"v{VER}"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / f"SRVR_GitHub_v{VER}"))

from create_srvr_firmware_bundle import create_bundle  # noqa: E402
from firmware_authority import validate_firmware_bundle  # noqa: E402


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def make_app(role: str) -> bytes:
    identity = f"HV_P2P_FW_ROLE={role};HV_P2P_FW_VERSION={SEMVER}".encode("ascii")
    target = b"HV_P2P_FW_TARGET=EDGEBOX_ESP100;"
    # Synthetic host-test fixture only: it deliberately has ESP image magic and
    # retained identity strings, but is never emitted as a release artifact.
    return b"\xE9" + b"HVP2P-HOST-TEST:" + identity + b":" + target + bytes(range(128))


def write_native(native: Path) -> tuple[bytes, bytes]:
    ctrl = make_app("CTRL")
    w1p = make_app("W1P")
    ctrl_path = native / "BINARIES" / "CTRL" / f"HV_P2P_CTRL_EDGEBOX_v{VER}.ino.bin"
    w1p_path = native / "BINARIES" / "W1P" / f"HV_P2P_W1P_EDGEBOX_v{VER}.ino.bin"
    ctrl_path.parent.mkdir(parents=True, exist_ok=True)
    w1p_path.parent.mkdir(parents=True, exist_ok=True)
    ctrl_path.write_bytes(ctrl)
    w1p_path.write_bytes(w1p)
    manifest = {
        "release": SEMVER,
        "applications": {
            "CTRL": {"file": ctrl_path.relative_to(native).as_posix(), "size": len(ctrl), "sha256": digest(ctrl_path)},
            "W1P": {"file": w1p_path.relative_to(native).as_posix(), "size": len(w1p), "sha256": digest(w1p_path)},
        },
    }
    (native / "NATIVE_BUILD_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return ctrl, w1p


def expect_builder_reject(native: Path, output: Path, contains: str) -> None:
    try:
        create_bundle(native, output)
    except SystemExit as exc:
        assert contains.lower() in str(exc).lower(), (contains, str(exc))
    else:
        raise AssertionError(f"bundle builder accepted invalid native artifact; expected {contains!r}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hvp2p_bundle_builder_") as td:
        tmp = Path(td)
        native = tmp / "native"
        native.mkdir()
        ctrl, w1p = write_native(native)
        bundle = tmp / "bundle"
        create_bundle(native, bundle)
        validated = validate_firmware_bundle(bundle, VER)
        assert validated.images["CTRL"].read_bytes() == ctrl
        assert validated.images["W1P"].read_bytes() == w1p
        assert {p.name for p in bundle.iterdir()} == {"manifest.json", "SHA256SUMS.txt", "ctrl.bin", "w1p.bin"}

        # The immutable runtime validator rejects extra payloads, not merely bad hashes.
        (bundle / "unexpected.bin").write_bytes(b"not part of the authority bundle")
        try:
            validate_firmware_bundle(bundle, VER)
        except ValueError as exc:
            assert "exactly" in str(exc)
        else:
            raise AssertionError("authority validator accepted an extra bundle payload")
        (bundle / "unexpected.bin").unlink()

        # Native-manifest tampering is rejected before a bundle is created.
        meta_path = native / "NATIVE_BUILD_MANIFEST.json"
        meta = json.loads(meta_path.read_text())
        meta["applications"]["CTRL"]["sha256"] = "0" * 64
        meta_path.write_text(json.dumps(meta) + "\n")
        expect_builder_reject(native, tmp / "rejected_hash", "sha-256")

        # Restore and prove role identity is enforced from the binary itself.
        write_native(native)
        ctrl_path = native / "BINARIES" / "CTRL" / f"HV_P2P_CTRL_EDGEBOX_v{VER}.ino.bin"
        bad = ctrl_path.read_bytes().replace(b"HV_P2P_FW_ROLE=CTRL", b"HV_P2P_FW_ROLE=FAIL")
        ctrl_path.write_bytes(bad)
        meta = json.loads(meta_path.read_text())
        meta["applications"]["CTRL"]["size"] = len(bad)
        meta["applications"]["CTRL"]["sha256"] = digest(ctrl_path)
        meta_path.write_text(json.dumps(meta) + "\n")
        expect_builder_reject(native, tmp / "rejected_role", "identity token")

    print("FIRMWARE_BUNDLE_BUILDER_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
