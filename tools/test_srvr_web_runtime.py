#!/usr/bin/env python3
"""Verify a live SRVR window on the firmware listener in an offscreen Qt session."""
from http.client import HTTPConnection
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

from native_build_firmware import SEMVER, make_firmware_bundle
from test_pdm_qt_runtime import scene_item, scene_items, wait_for
from test_srvr_authority_server import fixture_image

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt, QUrl, qInstallMessageHandler
from PySide6.QtGui import QColor, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from backend import HVP2PBackend
from firmware_authority import FirmwareAuthorityServer, MONITOR_TARGETS
from pdm_monitor import PdmMonitor, WsiMonitor
from web_mirror import WebMirror, _jpeg

SRVR = Path(__file__).resolve().parents[1] / f"SRVR_GitHub_{SEMVER}"


def request(port, path, method="GET", data=None, viewer="", headers=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=2)
    headers = dict(headers or {})
    if viewer:
        headers["X-SRVR-Viewer"] = viewer
    body = None
    if method == "POST":
        headers.setdefault("Origin", f"http://127.0.0.1:{port}")
        headers.setdefault("Content-Type", "application/json")
        body = json.dumps(data).encode()
    try:
        conn.request(method, path, body, headers)
        reply = conn.getresponse()
        return reply.status, reply.headers, reply.read()
    finally:
        conn.close()


def make_bundle(directory):
    ctrl, w1p, pdm = (directory / f"{role.lower()}.bin" for role in ("CTRL", "W1P", "PDM"))
    ctrl.write_bytes(fixture_image("CTRL"))
    w1p.write_bytes(fixture_image("W1P"))
    pdm.write_bytes(fixture_image("PDM", MONITOR_TARGETS["pdm"]))
    bundle = directory / "firmware_bundle"
    make_firmware_bundle(ctrl, w1p, pdm, bundle)
    return bundle


