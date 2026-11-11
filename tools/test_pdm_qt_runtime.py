#!/usr/bin/env python3
"""Exercise the live Monitoring tab, including Qt's rendering of missing values."""
import json
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
from unittest.mock import patch

from test_pdm_integration import Device, SEMVER, WindDevice

os.environ.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_QUICK_CONTROLS_STYLE="Basic")
from PySide6.QtCore import QMetaObject, QObject, QPoint, QPointF, QUrl, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from backend import HVP2PBackend
from firmware_authority import PdmIdleWindow
from pdm_monitor import PdmMonitor, WsiMonitor

SRVR = Path(__file__).resolve().parents[1] / f"SRVR_GitHub_{SEMVER}"


class DeviceHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.respond(body=payload)

    def do_GET(self):
        self.respond()

    def respond(self, **kwargs):
        try:
            body = self.server.device.fetch(self.server.device.address, self.path, **kwargs)
        except TimeoutError:
            self.send_error(503)
            return
        self.send_response(200)
        if self.path.startswith("/api/history?"):
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            middle = len(body) // 2
            for chunk in (body[:middle], body[middle:]):
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
            return
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def wait_for(app, condition, timeout=8):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "Timed out waiting for Monitoring tab"
        app.processEvents()
        time.sleep(0.01)


def check_visible_trace(window: QQuickWindow, count=4):
    pending = [window.contentItem()]
    plots = []
    while pending:
        item = pending.pop()
        if item.objectName() == "pdmPowerTrace":
            plots.append(item)
        pending.extend(item.childItems())
    assert len(plots) == count, len(plots)
    first = min(plots, key=lambda plot: plot.mapToScene(QPointF()).y() * window.width() + plot.mapToScene(QPointF()).x())
    origin = first.mapToScene(QPointF())
    image = window.grabWindow()
    ratio = image.devicePixelRatio()
    plot = image.copy(int(origin.x() * ratio), int(origin.y() * ratio),
                      int(first.width() * ratio), int(first.height() * ratio))
    assert not plot.isNull()
    for y in range(plot.height()):
        for x in range(plot.width()):
            color = plot.pixelColor(x, y)
            if color.red() < 80 and color.green() > 170 and color.blue() > 200:
                return first
    raise AssertionError("The rail with missing readings did not draw its valid samples")


def check_hover(app, window, plot, unit, fraction):
    origin = plot.mapToScene(QPointF())
    QTest.mouseMove(window, QPoint(int(origin.x() + plot.width() * fraction), int(origin.y() + 20)))
    marker = plot.findChild(QObject, "monitorHoverMarker")
    wait_for(app, lambda: marker.property("visible"))
    assert f" {unit}  •  " in plot.findChild(QObject, "monitorHoverReadout").property("text")


def update_log_settings(app, root, old_hours, old_period, new_hours, new_period):
    periods = [250, 500, 1000, 2000]
    dialog = root.findChild(QObject, "monitorLogSettings")
    button = root.findChild(QObject, "monitorLogButton")
    assert button.property("enabled")
    assert QMetaObject.invokeMethod(button, "clicked")
    wait_for(app, lambda: dialog.property("loaded"))
    interval = root.findChild(QObject, "monitorLogInterval")
    duration = root.findChild(QObject, "monitorLogDuration")
    assert interval.property("currentIndex") == periods.index(old_period)
    assert duration.property("currentIndex") == old_hours - 1
    interval.setProperty("currentIndex", periods.index(new_period))
    duration.setProperty("currentIndex", new_hours - 1)
    assert QMetaObject.invokeMethod(root.findChild(QObject, "monitorLogApply"), "clicked")
    wait_for(app, lambda: not dialog.property("visible"))


