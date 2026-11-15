"""Capture the live SRVR QML window and apply permitted input on the Qt thread."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import ipaddress
import logging
import time

from PySide6.QtCore import (QBuffer, QByteArray, QCoreApplication, QEvent, QFile, QIODevice,
                            QObject, QPoint, QPointF, Property, QSize, Qt, QTimer, Signal, Slot)
from PySide6.QtGui import QImage, QInputMethodEvent, QKeyEvent, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtNetwork import QNetworkInterface
from PySide6.QtQuick import QQuickWindow

from srvr_web import LAN_RANGES, POINT_ACTIONS, WEB_PREFIX, WebUi

LEFT = Qt.MouseButton.LeftButton
NO_BUTTON = Qt.MouseButton.NoButton
NO_MOD = Qt.KeyboardModifier.NoModifier
CAPTURE_INTERVAL = 0.18
KEY_MAP = {
    "Backspace": Qt.Key.Key_Backspace, "Delete": Qt.Key.Key_Delete, "Enter": Qt.Key.Key_Return,
    "Escape": Qt.Key.Key_Escape, "Tab": Qt.Key.Key_Tab, "Backtab": Qt.Key.Key_Backtab,
    "ArrowLeft": Qt.Key.Key_Left, "ArrowRight": Qt.Key.Key_Right, "ArrowUp": Qt.Key.Key_Up,
    "ArrowDown": Qt.Key.Key_Down, "Home": Qt.Key.Key_Home, "End": Qt.Key.Key_End,
    "PageUp": Qt.Key.Key_PageUp, "PageDown": Qt.Key.Key_PageDown, "SelectAll": Qt.Key.Key_A,
}


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


def _jpeg(image, background):
    # The Qt Quick content item includes the dialog overlay, with transparent
    # pixels wherever the scene normally shows the window's background.
    opaque = QImage(image.size(), QImage.Format.Format_RGB32)
    opaque.fill(background)
    painter = QPainter(opaque)
    painter.drawImage(0, 0, image)
    painter.end()
    encoded = QByteArray()
    buffer = QBuffer(encoded)
    if buffer.open(QIODevice.OpenModeFlag.WriteOnly) and opaque.save(buffer, "JPEG", 87):
        return bytes(encoded)
    return b""


class WebMirror(QObject):
    browserEditingChanged = Signal()

    def __init__(self, port, parent=None):
        super().__init__(parent)
        assets = {
            "/": _read_asset(":/web/index.html"),
            WEB_PREFIX + "app.css": _read_asset(":/web/app.css"),
            WEB_PREFIX + "app.js": _read_asset(":/web/app.js"),
        }
        self.server = WebUi(port, assets)
        self.server.set_networks(_lan_networks())
        self._window = None
        self._input_viewer = ""
        self._editing_viewer = ""
        self._last_capture = 0.0
        self._last_network_check = time.monotonic()
        self._grab = None
        self._capture_info = None
        self._pending = None
        self._encoder = ThreadPoolExecutor(max_workers=1, thread_name_prefix="HVP2P-Screen")
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self._idle = True

    def attach(self, window):
        if not isinstance(window, QQuickWindow):
            raise TypeError("SRVR Web UI requires the Qt Quick main window")
        self._window = window
        self._window.installEventFilter(self)
        self._timer.setInterval(250)
        self._timer.start()

    @Property(bool, notify=browserEditingChanged)
    def browserEditing(self):
        return bool(self._editing_viewer)

    @Slot(result=str)
    def inputViewer(self):
        return self._input_viewer

    @Slot()
    def close(self):
        self._timer.stop()
        self.server.close()
        self._encoder.shutdown(wait=False, cancel_futures=True)

    def _set_editing_viewer(self, viewer):
        changed = bool(self._editing_viewer) != bool(viewer)
        self._editing_viewer = viewer
        if changed:
            self.browserEditingChanged.emit()

    def eventFilter(self, watched, event):
        if self._input_viewer:
            return False
        kind = event.type()
        if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick,
                    QEvent.Type.MouseButtonRelease):
            self.server.desktop_input(event.buttons() != NO_BUTTON)
        elif kind == QEvent.Type.TouchBegin:
            self.server.desktop_input(True)
        elif kind in (QEvent.Type.TouchEnd, QEvent.Type.TouchCancel, QEvent.Type.UngrabMouse,
                      QEvent.Type.WindowDeactivate):
            self.server.desktop_input(False)
        elif kind in (QEvent.Type.KeyPress, QEvent.Type.Wheel, QEvent.Type.Resize,
                      QEvent.Type.InputMethod):
            self.server.desktop_input()
        else:
            return False
        self._set_editing_viewer("")
        return False

    def _tick(self):
        window = self._window
        now = time.monotonic()
        if now - self._last_network_check >= 3:
            self.server.set_networks(_lan_networks())
            self._last_network_check = now

        if self._editing_viewer and (window.isActive() or not self.server.control_live(self._editing_viewer)):
            self._set_editing_viewer("")

        idle = not self.server.viewers_active()
        if idle != self._idle:
            self._idle = idle
            self._timer.setInterval(250 if idle else 40)
        visible = (window.isVisible() and window.isExposed() and
                   window.visibility() != QQuickWindow.Visibility.Minimized)
        self.server.surface(visible=visible)
        self._finish_encode()

        generation = self.server.capture_generation()
        if generation is None:
            return
        for _ in range(4):
            action = self.server.next_input()
            if action is None:
                break
            if action.frame.size == (window.width(), window.height()):
                self._deliver(action)

        if self._grab is None and self._pending is None and now - self._last_capture >= CAPTURE_INTERVAL:
            source = (window.width(), window.height())
            target = QSize(*source)
            if target.width() > 1680 or target.height() > 1050:
                target.scale(1680, 1050, Qt.AspectRatioMode.KeepAspectRatio)
            self._last_capture = time.monotonic()
            self._capture_info = generation, source, self._last_capture
            grab = window.contentItem().grabToImage(target)
            if grab is not None and grab.data() is not None:
                self._grab = grab
                grab.ready.connect(self._image_ready)

    def _image_ready(self):
        image = self._grab.image()
        self._grab = None
        generation, size, captured = self._capture_info
        if not image.isNull() and generation == self.server.capture_generation():
            future = self._encoder.submit(_jpeg, image, self._window.color())
            self._pending = generation, size, captured, future

    def _finish_encode(self):
        if self._pending is None:
            return
        generation, size, captured, future = self._pending
        if not future.done():
            return
        self._pending = None
        try:
            jpeg = future.result()
        except Exception:
            logging.getLogger(__name__).exception("SRVR Web UI could not encode a frame")
            return
        if jpeg:
            self.server.publish(generation, size, captured, jpeg)

    def _point(self, normalized):
        x, y = normalized
        return QPointF(x * (self._window.width() - 1), y * (self._window.height() - 1))

    def _mouse(self, kind, point, button=NO_BUTTON, held=NO_BUTTON):
        screen_pos = QPointF(self._window.mapToGlobal(point.toPoint()))
        event = QMouseEvent(kind, point, screen_pos, button, held, NO_MOD)
        QCoreApplication.sendEvent(self._window, event)

    def _focus_item(self):
        # An exposed SRVR window can receive browser input while another app
        # on the host has the OS keyboard focus.
        active = self._window.activeFocusItem()
        if active:
            return active
        item = self._window.contentItem()
        while item.isFocusScope():
            focused = item.scopedFocusItem()
            if focused is None or not focused.isVisible() or not focused.isEnabled():
                break
            item = focused
        return item

    def _deliver(self, action):
        window = self._window
        kind, value = action.kind, action.value
        self._input_viewer = action.viewer
        try:
            if not window.isActive() and (kind in POINT_ACTIONS or kind in ("text", "key")):
                self._set_editing_viewer(action.viewer)
            if kind == "leave":
                QCoreApplication.sendEvent(window, QEvent(QEvent.Type.Leave))
            elif kind == "text":
                focus = self._focus_item()
                if focus and focus.metaObject().indexOfProperty("inputMethodComposing") >= 0:
                    event = QInputMethodEvent()
                    event.setCommitString(value)
                    QCoreApplication.sendEvent(focus, event)
            elif kind == "key":
                key, shift = value
                mods = Qt.KeyboardModifier.ShiftModifier if shift else NO_MOD
                if key == "SelectAll":
                    # Qt maps the system's command key to ControlModifier.
                    mods = Qt.KeyboardModifier.ControlModifier
                receiver = window if window.activeFocusItem() else self._focus_item()
                if receiver is not window and key in ("Tab", "Backtab"):
                    forward = key == "Tab"
                    reason = Qt.FocusReason.TabFocusReason if forward else Qt.FocusReason.BacktabFocusReason
                    receiver.nextItemInFocusChain(forward).forceActiveFocus(reason)
                    return
                for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                    QCoreApplication.sendEvent(receiver, QKeyEvent(event_type, KEY_MAP[key], mods))
            elif kind == "wheel":
                points, delta = value
                point = self._point(points[0])
                screen = QPointF(window.mapToGlobal(point.toPoint()))
                event = QWheelEvent(point, screen, QPoint(), QPoint(0, delta), NO_BUTTON, NO_MOD,
                                    Qt.ScrollPhase.NoScrollPhase, False)
                QCoreApplication.sendEvent(window, event)
            else:
                points = [self._point(pos) for pos in value]
                self._mouse(QEvent.Type.MouseMove, points[0])
                if kind == "hover":
                    return
                # A browser gesture arrives complete. No button remains held
                # between requests, even if the network drops mid-gesture.
                press = QEvent.Type.MouseButtonDblClick if kind == "double" else QEvent.Type.MouseButtonPress
                self._mouse(press, points[0], LEFT, LEFT)
                for point in points[1:]:
                    self._mouse(QEvent.Type.MouseMove, point, NO_BUTTON, LEFT)
                self._mouse(QEvent.Type.MouseButtonRelease, points[-1], LEFT)
        finally:
            self._input_viewer = ""