def exercise(app, window, web, authority, backend):
    port = authority.port
    legacy = authority.legacy_ports[0]
    root = request(port, "/")
    assert root[0] == 200 and b"HV P2P SRVR" in root[2] and b"<form" not in root[2]
    assert "frame-ancestors 'none'" in root[1]["Content-Security-Policy"]
    for kind in ("app.css", "app.js"):
        assert request(port, f"/srvr-web/{kind}")[0] == 200
    assert request(legacy, "/")[0] == 404
    assert request(legacy, "/srvr-web/frame")[0] == 404
    assert request(port, "/", headers={"Host": f"spoof.example:{port}"})[0] == 403
    assert request(port, "/srvr-web/frame", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert request(port, "/srvr-web/session", "POST", {},
                   headers={"Origin": "http://elsewhere.example"})[0] == 403
    assert request(port, "/srvr-web/frame")[0] == 410

    authority.select_monitor_peer("pdm", "127.0.0.1")
    manifest = request(port, "/firmware/pdm/manifest")
    assert manifest[0] == 200 and json.loads(manifest[2])["version"] == SEMVER
    assert request(legacy, "/firmware/pdm/manifest")[2] == manifest[2]
    assert request(port, "/firmware/w1p/image")[0] == 409

    def connect():
        status, _, body = request(port, "/srvr-web/session", "POST", {})
        assert status == 200
        return json.loads(body)["viewer"]

    # These are automatic per-tab identifiers. The desktop has had no input.
    first = connect()
    second = connect()
    assert first != second
    sizes = {first: (1280, 720), second: (1600, 800)}

    def latest(viewer=None, foreground=True):
        viewer = viewer or first
        width, height = sizes[viewer]
        return request(port, "/srvr-web/frame", viewer=viewer,
                       headers={"X-SRVR-Foreground": "1" if foreground else "0",
                                "X-SRVR-Viewport": f"{width}x{height}"})

    def browser(viewer=first):
        return web._viewports[viewer].quickWindow()

    def center(surface, name_or_item):
        item = scene_item(surface, name_or_item) if isinstance(name_or_item, str) else name_or_item
        return item.mapToScene(QPointF(item.width() / 2, item.height() / 2))

    def desktop_click(name_or_item):
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=center(window, name_or_item).toPoint())
        app.processEvents()

    def input_packet(name_or_item, frame, viewer):
        surface = browser(viewer)
        pt = center(surface, name_or_item)
        return {"kind": "click", "frame": frame, "points": [
            [pt.x() / (surface.width() - 1), pt.y() / (surface.height() - 1)],
        ]}

    def send(packet, viewer=first):
        return request(port, "/srvr-web/input", "POST", packet, viewer=viewer)[0]

    def click(name_or_item, frame, viewer=first):
        return send(input_packet(name_or_item, frame, viewer), viewer)

    def fresh_frame(after=0, viewer=first):
        number = 0

        def updated():
            nonlocal number
            status, headers, _ = latest(viewer)
            number = int(headers.get("X-SRVR-Frame", 0))
            return status == 200 and number > after

        wait_for(app, updated)
        return number

    initial = fresh_frame()
    initial_second = fresh_frame(viewer=second)
    status, headers, jpeg = latest()
    second_status, second_headers, second_jpeg = latest(second)
    assert status == second_status == 200
    assert headers["X-SRVR-Frame"] != second_headers["X-SRVR-Frame"]
    assert headers["X-SRVR-Input"] == second_headers["X-SRVR-Input"] == "ready"
    image = QImage.fromData(jpeg)
    assert (image.width(), image.height()) == sizes[first]
    second_image = QImage.fromData(second_jpeg)
    assert (second_image.width(), second_image.height()) == sizes[second]
    pixel, background = image.pixelColor(2, 2), window.color()
    assert max(abs(a - b) for a, b in zip(pixel.getRgb(), background.getRgb())) <= 5, (pixel, background)

    # The intended physical-pixel image must include all four quadrants on Retina.
    retina = QImage(64, 32, QImage.Format.Format_ARGB32_Premultiplied)
    retina.setDevicePixelRatio(2)
    retina.fill(QColor("#ff0000"))
    composed = QImage.fromData(_jpeg(retina, QColor("#000000")))
    assert composed.size() == retina.size()
    assert composed.pixelColor(60, 28).red() > 240

    # A bounded wait on the same frame and a subsequent request reuse TCP.
    connection = HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        frame_headers = {"X-SRVR-Viewer": first, "X-SRVR-Foreground": "1",
                         "X-SRVR-Frame": str(initial), "X-SRVR-Next-Frame": "1"}
        connection.request("GET", "/srvr-web/frame", headers=frame_headers)
        held = connection.getresponse()
        assert held.status == 204 and held.getheader("X-SRVR-Next-Frame") == "1"
        held.read()
        socket_used = connection.sock
        del frame_headers["X-SRVR-Frame"]
        connection.request("GET", "/srvr-web/frame", headers=frame_headers)
        available = connection.getresponse()
        assert available.status == 200 and available.read() == jpeg
        assert socket_used is not None and connection.sock is socket_used
    finally:
        connection.close()

    # Window resizes leave each browser's rendered layout and pointer
    # coordinates alone. A browser resize invalidates only its own frames.
    first_size = browser().size()
    second_size = browser(second).size()
    window.resize(1440, 900)
    app.processEvents()
    assert browser().size() == first_size and browser(second).size() == second_size
    sizes[second] = (1000, 1000)
    assert latest(second)[1].get("X-SRVR-Wait") == "frame"
    assert click("mainTab1", initial_second, second) == 409
    resize_frame = fresh_frame(initial_second, second)
    resized_image = QImage.fromData(latest(second)[2])
    assert resized_image.width() == resized_image.height() == 1050
    assert browser().size() == first_size and window.width() == 1440 and window.height() == 900
    assert request(port, "/srvr-web/frame", viewer=second,
                   headers={"X-SRVR-Viewport": "50000x0"})[0] == 400
    assert click("mainTab1", resize_frame, first) == 409

    initial = fresh_frame()
    assert click("mainTab3", initial) == 204
    wait_for(app, lambda: window.property("page") == 3)
    page = scene_item(window, "powerPage")
    assert page.property("subtab") == 0
    assert click("mainTab1", initial, second) == 409

    assert click("monitorOpenWeb", fresh_frame(initial)) == 204
    node_url = page.property("monitor").webUrl().toString()
    wait_for(app, lambda: latest()[1].get("X-SRVR-Open-URL") == node_url)
    assert "X-SRVR-Open-URL" not in latest(second)[1]

    before_desktop = fresh_frame(initial)
    desktop_click("monitorWsiTab")
    assert page.property("subtab") == 1 and web.server.control_live(first)
    assert click("monitorLogTab", before_desktop) == 409
    frame = fresh_frame(before_desktop)
    assert click("monitorLogTab", frame) == 204
    wait_for(app, lambda: page.property("subtab") == 2)
    assert scene_item(window, "monitorLogPage").property("visible")
    assert not page.property("historyActive")
    frame = fresh_frame(frame, second)
    assert click("srvrLogSearch", frame, second) == 204
    search = scene_item(browser(second), "srvrLogSearch")
    wait_for(app, lambda: search.hasFocus())
    frame = fresh_frame(frame, second)
    assert send({"kind": "text", "frame": frame, "text": "fixture é"}, second) == 204
    wait_for(app, lambda: search.property("text") == "fixture é")
    assert scene_item(window, "srvrLogSearch").property("text") == ""

    # Pressing and releasing at the desktop protects that gesture from a
    # stale browser click. Both browsers can act on the updated view.
    frame = fresh_frame(frame)
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=center(window, "mainTab1").toPoint())
    assert click("mainTab0", frame) == 409
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=center(window, "mainTab1").toPoint())
    wait_for(app, lambda: window.property("page") == 1)
    assert click("srvrSaveConfigButton", fresh_frame(frame, second), second) == 204
    picker = scene_item(browser(second), "webSrvrView").findChild(QObject, "srvrSaveConfigDialog")
    wait_for(app, lambda: picker.property("visible"))
    assert not window.findChild(QObject, "srvrSaveConfigDialog").property("visible")
    assert send({"kind": "key", "frame": fresh_frame(viewer=second), "key": "Escape"}, second) == 204
    wait_for(app, lambda: not picker.property("visible"))

    # Exercise the real QML recall and confirm actions, with a simulated
    # winch. Desktop input never transfers or revokes a browser's control.
    # Drive the motion tick explicitly so the smoke fixture's disconnected
    # CTRL/W1P cannot cancel the target before the recall assertion.
    backend.timer.stop()
    desktop_click("mainTab0")
    assert window.property("page") == 0
    backend.setPresetPosition(0, 10.0)
    recall = next(item for item in scene_items(browser())
                  if item.isVisible() and item.property("actionKey") == "preset:recall:0")
    frame = fresh_frame()
    assert click(recall, frame) == 204
    wait_for(app, lambda: scene_item(browser(), "webSrvrView").property("pendingShortcutAction")
             == "preset:recall:0")
    assert backend.goto_target_m is None
    assert click(recall, fresh_frame(frame)) == 204
    wait_for(app, lambda: backend._goto_browser == first and backend.goto_target_m is not None)
    desktop_click("mainTab2")
    assert window.property("page") == 2 and web.server.control_live(first)
    for surface in (window, browser(), browser(second)):
        check_geometry_layout(surface)
    window.resize(1280, 720)
    app.processEvents()
    check_geometry_layout(window)

    # An unrelated browser keeps polling while the initiating browser loses
    # its heartbeat. Only its own window drives the recall lease.
    deadline = time.monotonic() + 1.15
    while time.monotonic() < deadline:
        latest(second)
        QTest.qWait(125)
    assert not web.server.control_live(first) and web.server.control_live(second)
    with patch.object(backend, "_send_stop_command", wraps=backend._send_stop_command) as stop:
        with patch.object(backend, "_log", wraps=backend._log) as log:
            backend._motion_tick()
    assert stop.called and any("Browser control lost" in call.args[0] for call in log.call_args_list)
    assert backend.goto_target_m is None and not backend._goto_browser

    frame = fresh_frame(viewer=second)
    assert click("mainTab3", frame, second) == 204
    wait_for(app, lambda: window.property("page") == 3)
    assert request(port, "/srvr-web/disconnect", "POST", {}, viewer=first)[0] == 204
    assert latest(first)[0] == 410
    frame = fresh_frame(frame, second)
    assert click("monitorPdmTab", frame, second) == 204
    wait_for(app, lambda: page.property("subtab") == 0)
    window.showMinimized()
    wait_for(app, lambda: latest(second)[1].get("X-SRVR-Wait") == "window")
    assert not web.server.control_live(second)
    window.showNormal()
    fresh_frame(viewer=second)
    assert request(port, "/firmware/pdm/permit")[0] == 200
    assert request(port, "/firmware/pdm/image")[2] == authority.bundle.images["pdm"].payload
    assert request(port, "/firmware/w1p/image")[0] == 409

    latest(first, foreground=False)
    fresh_frame(viewer=second)
    browser_state = web.server._viewers[second]
    captured = browser_state.frames[-1].captured
    latest(second, foreground=False)
    assert web.server.capture_requests()[second] is None and not web.server.control_live(second)
    wait_for(app, lambda: not web._viewports[second].isVisible())
    wait_for(app, lambda: latest(second)[0] == 200 and browser_state.frames[-1].captured > captured)
    assert request(port, "/srvr-web/disconnect", "POST", {}, viewer=second)[0] == 204
    assert not web.server.viewers_active()
    reconnected = connect()
    sizes[reconnected] = (1280, 720)
    assert fresh_frame(viewer=reconnected)
    print("SRVR_LAN_UI_HTTP_QML_PASS: independent layouts and Free-D field alignment, two viewers, "
          "stale input, shared tabs, per-view focus and config dialogs, device link, per-browser recall STOP, "
          "Retina encoding, keep-alive, background pause, exposure, firmware and reconnect")


