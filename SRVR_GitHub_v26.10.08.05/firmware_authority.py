#!/usr/bin/env python3
"""Immutable SRVR firmware authority for HV P2P EdgeBox nodes.

The native GitHub firmware build creates ``firmware_bundle``.  SRVR verifies the
entire bundle before opening the HTTP authority endpoint; invalid or incomplete
bundles are never served.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Mapping
import json
import os
import sys
import threading

AUTHORITY_PORT = 5088
SCHEMA = "hv-p2p-firmware-manifest-v1"
AUTHORITY = "HV_P2P_SRVR"
EXPECTED_TARGET = "EDGEBOX_ESP100"
REQUIRED_ROLES = ("ctrl", "w1p")


class FirmwareAuthorityError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _bundle_candidates() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("HVP2P_FIRMWARE_BUNDLE_DIR", "").strip()
    if override:
        candidates.append(Path(override))
    here = Path(__file__).resolve().parent
    candidates.append(here / "firmware_bundle")
    exe = Path(sys.executable).resolve()
    candidates.extend([
        exe.parent / "firmware_bundle",
        exe.parent / "Resources" / "firmware_bundle",
        exe.parent.parent / "Resources" / "firmware_bundle",  # macOS .app/Contents/Resources
    ])
    seen: set[str] = set()
    out: list[Path] = []
    for item in candidates:
        key = str(item)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def find_bundle_dir() -> Path:
    for candidate in _bundle_candidates():
        if (candidate / "manifest.json").is_file():
            return candidate
    tried = ", ".join(str(p) for p in _bundle_candidates())
    raise FirmwareAuthorityError(f"firmware bundle missing; tried: {tried}")


@dataclass(frozen=True)
class FirmwareImage:
    role_key: str
    role: str
    target: str
    version: str
    release: str
    bundle_id: str
    path: Path
    size: int
    sha256: str

    def wire_manifest(self) -> bytes:
        doc = {
            "schema": SCHEMA,
            "authority": AUTHORITY,
            "bundle_id": self.bundle_id,
            "release": self.release,
            "role": self.role,
            "target": self.target,
            "version": self.version,
            "size": self.size,
            "sha256": self.sha256,
        }
        return (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class FirmwareBundle:
    def __init__(self, bundle_dir: Path, expected_release: str | None = None):
        self.bundle_dir = Path(bundle_dir).resolve()
        manifest_path = self.bundle_dir / "manifest.json"
        try:
            doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise FirmwareAuthorityError(f"invalid firmware manifest {manifest_path}: {exc}") from exc
        if doc.get("schema") != SCHEMA:
            raise FirmwareAuthorityError("firmware manifest schema mismatch")
        if doc.get("authority") != AUTHORITY:
            raise FirmwareAuthorityError("firmware manifest authority mismatch")
        release = str(doc.get("release", ""))
        if not release.startswith("v"):
            raise FirmwareAuthorityError("firmware manifest release is invalid")
        if expected_release and release != expected_release:
            raise FirmwareAuthorityError(f"firmware release {release} != SRVR {expected_release}")
        bundle_id = str(doc.get("bundle_id", ""))
        if len(bundle_id) != 64 or any(c not in "0123456789abcdef" for c in bundle_id.lower()):
            raise FirmwareAuthorityError("firmware bundle_id must be 64 hex characters")
        images = doc.get("images")
        if not isinstance(images, Mapping):
            raise FirmwareAuthorityError("firmware manifest images mapping missing")
        if set(images) != set(REQUIRED_ROLES):
            raise FirmwareAuthorityError("firmware bundle must contain exactly CTRL and W1P images")
        parsed: dict[str, FirmwareImage] = {}
        for role_key in REQUIRED_ROLES:
            meta = images.get(role_key)
            if not isinstance(meta, Mapping):
                raise FirmwareAuthorityError(f"firmware metadata missing for {role_key}")
            expected_role = role_key.upper()
            role = str(meta.get("role", ""))
            target = str(meta.get("target", ""))
            version = str(meta.get("version", ""))
            filename = str(meta.get("file", ""))
            expected_sha = str(meta.get("sha256", "")).lower()
            try:
                expected_size = int(meta.get("size", -1))
            except Exception as exc:
                raise FirmwareAuthorityError(f"invalid {role_key} image size") from exc
            if role != expected_role or target != EXPECTED_TARGET:
                raise FirmwareAuthorityError(f"{role_key} role/target mismatch")
            if version != release:
                raise FirmwareAuthorityError(f"{role_key} version does not match release")
            if Path(filename).name != filename or filename != f"{role_key}.bin":
                raise FirmwareAuthorityError(f"{role_key} image filename is not canonical")
            if len(expected_sha) != 64 or any(c not in "0123456789abcdef" for c in expected_sha):
                raise FirmwareAuthorityError(f"{role_key} SHA-256 is invalid")
            image_path = (self.bundle_dir / filename).resolve()
            if image_path.parent != self.bundle_dir or not image_path.is_file():
                raise FirmwareAuthorityError(f"{role_key} image missing")
            actual_size = image_path.stat().st_size
            if actual_size <= 0 or actual_size != expected_size:
                raise FirmwareAuthorityError(f"{role_key} image size mismatch")
            actual_sha = _sha256_file(image_path)
            if actual_sha != expected_sha:
                raise FirmwareAuthorityError(f"{role_key} image SHA-256 mismatch")
            parsed[role_key] = FirmwareImage(
                role_key, role, target, version, release, bundle_id,
                image_path, actual_size, actual_sha,
            )
        self.release = release
        self.bundle_id = bundle_id
        self.images = parsed


class FirmwareAuthorityServer:
    def __init__(self, expected_release: str, host: str = "0.0.0.0", port: int = AUTHORITY_PORT,
                 bundle_dir: Path | None = None):
        self.bundle = FirmwareBundle(bundle_dir or find_bundle_dir(), expected_release)
        bundle = self.bundle

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):
                # SRVR has its own operator log; keep the authority transport quiet.
                return

            def _reply(self, status: int, body: bytes, content_type: str):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-HV-P2P-Bundle", bundle.bundle_id)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                parts = [p for p in self.path.split("?", 1)[0].split("/") if p]
                if len(parts) != 3 or parts[0] != "firmware" or parts[1] not in bundle.images:
                    self._reply(404, b"not found\n", "text/plain; charset=utf-8")
                    return
                image = bundle.images[parts[1]]
                if parts[2] == "manifest":
                    self._reply(200, image.wire_manifest(), "application/json")
                elif parts[2] == "image":
                    self._reply(200, image.path.read_bytes(), "application/octet-stream")
                else:
                    self._reply(404, b"not found\n", "text/plain; charset=utf-8")

        self._httpd = ThreadingHTTPServer((host, int(port)), Handler)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="HVP2PFirmwareAuthority", daemon=True)
        self._closed = False

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)


def start_firmware_authority(expected_release: str, *, port: int = AUTHORITY_PORT) -> FirmwareAuthorityServer:
    server = FirmwareAuthorityServer(expected_release=expected_release, port=port)
    server.start()
    return server
