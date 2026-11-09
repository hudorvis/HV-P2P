#!/usr/bin/env python3
"""Immutable SRVR firmware authority for HV P2P nodes.

The native GitHub firmware build creates ``firmware_bundle``. SRVR requires the
verified CTRL/W1P pair before serving and validates any PDM image separately.
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
import time

AUTHORITY_PORT = 5088
SCHEMA = "hv-p2p-firmware-manifest-v1"
AUTHORITY = "HV_P2P_SRVR"
EXPECTED_TARGET = "EDGEBOX_ESP100"
PDM_TARGET = "OLIMEX_ESP32_POE_ISO"
PDM_SLOT_BYTES = 0x1e0000
REQUIRED_ROLES = ("ctrl", "w1p")


class FirmwareAuthorityError(RuntimeError):
    pass


class PdmIdleWindow:
    """A short lease based on local, continuously refreshed idle evidence."""
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._snapshot = ("", 0.0, 0.0)

    def observe(self, peer: str, idle: bool) -> None:
        if not idle:
            self._snapshot = ("", 0.0, 0.0)
            return
        now = self._clock()
        previous, start, expires = self._snapshot
        if previous != peer or expires <= now:
            start = now
        # One immutable snapshot. HTTP threads never call into Qt or motion.
        self._snapshot = (peer, start, now + 0.5)

    def permits(self, peer: str) -> bool:
        allowed, start, expires = self._snapshot
        now = self._clock()
        return peer == allowed and start + 3.0 <= now < expires


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
        if not set(REQUIRED_ROLES) <= set(images) or set(images) - {*REQUIRED_ROLES, "pdm"}:
            raise FirmwareAuthorityError("firmware bundle must contain CTRL and W1P, with optional PDM")
        self.release = release
        self.bundle_id = bundle_id
        self.images = {key: self._read_image(key, images[key], EXPECTED_TARGET) for key in REQUIRED_ROLES}
        self.pdm_error = ""
        self.pdm_image = b""
        if "pdm" in images:
            try:
                image = self._read_image("pdm", images["pdm"], PDM_TARGET)
                if not 32768 <= image.size <= PDM_SLOT_BYTES:
                    raise FirmwareAuthorityError("PDM image exceeds the Olimex OTA slot or is incomplete")
                payload = image.path.read_bytes()
                identity = f"HV_P2P_FW_ROLE=PDM;HV_P2P_FW_TARGET={PDM_TARGET};HV_P2P_FW_VERSION={release};"
                if not payload.startswith(b"\xe9") or identity.encode("ascii") not in payload or sha256(payload).hexdigest() != image.sha256:
                    raise FirmwareAuthorityError("PDM image identity or integrity mismatch")
                self.pdm_image = payload
                self.images["pdm"] = image
            except (FirmwareAuthorityError, OSError, ValueError) as exc:
                self.pdm_error = str(exc)

    def _read_image(self, key: str, meta: Mapping, expected_target: str) -> FirmwareImage:
        if not isinstance(meta, Mapping):
            raise FirmwareAuthorityError(f"firmware metadata missing for {key}")
        role, target, version = (str(meta.get(field, "")) for field in ("role", "target", "version"))
        filename = str(meta.get("file", ""))
        expected_sha = str(meta.get("sha256", "")).lower()
        try:
            expected_size = int(meta.get("size", -1))
        except (TypeError, ValueError, OverflowError) as exc:
            raise FirmwareAuthorityError(f"invalid {key} image size") from exc
        if role != key.upper() or target != expected_target:
            raise FirmwareAuthorityError(f"{key} role/target mismatch")
        if version != self.release:
            raise FirmwareAuthorityError(f"{key} version does not match release")
        if filename != f"{key}.bin":
            raise FirmwareAuthorityError(f"{key} image filename is not canonical")
        if len(expected_sha) != 64 or any(c not in "0123456789abcdef" for c in expected_sha):
            raise FirmwareAuthorityError(f"{key} SHA-256 is invalid")
        image_path = (self.bundle_dir / filename).resolve()
        if image_path.parent != self.bundle_dir or not image_path.is_file():
            raise FirmwareAuthorityError(f"{key} image missing")
        actual_size = image_path.stat().st_size
        if actual_size <= 0 or actual_size != expected_size:
            raise FirmwareAuthorityError(f"{key} image size mismatch")
        if key == "pdm" and actual_size > PDM_SLOT_BYTES:
            raise FirmwareAuthorityError("PDM image exceeds the Olimex OTA slot")
        if _sha256_file(image_path) != expected_sha:
            raise FirmwareAuthorityError(f"{key} image SHA-256 mismatch")
        return FirmwareImage(key, role, target, version, self.release, self.bundle_id,
                             image_path, actual_size, expected_sha)


class FirmwareAuthorityServer:
    def __init__(self, expected_release: str, host: str = "0.0.0.0", port: int = AUTHORITY_PORT,
                 bundle_dir: Path | None = None):
        self.bundle = FirmwareBundle(bundle_dir or find_bundle_dir(), expected_release)
        self.pdm_window = PdmIdleWindow()
        pdm_window = self.pdm_window
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
                kind = parts[2]
                if image.role_key == "pdm" and kind in ("permit", "image"):
                    if not pdm_window.permits(self.client_address[0]):
                        self._reply(409, b"PDM idle window closed\n", "text/plain")
                    elif kind == "permit":
                        self._reply(200, f"{image.release} {image.sha256}\n".encode("ascii"), "text/plain")
                    else:
                        self._reply(200, bundle.pdm_image, "application/octet-stream")
                elif kind == "manifest":
                    self._reply(200, image.wire_manifest(), "application/json")
                elif kind == "image":
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
        self.pdm_window.observe("", False)
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)


def start_firmware_authority(expected_release: str, *, port: int = AUTHORITY_PORT) -> FirmwareAuthorityServer:
    server = FirmwareAuthorityServer(expected_release=expected_release, port=port)
    server.start()
    return server