def check_geometry_layout(window):
    headings = scene_item(window, "geometryColumnHeadings")
    header_fields = [item for item in headings.childItems() if item.property("text") is not None]
    for index in range(5):
        label, *fields = scene_item(window, f"geometryPointRow{index}").childItems()
        assert label.property("text") == f"P{index + 1}"
        assert 0 < fields[0].x() - label.property("implicitWidth") < 40
        assert [field.x() for field in fields] == [field.x() for field in header_fields[1:]]
        assert [field.width() for field in fields] == [field.width() for field in header_fields[1:]]
        assert fields[-1].property("readOnly") is (index not in (0, 4))
    rows = [scene_item(window, name).childItems()
            for name in ("geometrySkateWeight", "geometryCableWeight", "geometryCableTension")]
    assert len({(value.x(), value.width(), unit.x(), unit.width()) for _, value, unit in rows}) == 1
    assert [unit.property("currentText") for _, _, unit in rows] == ["kg", "kg/100m", "kg"]


def main():
    with TemporaryDirectory() as temp:
        directory = Path(temp)
        subprocess.run(["pyside6-rcc", str(SRVR / "resources.qrc"), "-o", str(directory / "rc_resources.py")],
                       check=True)
        sys.path.insert(0, str(directory))
        import rc_resources  # noqa: F401

        app = QApplication(["test_srvr_web_runtime", "-platform", "offscreen"])
        previous = qInstallMessageHandler(
            lambda kind, context, text: print(text, file=sys.stderr)
            if "The font families specified are invalid: HelveticaNeue" not in text else None)
        authority = FirmwareAuthorityServer(SEMVER, host="127.0.0.1", port=0,
                                            bundle_dir=make_bundle(directory), legacy_ports=(0,))
        backend = HVP2PBackend(version=SEMVER[1:], smoke_test=True, firmware_bundle=authority.bundle)
        engine = QQmlApplicationEngine()
        web = WebMirror(authority.port, engine)
        backend.browser_control_live = web.server.control_live
        pdm = PdmMonitor(directory / "pdm.ini", "", smoke=True)
        wsi = WsiMonitor(directory / "wsi.ini", "", smoke=True)
        for name, obj in (("backend", backend), ("powerMonitor", pdm), ("windMonitor", wsi),
                          ("appVersion", SEMVER[1:])):
            engine.rootContext().setContextProperty(name, obj)
        engine.setInitialProperties({"webShare": web})
        try:
            engine.load(QUrl("qrc:/qml/DesktopWindow.qml"))
            window = engine.rootObjects()[0]
            window.resize(1280, 720)
            web.attach(window)
            authority.web_ui = web.server
            authority.start()
            exercise(app, window, web, authority, backend)
            window.close()
        finally:
            web.close()
            pdm.close()
            wsi.close()
            backend.shutdown()
            authority.close()
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            qInstallMessageHandler(previous)


if __name__ == "__main__":
    main()
