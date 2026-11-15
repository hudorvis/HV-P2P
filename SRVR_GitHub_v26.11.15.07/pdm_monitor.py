"""Qt bridge for the optional PDM; the HTTP worker never calls motion code."""
from http.client import HTTPException
import math
from queue import Empty, SimpleQueue
import threading
import time

from PySide6.QtCore import QObject, Property, QSettings, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkInterface

from firmware_authority import LEGACY_AUTHORITY_PORT
from pdm_client import DEFAULT_ADDRESS, PDM_HTTP_PORT, LOG_INTERVALS, PdmSession, WsiSession, lan_address


def local_ipv4_addresses():
    return sorted({address.toString() for address in QNetworkInterface.allAddresses()
                   if address.toIPv4Address() and not address.isLoopback()})


def graph_extrema(graphs):
    extrema = []
    for points in graphs:
        # The reducer retains each minute's minimum and maximum.
        values = [value for _, value in points if value is not None]
        extrema.append({"min": min(values, default=None), "max": max(values, default=None)})
    return extrema


class PdmMonitor(QObject):
    addressChanged = Signal()
    summaryChanged = Signal()
    graphsChanged = Signal()
    logBusyChanged = Signal()
    logSettingsFinished = Signal(bool, int, int, str)
    calibrationFinished = Signal(bool, int, "QVariantMap", str)
    _firmwareCheckError = Signal(str, str)
    _settingsResult = Signal(int, str, int, "QVariantMap", str)

    session_type = PdmSession
    default_address = DEFAULT_ADDRESS

    def __init__(self, settings_path, bundle_note="", smoke=False, *, authority=None, log=None):
        super().__init__()
        self._settings_requests = SimpleQueue()
        self._log_busy = False
        self._settingsResult.connect(self._complete_settings)
        self._firmwareCheckError.connect(self._log_firmware_check_error)
        self._settings = None if smoke else QSettings(str(settings_path), QSettings.IniFormat, self)
        address = self._settings.value("address", self.default_address, type=str) if self._settings else self.default_address
        try:
            address = lan_address(address) if address or self.default_address else ""
        except ValueError:
            address = self.default_address
        self._config = (address, False, 0)
        self._bundle_note = bundle_note
        self._authority = authority
        self._role = self.session_type.role
        self._firmware_enabled = authority is not None and not bundle_note and not smoke
        self._log = log
        self._last_ota_message = ""
        self._last_firmware_check_error = ""
        self._local_addresses = []
        self._local_addresses_at = 0.0
        self._summary = self.session_type(address).summary()
        self._summary["connection"] = "Offline" if address else "Set address"
        self._graphs = [[] for _ in self.session_type.keys]
        self._published = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._refresh)
        if self._firmware_enabled:
            self._authority.select_monitor_peer(self._role, address)
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
        self._summary = self.session_type(address).summary()
        self._summary["connection"] = ("Connecting" if active else "Offline") if address else "Set address"
        self._graphs = [[] for _ in self.session_type.keys]
        self.summaryChanged.emit()
        self.graphsChanged.emit()
        self._wake.set()

    @Slot(str, result=str)
    def saveAddress(self, value):
        try:
            address = lan_address(value) if value.strip() or self.default_address else ""
        except ValueError:
            return "Enter a valid Ethernet IPv4 address"
        if address != self.address:
            if self._settings:
                self._settings.setValue("address", address)
                self._settings.sync()
                if self._settings.status() != QSettings.NoError:
                    return "Could not save device address"
            if self._firmware_enabled and not self._stop.is_set():
                self._authority.select_monitor_peer(self._role, address)
            self._configure(address, self._config[1])
            self.addressChanged.emit()
        return ""

    @Slot(bool)
    def setActive(self, active):
        if self._config[1] != active:
            self._configure(self.address, active)

    @Slot(result=QUrl)
    def webUrl(self):
        if not self.address:
            return QUrl()
        port = self._summary["port"]
        url = QUrl(f"http://{self.address}/")
        if port != 80:
            url.setPort(port)
        return url

    @Slot()
    def openWeb(self):
        url = self.webUrl()
        if not url.isEmpty():
            QDesktopServices.openUrl(url)

    @Slot()
    def close(self):
        self._stop.set()
        if self._firmware_enabled:
            self._authority.select_monitor_peer(self._role, "")
        self._wake.set()
        self._timer.stop()

    @Property(bool, notify=logBusyChanged)
    def logBusy(self):
        return self._log_busy

    def _queue_settings(self, kind, channel, settings):
        address, active, generation = self._config
        if self._log_busy or not address or not active:
            return False
        self._log_busy = True
        self.logBusyChanged.emit()
        self._settings_requests.put((generation, kind, channel, settings))
        self._wake.set()
        return True

    @Slot(result=bool)
    def loadLogSettings(self):
        return self._queue_settings("log", 0, None)

    @Slot(int, int, result=bool)
    def saveLogSettings(self, hours, period):
        if not 1 <= hours <= 12 or period not in LOG_INTERVALS:
            return False
        return self._queue_settings("log", 0, (hours, period))

    @Slot(int, result=bool)
    def loadCalibration(self, channel):
        if self.session_type.role != "pdm" or not 1 <= channel <= len(self.session_type.keys):
            return False
        return self._queue_settings("calibration", channel, None)

    @Slot(int, str, bool, float, float, bool, str, bool, result=str)
    def saveChannelSettings(self, channel, name, name_edited, low, high, actual_edited, actual_text, alarms_edited):
        if self.session_type.role != "pdm" or not 1 <= channel <= len(self.session_type.keys):
            return "Select a PDM voltage channel"
        if not -1000 <= low < high <= 1000:
            return "Enter a low alarm below the high alarm (−1000 to 1000 V)"
        if name_edited and ("\0" in name or len(name.encode("utf-8")) > 128):
            return "Channel names must fit in 128 UTF-8 bytes"
        settings = {"name": name} if name_edited else {}
        calibration = {"low": low, "high": high}
        if actual_edited:
            try:
                actual = float(actual_text) if actual_text.strip() else None
            except ValueError:
                return "Enter an actual voltage from 0 to 1000 V"
            if actual is not None and (not math.isfinite(actual) or not 0 <= actual <= 1000):
                return "Enter an actual voltage from 0 to 1000 V"
            calibration["actual"] = actual
        if alarms_edited or actual_edited:
            settings["calibration"] = calibration
        if not self._queue_settings("calibration", channel, settings):
            return "Unable to save channel settings"
        return ""

    @Slot(int, str, int, "QVariantMap", str)
    def _complete_settings(self, generation, kind, channel, result, error):
        self._log_busy = False
        self.logBusyChanged.emit()
        if generation == self._config[2]:
            if kind == "log":
                self.logSettingsFinished.emit(not error, result.get("hours", 0), result.get("period", 0), error)
            else:
                self.calibrationFinished.emit(not error, channel, result, error)

    def _ota_message(self, report):
        if self._bundle_note:
            return self._bundle_note
        phase = report["update"]
        node = self._role.upper()
        if phase == "Current" and report["version"] == self._authority.bundle.release:
            return f"{node} verified the current firmware."
        if phase not in ("Looking for SRVR", "Waiting for idle", "Firmware permit retry", "Current", "—"):
            return phase
        if report["ethernet_link"] is False or report["ethernet_ready"] is False:
            return f"{node} needs an active Ethernet link and IP for updates."
        if report["ethernet_ip"] and report["ethernet_ip"] != self.address:
            return f"Use the {node} Ethernet address {report['ethernet_ip']} for updates."

        activity = self._authority.monitor_activity(self._role, self.address)
        for kind, (port, status) in activity.items():
            if kind == "manifest":
                continue
            if status == 403:
                return f"SRVR declined the update on TCP {port}. Check the configured {node} Ethernet address."
            if kind == "image":
                return f"{node} requested the firmware image on TCP {port}."
            return f"Firmware permit granted on TCP {port}. Waiting for the {node} to request the image."
        if "manifest" in activity:
            port, _ = activity["manifest"]
            return f"Manifest served to the {node} on TCP {port}. Waiting for its permit request."

        # Older PDMs reported no separate OTA port. Their web ports identify
        # the relevant migration listener, including the original 80/5088 pair.
        port = report["authority_port"] or (LEGACY_AUTHORITY_PORT if report["port"] == PDM_HTTP_PORT else report["port"])
        if port not in (self._authority.port, *self._authority.legacy_ports):
            return f"SRVR could not open TCP {port}. Free that port and restart SRVR to update this {node}."
        target = report["authority_ip"]
        if target and self._local_addresses and target not in self._local_addresses:
            addresses = ", ".join(self._local_addresses)
            detail = (f"{node}'s saved SRVR address {target} is not assigned to this computer. "
                      f"Active SRVR IPv4 addresses are {addresses}.")
            if report["firmware_check"]:
                return detail + f" If the {node} has a saved authority, update it with SRVR_IP over USB."
            return detail + f" Set the equipment-network address with SRVR_IP in the {node}'s USB Serial Monitor."
        destination = f"{target}:{port}" if target else f"TCP {port} on the saved SRVR address"
        return (f"Awaiting a firmware request from this {node} at {destination}. "
                f"Check the {node}'s USB Serial Monitor for the OTA error and check the SRVR firewall.")

    @Slot(str, str)
    def _log_firmware_check_error(self, address, error):
        if self._log is not None and address == self.address and error != self._last_firmware_check_error:
            self._last_firmware_check_error = error
            if error:
                self._log(f"[{self._role.upper()} OTA] {address} firmware check request failed. {error}")

    @Slot()
    def _refresh(self):
        result = self._published
        if result is None or result[0] != self._config[2]:
            return
        _, report, graphs, extrema = result
        report = dict(report)
        report["extrema"] = extrema
        if self._authority is not None and report["online"]:
            release = self._authority.bundle.release
            if self._log is not None:
                detail = self._ota_message(report)
                message = f"[{self._role.upper()} OTA] {self.address} running {report['version']}, SRVR release {release}. {detail}"
                if message != self._last_ota_message:
                    self._last_ota_message = message
                    self._log(message)
            if report["update"] == "Current" and report["version"] != release:
                report["update"] = "—"
            elif report["update"] == "Waiting for idle":
                report["update"] = "Checking for update"
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
        firmware_check = self._firmware_enabled
        firmware_check_at = 0.0
        while not self._stop.is_set():
            address, active, requested = self._config
            try:
                job = self._settings_requests.get_nowait()
            except Empty:
                job = None
            if job is not None and (job[0] != requested or not active or not address):
                self._settingsResult.emit(*job[:3], {}, "Device selection changed")
                job = None
            if not (active or firmware_check) or not address:
                self._wake.wait(0.5)
                self._wake.clear()
                continue
            if generation != requested:
                generation, session = requested, self.session_type(address)
                graphs = [[] for _ in self.session_type.keys]
                extrema = graph_extrema(graphs)
                poll_at = draw_at = firmware_check_at = 0.0
                graph_state = None
            if job is not None:
                _, kind, channel, settings = job
                result = {}
                try:
                    if kind == "log":
                        hours, period = session.log_settings(settings)
                        result = {"hours": hours, "period": period}
                    elif settings is None:
                        result = session.calibration(channel, settings)
                        result["name"] = session.channel_name(channel)
                    else:
                        if "name" in settings:
                            result["name"] = session.channel_name(channel, settings["name"])
                        if "calibration" in settings:
                            result.update(session.calibration(channel, settings["calibration"]))
                    self._settingsResult.emit(requested, kind, channel, result, "")
                except (OSError, ValueError, HTTPException, LookupError, TypeError) as exc:
                    error = str(exc) or "Settings request failed"
                    if settings is not None and "name" in result:
                        error = "Channel name saved. Voltage settings failed: " + error
                    self._settingsResult.emit(requested, kind, channel, result, error)
                poll_at = 0.0
            now = time.monotonic()
            if now >= poll_at:
                try:
                    boot = session.key[0] if session.key else None
                    interval = session.poll(track_samples=active)
                    if not boot or session.key[0] != boot:
                        firmware_check_at = 0.0
                except (OSError, ValueError, HTTPException, KeyError, TypeError):
                    session.online = False
                    interval = 1.0
                poll_at = now + interval if active else time.monotonic() + 5.0
                if (firmware_check and session.online and session.meta[0].get("fw_authority_ip")
                        and now >= self._local_addresses_at):
                    self._local_addresses = local_ipv4_addresses()
                    self._local_addresses_at = now + 5.0
                self._published = generation, session.summary(), graphs, extrema
                if session.online and active:
                    session.service_labels_and_clock()
            if (firmware_check and not self._stop.is_set() and time.monotonic() >= firmware_check_at
                    and self._config[0] == address):
                firmware_check_at = time.monotonic() + 15.0
                if session.online:
                    try:
                        session.request_firmware_check()
                    except (OSError, ValueError, HTTPException) as exc:
                        self._firmwareCheckError.emit(address, str(exc))
                    else:
                        self._firmwareCheckError.emit(address, "")
                else:
                    firmware_check_at = 0.0
            if not active:
                self._wake.wait(0.25)
                self._wake.clear()
                continue
            if session.online and session.history_needed and time.monotonic() >= session.history_retry:
                session.history_page()
            if time.monotonic() >= draw_at:
                state = session.timeline, session.timeline.count, session.cursor, session.offsets, session.period
                if state != graph_state:
                    graphs = session.timeline.graph(session.offsets, session.period)
                    extrema = graph_extrema(graphs)
                    graph_state = state
                draw_at = time.monotonic() + 1.0
            self._published = generation, session.summary(), graphs, extrema
            self._wake.wait(0.05)
            self._wake.clear()


class WsiMonitor(PdmMonitor):
    session_type = WsiSession
    default_address = ""
