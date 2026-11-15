"""Session and HTTP endpoints for the SRVR window on its firmware listener."""
from __future__ import annotations

import ipaddress
import json
import secrets
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlsplit

WEB_PREFIX = "/srvr-web/"
SESSION_SECONDS = 8.0
FRAME_SECONDS = 1.2
CONTROL_SECONDS = 1.0
NEXT_FRAME_WAIT = 0.25
MAX_VIEWERS = 8
LAN_RANGES = tuple(map(ipaddress.IPv4Network, (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "127.0.0.0/8",
)))
ASSET_TYPES = {
    "/": "text/html; charset=utf-8",
    WEB_PREFIX + "app.css": "text/css; charset=utf-8",
    WEB_PREFIX + "app.js": "text/javascript; charset=utf-8",
}
KEYS = frozenset(("Backspace", "Delete", "Enter", "Escape", "Tab", "Backtab",
                  "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End",
                  "PageUp", "PageDown", "SelectAll"))
POINT_ACTIONS = ("click", "double", "drag", "wheel")
FOCUS_KEYS = ("Enter", "Escape", "Tab", "Backtab", "PageUp", "PageDown")


@dataclass
class Viewer:
    host: str
    peer: str
    expires: float
    control_until: float = 0.0
    frame_requested: float = 0.0
    capture_until: float = 0.0
    waiting: bool = False
    open_url: str = ""


@dataclass(frozen=True)
class Frame:
    number: int
    size: tuple[int, int]
    captured: float


@dataclass(frozen=True)
class Input:
    frame: Frame
    kind: str
    value: object
    viewer: str

    @property
    def refreshes_view(self):
        return self.kind in POINT_ACTIONS or (self.kind == "key" and self.value[0] in FOCUS_KEYS)


def _points(points, maximum):
    if not isinstance(points, list) or not 1 <= len(points) <= maximum:
        return None
    for point in points:
        if (not isinstance(point, list) or len(point) != 2 or
                any(type(v) not in (int, float) or not 0.0 <= v <= 1.0 for v in point)):
            return None
    return tuple(tuple(point) for point in points)


def _input_value(kind, packet):
    if kind in ("hover", "click", "double", "drag", "wheel"):
        points = _points(packet.get("points"), 24 if kind == "drag" else 1)
        if points is not None:
            if kind != "wheel":
                return points
            delta = packet.get("delta")
            delta_x = packet.get("deltaX", 0)
            if all(type(value) in (int, float) and -480 <= value <= 480 for value in (delta, delta_x)):
                return points, int(delta_x), int(delta)
    elif kind == "key":
        key = packet.get("key")
        if isinstance(key, str) and key in KEYS:
            return key, packet.get("shift") is True
    elif kind == "text":
        value = packet.get("text")
        if isinstance(value, str) and 0 < len(value) <= 1024 and value.isprintable():
            return value
    elif kind == "leave":
        return ()
    return None


