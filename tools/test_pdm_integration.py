#!/usr/bin/env python3
"""Exercise optional authority and the SRVR client against PDM API fixtures."""
from contextlib import closing
from hashlib import sha256
from http.client import HTTPConnection
import gzip
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from embed_pdm_web import ASSETS
from native_build_firmware import PDM_TARGET, SEMVER, VER, make_firmware_bundle
from test_srvr_authority_server import fixture_image

ROOT = Path(__file__).resolve().parents[1]
PDM = ROOT / f"HV_P2P_PDM_v{VER}"
sys.path.insert(0, str(ROOT / f"SRVR_GitHub_v{VER}"))
from firmware_authority import AUTHORITY_PORT, LEGACY_AUTHORITY_PORT, PREVIOUS_NETWORK_PORT, FirmwareAuthorityServer, FirmwareBundle
from pdm_client import DEVICE_HTTP_PORT, LEGACY_PDM_HTTP_PORT, PdmSession, Timeline, WsiSession, parse_history_page

EPOCH = 1_794_233_000_000
HEADER = "t_ms,utc_ms,v48_1,v48_2,v24,v12\n"


def get(server, path, *, source="127.0.0.1", port=None):
    with closing(HTTPConnection("127.0.0.1", port or server.port, timeout=2, source_address=(source, 0))) as client:
        client.request("GET", path)
        response = client.getresponse()
        return response.status, response.read()


class Device:
    address = "172.20.1.110"
    live_path = "/api/voltages"
    keys = ("v48_1", "v48_2", "v24", "v12")
    role = "pdm"
    http_port = DEVICE_HTTP_PORT
    fw_update = "Current"
    def __init__(self):
        self.samples = {}
        self.now = 10_500
        self.durable = 10_000
        self.generation = 1
        self.boot = "oldboot"
        self.online = True
        self.sd = True
        self.synced = True
        self.partial = False
        self.hours = 12
        self.period = 500
        self.offset = 0.75
        self.other_offsets = [0.0] * 3
        self.actuals = [None] * 4
        self.thresholds = [dict(low=40, high=55), dict(low=40, high=55),
                           dict(low=20, high=28), dict(low=10, high=14)]
        self.calibration_writes = []
        self.names = ("Radio supply", "Brake supply", "24 V", "12 V")
        self.cursors = []
        self.clock_writes = []
        for stamp in (8500, 9000, 9500, 10000, 10500):
            self.add(stamp, None if stamp == 9500 else 47.5)

    def add(self, sample_id, voltage=47.5):
        self.now = sample_id
        self.samples[sample_id] = (sample_id, EPOCH + sample_id if self.synced else 0, voltage, 49.5, 24.0, 12.0)

    def fetch(self, address, path, **kwargs):
        assert address == self.address
        if kwargs.get("port", self.http_port) != self.http_port:
            raise ConnectionRefusedError
        if not self.online:
            raise TimeoutError("PDM absent")
        url = urlsplit(path)
        query = parse_qs(url.query)
        if url.path == self.live_path:
            after = int(query["after"][0])
            self.cursors.append(after)
            latest = self.samples[max(self.samples)]
            rows = [row for row in self.samples.values() if row[0] > after]
            data = dict(boot=self.boot, generation=self.generation, now_t=self.now,
                        now_utc_ms=EPOCH + self.now if self.synced else 0,
                        stored_through=self.durable, t=latest[0], utc_ms=latest[1],
                        sd_ok=self.sd, log_healthy=self.sd, sample_period_ms=self.period,
                        log_hours=self.hours, offset0=self.offset, recent=rows[:32],
                        gap=False, more=len(rows) > 32, fw_version=SEMVER,
                        fw_update=self.fw_update, fw_progress=0, alarms=["OK"] * len(self.keys))
            data.update(zip(self.keys, latest[2:]))
            data.update({f"offset{i}": value for i, value in enumerate(self.other_offsets, 1)})
        elif url.path == "/api/history":
            assert query["format"] == ["csv"] and query["generation"] == [str(self.generation)]
            end = int(query["end"][0])
            before = int(query["before"][0])
            ids = sorted((stamp for stamp in self.samples if stamp < before and stamp <= min(end, self.durable)),
                         reverse=True)
            rows = "".join(",".join("" if value is None else str(value) for value in self.samples[stamp]) + "\n"
                           for stamp in ids[:2])
            tail = "" if self.partial else f"#end,{ids[1] if len(ids) > 2 else 0},0\n"
            return (",".join(("t_ms", "utc_ms", *self.keys)) + "\n" + rows + tail).encode()
        elif url.path == "/api/logcfg":
            settings = kwargs.get("body")
            if settings is not None:
                self.hours = settings["log_hours"]
                self.period = settings["sample_period_ms"]
            data = dict(log_hours=self.hours, sample_period_ms=self.period)
            if settings is not None:
                data["ok"] = True
        elif url.path == "/api/names":
            data = {f"ch{index}": name for index, name in enumerate(self.names, 1)}
            if settings := kwargs.get("body"):
                data.update(settings)
                self.names = tuple(data[f"ch{index}"] for index in range(1, 5))
                data["ok"] = True
        elif url.path == "/api/calibration":
            settings = kwargs.get("body")
            if settings is not None:
                self.calibration_writes.append(settings)
                index = settings["channel"] - 1
                self.thresholds[index] = dict(low=settings["low"], high=settings["high"])
                if "actual" in settings:
                    actual = settings["actual"]
                    self.actuals[index] = actual
                    raw = self.samples[max(self.samples)][index + 2]
                    offset = actual - raw if actual is not None else 0.0
                    if index == 0:
                        self.offset = offset
                    else:
                        self.other_offsets[index - 1] = offset
            data = dict(ok=settings is not None, thresholds=self.thresholds, actuals=self.actuals)
        elif url.path == "/api/time":
            self.clock_writes.append(kwargs["body"]["utc_ms"])
            data = {"ok": True}
        else:
            raise AssertionError(path)
        if self.role != "pdm":
            data["role"] = self.role
        return json.dumps(data).encode()


