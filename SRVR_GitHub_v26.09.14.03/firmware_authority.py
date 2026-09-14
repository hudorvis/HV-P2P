from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sys
import threading
from typing import Any

BUNDLE_SCHEMA = 1
DEFAULT_FIRMWARE_PORT = 8088
_ALLOWED_ROLES = {"CTRL", "W1P"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def locate_firmware_bundle(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    """Locate the immutable bundle in source, Nuitka standalone, or app-bundle layouts."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("HVP2P_FIRMWARE_BUNDLE")
    if env:
        candidates.append(Path(env))
    module_dir = Path(__file__).resolve().parent
    candidates.append(module_dir / "firmware_bundle")
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "firmware_bundle")
        # Defensive macOS app-bundle fallback if data lands in Contents/Resources.
        if exe_dir.name == "MacOS" and exe_dir.parent.name == "Contents":
            candidates.append(exe_dir.parent / "Resources" / "firmware_bundle")
    except Exception:
        pass
    candidates.append(Path.cwd() / "firmware_bundle")

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except Exception:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "manifest.json").is_file():
            return resolved
    return None


@dataclass(frozen=True)
class ValidatedFirmwareBundle:
    root: Path
    manifest: dict[str, Any]
    images: dict[str, Path]

    @property
    def release(self) -> str:
        return str(self.manifest["release"])

    def role_manifest(self, role: str) -> dict[str, Any]:
        role = role.upper()
        entry = dict(self.manifest["roles"][role])
        return {
            "schema": self.manifest["schema"],
            "authority": self.manifest["authority"],
            "release": self.manifest["release"],
            "bundle_id": self.manifest["bundle_id"],
            **entry,
            "image": f"/firmware/{role.lower()}/image",
        }


def validate_firmware_bundle(bundle_dir: str | os.PathLike[str], app_version: str | None = None) -> ValidatedFirmwareBundle:
    root = Path(bundle_dir).resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"firmware manifest missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid firmware manifest JSON: {exc}") from exc

    if manifest.get("schema") != BUNDLE_SCHEMA:
        raise ValueError(f"unsupported firmware bundle schema: {manifest.get('schema')!r}")
    if manifest.get("authority") != "HV_P2P_SRVR":
        raise ValueError("firmware bundle authority identity mismatch")
    release = str(manifest.get("release", ""))
    if not re.fullmatch(r"v\d+\.\d+\.\d+\.\d+", release):
        raise ValueError(f"invalid firmware release: {release!r}")
    if app_version is not None and release != f"v{app_version}":
        raise ValueError(f"bundle release {release} does not match running SRVR v{app_version}")
    bundle_id = str(manifest.get("bundle_id", ""))
    if not _SHA256_RE.fullmatch(bundle_id):
        raise ValueError("firmware bundle_id must be a lowercase SHA-256")

    roles = manifest.get("roles")
    if not isinstance(roles, dict) or set(roles) != _ALLOWED_ROLES:
        raise ValueError("firmware bundle must contain exactly CTRL and W1P roles")

    images: dict[str, Path] = {}
    for role in sorted(_ALLOWED_ROLES):
        entry = roles.get(role)
        if not isinstance(entry, dict):
            raise ValueError(f"{role} manifest entry is invalid")
        if entry.get("role") != role:
            raise ValueError(f"{role} role identity mismatch")
        if entry.get("target") != "EDGEBOX_ESP100":
            raise ValueError(f"{role} target must be EDGEBOX_ESP100")
        if entry.get("version") != release:
            raise ValueError(f"{role} version does not match bundle release")
        filename = str(entry.get("file", ""))
        if Path(filename).name != filename or not filename.endswith(".bin"):
            raise ValueError(f"{role} image filename is not a safe bundle basename")
        image = (root / filename).resolve()
        if image.parent != root or not image.is_file():
            raise ValueError(f"{role} image missing from immutable bundle")
        size = entry.get("size")
        if not isinstance(size, int) or not (0 < size <= 0x600000):
            raise ValueError(f"{role} image size is invalid")
        if image.stat().st_size != size:
            raise ValueError(f"{role} image size does not match manifest")
        expected_sha = str(entry.get("sha256", ""))
        if not _SHA256_RE.fullmatch(expected_sha):
            raise ValueError(f"{role} SHA-256 is invalid")
        actual_sha = _sha256_file(image)
        if actual_sha != expected_sha:
            raise ValueError(f"{role} image SHA-256 mismatch")
        raw = image.read_bytes()
        if raw[:1] != b"\xE9":
            raise ValueError(f"{role} image is not an ESP application image")
        identity = str(entry.get("identity_token", ""))
        target_token = str(entry.get("target_token", ""))
        if identity != f"HV_P2P_FW_ROLE={role};HV_P2P_FW_VERSION={release}":
            raise ValueError(f"{role} identity token metadata mismatch")
        if target_token != "HV_P2P_FW_TARGET=EDGEBOX_ESP100;":
            raise ValueError(f"{role} target token metadata mismatch")
        if identity.encode("ascii") not in raw:
            raise ValueError(f"{role} image does not contain its manifest identity token")
        if target_token.encode("ascii") not in raw:
            raise ValueError(f"{role} image does not contain its EdgeBox target token")
        images[role] = image

    expected_bundle_id = sha256(
        (release + "\n" + roles["CTRL"]["sha256"] + "\n" + roles["W1P"]["sha256"] + "\n").encode("ascii")
    ).hexdigest()
    if bundle_id != expected_bundle_id:
        raise ValueError("firmware bundle_id does not match release/image identities")

    expected_bundle_files = {"manifest.json", "SHA256SUMS.txt", "ctrl.bin", "w1p.bin"}
    actual_entries = {p.name for p in root.iterdir()}
    if actual_entries != expected_bundle_files or not all((root / name).is_file() for name in expected_bundle_files):
        raise ValueError("firmware bundle must contain exactly manifest.json, SHA256SUMS.txt, ctrl.bin and w1p.bin")

    sums_path = root / "SHA256SUMS.txt"
    if not sums_path.is_file():
        raise ValueError("firmware bundle SHA256SUMS.txt is missing")
    expected_sums: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or not _SHA256_RE.fullmatch(parts[0]) or Path(parts[1]).name != parts[1]:
            raise ValueError("invalid firmware bundle SHA256SUMS.txt entry")
        expected_sums[parts[1]] = parts[0]
    if set(expected_sums) != {"manifest.json", "ctrl.bin", "w1p.bin"}:
        raise ValueError("firmware bundle SHA256SUMS.txt must cover manifest.json, ctrl.bin and w1p.bin")
    for name, digest in expected_sums.items():
        if _sha256_file(root / name) != digest:
            raise ValueError(f"firmware bundle checksum mismatch for {name}")

    return ValidatedFirmwareBundle(root=root, manifest=manifest, images=images)


class _AuthorityHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _handler_factory(bundle: ValidatedFirmwareBundle):
    class Handler(BaseHTTPRequestHandler):
        server_version = "HV-P2P-FirmwareAuthority/1"

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"[FW AUTH HTTP] {self.address_string()} {fmt % args}")

        def _headers(self, status: int, content_type: str, length: int, etag: str | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-HV-P2P-Release", bundle.release)
            if etag:
                self.send_header("ETag", f'"{etag}"')
            self.end_headers()

        def _send_json(self, payload: dict[str, Any], head_only: bool = False) -> None:
            raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            self._headers(200, "application/json; charset=utf-8", len(raw), bundle.manifest["bundle_id"])
            if not head_only:
                self.wfile.write(raw)

        def _serve(self, head_only: bool = False) -> None:
            # Exact path matching only; query strings and traversal are intentionally unsupported.
            path = self.path
            if path == "/firmware/manifest":
                self._send_json(bundle.manifest, head_only)
                return
            for role in ("CTRL", "W1P"):
                prefix = f"/firmware/{role.lower()}"
                if path == prefix + "/manifest":
                    self._send_json(bundle.role_manifest(role), head_only)
                    return
                if path == prefix + "/image":
                    image = bundle.images[role]
                    entry = bundle.manifest["roles"][role]
                    self._headers(200, "application/octet-stream", entry["size"], entry["sha256"])
                    if not head_only:
                        with image.open("rb") as f:
                            for chunk in iter(lambda: f.read(64 * 1024), b""):
                                self.wfile.write(chunk)
                    return
            payload = b"Not found\n"
            self._headers(404, "text/plain; charset=utf-8", len(payload))
            if not head_only:
                self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            self._serve(False)

        def do_HEAD(self) -> None:  # noqa: N802
            self._serve(True)

        def do_POST(self) -> None:  # noqa: N802
            payload = b"Method not allowed\n"
            self._headers(405, "text/plain; charset=utf-8", len(payload))
            self.wfile.write(payload)

    return Handler


class FirmwareAuthorityService:
    """Read-only SRVR-authoritative HTTP firmware service for CTRL and W1P."""

    def __init__(self, app_version: str, *, bundle_dir: str | os.PathLike[str] | None = None,
                 bind: str = "0.0.0.0", port: int = DEFAULT_FIRMWARE_PORT):
        self.app_version = app_version
        self.bundle_dir = bundle_dir
        self.bind = bind
        self.port = int(port)
        self.bundle: ValidatedFirmwareBundle | None = None
        self._server: _AuthorityHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def bound_port(self) -> int | None:
        return int(self._server.server_address[1]) if self._server else None

    def start(self) -> None:
        if self._server is not None:
            return
        located = locate_firmware_bundle(self.bundle_dir)
        if located is None:
            raise RuntimeError("SRVR firmware bundle is not present")
        self.bundle = validate_firmware_bundle(located, self.app_version)
        server = _AuthorityHTTPServer((self.bind, self.port), _handler_factory(self.bundle))
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, name="hvp2p-firmware-authority", daemon=True)
        self._thread.start()
        print(f"[FW AUTH] release={self.bundle.release} bundle={self.bundle.manifest['bundle_id']} "
              f"listening={self.bind}:{self.bound_port} root={self.bundle.root}")

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)


__all__ = [
    "BUNDLE_SCHEMA", "DEFAULT_FIRMWARE_PORT", "FirmwareAuthorityService",
    "ValidatedFirmwareBundle", "locate_firmware_bundle", "validate_firmware_bundle",
]
