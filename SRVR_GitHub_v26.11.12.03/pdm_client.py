"""Bounded LAN HTTP and history for the PDM and WSI monitoring nodes."""
from __future__ import annotations

from collections import deque
from contextlib import closing
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPException
from ipaddress import IPv4Address
import json
import math
import time
from urllib.parse import urlencode

DEFAULT_ADDRESS = "172.20.1.110"
DEVICE_HTTP_PORT = 5000
LEGACY_PDM_HTTP_PORT = 80
DEFAULT_LABELS = ("48 V #1", "48 V #2", "24 V", "12 V")
VOLTAGE_KEYS = ("v48_1", "v48_2", "v24", "v12")
LOG_INTERVALS = (250, 500, 1000, 2000)
HOUR_MS = 3_600_000
HISTORY_LIMIT = 172_800
HISTORY_PAGE_ROWS = 1536
MAX_ID = 9_007_199_254_740_990


def lan_address(value: str) -> str:
    ip = IPv4Address(value.strip())
    if ip.is_unspecified or ip.is_multicast or ip.is_reserved or ip.is_link_local:
        raise ValueError("Enter a device Ethernet IPv4 address")
    return str(ip)


def request(address: str, path: str, *, port=DEVICE_HTTP_PORT, timeout=3.0, body: dict | None = None) -> bytes:
    # No system proxy, redirect, shared socket, or retry on the motion path.
    deadline = time.monotonic() + timeout
    with closing(HTTPConnection(address, port, timeout=min(timeout, 3))) as connection:
        headers = {"Connection": "close"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection.request("GET" if body is None else "POST", path,
                           None if body is None else json.dumps(body), headers)
        socket = connection.sock
        socket.settimeout(max(0.001, deadline - time.monotonic()))
        with closing(connection.getresponse()) as response:
            if response.status != 200:
                detail = ""
                if body is not None and response.length is not None and 0 < response.length <= 1024:
                    try:
                        detail = str(json.loads(response.read()).get("error", ""))[:200]
                    except (ValueError, AttributeError):
                        pass
                raise ValueError(detail or f"Device HTTP {response.status}")
            data = bytearray()
            while not response.isclosed():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("PDM reply exceeded time limit")
                socket.settimeout(remaining)
                chunk = response.read1(8192)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > 256 * 1024:
                    raise ValueError("PDM reply exceeded size limit")
            if response.length not in (0, None):
                raise ValueError("PDM reply ended early")
            return bytes(data)


def _uint(value) -> int:
    if type(value) is str and value.isascii() and value.isdecimal() and len(value) <= 16:
        value = int(value)
    if type(value) is not int or not 0 <= value <= MAX_ID:
        raise ValueError("Invalid PDM sample or cursor")
    return value


def _voltage(value) -> float | None:
    if value is None or value == "":
        return None
    number = float(value)
    if not math.isfinite(number) or abs(number) > 10000:
        raise ValueError("Invalid PDM voltage")
    return number


def _sample(values, channels=4) -> tuple:
    if not isinstance(values, (list, tuple)) or len(values) != channels + 2:
        raise ValueError("Invalid PDM sample")
    sample_id, utc = _uint(values[0]), _uint(values[1])
    if not sample_id:
        raise ValueError("Missing PDM sample ID")
    return sample_id, utc, tuple(_voltage(value) for value in values[2:])


def parse_history_page(payload: bytes, before: int, keys=VOLTAGE_KEYS) -> tuple[list, int, int]:
    lines = payload.decode("ascii").splitlines()
    if not 2 <= len(lines) <= HISTORY_PAGE_ROWS + 2 or lines[0] != ",".join(("t_ms", "utc_ms", *keys)):
        raise ValueError("Invalid PDM history header or page size")
    trailer = lines[-1].split(",")
    if len(trailer) != 3 or trailer[0] != "#end":
        raise ValueError("Incomplete PDM history page")
    next_cursor, legacy_offset = _uint(trailer[1]), _uint(trailer[2])
    rows = []
    previous = before
    for line in lines[1:-1]:
        row = _sample(line.split(","), len(keys))
        if row[0] >= previous:
            raise ValueError("Out-of-order PDM history page")
        rows.append(row)
        previous = row[0]
    if next_cursor and (not rows or next_cursor != previous):
        raise ValueError("PDM history cursor did not advance")
    return rows, next_cursor, legacy_offset


@dataclass(frozen=True, slots=True)
class Reading:
    id: int
    when: int
    estimated: bool
    values: tuple

    def sample(self) -> tuple:
        return self.id, 0 if self.estimated else self.when, self.values


class Minute:
    def __init__(self, key):
        self.key = key
        self.rows = deque()
        self.cache = None

    def reduced(self, gap_ms, *, detailed=False):
        cache_key = gap_ms, detailed
        if self.cache is not None and self.cache[0] == cache_key:
            return self.cache[1]
        rows = list(self.rows)
        curves = []
        for channel in range(len(rows[0].values)):
            values = [row.values[channel] for row in rows]
            finite = [i for i, value in enumerate(values) if value is not None]
            selected = {0, len(rows) - 1}
            if finite:
                selected.update((min(finite, key=values.__getitem__), max(finite, key=values.__getitem__)))
            if detailed or len(rows) <= 6:
                selected.update(range(len(rows)))
            points = []
            previous = None
            for index in sorted(selected):
                if previous is not None:
                    for j in range(previous + 1, index + 1):
                        if rows[j].when - rows[j - 1].when > gap_ms or (j < index and values[j] is None):
                            points.append((rows[j - 1].when + 1, None))
                            break
                points.append((rows[index].when, values[index]))
                previous = index
            curves.append(points)
        self.cache = cache_key, curves
        return curves


class Timeline:
    def __init__(self):
        self.minutes = deque()
        self.count = 0

    def add(self, sample: tuple, anchor: tuple[int, int], *, older=False) -> bool:
        sample_id, utc, values = sample
        adjacent = None
        if self.minutes:
            adjacent = self.minutes[0].rows[0] if older else self.minutes[-1].rows[-1]
            if (older and sample_id >= adjacent.id) or (not older and sample_id <= adjacent.id):
                return False
        if self.count >= HISTORY_LIMIT:
            if older:
                return False
            self._drop_oldest()
        estimated = not utc
        when = utc or anchor[1] + sample_id - anchor[0]
        # Same chronological projection as the browser's Readings.write().
        if adjacent and ((older and (estimated or when >= adjacent.when)) or (not older and when <= adjacent.when)):
            when, estimated = adjacent.when + sample_id - adjacent.id, True
        key = when // 60_000
        edge = 0 if older else -1
        if not self.minutes or self.minutes[edge].key != key:
            (self.minutes.appendleft if older else self.minutes.append)(Minute(key))
        minute = self.minutes[edge]
        (minute.rows.appendleft if older else minute.rows.append)(Reading(sample_id, when, estimated, values))
        minute.cache = None
        self.count += 1
        return True

    def _drop_oldest(self):
        minute = self.minutes[0]
        minute.rows.popleft()
        minute.cache = None
        self.count -= 1
        if not minute.rows:
            self.minutes.popleft()

    def trim(self, anchor, hours):
        cutoff_id, cutoff_time = (value - hours * HOUR_MS for value in anchor)
        while self.minutes:
            first = self.minutes[0].rows[0]
            if first.id >= cutoff_id and first.when >= cutoff_time:
                break
            self._drop_oldest()

    def after(self, sample_id):
        # Only the recent suffix is copied when a durable snapshot finishes.
        newer = []
        for minute in reversed(self.minutes):
            for row in reversed(minute.rows):
                if row.id <= sample_id:
                    return reversed(newer)
                newer.append(row)
        return reversed(newer)

    def graph(self, offsets, period):
        gap_ms = max(6000, 4 * period)
        curves = [[] for _ in offsets]
        previous = None
        for minute in self.minutes:
            if previous is not None and minute.rows[0].when - previous > gap_ms:
                for curve in curves:
                    curve.append([previous + 1, None])
            for curve, points, offset in zip(curves, minute.reduced(gap_ms, detailed=minute is self.minutes[-1]), offsets):
                curve.extend([when, None if value is None else value + offset] for when, value in points)
            previous = minute.rows[-1].when
        return curves


@dataclass(slots=True)
class HistoryLoad:
    timeline: Timeline
    anchor: tuple[int, int]
    durable: int
    generation: int
    hours: int
    before: int
    offset: int = 0
    pages: int = 0


class PdmSession:
    """One PDM connection. Interleave live polling with durable history pages."""
    role = "pdm"
    labels_default = DEFAULT_LABELS
    keys = VOLTAGE_KEYS
    live_path = "/api/voltages"
    ports = (DEVICE_HTTP_PORT, LEGACY_PDM_HTTP_PORT)

    def __init__(self, address, fetch=request):
        self.address = lan_address(address) if address else ""
        self.fetch = fetch
        self.port = self.ports[0]
        self.labels = self.labels_default
        self.timeline = Timeline()
        self.loading = None
        self.history_needed = True
        self.history_status = f"Waiting for {self.role.upper()}"
        self.history_retry = 0.0
        self.labels_at = 0.0
        self.clock_at = 0.0
        self.key = None
        self.synced = False
        self.cursor = 0
        self.meta = None
        self.period = 500
        self.hours = 12
        self.offsets = (0.0,) * len(self.keys)
        self.latest = None
        self.last_rx = 0.0
        self.online = False
        self.legacy_version = "—"

    def json(self, path, **kwargs):
        data = json.loads(self.fetch(self.address, path, port=self.port, **kwargs))
        if not isinstance(data, dict):
            raise ValueError("Invalid PDM JSON")
        return data

    def _check_role(self, data):
        # Existing PDM firmware predates the role field.
        if data.get("role", "pdm") != self.role:
            raise ValueError(f"Expected a {self.role.upper()} response at this address")

    @staticmethod
    def _log_values(data):
        hours, period = _uint(data["log_hours"]), _uint(data["sample_period_ms"])
        if not 1 <= hours <= 12 or period not in LOG_INTERVALS:
            raise ValueError("Invalid log duration or interval")
        return hours, period

    def log_settings(self, settings=None):
        data = self.json("/api/logcfg")
        self._check_role(data)
        if settings is None:
            return self._log_values(data)
        hours, period = settings
        body = {"log_hours": hours, "sample_period_ms": period}
        self._log_values(body)
        data = self.json("/api/logcfg", body=body)
        self._check_role(data)
        if data.get("ok") is not True or self._log_values(data) != settings:
            raise ValueError("Device did not confirm the requested log settings")
        return hours, period

    def calibration(self, channel, settings=None):
        if self.role != "pdm" or not 1 <= channel <= len(self.keys):
            raise ValueError("Select a PDM voltage channel")
        path = "/api/calibration"
        index = channel - 1
        if settings is None:
            data = self.json(path)
        else:
            low, high = settings["low"], settings["high"]
            if not -1000 <= low < high <= 1000:
                raise ValueError("Enter a low alarm below the high alarm (−1000 to 1000 V)")
            actual = settings.get("actual")
            if actual is not None and not 0 <= actual <= 1000:
                raise ValueError("Enter an actual voltage from 0 to 1000 V")
            data = self.json(path, body={"channel": channel, **settings})
            if data.get("ok") is not True:
                raise ValueError("PDM did not confirm the calibration save")
        self._check_role(data)
        thresholds = data["thresholds"][index]
        result = dict(low=_voltage(thresholds["low"]), high=_voltage(thresholds["high"]),
                      actual=_voltage(data["actuals"][index]))
        if result["low"] is None or result["high"] is None or not -1000 <= result["low"] < result["high"] <= 1000:
            raise ValueError("PDM returned invalid alarm thresholds")
        if settings is not None:
            for field, expected in settings.items():
                returned = result[field]
                if expected != returned and (expected is None or returned is None
                                             or not math.isclose(expected, returned, abs_tol=0.0001)):
                    raise ValueError("PDM did not confirm the requested channel settings")
        return result

    def _live_response(self):
        path = f"{self.live_path}?after={self.cursor}"
        preferred = self.port
        try:
            return self.json(path)
        except (OSError, HTTPException) as preferred_error:
            alternate = next((port for port in self.ports if port != preferred), None)
            if alternate is None:
                raise
            self.port = alternate
            try:
                data = self.json(path)
                self._check_role(data)
            except (OSError, HTTPException, ValueError):
                self.port = preferred
                raise preferred_error from None
            return data

    def poll(self) -> float:
        data = self._live_response()
        self._check_role(data)
        boot = data.get("boot")
        if not isinstance(boot, str) or not 1 <= len(boot) <= 32:
            raise ValueError("PDM sample identity missing")
        generation = _uint(data["generation"])
        now_id, device_utc = _uint(data["now_t"]), _uint(data["now_utc_ms"])
        durable, sample_id = _uint(data["stored_through"]), _uint(data["t"])
        hours, period = self._log_values(data)
        if max(sample_id, durable) > now_id:
            raise ValueError("Invalid PDM time or log settings")
        offsets = tuple(_voltage(data.get(f"offset{i}")) or 0.0 for i in range(len(self.keys)))
        latest = _sample([sample_id, data.get("utc_ms", 0), *(data.get(key) for key in self.keys)], len(self.keys)) if sample_id else None
        recent = data.get("recent", [])
        if not isinstance(recent, list) or len(recent) > 32:
            raise ValueError("Invalid PDM recent sample list")
        rows = [_sample(row, len(self.keys)) for row in recent]
        if any(row[0] > sample_id for row in rows):
            raise ValueError("PDM recent sample is newer than live sample")
        anchor = now_id, device_utc or time.time_ns() // 1_000_000
        identity = boot, generation
        changed = identity != self.key
        if changed:
            self.key, self.cursor = identity, 0
            self.timeline = Timeline()
            self.labels_at = self.clock_at = self.history_retry = 0.0
            self.legacy_version = "—"
        if changed or hours != self.hours or bool(device_utc) != self.synced or data.get("gap") or not self.online:
            self.loading = None
            self.history_needed = True
        self.period, self.hours, self.synced, self.offsets = period, hours, bool(device_utc), offsets
        self.latest, self.meta = latest, (data, anchor, durable, generation)
        backfill = changed and 0 < durable < sample_id
        if backfill:
            # Drain samples still in the device's ring after the SD snapshot.
            self.cursor = durable
            rows = []
        elif latest and (changed or data.get("gap") or not rows):
            rows = [latest]
        more = data.get("more") is True and bool(rows) and not changed and not data.get("gap")
        for row in rows:
            if row[0] > self.cursor:
                self.timeline.add(row, anchor)
                self.cursor = row[0]
        self.timeline.trim(anchor, hours)
        self.last_rx, self.online = time.monotonic(), True
        return 0.05 if backfill or more else period / 1000

    def service_labels_and_clock(self):
        now = time.monotonic()
        if now >= self.labels_at:
            self.labels_at = now + 5.0
            try:
                names = self.json("/api/names")
                self.labels = tuple(
                    name if isinstance(name := names.get(f"ch{i+1}"), str) and 0 < len(name) <= 128 else fallback
                    for i, fallback in enumerate(self.labels_default)
                )
            except (OSError, ValueError, HTTPException):
                pass
            if self.meta and not self.meta[0].get("fw_version") and self.legacy_version == "—":
                try:
                    self.legacy_version = str(self.json("/api/self-test").get("version", "—"))[:48]
                except (OSError, ValueError, HTTPException):
                    pass
        if not self.synced and now >= self.clock_at:
            self.clock_at = now + 10
            try:
                self.json("/api/time", body={"utc_ms": time.time_ns() // 1_000_000})
            except (OSError, ValueError, HTTPException):
                pass

    def history_page(self):
        if not self.history_needed or not self.meta or time.monotonic() < self.history_retry:
            return
        data, anchor, durable, generation = self.meta
        if not data.get("sd_ok"):
            self.history_status = "SD history unavailable"
            return
        if self.loading is None:
            self.loading = HistoryLoad(Timeline(), anchor, durable, generation, self.hours, durable + 1)
        load = self.loading
        self.history_status = "Loading retained history…"
        query = urlencode(dict(format="csv", hours=load.hours, end=load.anchor[0],
                               before=load.before, offset=load.offset, generation=load.generation))
        try:
            payload = self.fetch(self.address, f"/api/history?{query}", port=self.port, timeout=23.0)
            rows, load.before, load.offset = parse_history_page(payload, load.before, self.keys)
            load.pages += 1
            if load.pages > HISTORY_LIMIT // HISTORY_PAGE_ROWS + 4:
                raise ValueError("PDM history exceeds the retained window")
            for row in rows:
                load.timeline.add(row, load.anchor, older=True)
            if not load.before:
                for row in self.timeline.after(load.durable):
                    load.timeline.add(row.sample(), anchor)
                load.timeline.trim(anchor, self.hours)
                self.timeline = load.timeline
                self.loading = None
                self.history_needed = False
                self.history_status = "Retained history loaded" if self.timeline.count else "No retained samples"
        except (OSError, ValueError, HTTPException):
            self.loading = None
            self.history_retry = time.monotonic() + 5.0
            self.history_status = "History interrupted • retrying"

    def summary(self) -> dict:
        data, anchor = self.meta[:2] if self.meta else ({}, (0, 0))
        fresh = bool(self.latest and 0 <= anchor[0] - self.latest[0] <= max(2000, 2 * self.period))
        values, when, estimated = [None] * len(self.keys), 0, False
        if self.latest:
            sample_id, utc, raw = self.latest
            values = [None if value is None else value + offset for value, offset in zip(raw, self.offsets)]
            when, estimated = utc or anchor[1] + sample_id - anchor[0], not utc
        alarms = data.get("alarms")
        if not isinstance(alarms, list) or len(alarms) != len(self.keys):
            alarms = [""] * len(self.keys)
        return dict(online=self.online, fresh=fresh, last_rx=self.last_rx, labels=list(self.labels),
                    voltages=values, alarms=alarms, when=when, estimated=estimated, period=self.period,
                    hours=self.hours, samples=self.timeline.count, history=self.history_status,
                    version=str(data.get("fw_version", self.legacy_version))[:48],
                    update=str(data.get("fw_update", "USB bootstrap required" if data and self.role == "pdm" else "—"))[:48],
                    progress=min(100, max(0, data["fw_progress"])) if type(data.get("fw_progress")) is int else 0,
                    logging=bool(data.get("log_healthy")), port=self.port,
                    authority_ip=str(data.get("fw_authority_ip", ""))[:15],
                    ethernet_ip=str(data.get("ip", ""))[:15], ethernet_ready=data.get("eth_has_ip"),
                    ethernet_link=data.get("eth_link"))


class WsiSession(PdmSession):
    """Wind node using metres per second in live readings and retained history."""

    role = "wsi"
    labels_default = ("Wind Speed",)
    keys = ("wind_mps",)
    live_path = "/api/wind"
    ports = (DEVICE_HTTP_PORT,)