def run(directory, server, wind_server):
    app = QGuiApplication([])
    messages = []
    qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    backend = HVP2PBackend(version=SEMVER[1:], smoke_test=True)
    engine = QQmlApplicationEngine()
    settings = directory / "pdm.ini"
    monitor = PdmMonitor(settings, PdmIdleWindow(), lambda: False, "")
    monitor.setParent(engine)
    wind = WsiMonitor(directory / "wsi.ini")
    wind.setParent(engine)
    assert wind.saveAddress(wind_server.device.address) == ""
    context = engine.rootContext()
    context.setContextProperty("backend", backend)
    context.setContextProperty("powerMonitor", monitor)
    context.setContextProperty("windMonitor", wind)
    context.setContextProperty("appVersion", SEMVER[1:])
    try:
        engine.load(QUrl("qrc:/qml/Main.qml"))
        root = engine.rootObjects()[0]
        root.resize(1280, 720)
        root.setProperty("page", 4)
        wait_for(app, lambda: monitor.summary["samples"] == len(server.device.samples) and len(monitor.graphs[0]) > 2)
        assert monitor.summary["labels"][0] == "Radio supply" and monitor.summary["connection"] == "Live"
        assert any(value is None for _, value in monitor.graphs[0])
        app.processEvents()
        plot = check_visible_trace(root)
        check_hover(app, root, plot, "V", 0.85)
        update_log_settings(app, root, 12, 500, 6, 1000)
        wait_for(app, lambda: wind.summary["samples"] >= 5 and len(wind.graphs[0]) > 2)
        page = root.findChild(QObject, "powerPage")
        page.setProperty("windSelected", True)
        app.processEvents()
        wind_plot = check_visible_trace(root, count=1)
        check_hover(app, root, wind_plot, "m/s", 0.85)
        update_log_settings(app, root, 12, 500, 3, 2000)
        assert server.device.hours == 6 and server.device.period == 1000
        assert wind_server.device.hours == 3 and wind_server.device.period == 2000
        page.setProperty("windSelected", False)
        server.device.now += 4000
        wait_for(app, lambda: monitor.summary["connection"] == "Stale data")
        server.device.online = False
        wait_for(app, lambda: monitor.summary["connection"] == "Offline")
        assert monitor.saveAddress("172.20.1.121") == "" and "172.20.1.121" in settings.read_text()
        assert monitor.saveAddress("1.2.3.999") and monitor.address == "172.20.1.121"
        root.setProperty("page", 0)
    finally:
        monitor.close()
        wind.close()
        backend.shutdown()
        del engine
    relevant = [message for message in messages if "PowerPage" in message or "PowerTrace" in message]
    assert not relevant, relevant[:8]


if __name__ == "__main__":
    with (TemporaryDirectory(prefix="hvp2p-pdm-qt-") as scratch,
          ThreadingHTTPServer(("127.0.0.1", 0), DeviceHandler) as server,
          ThreadingHTTPServer(("127.0.0.1", 0), DeviceHandler) as wind_server):
        directory = Path(scratch)
        subprocess.run(["pyside6-rcc", str(SRVR / "resources.qrc"), "-o", str(directory / "rc_resources.py")], check=True)
        sys.path.insert(0, scratch)
        import rc_resources  # noqa: F401
        server.device = Device()
        for i in range(1, 33):
            server.device.add(10500 + 500 * i, None if 12 <= i <= 17 else 47.5 + (i % 9) * 0.03)
        server.device.durable = server.device.now - 500
        wind_server.device = WindDevice()
        ports = {server.device.address: server.server_port, wind_server.device.address: wind_server.server_port}
        threading.Thread(target=server.serve_forever, daemon=True).start()
        threading.Thread(target=wind_server.serve_forever, daemon=True).start()
        try:
            with patch("pdm_client.HTTPConnection", side_effect=lambda address, port, timeout:
                       HTTPConnection("127.0.0.1", ports[address], timeout=timeout)):
                run(directory, server, wind_server)
        finally:
            server.shutdown()
            wind_server.shutdown()
    print("PDM_WSI_MONITORING_QML_HTTP_FIXTURE_PASS")
