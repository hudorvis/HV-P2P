"""Qt bridge for the optional PDM; the HTTP worker never calls motion code."""
from http.client import HTTPException
import threading
import time

from PySide6.QtCore import QObject, Property, QSettings, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from pdm_client import DEFAULT_ADDRESS, PdmSession, lan_address


class PdmMonitor(QObject):
    addressChanged = Signal()
    summaryChanged = Signal()
    graphsChanged = Signal()

    def __init__(self, settings_path, idle_window, idle_check, bundle_note, smoke=False):
        super().__init__()
        self._settings = None if smoke else QSettings(str(settings_path), QSettings.IniFormat, self)
        address = self._settings.value("address", DEFAULT_ADDRESS, type=str) if self._settings else DEFAULT_ADDRESS
        try:
            address = lan_address(address)
        except ValueError:
            address = DEFAULT_ADDRESS
        self._config = (address, False, 0)
        self._window = idle_window
        self._idle_check = idle_check
        self._bundle_note = bundle_note
        self._summary = PdmSession(address).summary()
        self._summary["connection"] = "Offline"
        self._graphs = [[], [], [], []]
        self._published = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._refresh)
        if not smoke:
            self._timer.start()
            threading.Thread(target=self._worker, name="HVP2P-PDM", daemon=True).start()

    @Property(str, notify=addressChanged)
    def address(self):
        return self._config[0]

    @Property(str, constant=True)
    def bundleNote(self):
        return self._bundle_note

    @Property("QVariantMap", notify=summaryChanged)
    def summary(self):
        return self._summary

    @Property("QVariantList", notify=graphsChanged)
    def graphs(self):
        return self._graphs

    def _configure(self, address, active):
        _, _, generation = self._config
        self._config = (address, active, generation + 1)
        self._summary = PdmSession(address).summary()
        self._summary["connection"] = "Connecting" if active else "Offline"
        self._graphs = [[], [], [], []]
        self.summaryChanged.emit()
        self.graphsChanged.emit()
        self._wake.set()

    @Slot(str, result=str)
    def saveAddress(self, value):
        try:
            address = lan_address(value)
        except ValueError:
            return "Enter a valid Ethernet IPv4 address"
        if address != self.address:
            self._window.observe("", False)
            if self._settings:
                self._settings.setValue("address", address)
                self._settings.sync()
                if self._settings.status() != QSettings.NoError:
                    return "Could not save PDM address"
            self._configure(address, self._config[1])
            self.addressChanged.emit()
        return ""

    @Slot(bool)
    def setActive(self, active):
        if self._config[1] != active:
            self._configure(self.address, active)

    @Slot()
    def openWeb(self):
        QDesktopServices.openUrl(QUrl(f"http://{self.address}/"))

    @Slot()
    def observeSystemIdle(self):
        self._window.observe(self.address, not self._stop.is_set() and not self._bundle_note and self._idle_check())

    @Slot()
    def close(self):
        self._stop.set()
        self._window.observe("", False)
        self._wake.set()
        self._timer.stop()

    @Slot()
    def _refresh(self):
        result = self._published
        if result is None or result[0] != self._config[2]:
            return
        _, report, graphs = result
        report = dict(report)
        age = time.monotonic() - report["last_rx"]
        if not report["online"]:
            report["connection"] = "Offline"
        elif not report["fresh"] or age > max(2.5, 2.5 * report["period"] / 1000):
            report["connection"] = "Stale data"
        else:
            report["connection"] = "Live"
        if report != self._summary:
            self._summary = report
            self.summaryChanged.emit()
        if graphs is not self._graphs:
            self._graphs = graphs
            self.graphsChanged.emit()

    def _worker(self):
        generation = -1
        session = None
        while not self._stop.is_set():
            address, active, requested = self._config
            if not active:
                self._wake.wait(0.5)
                self._wake.clear()
                continue
            if generation != requested:
                generation, session = requested, PdmSession(address)
                graphs = [[], [], [], []]
                poll_at = draw_at = 0.0
                graph_state = None
            now = time.monotonic()
            if now >= poll_at:
                try:
                    interval = session.poll()
                except (OSError, ValueError, HTTPException, KeyError, TypeError):
                    session.online = False
                    interval = 1.0
                poll_at = now + interval
                self._published = generation, session.summary(), graphs
                if session.online:
                    session.service_labels_and_clock()
            if session.online and session.history_needed and time.monotonic() >= session.history_retry:
                session.history_page()
            if time.monotonic() >= draw_at:
                state = session.timeline, session.timeline.count, session.cursor, session.offsets, session.period
                if state != graph_state:
                    graphs = session.timeline.graph(session.offsets, session.period)
                    graph_state = state
                draw_at = time.monotonic() + 1.0
            self._published = generation, session.summary(), graphs
            self._wake.wait(0.05)
            self._wake.clear()