class WindDevice(Device):
    address = "172.20.1.111"
    live_path = "/api/wind"
    keys = ("wind_mps",)
    role = "wsi"

    def __init__(self):
        super().__init__()
        self.names = ("Wind Speed",)
        self.offset = 0
        self.add(11_000, 7.5)
        self.durable = 10_500

    def add(self, sample_id, voltage=7.5):
        self.now = sample_id
        self.samples[sample_id] = (sample_id, EPOCH + sample_id, voltage if voltage is None else min(voltage, 7.5))


class PdmIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bundle = root / "bundle"
        self.apps = (fixture_image("CTRL"), fixture_image("W1P"), fixture_image("PDM", PDM_TARGET))
        files = []
        for index, image in enumerate(self.apps):
            path = root / f"{index}.bin"
            path.write_bytes(image)
            files.append(path)
        self.manifest = make_firmware_bundle(*files, self.bundle)

    def test_wind_history_and_independent_log_settings(self):
        power, wind = Device(), WindDevice()
        pdm = PdmSession(power.address, power.fetch)
        wsi = WsiSession(wind.address, wind.fetch)
        self.assertEqual(pdm.log_settings((6, 1000)), (6, 1000))
        self.assertEqual(wsi.log_settings((3, 2000)), (3, 2000))
        self.assertEqual(pdm.log_settings(), (6, 1000))
        self.assertEqual(wsi.log_settings(), (3, 2000))
        wsi.poll()
        for _ in range(4):
            wsi.history_page()
        self.assertEqual(wsi.summary()["voltages"], [7.5])
        self.assertGreater(wsi.timeline.count, 0)
        self.assertEqual(len(wsi.timeline.graph(wsi.offsets, wsi.period)), 1)
        with self.assertRaisesRegex(ValueError, "Expected a WSI"):
            WsiSession(power.address, power.fetch).log_settings((1, 250))
        self.assertEqual(pdm.log_settings(), (6, 1000))

    def server(self, *, legacy_ports=()):
        server = FirmwareAuthorityServer(SEMVER, host="127.0.0.1", port=0, bundle_dir=self.bundle,
                                         legacy_ports=legacy_ports)
        server.start()
        self.addCleanup(server.close)
        return server

    def test_channel_calibration_and_legacy_dashboard_migration(self):
        power = Device()
        power.http_port = LEGACY_PDM_HTTP_PORT
        pdm = PdmSession(power.address, power.fetch)
        pdm.poll()
        self.assertEqual(pdm.port, 80)
        self.assertEqual(pdm.calibration(1), dict(low=40, high=55, actual=None))
        self.assertEqual(pdm.calibration(2, dict(low=44, high=58, actual=51)),
                         dict(low=44, high=58, actual=51))
        self.assertEqual(pdm.calibration(2, dict(low=43, high=58))["actual"], 51)
        self.assertNotIn("actual", power.calibration_writes[-1])
        self.assertEqual(pdm.calibration(1), dict(low=40, high=55, actual=None))
        with self.assertRaisesRegex(ValueError, "low alarm below"):
            pdm.calibration(2, dict(low=58, high=43))
        for port in (PREVIOUS_NETWORK_PORT, DEVICE_HTTP_PORT):
            power.http_port = port
            pdm.poll()
            self.assertEqual(pdm.port, port)
        self.assertEqual(pdm.summary()["voltages"][1], 51)
        pdm.calibration(2, dict(low=43, high=58, actual=None))
        pdm.poll()
        self.assertEqual(pdm.summary()["voltages"][1], 49.5)
        with self.assertRaisesRegex(ValueError, "Select a PDM"):
            WsiSession("172.20.1.111", WindDevice().fetch).calibration(1)

    def test_long_legacy_name_is_readable_and_editable(self):
        device = Device()
        inherited_name = "Standby 48 V — " * 12
        device.names = (inherited_name, *device.names[1:])
        pdm = PdmSession(device.address, device.fetch)
        pdm.poll()
        pdm.service_labels_and_clock()
        self.assertEqual(pdm.summary()["labels"][0], inherited_name)
        self.assertEqual(pdm.channel_name(1), inherited_name)
        pdm.calibration(1, dict(low=41, high=55))
        self.assertEqual(pdm.channel_name(1), inherited_name)
        self.assertEqual(pdm.channel_name(1, "Standby 48 V"), "Standby 48 V")

    def test_pdm_optional_and_wrong_target(self):
        for problem in ("absent", "wrong manifest target", "wrong binary target", "damaged"):
            with self.subTest(problem=problem):
                self.manifest["images"]["pdm"] = dict(self.manifest["images"].get("pdm", {}),
                    file="pdm.bin", role="PDM", target=PDM_TARGET, version=SEMVER,
                    sha256=sha256(self.apps[2]).hexdigest(), size=len(self.apps[2]))
                payload = self.apps[2]
                if problem == "absent":
                    del self.manifest["images"]["pdm"]
                elif problem == "wrong manifest target":
                    self.manifest["images"]["pdm"]["target"] = "EDGEBOX_ESP100"
                elif problem == "wrong binary target":
                    payload = payload.replace(PDM_TARGET.encode(), b"X" * len(PDM_TARGET))
                    self.manifest["images"]["pdm"]["sha256"] = sha256(payload).hexdigest()
                else:
                    payload = payload[:-1] + b"X"
                (self.bundle / "pdm.bin").write_bytes(payload)
                (self.bundle / "manifest.json").write_text(json.dumps(self.manifest))
                bundle = FirmwareBundle(self.bundle, SEMVER)
                self.assertEqual(set(bundle.images), {"ctrl", "w1p"})
                self.assertEqual(bool(bundle.pdm_error), problem != "absent")
                server = self.server()
                server.w1p_gate.select_controller("127.0.0.1")
                server.w1p_gate.observe("127.0.0.1", server.w1p_gate._clock() + 3.5)
                self.assertEqual(get(server, "/firmware/pdm/manifest")[0], 404)
                self.assertEqual(get(server, "/firmware/ctrl/image"), (200, self.apps[0]))
                self.assertEqual(get(server, "/firmware/w1p/image"), (200, self.apps[1]))
                server.close()

    def test_live_idle_lease_and_independent_edgebox_routes(self):
        self.assertEqual((AUTHORITY_PORT, PREVIOUS_NETWORK_PORT, LEGACY_AUTHORITY_PORT), (5760, 5000, 5088))
        for pattern in ("HV_P2P_CTRL_EDGEBOX_*", "HV_P2P_W1P_EDGEBOX_*", "HV_P2P_PDM_*"):
            header = next(ROOT.glob(pattern)) / "HV_P2P_SRVR_Authority_OTA.h"
            self.assertIn(f"AUTHORITY_PORT = {AUTHORITY_PORT};", header.read_text())
        self.assertIn(f"DEVICE_HTTP_PORT = {DEVICE_HTTP_PORT};", (PDM / "pdm_app.cpp").read_text())
        server = self.server(legacy_ports=(0, 0))
        now = 0.0
        window = server.pdm_window
        window._clock = lambda: now
        server.w1p_gate._clock = lambda: now
        server.w1p_gate.select_controller("127.0.0.1")
        path = "/firmware/pdm"
        status, body = get(server, path + "/manifest")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["target"], PDM_TARGET)
        self.assertEqual(server.pdm_manifest_port("127.0.0.1"), server.port)
        self.assertEqual(len(server.legacy_ports), 2)
        for port in server.legacy_ports:
            self.assertEqual(get(server, path + "/manifest", port=port), (status, body))
            self.assertEqual(server.pdm_manifest_port("127.0.0.1"), port)
            self.assertEqual(get(server, path + "/image", port=port)[0], 409)
        self.assertIsNone(server.pdm_manifest_port("127.0.0.2"))
        self.assertEqual(get(server, path + "/image")[0], 409)
        for tick in range(12):
            now = tick * 0.25
            window.observe("127.0.0.1", True)
        self.assertEqual(get(server, path + "/permit")[0], 409)
        now = 3.0
        window.observe("127.0.0.1", True)
        self.assertEqual(get(server, path + "/permit"), (200, f"{SEMVER} {sha256(self.apps[2]).hexdigest()}\n".encode()))
        self.assertEqual(get(server, path + "/image"), (200, self.apps[2]))
        self.assertEqual(get(server, "/firmware/w1p/image")[0], 409)
        for port in server.legacy_ports:
            self.assertEqual(get(server, path + "/image", port=port), (200, self.apps[2]))
        self.assertEqual(get(server, path + "/image", source="127.0.0.2")[0], 409)
        now += 0.5
        self.assertEqual(get(server, path + "/permit")[0], 409)
        for tick in range(13):
            now = 4.0 + tick * 0.25
            window.observe("127.0.0.1", True)
        self.assertEqual(get(server, path + "/permit")[0], 200)
        window.observe("127.0.0.1", False)
        self.assertEqual(get(server, path + "/permit")[0], 409)
        server.w1p_gate.observe("127.0.0.1", now + 3.5)
        self.assertEqual(get(server, "/firmware/w1p/image"), (200, self.apps[1]))

    def test_history_load_during_logging_and_reboot(self):
        device = Device()
        session = PdmSession("172.20.1.110", device.fetch)
        self.assertEqual(session.poll(), 0.05)
        session.service_labels_and_clock()
        self.assertEqual(session.summary()["labels"], list(device.names))
        self.assertEqual(session.summary()["voltages"][0], 48.25)
        self.assertEqual(session.summary()["version"], SEMVER)
        session.history_page()
        self.assertTrue(session.history_needed)
        device.add(11000, 48.0)
        device.durable = 11000
        session.poll()
        self.assertEqual(device.cursors[-1], 10000)
        session.history_page()
        self.assertFalse(session.history_needed)
        self.assertEqual([row.id for row in session.timeline.after(0)], sorted(device.samples))
        self.assertIn([EPOCH + 9500, None], session.timeline.graph(session.offsets, session.period)[0])
        device.offset = -0.5
        session.poll()
        self.assertEqual(session.timeline.count, 6)
        self.assertEqual(session.summary()["voltages"][0], 47.5)
        self.assertEqual(session.timeline.graph(session.offsets, session.period)[0][0], [EPOCH + 8500, 47.0])
        device.online = False
        with self.assertRaises(TimeoutError):
            session.poll()
        session.online = False
        self.assertFalse(session.summary()["online"])
        device.online = True
        device.boot = "newboot"
        device.generation += 1
        device.synced = False
        device.add(11500)
        with patch("pdm_client.time.time_ns", return_value=(EPOCH + device.now) * 1_000_000):
            session.poll()
            session.service_labels_and_clock()
            self.assertEqual(len(device.clock_writes), 1)
            self.assertTrue(session.summary()["estimated"])
            self.assertTrue(session.history_needed)
            session.poll()
            for _ in range(3):
                session.history_page()
        self.assertFalse(session.history_needed)
        self.assertEqual([row.id for row in session.timeline.after(0)], sorted(device.samples))
        self.assertEqual(session.summary()["labels"], list(device.names))
        self.assertEqual(session.summary()["voltages"][0], 47.0)
        self.assertTrue(session.summary()["logging"])

    def test_partial_pages_and_missing_data(self):
        device = Device()
        session = PdmSession("172.20.1.110", device.fetch)
        session.poll()
        device.partial = True
        session.history_page()
        self.assertTrue(session.history_needed)
        self.assertIsNone(session.loading)
        device.partial = False
        device.sd = False
        session.history_retry = 0.0
        session.poll()
        session.history_page()
        self.assertEqual(session.summary()["history"], "SD history unavailable")
        device.now += 4000
        session.poll()
        self.assertFalse(session.summary()["fresh"])
        for invalid in ("", "#end,2,0\n", "2,0,1,2,3,4\n#end,3,0\n",
                        "2,0,1,2,3,4\n2,0,1,2,3,4\n#end,0,0\n"):
            with self.assertRaises(ValueError):
                parse_history_page((HEADER + invalid).encode(), 10)
        history = Timeline()
        for stamp, utc in ((10, 0), (20, EPOCH - 1000), (8000, 0)):
            history.add((stamp, utc, (48.0,) * 4), (0, EPOCH))
        self.assertEqual(history.graph((0, 0, 0, 0), 500)[0],
                         [[EPOCH + 10, 48.0], [EPOCH + 20, 48.0], [EPOCH + 21, None], [EPOCH + 8000, 48.0]])

    def test_firmware_embeds_the_exact_web_assets(self):
        header = (PDM / "pdm_web_assets.h").read_text()
        for filename, symbol in ASSETS.items():
            match = re.search(rf"\b{symbol}\[\] PROGMEM = \{{([^}}]+)\}};", header)
            self.assertIsNotNone(match, symbol)
            data = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-f]{2})", match[1]))
            self.assertEqual(gzip.decompress(data), (PDM / "web" / filename).read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
