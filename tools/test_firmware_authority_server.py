#!/usr/bin/env python3
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

VER = "26.09.15.02"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / f"SRVR_GitHub_v{VER}"))
from firmware_authority import FirmwareAuthorityService, validate_firmware_bundle


def d(data: bytes) -> str:
    return sha256(data).hexdigest()


def make_fixture(root: Path) -> None:
    roles = {}
    for role, filename in (("CTRL", "ctrl.bin"), ("W1P", "w1p.bin")):
        identity = f"HV_P2P_FW_ROLE={role};HV_P2P_FW_VERSION=v{VER}"
        target = "HV_P2P_FW_TARGET=EDGEBOX_ESP100;"
        data = b"\xE9" + b"fixture:" + identity.encode() + b":" + target.encode() + bytes(range(64))
        (root / filename).write_bytes(data)
        roles[role] = {
            "role": role, "target": "EDGEBOX_ESP100", "hardware": "Seeed EdgeBox-ESP-100",
            "version": f"v{VER}", "file": filename, "size": len(data), "sha256": d(data),
            "identity_token": identity, "target_token": target,
        }
    bundle_id = sha256((f"v{VER}\n" + roles["CTRL"]["sha256"] + "\n" + roles["W1P"]["sha256"] + "\n").encode()).hexdigest()
    manifest = {"schema": 1, "authority": "HV_P2P_SRVR", "release": f"v{VER}", "bundle_id": bundle_id,
                "source_native_manifest_sha256": "0" * 64, "roles": roles}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    lines = [f"{d((root/name).read_bytes())}  {name}" for name in ("manifest.json", "ctrl.bin", "w1p.bin")]
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n")


def fetch(url: str) -> tuple[int, bytes, dict]:
    with urlopen(url, timeout=3) as r:
        return r.status, r.read(), dict(r.headers)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hvp2p_fw_auth_") as td:
        root = Path(td)
        make_fixture(root)
        validated = validate_firmware_bundle(root, VER)
        assert validated.release == f"v{VER}"
        service = FirmwareAuthorityService(VER, bundle_dir=root, bind="127.0.0.1", port=0)
        service.start()
        try:
            base = f"http://127.0.0.1:{service.bound_port}"
            status, raw, headers = fetch(base + "/firmware/ctrl/manifest")
            assert status == 200 and headers["X-HV-P2P-Release"] == f"v{VER}"
            ctrl = json.loads(raw)
            assert ctrl["role"] == "CTRL" and ctrl["target"] == "EDGEBOX_ESP100"
            assert ctrl["image"] == "/firmware/ctrl/image"
            status, image, _ = fetch(base + ctrl["image"])
            assert status == 200 and d(image) == ctrl["sha256"] and len(image) == ctrl["size"]
            status, full, _ = fetch(base + "/firmware/manifest")
            assert json.loads(full)["bundle_id"] == validated.manifest["bundle_id"]
            req = Request(base + "/firmware/w1p/image", method="HEAD")
            with urlopen(req, timeout=3) as r:
                assert r.status == 200 and int(r.headers["Content-Length"]) == validated.manifest["roles"]["W1P"]["size"]
            for bad in ("/firmware/ctrl/../w1p/image", "/firmware/ctrl/image?x=1", "/update"):
                try:
                    fetch(base + bad)
                except HTTPError as exc:
                    assert exc.code == 404
                else:
                    raise AssertionError(f"unexpected route accepted: {bad}")
            try:
                req = Request(base + "/firmware/ctrl/image", data=b"x", method="POST")
                urlopen(req, timeout=3)
            except HTTPError as exc:
                assert exc.code == 405
            else:
                raise AssertionError("firmware authority accepted POST")
        finally:
            service.stop()

        # Tampering must make the immutable bundle invalid before the service starts.
        with (root / "ctrl.bin").open("ab") as f:
            f.write(b"tamper")
        try:
            validate_firmware_bundle(root, VER)
        except ValueError as exc:
            assert "size" in str(exc) or "SHA-256" in str(exc) or "checksum" in str(exc)
        else:
            raise AssertionError("tampered firmware bundle validated")

    print("FIRMWARE_AUTHORITY_SERVER_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
