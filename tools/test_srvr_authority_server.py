#!/usr/bin/env python3
"""Exercise SRVR release validation and CTRL-first downloads over real HTTP."""
from hashlib import sha256
from http.client import HTTPConnection
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from native_build_firmware import SEMVER, bundle_id_for

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / f"SRVR_GitHub_{SEMVER}"))
from firmware_authority import (
    AUTHORITY, EXPECTED_TARGET, SCHEMA, FirmwareAuthorityError, FirmwareAuthorityServer, FirmwareBundle,
)


def fixture_image(role, target=EXPECTED_TARGET):
    identity = f"HV_P2P_FW_ROLE={role};HV_P2P_FW_TARGET={target};HV_P2P_FW_VERSION={SEMVER};"
    return b"\xe9" + identity.encode("ascii") + bytes(32768)


def get(port, path):
    conn = HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


class AuthorityServerTest(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)
        self.ctrl = fixture_image("CTRL")
        self.w1p = fixture_image("W1P")
        self.manifest_path = self.path / "manifest.json"
        self.manifest = dict(schema=SCHEMA, authority=AUTHORITY, release=SEMVER, images={},
                             bundle_id=bundle_id_for(SEMVER, sha256(self.ctrl).hexdigest(),
                                                     sha256(self.w1p).hexdigest()))
        for role, payload in (("ctrl", self.ctrl), ("w1p", self.w1p)):
            self.set_image(role, payload)

    def set_image(self, role, payload):
        filename = f"{role}.bin"
        (self.path / filename).write_bytes(payload)
        self.manifest["images"][role] = dict(
            file=filename, role=role.upper(), target=EXPECTED_TARGET, version=SEMVER,
            size=len(payload), sha256=sha256(payload).hexdigest())
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_startup_rejects_invalid_bundle(self):
        (self.path / "ctrl.bin").write_bytes(self.ctrl[:-1] + b"X")
        with self.assertRaisesRegex(FirmwareAuthorityError, "ctrl image SHA-256 mismatch"):
            FirmwareBundle(self.path, SEMVER)
        self.set_image("ctrl", fixture_image("W1P"))
        with self.assertRaisesRegex(FirmwareAuthorityError, "ctrl image identity mismatch"):
            FirmwareBundle(self.path, SEMVER)
        self.manifest_path.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(FirmwareAuthorityError, "manifest schema mismatch"):
            FirmwareBundle(self.path, SEMVER)

    def test_w1p_sequence_and_immutable_images_across_all_listeners(self):
        authority = FirmwareAuthorityServer(SEMVER, host="127.0.0.1", port=0, bundle_dir=self.path,
                                            legacy_ports=(0, 0))
        self.addCleanup(authority.close)
        now = 10.0
        authority.w1p_gate._clock = lambda: now
        authority.w1p_gate.select_controller("172.20.1.101")
        authority.start()
        ports = (authority.port, *authority.legacy_ports)
        self.assertEqual(len(ports), 3)
        w1p_image = "/firmware/w1p/image"
        ctrl_image = "/firmware/ctrl/image"

        # Changing the bundle on disk cannot replace the already-verified bytes.
        (self.path / "ctrl.bin").write_bytes(self.ctrl[:-1] + b"X")
        (self.path / "w1p.bin").unlink()
        for port in ports:
            status, response = get(port, "/firmware/w1p/manifest")
            manifest = json.loads(response)
            self.assertEqual((status, manifest["target"], manifest["version"]), (200, EXPECTED_TARGET, SEMVER))
            self.assertEqual(manifest["sha256"], sha256(self.w1p).hexdigest())
            self.assertEqual(get(port, ctrl_image), (200, self.ctrl))
            self.assertEqual(get(port, w1p_image)[0], 409)

        authority.w1p_gate.observe("172.20.1.100", 11.0)
        self.assertEqual(get(authority.port, w1p_image)[0], 409)
        authority.w1p_gate.observe("172.20.1.101", 11.0)
        for port in ports:
            self.assertEqual(get(port, w1p_image), (200, self.w1p))
        now = 11.0
        for port in ports:
            self.assertEqual(get(port, w1p_image)[0], 409)
        authority.w1p_gate.observe("172.20.1.101", 12.0)
        authority.w1p_gate.select_controller("172.20.1.103")
        self.assertEqual(get(authority.port, w1p_image)[0], 409)
        authority.w1p_gate.observe("172.20.1.103", 12.0)
        authority.w1p_gate.observe("172.20.1.103", 0.0)
        self.assertEqual(get(authority.port, w1p_image)[0], 409)
        authority.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
