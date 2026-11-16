"""Render browser-sized SRVR views and deliver permitted input on the Qt thread."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import ipaddress
import logging
import time

from PySide6.QtCore import (QBuffer, QByteArray, QCoreApplication, QEvent, QFile, QIODevice,
                            QMetaObject, QObject, QPoint, QPointF, QSize, Qt, QTimer, QUrl, Signal, Slot)
from PySide6.QtGui import QImage, QInputMethodEvent, QKeyEvent, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtNetwork import QNetworkInterface
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickWidgets import QQuickWidget

from srvr_web import LAN_RANGES, WEB_PREFIX, WebUi

LEFT = Qt.MouseButton.LeftButton
NO_BUTTON = Qt.MouseButton.NoButton
NO_MOD = Qt.KeyboardModifier.NoModifier
CAPTURE_INTERVAL = 0.18
INTERACTIVE_INTERVAL = 0.06
INTERACTIVE_SECONDS = 0.35
MAX_FRAME_EDGE = 4096
MAX_FRAME_PIXELS = 3840 * 2160
KEY_MAP = {
    "Backspace": Qt.Key.Key_Backspace, "Delete": Qt.Key.Key_Delete, "Enter": Qt.Key.Key_Return,
    "Escape": Qt.Key.Key_Escape, "Tab": Qt.Key.Key_Tab, "Backtab": Qt.Key.Key_Backtab,
    "ArrowLeft": Qt.Key.Key_Left, "ArrowRight": Qt.Key.Key_Right, "ArrowUp": Qt.Key.Key_Up,
    "ArrowDown": Qt.Key.Key_Down, "Home": Qt.Key.Key_Home, "End": Qt.Key.Key_End,
    "PageUp": Qt.Key.Key_PageUp, "PageDown": Qt.Key.Key_PageDown, "SelectAll": Qt.Key.Key_A,
}


class BrowserViewport(QQuickWidget):
    def __init__(self, engine, navigation, web):
        super().__init__(engine, None)
        self.render_error = ""
        self.sceneGraphError.connect(self._scene_graph_error)
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.quickWindow().setObjectName("srvrBrowserWindow")
        self.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.setInitialProperties({"navigation": navigation, "webShare": web})
        self.setSource(QUrl("qrc:/qml/WebViewport.qml"))
        self.requested = None
        self.last_capture = 0.0
        self.interactive_until = 0.0

    def _scene_graph_error(self, _error, message):
        self.render_error = message

    def fit(self, viewport):
        width, height, density = viewport
        # Render at the viewer's physical pixel density, with a bounded GPU
        # target per viewer. The hidden widget itself follows the host DPR.
        scale = min(density / 100, MAX_FRAME_EDGE / max(width, height),
                    (MAX_FRAME_PIXELS / (width * height)) ** 0.5)
        host_density = self.devicePixelRatioF()
        size = QSize(max(2, round(width * scale / host_density)),
                     max(2, round(height * scale / host_density)))
        layout_scale = min(4096 / max(width, height), max(1.0, 1672 / width, 941 / height))
        self.rootObject().setProperty("layoutWidth", width * layout_scale)
        self.resize(size)
        self.show()
        if self.requested != viewport:
            self.requested = viewport
            self.last_capture = 0.0

    def dismiss_file_picker(self):
        # Qt's file dialogs can keep a scoped focus item without active focus
        # in a window that never takes the host's keyboard focus.
        for name in ("srvrSaveConfigDialog", "srvrLoadConfigDialog", "srvrLogDestination"):
            dialog = self.rootObject().findChild(QObject, name)
            if dialog is not None and dialog.property("visible"):
                return QMetaObject.invokeMethod(dialog, "reject")
        return False


def _lan_networks():
    flags = QNetworkInterface.InterfaceFlag
    networks = {"127.0.0.1": ipaddress.IPv4Network("127.0.0.0/8")}
    for interface in QNetworkInterface.allInterfaces():
        if not interface.flags() & flags.IsUp or interface.flags() & flags.IsLoopBack:
            continue
        for entry in interface.addressEntries():
            try:
                host = ipaddress.IPv4Address(entry.ip().toString())
            except ValueError:
                continue
            if entry.prefixLength() >= 1 and any(host in private for private in LAN_RANGES):
                networks[str(host)] = ipaddress.IPv4Network((host, entry.prefixLength()), strict=False)
    return dict(sorted(networks.items()))


def _read_asset(path):
    file = QFile(path)
    if not file.open(QIODevice.OpenModeFlag.ReadOnly):
        raise OSError(f"Could not read SRVR Web UI resource {path}")
    return bytes(file.readAll())


def _png(image, background):
    # The Qt Quick content item includes the dialog overlay, with transparent
    # pixels wherever the scene normally shows the window's background.
    opaque = QImage(image.size(), QImage.Format.Format_RGB32)
    # Qt paints an image in its logical size. Both rasters must use the same
    # device-pixel ratio or a Retina grab occupies only the top-left of the PNG.
    opaque.setDevicePixelRatio(image.devicePixelRatio())
    opaque.fill(background)
    painter = QPainter(opaque)
    painter.drawImage(0, 0, image)
    painter.end()
    encoded = QByteArray()
    buffer = QBuffer(encoded)
    # Use fast lossless compression so thin strokes and coloured text survive.
    if buffer.open(QIODevice.OpenModeFlag.WriteOnly) and opaque.save(buffer, "PNG", 85):
        return bytes(encoded)
    return b""


class WebMirror(QObject):
    _work_ready = Signal()

    def __init__(self, port, parent=None):
        super().__init__(parent)
        assets = {
            "/": _read_asset(":/web/index.html"),
            WEB_PREFIX + "app.css": _read_asset(":/web/app.css"),
            WEB_PREFIX + "app.js": _read_asset(":/web/app.js"),
        }
        self._closed = False
        self.server = WebUi(port, assets, wake=self._wake)
        self.server.set_networks(_lan_networks())
        self._engine = parent
        self._desktop = None
        self._viewports = {}
        self._input_viewer = ""
        self._last_network_check = time.monotonic()
        self._pending = None
        self._encoder = ThreadPoolExecutor(max_workers=1, thread_name_prefix="HVP2P-Screen")
        self._timer = QTimer(self)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._tick)
        self._work_ready.connect(self._tick, Qt.ConnectionType.QueuedConnection)
        self._idle = True

    def attach(self, window):
        if not isinstance(window, QQuickWindow):
            raise TypeError("SRVR Web UI requires the Qt Quick main window")
        self._desktop = window
        self._desktop.installEventFilter(self)
        self._timer.setInterval(250)
        self._timer.start()

    @Slot(result=str)
    def inputViewer(self):
        return self._input_viewer

    @Slot(QUrl, result=bool)
    def openDeviceWeb(self, url):
        if not self._input_viewer:
            return False
        self.server.open_device_web(self._input_viewer, url.toString())
        return True

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        self.server.close()
        for viewport in self._viewports.values():
            viewport.close()
            viewport.deleteLater()
        self._viewports.clear()
        self._encoder.shutdown(wait=False, cancel_futures=True)

    def _wake(self):
        if not self._closed:
            self._work_ready.emit()

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick,
                    QEvent.Type.MouseButtonRelease):
            self.server.desktop_input(event.buttons() != NO_BUTTON)
        elif kind == QEvent.Type.TouchBegin:
            self.server.desktop_input(True)
        elif kind in (QEvent.Type.TouchEnd, QEvent.Type.TouchCancel, QEvent.Type.UngrabMouse,
                      QEvent.Type.WindowDeactivate):
            self.server.desktop_input(False)
        elif kind in (QEvent.Type.KeyPress, QEvent.Type.Wheel, QEvent.Type.InputMethod):
            self.server.desktop_input()
        else:
            return False
        return False

    @Slot()
    def _tick(self):
        if self._closed or self._desktop is None:
            return
        window = self._desktop
        now = time.monotonic()
        if now - self._last_network_check >= 3:
            self.server.set_networks(_lan_networks())
            self._last_network_check = now

        visible = (window.isVisible() and window.isExposed() and
                   window.visibility() != QQuickWindow.Visibility.Minimized)
        self.server.surface(visible=visible)
        self._finish_encode()

        requests = self.server.capture_requests()
        for viewer, viewport in tuple(self._viewports.items()):
            if viewer not in requests:
                viewport.close()
                viewport.deleteLater()
                del self._viewports[viewer]
            elif requests[viewer] is None:
                viewport.hide()
            elif viewport.requested != requests[viewer] or not viewport.isVisible():
                viewport.fit(requests[viewer])

        active = {viewer: size for viewer, size in requests.items() if size is not None}
        idle = not active
        if idle != self._idle:
            self._idle = idle
            self._timer.setInterval(250 if idle else 25)
        if idle:
            return
        for _ in range(4):
            action = self.server.next_input()
            if action is None:
                break
            viewport = self._viewports.get(action.viewer)
            if viewport is None or not viewport.isVisible():
                continue
            target = viewport.quickWindow()
            if action.frame.size == (target.width(), target.height()):
                self._deliver(viewport, action)
                viewport.interactive_until = now + INTERACTIVE_SECONDS

        if self._pending is None:
            self._capture_next(active, now)

    def _capture_next(self, active, now):
        def next_capture(viewer):
            viewport = self._viewports.get(viewer)
            if viewport is None:
                return 0.0
            interval = INTERACTIVE_INTERVAL if now < viewport.interactive_until else CAPTURE_INTERVAL
            return viewport.last_capture + interval

        viewer = min(active, key=next_capture)
        if next_capture(viewer) > now:
            return
        viewport = self._viewports.get(viewer)
        if viewport is None:
            viewport = self._viewports[viewer] = BrowserViewport(
                self._engine, self._desktop.property("navigation"), self)
            if viewport.rootObject() is None:
                logging.getLogger(__name__).error("Could not load SRVR Web UI: %s", viewport.errors())
                # Prevent a missing resource from repeatedly instantiating a widget.
                self.close()
                return
            viewport.fit(active[viewer])

        target = viewport.quickWindow()
        captured = viewport.last_capture = time.monotonic()
        image = viewport.grabFramebuffer()
        if viewport.render_error:
            logging.getLogger(__name__).error("Could not render SRVR Web UI: %s", viewport.render_error)
            self.close()
            return
        if image.isNull():
            return
        future = self._encoder.submit(_png, image, self._desktop.color())
        self._pending = viewer, active[viewer], (target.width(), target.height()), captured, future
        future.add_done_callback(lambda _: self._wake())

    def _finish_encode(self):
        if self._pending is None:
            return
        viewer, viewport, size, captured, future = self._pending
        if not future.done():
            return
        self._pending = None
        try:
            png = future.result()
        except Exception:
            logging.getLogger(__name__).exception("SRVR Web UI could not encode a frame")
            return
        if png:
            self.server.publish(viewer, viewport, size, captured, png)

    @staticmethod
    def _point(window, normalized):
        x, y = normalized
        return QPointF(x * (window.width() - 1), y * (window.height() - 1))

    @staticmethod
    def _mouse(window, kind, point, button=NO_BUTTON, held=NO_BUTTON):
        screen_pos = QPointF(window.mapToGlobal(point.toPoint()))
        event = QMouseEvent(kind, point, screen_pos, button, held, NO_MOD)
        QCoreApplication.sendEvent(window, event)

    @staticmethod
    def _focus_item(window):
        active = window.activeFocusItem()
        if active:
            return active
        item = window.contentItem()
        while item.isFocusScope():
            focused = item.scopedFocusItem()
            if focused is None or not focused.isVisible() or not focused.isEnabled():
                break
            item = focused
        return item

    def _deliver(self, viewport, action):
        window = viewport.quickWindow()
        kind, value = action.kind, action.value
        self._input_viewer = action.viewer
        try:
            if kind == "leave":
                QCoreApplication.sendEvent(window, QEvent(QEvent.Type.Leave))
            elif kind == "text":
                focus = self._focus_item(window)
                if focus and focus.metaObject().indexOfProperty("inputMethodComposing") >= 0:
                    event = QInputMethodEvent()
                    event.setCommitString(value)
                    QCoreApplication.sendEvent(focus, event)
                elif value == " ":
                    # Space activates a focused Qt control when it isn't text entry.
                    self.server.desktop_input()
                    self._send_key(window if window.activeFocusItem() else focus, Qt.Key.Key_Space, NO_MOD, " ")
            elif kind == "key":
                key, shift = value
                if key == "Escape" and viewport.dismiss_file_picker():
                    return
                mods = Qt.KeyboardModifier.ShiftModifier if shift else NO_MOD
                if key == "SelectAll":
                    # Qt maps the system's command key to ControlModifier.
                    mods = Qt.KeyboardModifier.ControlModifier
                receiver = window if window.activeFocusItem() else self._focus_item(window)
                if receiver is not window and key in ("Tab", "Backtab"):
                    forward = key == "Tab"
                    reason = Qt.FocusReason.TabFocusReason if forward else Qt.FocusReason.BacktabFocusReason
                    receiver.nextItemInFocusChain(forward).forceActiveFocus(reason)
                    return
                self._send_key(receiver, KEY_MAP[key], mods)
            elif kind == "wheel":
                points, dx, dy = value
                point = self._point(window, points[0])
                screen = QPointF(window.mapToGlobal(point.toPoint()))
                event = QWheelEvent(point, screen, QPoint(), QPoint(dx, dy), NO_BUTTON, NO_MOD,
                                    Qt.ScrollPhase.NoScrollPhase, False)
                QCoreApplication.sendEvent(window, event)
            else:
                points = [self._point(window, pos) for pos in value]
                self._mouse(window, QEvent.Type.MouseMove, points[0])
                if kind == "hover":
                    return
                # A browser gesture arrives complete. No button remains held
                # between requests, even if the network drops mid-gesture.
                press = QEvent.Type.MouseButtonDblClick if kind == "double" else QEvent.Type.MouseButtonPress
                self._mouse(window, press, points[0], LEFT, LEFT)
                for point in points[1:]:
                    self._mouse(window, QEvent.Type.MouseMove, point, NO_BUTTON, LEFT)
                self._mouse(window, QEvent.Type.MouseButtonRelease, points[-1], LEFT)
        finally:
            self._input_viewer = ""

    @staticmethod
    def _send_key(receiver, key, modifiers, text=""):
        for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QCoreApplication.sendEvent(receiver, QKeyEvent(event_type, key, modifiers, text))
