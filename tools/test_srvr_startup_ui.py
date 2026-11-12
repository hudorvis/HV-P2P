#!/usr/bin/env python3
"""Reproduce an occupied authority port and exercise the Qt Quick Retry button."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import queue
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

from test_pdm_integration import PdmIntegration, SEMVER, get

from PySide6.QtCore import QObject, QMetaObject, QTimer
from PySide6.QtGui import QGuiApplication

import firmware_authority
import backend
import main

ROOT = Path(__file__).resolve().parents[1]
SRVR = ROOT / f"SRVR_GitHub_{SEMVER}"


def check_verified_ctrl_stage(fixture):
    authority = fixture.server()
    controller = backend.HVP2PBackend(version=SEMVER[1:], smoke_test=True, firmware_bundle=authority.bundle,
                                     w1p_update_gate=authority.w1p_gate)
    path = "/firmware/w1p/image"
    status = f"HMI_STATUS|ctrl_version={SEMVER}|fw_required={SEMVER}|fw_match=1|fw_authority=matched|"
    digest = authority.bundle.images["ctrl"].sha256
    peer = controller.ctrl_ip
    try:
        assert get(authority, path)[0] == 409
        controller._handle_ctrl_hmi_status(status + f"fw_sha256={'0' * 64}", peer)
        assert not controller._ctrl_fw_match and get(authority, path)[0] == 409
        controller._handle_ctrl_hmi_status(status + f"fw_sha256={digest}", peer)
        assert controller._ctrl_fw_match and get(authority, path) == (200, fixture.apps[1])
        controller._set_fw_progress("ctrl", True, "Downloading", 42)
        controller._handle_ctrl_hmi_status(status.replace("fw_match=1|fw_authority=matched",
                                                         "fw_match=0|fw_authority=update_failed_image_stream_closed"),
                                           peer)
        assert not controller._fw_progress["ctrl"]["active"] and get(authority, path)[0] == 409
        controller._set_fw_progress("w1p", True, "Downloading", 42)
        controller._settle_node_fw_progress("w1p", "update_failed_image_sha256_mismatch", False)
        assert not controller._fw_progress["w1p"]["active"]

        # The legacy HTTP bridge must also use the bytes verified at startup.
        uploads = []

        class UploadDevice(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                uploads.append((self.path, self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.end_headers()

        with ThreadingHTTPServer(("127.0.0.1", 0), UploadDevice) as device:
            worker = threading.Thread(target=device.serve_forever, daemon=True)
            worker.start()
            try:
                (fixture.bundle / "w1p.bin").write_bytes(fixture.apps[1][:-1] + b"X")
                with patch.object(backend, "AUTHORITY_PORT", device.server_port):
                    controller._legacy_firmware_push_worker("w1p", "127.0.0.1")
                    assert not uploads
                    controller._handle_ctrl_hmi_status(status + f"fw_sha256={digest}", peer)
                    controller._legacy_firmware_push_worker("w1p", "127.0.0.1")
                assert len(uploads) == 1 and uploads[0][0] == "/update/app"
                assert uploads[0][1].split(b"\r\n\r\n", 1)[1].startswith(fixture.apps[1] + b"\r\n")
            finally:
                device.shutdown()
                worker.join(timeout=2)
                (fixture.bundle / "w1p.bin").write_bytes(fixture.apps[1])
        controller.setNetwork("CTRL", "172.20.1.113")
        controller._handle_ctrl_hmi_status(status + f"fw_sha256={digest}", peer)
        assert get(authority, path)[0] == 409
    finally:
        controller.shutdown()
        authority.close()


def check_control_migration():
    with (socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as modern,
          socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as previous):
        for node in (modern, previous):
            node.bind(("127.0.0.1", 0))
            node.settimeout(2)
        current_port, previous_port = modern.getsockname()[1], previous.getsockname()[1]
        rx = queue.Queue()
        with (patch.object(backend, "SERVER_BIND_PORT", current_port),
              patch.object(backend, "PREVIOUS_NETWORK_PORT", previous_port)):
            client = backend.W1PClient("127.0.0.1", current_port, rx, lambda message: None)
            client.start()
            try:
                message, peer = previous.recvfrom(1024)
                assert message == b"STATUS\n"
                previous.sendto(b"STATUS FW=v26.11.12.04 FW_MATCH=1 FW_AUTH=matched\n", peer)
                deadline = time.monotonic() + 2
                while not client.legacy_connected and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert client.legacy_connected and not client.connected and rx.empty()
                assert client.firmware_snapshot()[:2] == ("v26.11.12.04", False)
                stopped_bench = SimpleNamespace(
                    smoke_test=False, calibration_open=False, joystick_calibration_open=False,
                    battery_change_mode=False, goto_target_m=None, last_winch_output=0,
                    requested_speed_mps=0, _w1p_status_fresh=lambda: False, _srvr_estop=True, w1p=client,
                )
                assert not backend.HVP2PBackend.pdm_update_idle(stopped_bench)

                beacon = f"SRVR_FW|version={SEMVER}|session=test"
                client.send(beacon)
                client.send("VEL 1.000")
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    message, _ = previous.recvfrom(1024)
                    if message == (beacon + "\n").encode():
                        break
                    assert message == b"STATUS\n"
                else:
                    raise AssertionError("Previous W1P did not receive the migration beacon")
                while time.monotonic() < deadline:
                    message, _ = modern.recvfrom(1024)
                    if message == b"VEL 1.000\n":
                        break
                    assert message in (b"STATUS\n", (beacon + "\n").encode())
                else:
                    raise AssertionError("Current W1P did not receive its velocity command")
                previous.settimeout(0.35)
                try:
                    message, _ = previous.recvfrom(1024)
                    assert message == b"STATUS\n"
                except TimeoutError:
                    pass

                status = f"STATUS FW={SEMVER} FW_MATCH=1 FW_AUTH=matched"
                modern.sendto((status + "\n").encode(), peer)
                assert rx.get(timeout=2) == status and client.connected
            finally:
                client.close()
                client.join(timeout=2)


def check_retry(app, fixture, *, legacy_conflict):
    with socket.socket() as primary, socket.socket() as legacy:
        primary.bind(("0.0.0.0", 0))
        legacy.bind(("0.0.0.0", 0))
        primary_port = primary.getsockname()[1]
        legacy_port = legacy.getsockname()[1]
        blocked, free = (legacy, primary) if legacy_conflict else (primary, legacy)
        blocked_port = blocked.getsockname()[1]
        blocked.listen()
        free.close()

        with (patch.object(firmware_authority, "AUTHORITY_PORT", primary_port),
              patch.object(firmware_authority, "PREVIOUS_NETWORK_PORT", legacy_port),
              patch.object(firmware_authority, "LEGACY_AUTHORITY_PORT", 0),
              patch.object(main, "AUTHORITY_PORT", primary_port),
              patch.dict("os.environ", {"HVP2P_FIRMWARE_BUNDLE_DIR": str(fixture.bundle)})):
            startup = main.AuthorityStartup(primary_port)
            startup.retry()
            if legacy_conflict:
                authority = startup.authority
                assert authority is not None
                try:
                    assert startup.exit_code == 0
                    assert [error.port for error in authority.legacy_bind_errors] == [legacy_port]
                    assert legacy_port not in authority.legacy_ports
                    assert len(authority.legacy_ports) == 1
                    for port in (authority.port, *authority.legacy_ports):
                        assert get(authority, "/firmware/pdm/manifest", port=port)[0] == 200
                        assert get(authority, "/firmware/pdm/permit", port=port)[0] == 409
                finally:
                    authority.close()
                return
            assert startup.authority is None and startup.exit_code == 11
            assert f"TCP port {blocked_port}" in startup.detail
            errors = []

            def release_port_and_retry():
                window = next((win for win in app.topLevelWindows()
                               if win.objectName() == "startupErrorWindow" and win.isVisible()), None)
                try:
                    assert window is not None
                    button = window.findChild(QObject, "startupRetry")
                    assert button is not None
                    assert QMetaObject.invokeMethod(button, "clicked")
                    assert startup.authority is None
                    blocked.close()
                    assert QMetaObject.invokeMethod(button, "clicked")
                    assert startup.authority is not None
                except Exception as exc:
                    errors.append(exc)
                    if window is not None:
                        window.close()

            watchdog = QTimer()
            watchdog.setSingleShot(True)
            watchdog.timeout.connect(app.quit)
            watchdog.start(5000)
            QTimer.singleShot(0, release_port_and_retry)
            try:
                startup.wait_for_retry(app)
            finally:
                watchdog.stop()
            authority = startup.authority
            try:
                if errors:
                    raise errors[0]
                assert authority is not None
                for port in (primary_port, legacy_port):
                    assert get(authority, "/firmware/ctrl/manifest", port=port)[0] == 200
                    assert get(authority, "/firmware/pdm/permit", port=port)[0] == 409
            finally:
                if authority is not None:
                    authority.close()


if __name__ == "__main__":
    with TemporaryDirectory(prefix="hvp2p-srvr-startup-") as scratch:
        resources = Path(scratch) / "rc_resources.py"
        subprocess.run(["pyside6-rcc", str(SRVR / "resources.qrc"), "-o", str(resources)], check=True)
        sys.path.insert(0, scratch)
        import rc_resources  # noqa: F401

        app = QGuiApplication(["test_srvr_startup_ui", "-platform", "offscreen"])
        fixture = PdmIntegration()
        fixture.setUp()
        try:
            check_retry(app, fixture, legacy_conflict=False)
            check_retry(app, fixture, legacy_conflict=True)
            check_control_migration()
            check_verified_ctrl_stage(fixture)
        finally:
            fixture.doCleanups()
    print("SRVR_STARTUP_WINDOW_PORT_RETRY_PASS")