class WebUi:
    """Serve the same SRVR window to the LAN and track each input stream."""

    def __init__(self, port, assets, wake=None):
        self.port = port
        self.assets = assets
        self._lock = threading.Condition()
        self._wake = wake
        self._posts = threading.BoundedSemaphore(4)
        self._networks = {}
        self._visible = False
        self._closed = False
        self._viewers = {}
        self._generation = 0
        self._number = 0
        self._jpeg = None
        self._frames = deque(maxlen=24)
        self._input = deque(maxlen=16)
        self._refresh_pending = False
        self._desktop_gesture = False
        self._layout_changed = 0.0

    def _clear_input(self):
        self._input.clear()
        self._refresh_pending = False

    def _invalidate(self):
        self._generation += 1
        self._jpeg = None
        self._frames.clear()
        self._clear_input()
        self._lock.notify_all()

    def _detach(self, viewer_id):
        del self._viewers[viewer_id]
        self._input = deque((action for action in self._input if action.viewer != viewer_id),
                            maxlen=self._input.maxlen)
        self._refresh_pending = any(action.refreshes_view for action in self._input)
        if not self._viewers:
            self._invalidate()
        else:
            self._lock.notify_all()

    def _expire(self, now):
        for viewer_id, viewer in tuple(self._viewers.items()):
            if now >= viewer.expires:
                self._detach(viewer_id)

    def viewers_active(self):
        with self._lock:
            self._expire(time.monotonic())
            return bool(self._viewers)

    def _on_lan(self, host, peer):
        network = self._networks.get(host)
        address = ipaddress.IPv4Address(peer)
        return network is not None and address in network and any(address in private for private in LAN_RANGES)

    def set_networks(self, networks):
        with self._lock:
            self._networks = networks
            for viewer_id, viewer in tuple(self._viewers.items()):
                if not self._on_lan(viewer.host, viewer.peer):
                    self._detach(viewer_id)

    def close(self):
        with self._lock:
            self._closed = True
            self._viewers.clear()
            self._invalidate()

    def desktop_input(self, gesture=None):
        with self._lock:
            if gesture is not None:
                self._desktop_gesture = gesture
            if self._viewers:
                self._layout_changed = time.monotonic()
                self._clear_input()

    def surface(self, visible):
        with self._lock:
            if self._visible != visible:
                self._visible = visible
                for viewer in self._viewers.values():
                    viewer.control_until = 0.0
                self._invalidate()

    def capture_generation(self):
        with self._lock:
            now = time.monotonic()
            self._expire(now)
            if self._visible and self._capture_requested(now):
                return self._generation
            return None

    def _capture_requested(self, now):
        return any(viewer.capture_until > now for viewer in self._viewers.values())

    def publish(self, generation, size, captured, jpeg):
        with self._lock:
            now = time.monotonic()
            self._expire(now)
            if (generation == self._generation and now - captured < FRAME_SECONDS
                    and not self._refresh_pending and captured >= self._layout_changed):
                # The same rendered view can renew freshness without asking
                # browsers to decode it again. A changed layout needs a new
                # frame number even when its JPEG happens to match.
                if (self._frames and self._frames[-1].captured >= self._layout_changed
                        and self._frames[-1].size == size and self._jpeg == jpeg):
                    self._frames[-1] = Frame(self._number, size, captured)
                    return
                self._number += 1
                self._jpeg = jpeg
                self._frames.append(Frame(self._number, size, captured))
                self._lock.notify_all()

    def next_input(self):
        with self._lock:
            now = time.monotonic()
            self._expire(now)
            if self._desktop_gesture:
                return None
            while self._input:
                action = self._input.popleft()
                if action.refreshes_view:
                    self._refresh_pending = False
                viewer = self._viewers.get(action.viewer)
                if (not self._control_live(viewer, now)
                        or now - action.frame.captured >= FRAME_SECONDS
                        or action.frame.captured < self._layout_changed):
                    continue
                if action.refreshes_view:
                    self._layout_changed = now
                return action
            return None

    def _control_live(self, viewer, now):
        return self._visible and viewer is not None and now < viewer.control_until

    def control_live(self, viewer_id):
        with self._lock:
            return self._control_live(self._viewers.get(viewer_id), time.monotonic())

    def open_device_web(self, viewer_id, url):
        destination = urlsplit(url)
        if (destination.scheme != "http" or not destination.hostname or destination.username is not None
                or not url.isascii() or any(not 32 < ord(char) < 127 for char in url)):
            return False
        try:
            ipaddress.IPv4Address(destination.hostname)
        except ValueError:
            return False
        with self._lock:
            viewer = self._viewers.get(viewer_id)
            if not self._control_live(viewer, time.monotonic()):
                return False
            viewer.open_url = url
            self._lock.notify_all()
            return True

    def _local_request(self, handler, path):
        host = handler.connection.getsockname()[0]
        origin = f"http://{host}:{self.port}"
        if handler.headers.get_all("Host") != [f"{host}:{self.port}"]:
            return False
        if path not in self.assets and handler.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site"):
            return False
        if handler.command == "POST" and handler.headers.get_all("Origin") != [origin]:
            return False
        with self._lock:
            return self._on_lan(host, handler.client_address[0])

    def _viewer(self, handler, now):
        self._expire(now)
        viewer_id = handler.headers.get("X-SRVR-Viewer", "")
        viewer = self._viewers.get(viewer_id)
        if viewer and (viewer.host, viewer.peer) == (handler.connection.getsockname()[0], handler.client_address[0]):
            return viewer_id, viewer
        return "", None

    @staticmethod
    def _reply(handler, status, body=b"", content_type="text/plain; charset=utf-8", headers=(),
               keep_alive=False):
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; "
                            "style-src 'self'; connect-src 'self'; img-src 'self' blob:; "
                            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("Referrer-Policy", "no-referrer")
        if not keep_alive:
            handler.send_header("Connection", "close")
            handler.close_connection = True
        for name, value in headers:
            handler.send_header(name, value)
        handler.end_headers()
        if handler.command != "HEAD":
            handler.wfile.write(body)

    def handle(self, handler):
        path = urlsplit(handler.path).path
        handler.connection.settimeout(2.0)
        handler.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        if not self._local_request(handler, path):
            self._reply(handler, 403, b"Open SRVR using its IPv4 address on the same local network.")
        elif handler.command in ("GET", "HEAD") and (
                handler.headers.get("Transfer-Encoding")
                or handler.headers.get_all("Content-Length") not in (None, ["0"])):
            self._reply(handler, 400)
        elif handler.command in ("GET", "HEAD") and path in self.assets:
            self._reply(handler, 200, self.assets[path], ASSET_TYPES[path])
        elif handler.command == "GET" and path == WEB_PREFIX + "frame":
            self._serve_frame(handler)
        elif handler.command == "POST" and path in (WEB_PREFIX + "session", WEB_PREFIX + "input",
                                                    WEB_PREFIX + "disconnect"):
            self._post(handler, path.removeprefix(WEB_PREFIX))
        else:
            self._reply(handler, 404)

    def _serve_frame(self, handler):
        received = time.monotonic()
        foreground = handler.headers.get("X-SRVR-Foreground", "")
        wants_next = handler.headers.get("X-SRVR-Next-Frame") == "1"
        seen = handler.headers.get("X-SRVR-Frame")
        with self._lock:
            viewer_id, viewer = self._viewer(handler, received)
            if viewer is not None:
                wake = foreground != "0" and not self._capture_requested(received)
                viewer.expires = received + SESSION_SECONDS
                viewer.frame_requested = received
                viewer.capture_until = received + FRAME_SECONDS if foreground != "0" else 0.0
                viewer.control_until = (received + CONTROL_SECONDS
                                        if foreground == "1" and self._recent_frame(received) else 0.0)
            else:
                wake = False
        if wake and self._wake:
            self._wake()

        status, body, content_type, headers = 204, b"", "text/plain", ()
        with self._lock:
            if viewer is not None and wants_next and foreground != "0" and not viewer.waiting:
                viewer.waiting = True
                try:
                    self._lock.wait_for(
                        lambda: (self._viewers.get(viewer_id) is not viewer or not self._visible
                                 or viewer.open_url or self._has_new_frame(seen)),
                        timeout=NEXT_FRAME_WAIT,
                    )
                finally:
                    viewer.waiting = False
            now = time.monotonic()
            self._expire(now)
            if viewer is None or self._viewers.get(viewer_id) is not viewer:
                status = 410
            else:
                if wants_next:
                    headers = (("X-SRVR-Next-Frame", "1"),)
                if viewer.open_url:
                    headers += (("X-SRVR-Open-URL", viewer.open_url),)
                    viewer.open_url = ""
                if not self._visible:
                    headers += (("X-SRVR-Wait", "window"),)
                elif self._recent_frame(now):
                    if foreground == "1" and viewer.frame_requested == received:
                        viewer.control_until = received + CONTROL_SECONDS
                        headers += (("X-SRVR-Input", "ready"),)
                    frame = self._frames[-1]
                    if self._refresh_pending or frame.captured < self._layout_changed:
                        headers += (("X-SRVR-Wait", "frame"),)
                    else:
                        number = str(frame.number)
                        headers += (("X-SRVR-Frame", number),)
                        if seen != number:
                            status, body, content_type = 200, self._jpeg, "image/jpeg"
        self._reply(handler, status, body, content_type, headers, keep_alive=status in (200, 204))

    def _recent_frame(self, now):
        return self._visible and self._frames and now - self._frames[-1].captured < FRAME_SECONDS

    def _has_new_frame(self, seen):
        return (self._recent_frame(time.monotonic()) and not self._refresh_pending
                and self._frames[-1].captured >= self._layout_changed
                and str(self._frames[-1].number) != seen)

    def _post(self, handler, route):
        # Bound the number of request bodies and their read time.
        if not self._posts.acquire(blocking=False):
            self._reply(handler, 503)
            return
        try:
            lengths = handler.headers.get_all("Content-Length") or []
            length = int(lengths[0]) if len(lengths) == 1 and lengths[0].isdecimal() else -1
            if (handler.headers.get("Transfer-Encoding") or
                    handler.headers.get_content_type() != "application/json" or not 2 <= length <= 8192):
                self._reply(handler, 400)
                return
            payload = handler.rfile.read(length)
            if len(payload) != length:
                self._reply(handler, 400)
                return
            packet = json.loads(payload)
        except (ValueError, RecursionError, OSError):
            self._reply(handler, 400)
            return
        finally:
            self._posts.release()
        if not isinstance(packet, dict):
            self._reply(handler, 400)
        elif route == "session":
            self._connect(handler)
        else:
            self._operator_request(handler, route, packet)

    def _connect(self, handler):
        # The browser gets a transient ID automatically. It identifies the
        # origin of a recall so another viewer's heartbeat cannot sustain it.
        with self._lock:
            now = time.monotonic()
            self._expire(now)
            if self._closed or len(self._viewers) >= MAX_VIEWERS:
                viewer_id = ""
            else:
                viewer_id = secrets.token_urlsafe(18)
                self._viewers[viewer_id] = Viewer(handler.connection.getsockname()[0],
                                                  handler.client_address[0], now + SESSION_SECONDS)
        if viewer_id:
            self._reply(handler, 200, json.dumps({"viewer": viewer_id}).encode(), "application/json",
                        keep_alive=True)
        else:
            self._reply(handler, 503)

    def _operator_request(self, handler, route, packet):
        now = time.monotonic()
        headers = ()
        wake = False
        with self._lock:
            viewer_id, viewer = self._viewer(handler, now)
            if viewer is None:
                status = 410
            elif route == "disconnect":
                self._detach(viewer_id)
                status = 204
            elif not self._control_live(viewer, now):
                status = 409
            else:
                first_input = not self._input
                status, headers = self._queue_input(packet, viewer_id, now)
                wake = status == 204 and first_input
        if wake and self._wake:
            self._wake()
        self._reply(handler, status, headers=headers, keep_alive=True)

    def _queue_input(self, packet, viewer_id, now):
        kind = packet.get("kind")
        value = _input_value(kind, packet)
        number = packet.get("frame")
        frame = next((f for f in self._frames if f.number == number), None) if type(number) is int else None
        if value is None:
            return 400, ()
        if (frame is None or now - frame.captured >= FRAME_SECONDS or frame.captured < self._layout_changed
                or self._desktop_gesture or self._refresh_pending):
            return 409, ()
        if len(self._input) == self._input.maxlen:
            return 429, ()
        action = Input(frame, kind, value, viewer_id)
        self._input.append(action)
        if action.refreshes_view:
            self._refresh_pending = True
            return 204, (("X-SRVR-Input-Frame", str(self._number)),)
        return 204, ()
