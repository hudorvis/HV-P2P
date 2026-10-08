#!/usr/bin/env python3
"""HV P2P SRVR Qt Quick backend.

This is deliberately UI-free: no Tkinter/ttk imports and no GUI widgets.
The transport/protocol constants and safety/motion behaviours are carried
forward from the supplied HV P2P SRVR v26.06.26.25 backend.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from datetime import datetime
import copy, http.client, ipaddress, json, math, os, queue, socket, struct, sys, threading, time
from urllib.parse import unquote, urlparse

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer

# Proven controller protocol / timing carried forward from v26.06.26.25
SERVER_BIND_PORT = 5000
HEARTBEAT_CODE = 0xA5
HEARTBEAT_ACK = 0x5A
CONTROL_PACKET_CODE = 0xA6
FLAG_ESTOP_PRESSED = 0x10
FLAG_CANCEL_PRESSED = 0x01
FLAG_MODE_TOGGLE = 0x02
FLAG_BATT_CHANGE_TOGGLE = 0x04
FLAG_AUX1 = 0x20
FLAG_AUX2 = 0x40
FLAG_AUX3 = 0x80
FLAG_AUX4 = 0x0100
FLAG_ADS1115_FAULT = 0x0200
# A7 carries 16-bit flags. AUX5 is a touchscreen/virtual AUX extension that is
# backward-compatible with v26.06.26.25 controllers which simply leave it clear.
FLAG_AUX5 = 0x0400
FLAG_CTRL_HMI_FAULT = 0x0800
FLAG_CTRL_FW_FAULT = 0x1000
FLAG_CAL_CANCEL = 0x2000
CTRL_RX_WINDOW_S = 0.75
CTRL_RX_MIN_PKTS = 2
JOY_DEADBAND_PCT = 5.0
WINCH_STATUS_TIMEOUT_S = 0.75
WINCH_PROBE_INTERVAL_S = 0.25
HMI_STATUS_TIMEOUT_S = 3.5
HMI_DISPLAY_MIN_CHANGE_INTERVAL_S = 0.10
CTRL_MARKER_MIN_CHANGE_INTERVAL_S = 0.05
HMI_DISPLAY_KEEPALIVE_S = 3.0
VEL_KEEPALIVE_S = 0.15  # ordinary SRVR refresh cadence; W1P watchdog remains 500 ms
VEL_BACKGROUND_REFRESH_S = 0.18  # sits behind the normal ~150 ms Qt cadence; bridges only a missed interval
VEL_REFRESH_LEASE_S = 0.22       # short producer lease; expiry stops refresh so the unchanged 500 ms W1P watchdog still wins
VEL_REFRESH_AXIS_TOL = 0.035      # raw CTRL-axis coherence window for background lease renewal
SRVR_ALIVE_INTERVAL_S = 0.25      # process/transport liveness independent of Qt window focus
FIRMWARE_BEACON_INTERVAL_S = 0.50  # release discovery/order must also be independent of the Qt event loop
FIRMWARE_RECOVERY_INTERVAL_S = 0.25 # bounded pull-fallback evaluation must also be independent of Qt
W1P_FINAL_STAGE_WAIT_S = 8.0        # short ordered W1P safe-idle attempt; CTRL-TS must not remain stranded
W1P_ACTIVE_UPDATE_WAIT_S = 60.0     # preserve CTRL -> W1P -> CTRL-TS while W1P is genuinely making update progress

# Automatic centre-drift compensation is deliberately conservative. It is a
# runtime trim only: calibration endpoints and the saved Centre capture are never
# silently rewritten. Learning is allowed only while the whole motion system is
# stationary and the raw stick is already close to the captured centre.
JOY_CENTRE_DRIFT_IDLE_S = 5.0
JOY_CENTRE_DRIFT_SAMPLE_WINDOW_S = 2.0
JOY_CENTRE_DRIFT_CAPTURE_FRAC = 0.08
JOY_CENTRE_DRIFT_STABILITY_FRAC = 0.015
JOY_CENTRE_DRIFT_MAX_FRAC = 0.03
JOY_CENTRE_DRIFT_TAU_S = 20.0

# Predictive Near/Far soft-limit envelope. The configured deceleration is
# deliberately derated so the calculation does not assume ideal braking. The
# reaction allowance covers the 25 ms SRVR loop, command transport and drive
# update latency; W1P independently enforces a matching local envelope.
PREDICTIVE_LIMIT_REACTION_S = 0.20
PREDICTIVE_LIMIT_MARGIN_M = 0.05
PREDICTIVE_LIMIT_DECEL_FACTOR = 0.75
LIMIT_STATUS_DISTANCE_M = 1.0       # operator Near/Far status window from either calibrated endpoint
RAMP_STATUS_SPEED_EPS_MPS = 0.03    # ignore stationary/noise-level feedback when reporting Ramping
CTRL_AUX_BITS = (FLAG_AUX1, FLAG_AUX2, FLAG_AUX3, FLAG_AUX4, FLAG_AUX5)


def _s24_to_int(b: bytes) -> int:
    if len(b) < 3: return 0
    v = (b[0] << 16) | (b[1] << 8) | b[2]
    return v - 0x1000000 if v & 0x800000 else v


def _u24_to_int(b: bytes) -> int:
    if len(b) < 3: return 0
    return (b[0] << 16) | (b[1] << 8) | b[2]


def _s24be(value: int) -> bytes:
    value = max(-8388608, min(8388607, int(value)))
    if value < 0: value += 1 << 24
    return bytes(((value >> 16) & 0xff, (value >> 8) & 0xff, value & 0xff))


def _u24be(value: int) -> bytes:
    value = max(0, min(0xFFFFFF, int(value)))
    return bytes(((value >> 16) & 0xff, (value >> 8) & 0xff, value & 0xff))


def _lens24be(value: int, lens_type: str) -> bytes:
    return _u24be(value) if str(lens_type).lower() == "u24" else _s24be(value)


def _freed_checksum_valid(data: bytes) -> bool:
    # Free-D D1 is 29 bytes. Byte 28 makes the low 8 bits of the complete
    # packet sum equal 0x40, matching the existing transmitter implementation.
    return len(data) >= 29 and ((sum(data[:29]) & 0xFF) == 0x40)


def _fsync_parent_directory(path: Path) -> None:
    try:
        fd = os.open(str(path.parent), os.O_RDONLY)
    except Exception:
        return
    try:
        os.fsync(fd)
    except Exception:
        pass
    finally:
        os.close(fd)


def _atomic_replace_bytes(path: Path, payload: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
    try:
        with open(temp, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
        _fsync_parent_directory(path)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except Exception:
            pass


def _atomic_write_text(path: Path, text: str, make_backup: bool = True) -> None:
    path = Path(path)
    if make_backup and path.exists():
        # The previous complete file becomes the recovery copy before the new
        # temp file is atomically renamed into place.
        _atomic_replace_bytes(path.with_suffix(path.suffix + ".bak"), path.read_bytes())
    _atomic_replace_bytes(path, str(text).encode("utf-8"))


@dataclass
class LimitPoint:
    name: str
    position_m: Optional[float] = None
    ramp_mode: str = "Distance"
    ramp_distance_m: float = 2.0
    ramp_percentage: float = 10.0

@dataclass
class WinchState:
    pos_m: Optional[float] = 0.0
    total_length_m: float = 100.0
    near_limit: LimitPoint = field(default_factory=lambda: LimitPoint("Near Limit", 0.0))
    ref_point: LimitPoint = field(default_factory=lambda: LimitPoint("Reference Point", 50.0))
    far_limit: LimitPoint = field(default_factory=lambda: LimitPoint("Far Limit", 100.0))
    estop_active: bool = True


class W1PClient(threading.Thread):
    def __init__(self, host: str, port: int, rxq: queue.Queue, log):
        super().__init__(daemon=True)
        self.host, self.port, self.rxq, self.log = host, port, rxq, log
        self.stop_evt = threading.Event()
        self.txq: queue.Queue[str] = queue.Queue(maxsize=500)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        # Normal telemetry and shutdown safety writes share one UDP socket. Keep
        # the direct fail-safe path serialized with the background TX thread.
        self._tx_lock = threading.Lock()
        self.last_seen = 0.0
        self.last_probe = 0.0
        # Non-zero VEL refresh has a short producer lease. The background UDP
        # worker may bridge brief Qt/macOS scheduling stalls, but once SRVR stops
        # renewing the lease it stops refreshing and W1P's unchanged 500 ms
        # watchdog remains the final independent stop.
        self._vel_refresh_lock = threading.Lock()
        self._vel_refresh_text = ""
        self._vel_refresh_until = 0.0
        self._vel_refresh_last_tx = 0.0
        self._vel_refresh_source_axis = None
        # Firmware-order snapshot is parsed directly in the W1P network thread.
        # The Qt timer may be delayed on macOS, but CTRL-TS final-stage gating
        # must still know whether a present W1P has converged to this SRVR.
        self._fw_snapshot_lock = threading.Lock()
        self._fw_version = ""
        self._fw_match = False
        self._fw_authority = "unknown"
        self._fw_snapshot_at = 0.0

    @property
    def connected(self):
        return self.last_seen > 0 and time.time() - self.last_seen <= WINCH_STATUS_TIMEOUT_S

    def _update_firmware_snapshot(self, line: str) -> None:
        text = str(line or "").strip()
        fields = {}
        if text.startswith("STATUS"):
            for token in text.split()[1:]:
                if "=" in token:
                    key, value = token.split("=", 1)
                    fields[key.strip()] = value.strip()
            with self._fw_snapshot_lock:
                if "FW" in fields:
                    self._fw_version = fields["FW"]
                if "FW_MATCH" in fields:
                    self._fw_match = fields["FW_MATCH"] == "1"
                if "FW_AUTH" in fields:
                    self._fw_authority = fields["FW_AUTH"]
                self._fw_snapshot_at = time.monotonic()
            return

        if text.startswith("FW_PROGRESS|"):
            for token in text.split("|")[1:]:
                if "=" in token:
                    key, value = token.split("=", 1)
                    fields[key.strip()] = value.strip()
            if str(fields.get("device", "W1P")).upper() != "W1P":
                return
            active = str(fields.get("active", "1")).lower() in ("1", "true", "on")
            phase = str(fields.get("phase", "Updating")).strip().lower()
            with self._fw_snapshot_lock:
                # Progress is intentionally not allowed to claim FW_MATCH. It
                # only proves the participating W1P is still alive in its OTA
                # stage while normal STATUS output may be paused by download.
                self._fw_match = False
                self._fw_authority = "updating" if active else ("rebooting" if phase == "complete" else phase)
                self._fw_snapshot_at = time.monotonic()
            return

    def firmware_snapshot(self):
        with self._fw_snapshot_lock:
            return (self._fw_version, bool(self._fw_match), self._fw_authority, float(self._fw_snapshot_at))

    def send(self, text: str):
        try: self.txq.put_nowait(str(text))
        except queue.Full: pass

    def arm_velocity_refresh(self, text: str, source_axis=None):
        text = str(text or "").strip()
        with self._vel_refresh_lock:
            if not text or text == "VEL 0":
                self._vel_refresh_text = ""
                self._vel_refresh_until = 0.0
                self._vel_refresh_source_axis = None
                return
            self._vel_refresh_text = text
            try:
                self._vel_refresh_source_axis = float(source_axis) if source_axis is not None else None
            except Exception:
                self._vel_refresh_source_axis = None
            self._vel_refresh_until = time.monotonic() + VEL_REFRESH_LEASE_S

    def renew_velocity_refresh_from_controller(self, source_axis, unsafe: bool = False):
        """Keep the existing non-zero VEL bridge alive only from coherent CTRL input.

        The Qt motion loop remains the producer of the actual velocity command.
        Fresh CTRL packets may only renew that command's short worker lease when
        the raw joystick has not materially moved since the command was produced.
        A safety flag or changed stick position immediately stops lease renewal,
        leaving W1P's unchanged 500 ms VEL watchdog as the independent stop.
        """
        with self._vel_refresh_lock:
            if unsafe or not self._vel_refresh_text or self._vel_refresh_source_axis is None:
                if unsafe:
                    self._vel_refresh_text = ""
                    self._vel_refresh_until = 0.0
                    self._vel_refresh_source_axis = None
                return False
            try:
                coherent = abs(float(source_axis) - float(self._vel_refresh_source_axis)) <= VEL_REFRESH_AXIS_TOL
            except Exception:
                coherent = False
            if not coherent:
                self._vel_refresh_text = ""
                self._vel_refresh_until = 0.0
                self._vel_refresh_source_axis = None
                return False
            self._vel_refresh_until = time.monotonic() + VEL_REFRESH_LEASE_S
            return True

    def clear_velocity_refresh(self):
        with self._vel_refresh_lock:
            self._vel_refresh_text = ""
            self._vel_refresh_until = 0.0
            self._vel_refresh_source_axis = None

    def emergency_stop(self):
        """Send STOP + Servo Enable inhibit immediately, bypassing any TX backlog.

        This is used only for SRVR shutdown. The independent W1P 500 ms VEL
        freshness watchdog remains unchanged as the abnormal-exit fallback.
        """
        payload = b"STOP\nSW_SRVON 0\n"
        self.clear_velocity_refresh()
        try:
            # Discard ordinary queued settings/status requests so they cannot be
            # transmitted after the shutdown safety command.
            with self.txq.mutex:
                self.txq.queue.clear()
            with self._tx_lock:
                # UDP is intentionally duplicated: the commands are idempotent
                # and this greatly reduces the chance that a single datagram loss
                # delays the stopped/braked state until a watchdog expires.
                for _ in range(3):
                    self.sock.sendto(payload, (self.host, self.port))
        except Exception as exc:
            self.log(f"[W1P SAFETY TX] {exc}")

    def reconfigure(self, host: str, port: int):
        self.host, self.port, self.last_seen = host, port, 0.0
        with self._fw_snapshot_lock:
            self._fw_version = ""
            self._fw_match = False
            self._fw_authority = "unknown"
            self._fw_snapshot_at = 0.0

    def run(self):
        while not self.stop_evt.is_set():
            try:
                while True:
                    text = self.txq.get_nowait()
                    payload = text if text.endswith("\n") else text + "\n"
                    with self._tx_lock:
                        self.sock.sendto(payload.encode("ascii", "ignore"), (self.host, self.port))
                    # Healthy SRVR operation already refreshes non-zero VEL at
                    # approximately 150 ms. Record those ordinary transmissions
                    # so the worker-side bridge stays dormant unless that cadence
                    # is actually missed (for example while macOS deprioritises
                    # the Qt GUI thread in the background).
                    if str(text).strip().startswith("VEL ") and str(text).strip() != "VEL 0":
                        with self._vel_refresh_lock:
                            self._vel_refresh_last_tx = time.monotonic()
            except queue.Empty: pass
            except Exception as exc: self.log(f"[W1P TX] {exc}")

            # Bridge only brief producer stalls. This is not a replacement for
            # W1P's 500 ms watchdog: the lease expires unless _send_velocity()
            # continues to renew the current command.
            mono_now = time.monotonic()
            refresh_text = ""
            with self._vel_refresh_lock:
                if self._vel_refresh_text and mono_now < self._vel_refresh_until and (mono_now - self._vel_refresh_last_tx) >= VEL_BACKGROUND_REFRESH_S:
                    refresh_text = self._vel_refresh_text
                    self._vel_refresh_last_tx = mono_now
                elif self._vel_refresh_text and mono_now >= self._vel_refresh_until:
                    self._vel_refresh_text = ""
                    self._vel_refresh_until = 0.0
            if refresh_text:
                try:
                    with self._tx_lock:
                        self.sock.sendto((refresh_text + "\n").encode("ascii", "ignore"), (self.host, self.port))
                except Exception as exc:
                    self.log(f"[W1P VEL REFRESH] {exc}")

            now = time.time()
            if now - self.last_probe >= WINCH_PROBE_INTERVAL_S:
                self.last_probe = now
                try:
                    with self._tx_lock:
                        self.sock.sendto(b"STATUS\n", (self.host, self.port))
                except Exception: pass
            try:
                while True:
                    data, addr = self.sock.recvfrom(4096)
                    if addr[0] != self.host: continue
                    for raw in data.decode("ascii", "ignore").splitlines():
                        line = raw.strip()
                        if line.startswith(("STATUS", "HELLO", "PONG", "OK", "ERR", "FW_PROGRESS", "W1PTS_AUX", "W1P_HMI_STATUS")):
                            self.last_seen = time.time()
                            self._update_firmware_snapshot(line)
                            try: self.rxq.put_nowait(line)
                            except queue.Full: pass
            except BlockingIOError: pass
            except Exception: pass
            time.sleep(0.015)

    def close(self):
        self.clear_velocity_refresh()
        self.stop_evt.set()
        try: self.sock.close()
        except Exception: pass


class HVP2PBackend(QObject):
    stateChanged = Signal()          # fast live telemetry / safety updates
    configChanged = Signal()         # operator-editable configuration updates
    logChanged = Signal()
    calibrationChanged = Signal()
    joystickCalibrationChanged = Signal()

    def __init__(self, version="26.10.08.03", smoke_test: bool = False, firmware_bundle=None):
        super().__init__()
        self.version = version
        self.smoke_test = bool(smoke_test)
        self._firmware_bundle = firmware_bundle
        self._legacy_fw_push_active = {"ctrl": False, "w1p": False}
        self._legacy_fw_push_last_attempt = {"ctrl": 0.0, "w1p": 0.0}
        # Modern nodes normally pull from the SRVR authority themselves.  If a
        # proven older node remains mismatched for several seconds without
        # entering its pull/update state, SRVR uses the existing verified HTTP
        # upload endpoint as a bounded fallback.  This removes any dependence on
        # a manual ESP32 reboot to start an update.
        self._fw_mismatch_since = {"ctrl": 0.0, "w1p": 0.0}
        self._fw_modern_fallback_delay_s = 2.5
        # Operator-visible coordinated firmware update state. W1P reports its
        # own authority-download progress, while the legacy SRVR bridge updates
        # the same structure for older CTRL/W1P releases. CTRL v26.10.08.03+
        # additionally reports directly to CTRL-TS while its own loop is blocked.
        self._fw_progress = {
            "ctrl": {"active": False, "phase": "Idle", "pct": 0},
            "w1p": {"active": False, "phase": "Idle", "pct": 0},
        }
        # If W1P is present when a release change is discovered, hold the final
        # CTRL-TS stage until W1P reports this exact release/match. The latch
        # survives W1P's normal OTA reboot; a genuinely absent W1P never sets it.
        self._w1p_fw_order_pending = False
        self._w1p_fw_order_pending_since = 0.0
        # After CTRL converges, allow a short W1P discovery window before the
        # final CTRL-TS stage. W1P probes every 250 ms, so 3 s is generous for a
        # healthy present node but still keeps a genuinely absent W1P bounded.
        self._w1p_fw_discovery_grace_s = 3.0
        self._w1p_fw_order_absent_timeout_s = 15.0
        # Final CTRL-TS grant is monotonic for this SRVR release once the ordered
        # preceding stages have either converged or exhausted their bounded
        # recovery window. A present W1P that cannot prove safe idle must not
        # strand the independent touchscreen update forever. Motion remains
        # fail-closed until W1P itself later converges.
        self._ctrl_ts_grant_latched = False
        self._ctrl_ts_gate_reason = "waiting_ctrl"
        self._ctrl_ts_gate_log_reason = ""
        self.started = time.time()
        # A short per-process authority session token is advertised to CTRL/W1P on
        # their existing real-time links. A new SRVR process therefore causes one
        # fail-safe manifest re-verification without any periodic blocking HTTP poll
        # inside either field node's motion loop.
        self._firmware_authority_session = f"{os.getpid():x}{time.time_ns() & 0xFFFFFFFF:x}"[-16:]
        self._last_ctrl_fw_beacon = 0.0
        self._last_w1p_fw_beacon = 0.0
        self._lock = threading.RLock()
        self._logs = deque(maxlen=1200)
        # Keep the proven plain-text log untouched for disk export while also
        # maintaining structured entries for the locked Log page filters/table.
        self._log_entries = deque(maxlen=1200)
        self._log_revision = 0
        self.state = WinchState()
        self.ctrl_ip = "172.20.1.101"
        self.w1p_ip = "172.20.1.102"
        self.w1p_reported_ip = ""
        self.w1p_port = 5000
        # CTRL now normalises the installed APEM electrical polarity at the hardware
        # boundary: physical Left=-1 and Right=+1. The user Invert option remains
        # available, but the safe/default direction is therefore Normal.
        self.reverse_joystick = False
        self.reverse_motor = False
        self.joystick_deadband_pct = JOY_DEADBAND_PCT
        # Joystick calibration maps the CTRL raw -1..+1 value onto a corrected
        # -1..+1 operator axis. Defaults are identity so existing systems behave
        # exactly as before until the wizard is completed.
        self.joystick_cal_left = -1.0
        self.joystick_cal_centre = 0.0
        self.joystick_cal_right = 1.0
        self._joystick_centre_trim_raw = 0.0
        self._joystick_centre_idle_since = 0.0
        self._joystick_centre_samples = deque(maxlen=120)
        self._joystick_centre_last_update = time.monotonic()
        self._joystick_centre_warned = False
        self.position_source = "Encoder"
        self._virtual_velocity_mps = 0.0
        self._virtual_last_tick = time.monotonic()
        self._virtual_inhibit_last_tx = 0.0
        self.ctrl_aux_assignments = [
            "Drive Mode", "Near Limit Save", "Preset 5 Recall",
            "Battery Change Mode", "Ref Point Slip",
        ]
        self.w1p_aux_assignments = [
            "Acceleration Mode", "Far Limit Recall", "Preset 2 Slip",
            "Ref Point Save", "Preset 10 Recall",
        ]
        self._limit_raw = {"near": None, "ref": None, "far": None}
        self.winch_units_per_m = 21220.7
        self.max_speed_mps = 25.0
        self.goto_speed_mps = 7.5
        self.max_accel_mps2 = 5.0
        self.max_decel_mps2 = 5.0
        self.max_crossover_mps2 = 10.0
        self.max_stop_decel_mps2 = 7.5
        self.drive_modes = [
            {"name":"Mode 1", "max_speed_mps":25.0, "goto_speed_mps":7.5, "accel_mps2":5.0, "decel_mps2":5.0, "crossover_mps2":10.0, "stop_decel_mps2":7.5},
            {"name":"Mode 2", "max_speed_mps":25.0, "goto_speed_mps":7.5, "accel_mps2":5.0, "decel_mps2":5.0, "crossover_mps2":10.0, "stop_decel_mps2":7.5},
        ]
        self.active_drive_mode = 0
        self.acceleration_mode = "Speed"
        self.battery_change_mode = False
        self._battery_change_went_outside_limits = False
        self._last_service_mode_sent = None
        self.current_speed_mps = 0.0
        self.requested_speed_mps = 0.0
        self.goto_target_m = None
        self._goto_approach_dir = 0.0
        self._goto_last_error_m = 0.0
        self._last_safety_stop_ts = 0.0
        self._safety_active_last = False
        self._safety_servo_inhibited = False
        self.last_sent_vel = 0.0
        self.last_winch_output = 0.0
        self._winch_position_accept_jump_until = 0.0
        self._winch_last_pos_accept_t = 0.0
        self._winch_last_pos_reject_log_t = 0.0
        self.winch_rs_status = "Disconnected"
        self.winch_drive_writes_enabled = False
        self.winch_sw_srvon = False
        self.winch_sw_srvon_ready = False
        self.winch_sw_srvon_ok = False
        self.winch_sw_srvon_inhibit = True
        self.winch_do2_ready_config_ok = False
        self.winch_do2_assignment = None
        self.winch_ready_output = False
        self.winch_do3_enabled_config_ok = False
        self.winch_do3_assignment = None
        self.winch_enabled_output = False
        self.winch_do4_brake_config_ok = False
        self.winch_do4_assignment = None
        self.winch_brake_released = False
        self.winch_do5_fault_config_ok = False
        self.winch_do5_assignment = None
        self.winch_fault_output = False
        self._w1p_estop = False
        self.winch_vel_watchdog_fault = False
        self.winch_service_safety_lock = False
        self._w1p_internal_safety = False
        self._w1p_boot_id = ""
        self._ctrl_estop = False
        self._srvr_estop = False
        self._not_calibrated = True
        self._ctrl_rx_times = deque(maxlen=200)
        self._ctrl_last_seen = 0.0
        self._ctrl_flags = 0
        self._ctrl_axis = 0.0
        self._mode_last = self._batt_last = False
        # A7 carries five AUX bits in this integration revision. AUX1..AUX5 are
        # touchscreen-only CTRL-TS controls; the existing 16-bit packet retains
        # backward wire compatibility while carrying the fifth virtual AUX bit.
        self._ctrl_aux_last = [False] * 5
        # Capture AUX rising edges in the UDP listener thread so touchscreen
        # commands cannot disappear merely because the Qt/UI timer stalls.
        self._ctrl_aux_rx_last = [False] * 5
        self._ctrl_aux_events = queue.Queue(maxsize=32)
        self._ctrl_aux_event_drops = 0
        self._ctrl_cal_cancel_rx_last = False
        self._ctrl_cal_cancel_pending = False
        self._ctrl_cal_cancel_last = False
        # Secondary controller/touchscreen health reporting carried forward from
        # the proven v26.06.26.25 backend. These do not replace the primary
        # joystick/W1P safety path; they drive the Setup link indicators.
        self._ctrl_ts_last_seen = 0.0
        self._ctrl_ts_connected_reported = False
        self._ctrl_ts_version = ""
        self._ctrl_ts_required_version = ""
        self._ctrl_ts_fw_state = "idle"
        self._ctrl_ts_fw_pct = 0
        self._ctrl_ts_boot_id = ""
        self._ctrl_ts_reset_reason = -1
        self._ctrl_ts_image_available = False
        self._ctrl_ts_compatible_reported = False
        self._ctrl_ts_age_ms = 999999
        # Physical RS485 activity is distinct from firmware compatibility. An old
        # CTRL-TS can exchange HELLO/update frames while ctrl_ts=0 by design.
        self._ctrl_ts_rs485_alive_reported = False
        self._ctrl_ts_grant_reported = -1
        self._ctrl_ts_poll_timeouts = 0
        self._ctrl_ts_events_rejected = 0
        self._ctrl_ts_queue_drops = 0
        self._ctrl_ts_parser_crc = 0
        self._ctrl_ts_parser_resync = 0
        self._ctrl_ts_heap_free = 0
        self._ctrl_ts_min_heap = 0
        self._ctrl_ts_psram_free = 0
        self._ctrl_ts_diag_last_log_at = 0.0
        self._ctrl_ts_diag_last_logged = (0, 0, 0, 0, 0)
        self._ctrl_ts_last_event_id = 0
        self._ctrl_ts_last_event_cmd = ""
        self._ctrl_fw_version = ""
        self._w1p_fw_version = ""
        # Firmware authority is safety state, not merely diagnostic metadata.
        # Defaults are deliberately fail-closed until a fresh status explicitly
        # reports an exact SRVR image match.
        self._ctrl_fw_match = False
        self._ctrl_fw_match_since = 0.0
        self._ctrl_fw_authority = "unknown"
        self._ctrl_fw_required = ""
        self._w1p_fw_match = False
        self._w1p_fw_authority = "unknown"
        self._w1p_status_last_seen = 0.0
        self._w1p_status_rejected = 0
        self._w1p_status_reject_last_log = 0.0
        # SRVR is authoritative for persistent W1P configuration.  W1P STATUS
        # is confirmation, not a source that may silently overwrite a freshly
        # selected operator setting after a lost UDP SET command.
        self._w1p_reported_config = {}
        self._w1p_settings_pending = set()
        self._w1p_setting_last_tx = {}
        self._w1p_setting_last_value = {}
        self._w1p_setting_last_any_tx = 0.0
        self._w1p_setting_retry_s = 0.35
        self._w1p_setting_min_gap_s = 0.04
        self._config_notify_pending = False
        self._ads1115_status_last_seen = 0.0
        self._ads1115_connected_reported = False
        self._w1p_ts_last_seen = 0.0
        self._w1p_ts_connected_reported = False
        self._w1p_ts_version = ""
        self._w1p_ts_age_ms = 999999
        # Lightweight presence/firmware/shutdown packets retain the independent
        # socket, but DSP1 display telemetry is staged onto the controller worker's
        # *bound UDP/5000 socket*. That is the exact return path already proven by
        # CTRL heartbeats. Keeping DSP1 off an unbound ephemeral source removes a
        # multi-NIC/source-route failure mode where joystick/heartbeat traffic was
        # healthy while CTRL silently rejected one-way display packets from a
        # different local source address and therefore showed its fallback HMI.
        self._ctrl_display_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._ctrl_presence_tx_lock = threading.Lock()
        self._ctrl_bound_display_lock = threading.Lock()
        self._ctrl_bound_display_pending = None
        self._ctrl_bound_marker_pending = None
        self._ctrl_bound_display_tx = 0
        self._ctrl_bound_display_tx_errors = 0
        self._ctrl_bound_marker_tx = 0
        self._ctrl_bound_marker_tx_errors = 0
        self._srvr_alive_thread = None
        self._last_ctrl_display_packet = b""
        self._last_ctrl_display_change_tx = 0.0
        self._last_ctrl_display_keepalive_tx = 0.0
        self._last_ctrl_display_build_at = 0.0
        self._last_ctrl_marker_packet = b""
        self._last_ctrl_marker_tx = 0.0
        # Cache cable profiles so two diagrams on the same page reuse one
        # calculation instead of repeating 121 sag samples per state signal.
        self._cable_profile_cache_key = None
        self._cable_profile_cache_value = []
        self._freed_profile_cache_key = None
        self._freed_profile_cache_value = []
        self._stop_evt = threading.Event()
        self._w1p_rx: queue.Queue[str] = queue.Queue(maxsize=1000)
        self.w1p = W1PClient(self.w1p_ip, self.w1p_port, self._w1p_rx, self._log)

        # Long names remain user-editable. Short names are the fixed P1..P10
        # identifiers. One global display mode is propagated to SRVR diagrams and
        # CTRL-TS so the same name style is shown everywhere.
        self.preset_names = [f"P{i}" for i in range(1,11)]
        self.preset_name_mode = "Short Names"
        self.preset_positions = [None] * 10
        self.preset_visible = [True] * 10

        # Free-D
        self.freed_input_enabled = True
        self.freed_input_bind_ip = "0.0.0.0"
        self.freed_input_port = 40001
        self.freed_output_enabled = False
        self.freed_target_ip = "172.20.1.120"
        self.freed_target_port = 40000
        self.freed_rate_hz = 50.0
        self.freed_out_fps = 0.0
        self.freed_in_fps = 0.0
        self.freed_input_last_rx = 0.0
        self.freed_in_camera_id = 1
        self.freed_in_raw = {"Cam ID":1,"Pan":0,"Tilt":0,"Roll":0,"Zoom":0,"Focus":0}
        self.freed_in = {"Cam ID":1,"Pan":0.0,"Tilt":0.0,"Roll":0.0,"Zoom":0,"Focus":0}
        self.freed_input_offsets = {"Pan":0.0,"Tilt":0.0,"Roll":0.0}
        self.freed_input_inverts = {"Pan":False,"Tilt":False,"Roll":False,"Zoom":False,"Focus":False}
        self.freed_output_offsets = {"X":0.0,"Y":0.0,"Z":0.0}
        self.freed_output_inverts = {"X":False,"Y":False,"Z":False}
        self.freed_pos_scale = 640.0
        self.freed_lens_type = "u16"
        self.freed_lens_scale_mode = "Auto"
        self.freed_lens_cal = {"zoom_wide":0.0,"zoom_tele":32767.0,"focus_near":0.0,"focus_far":32767.0}
        self._freed_lens_auto_seen = {"zoom_min":None,"zoom_max":None,"focus_min":None,"focus_max":None}
        self.geometry = [
            {"name":"P1","x":0.0,"y":0.0,"z":0.0},
            {"name":"P2","x":25.0,"y":5.0,"z":None},
            {"name":"P3","x":50.0,"y":8.0,"z":None},
            {"name":"P4","x":75.0,"y":5.0,"z":None},
            {"name":"P5","x":100.0,"y":0.0,"z":0.0},
        ]
        self.skate_weight_kg = 25.0
        self.cable_weight_kg100m = 4.5
        self.cable_tension_kg = 100.0
        self.skate_weight_unit = "kg"
        self.cable_weight_unit = "kg/100m"
        self.cable_tension_unit = "kg"
        self.highline_mode = "Single Highline"
        self._freed_in_stop = threading.Event()
        self._freed_in_sock = None
        self._freed_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._freed_out_times = deque(maxlen=240)
        self._freed_in_times = deque(maxlen=120)
        self._last_freed_tx = 0.0

        # Calibration popup state
        self.calibration_open = False
        self.calibration_type = "Limit"
        self.calibration_step = 0
        self.calibration_title = "Set Near Limit"
        # Live/pending values shown by the Limit Calibration wizard. Near is
        # canonicalised to 0.00 m when captured; Far establishes the span and
        # Ref is captured inside that span. Keeping these separate from the
        # applied calibration makes the in-progress wizard observable without
        # pretending an unfinished calibration is already authoritative.
        self._limit_cal_pending = {"near": None, "ref": None, "far": None}
        self._limit_cal_capture = {"near_raw": None, "far_raw": None, "ref_raw": None,
                                   "near_pos": None, "far_pos": None, "ref_pos": None,
                                   "pending_reverse_motor": None}

        # Three-step joystick calibration wizard. Temporary captures are kept
        # separate until Right is accepted, so Cancel never alters calibration.
        self.joystick_calibration_open = False
        self.joystick_calibration_step = 0
        self.joystick_calibration_title = "Set Joystick Left"
        self.joystick_calibration_error = ""
        self._joystick_cal_pending = {"left": None, "centre": None, "right": None}
        # After a joystick-calibration wizard closes, motion stays inhibited until
        # the operator releases the stick back into the configured deadband. This
        # prevents the final full-Right capture (or a Cancel while displaced) from
        # immediately becoming a live motion command on the next 50 ms tick.
        self._joystick_neutral_required = False

        self._config_path = self._config_file_path()
        self._config_write_queue = queue.Queue(maxsize=1)
        self._config_write_stop = threading.Event()
        self._config_write_thread = None
        self._config_async_ready = False
        self._load_config()
        self._saved_freed_snapshot = self._freed_snapshot()
        self._saved_setup_snapshot = self._setup_snapshot()
        # Setup and Free-D retain mirror dictionaries for stable QML bindings, but
        # edits are committed to live state and persistent config immediately. Text
        # fields commit on Enter/focus loss; buttons/combos commit on activation.
        self._setup_draft = copy.deepcopy(self._saved_setup_snapshot)
        self._freed_draft = copy.deepcopy(self._saved_freed_snapshot)
        self._pending_import_config = None
        self._pending_import_setup_handled = True
        self._pending_import_freed_handled = True
        self._setup_draft_dirty = False
        self._freed_draft_dirty = False
        self.w1p.reconfigure(self.w1p_ip, self.w1p_port)
        if not self.smoke_test:
            self._config_async_ready = True
            self._config_write_thread = threading.Thread(target=self._config_write_worker, name="HVP2P-ConfigWriter", daemon=True)
            self._config_write_thread.start()
            self.w1p.start()
            self._start_controller_listener()
            self._start_srvr_alive_worker()
            self._start_freed_input()
            self._sync_w1p_settings()

        self.timer = QTimer(self)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._log("[SRVR] Qt Quick backend ready")

    @staticmethod
    def _app_data_dir(platform_name: str | None = None, env: dict | None = None, home: Path | None = None) -> Path:
        """Return the native per-user SRVR data directory for the active desktop OS.

        macOS intentionally retains the historical Application Support location.
        Windows uses LOCALAPPDATA (falling back to APPDATA, then AppData/Local).
        Linux/other Unix follows XDG_CONFIG_HOME when present.  Keeping this in a
        deterministic helper also lets CI prove each platform mapping without
        changing the runner's real profile.
        """
        platform_name = str(platform_name or sys.platform).lower()
        env = os.environ if env is None else env
        home = Path.home() if home is None else Path(home)
        if platform_name.startswith("win"):
            base = env.get("LOCALAPPDATA") or env.get("APPDATA")
            return (Path(base) if base else home / "AppData" / "Local") / "HV P2P SRVR"
        if platform_name == "darwin":
            return home / "Library" / "Application Support" / "HV P2P SRVR"
        xdg = env.get("XDG_CONFIG_HOME")
        return (Path(xdg) if xdg else home / ".config") / "HV P2P SRVR"

    def _config_file_path(self):
        home = self._app_data_dir()
        try:
            home.mkdir(parents=True, exist_ok=True)
        except Exception:
            home = Path.home()
        return home / "config.json"

    @staticmethod
    def _classify_log_message(msg: str):
        """Return (level, source, view, clean_message) without changing saved logs."""
        text = str(msg).strip()
        source = "SYSTEM"
        clean = text
        if text.startswith("[") and "]" in text:
            tag, clean = text[1:].split("]", 1)
            clean = clean.strip()
            tag_u = tag.upper()
            if "FREE-D" in tag_u:
                source = "FREE-D"
            elif "W1P" in tag_u:
                source = "W1P"
            elif "CTRL" in tag_u or "ADS1115" in tag_u:
                source = "CTRL"
            elif "CALIBRATION" in tag_u:
                source = "CAL"
            elif "CONFIG" in tag_u:
                source = "CONFIG"
            else:
                source = "SYSTEM"

        hay = (text + " " + clean).lower()
        if any(k in hay for k in ("fault", "failed", "failure", "error", "estop", "e-stop", "overcurrent")):
            level = "FAULT"
        elif any(k in hay for k in ("warn", "warning", "rejected", "timeout", "mismatch", "disconnected")):
            level = "WARN"
        else:
            level = "INFO"

        if source == "FREE-D":
            view = "Free-D"
        elif source in ("CTRL", "W1P") or any(k in hay for k in ("udp", "network", "rs485", "connected", "link")):
            view = "Network"
        elif any(k in hay for k in ("estop", "e-stop", "fault", "safety", "limit", "servo", "brake")):
            view = "Safety"
        else:
            view = "Live"
        return level, source, view, clean

    def _log(self, msg):
        raw = str(msg).strip()
        line = f"{time.strftime('%H:%M:%S')}  {raw}"
        level, source, view, clean = self._classify_log_message(raw)
        entry = {
            "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "level": level,
            "source": source,
            "view": view,
            "message": clean or raw,
        }
        with self._lock:
            self._logs.append(line)
            self._log_entries.append(entry)
            self._log_revision += 1
        self.logChanged.emit()

    # --- controller ---
    def _start_controller_listener(self):
        threading.Thread(target=self._controller_worker, name="HVP2P-CTRL-RX", daemon=True).start()

    def _start_srvr_alive_worker(self):
        """Keep CTRL liveness *and firmware discovery* independent of Qt.

        v26.10.05.10 kept SRVR_ALIVE on this background worker but still emitted
        SRVR_FW/firmware-order beacons from the 25 ms Qt timer. On macOS the UI
        event loop can be delayed while the app is backgrounded, leaving CTRL
        apparently connected yet unaware that a newer SRVR release exists. A
        manual CTRL reboot then appeared to "fix" the update because boot-time
        authority discovery does not depend on Qt.

        This worker now owns both presence and lightweight firmware beacons. It
        performs no HTTP/flash work and no motion decisions. CTRL/W1P remain the
        nodes that verify/download the immutable authority image, and shutdown
        still sets _stop_evt before SRVR_OFFLINE is sent under the same CTRL TX
        lock, so no background beacon can resurrect a closed desktop session.
        """
        if self._srvr_alive_thread and self._srvr_alive_thread.is_alive():
            return
        self._srvr_alive_thread = threading.Thread(target=self._srvr_alive_worker, name="HVP2P-SRVR-Comms", daemon=True)
        self._srvr_alive_thread.start()

    def _srvr_alive_worker(self):
        next_alive = 0.0
        next_fw = 0.0
        next_recovery = 0.0
        while not self._stop_evt.is_set():
            now = time.monotonic()
            if now >= next_alive:
                next_alive = now + SRVR_ALIVE_INTERVAL_S
                target = str(self.ctrl_ip or "").strip()
                if target:
                    try:
                        with self._ctrl_presence_tx_lock:
                            if not self._stop_evt.is_set():
                                self._ctrl_display_sock.sendto(b"SRVR_ALIVE\n", (target, SERVER_BIND_PORT))
                    except Exception:
                        pass

            # Release discovery and the CTRL->W1P->CTRL-TS coordinator grant are
            # safety/update transport, not UI presentation. Service them here so
            # window focus, rendering load or a stalled Qt timer cannot be a
            # prerequisite for automatic firmware convergence.
            if now >= next_fw and not self._stop_evt.is_set():
                next_fw = now + FIRMWARE_BEACON_INTERVAL_S
                try:
                    self._send_ctrl_firmware_beacon(force=True)
                except Exception as exc:
                    self._log(f"[FW COORD] CTRL beacon worker recovered from error: {exc}")
                try:
                    self._send_w1p_firmware_beacon(force=True)
                except Exception as exc:
                    self._log(f"[FW COORD] W1P beacon worker recovered from error: {exc}")

            # The primary modern path is node-pull after SRVR_FW. Recovery from a
            # lost/missed pull used to be evaluated only by the Qt timer, which
            # meant a field node could remain stale until a manual reboot. Keep
            # the existing HTTP push fallback, but evaluate its eligibility from
            # this communications worker as well. The upload itself already runs
            # on its own daemon thread and each ESP32 re-proves a safe service
            # state before accepting flash writes.
            if now >= next_recovery and not self._stop_evt.is_set():
                next_recovery = now + FIRMWARE_RECOVERY_INTERVAL_S
                try:
                    self._service_firmware_recovery_background()
                except Exception as exc:
                    self._log(f"[FW COORD] recovery worker recovered from error: {exc}")

            self._stop_evt.wait(0.05)

    def _stage_ctrl_display_datagram(self, packet: bytes, target: str) -> bool:
        """Coalesce DSP1 onto the proven bound CTRL UDP/5000 return path.

        Only the latest display snapshot matters. The controller worker owns the
        bound socket, so staging rather than sending from the Qt thread preserves
        one socket owner and guarantees the same source address/port as heartbeat
        ACKs that CTRL already accepts.
        """
        if not packet or not target or self._stop_evt.is_set():
            return False
        with self._ctrl_bound_display_lock:
            self._ctrl_bound_display_pending = (bytes(packet), (str(target), SERVER_BIND_PORT))
        return True

    def _flush_ctrl_display_datagram(self, sock) -> None:
        pending = None
        with self._ctrl_bound_display_lock:
            if self._ctrl_bound_display_pending is not None:
                pending = self._ctrl_bound_display_pending
                self._ctrl_bound_display_pending = None
        if pending is None or self._stop_evt.is_set():
            return
        payload, target = pending
        try:
            sock.sendto(payload, target)
            self._ctrl_bound_display_tx += 1
        except Exception:
            self._ctrl_bound_display_tx_errors += 1
            # Preserve the latest snapshot for the next worker pass unless a newer
            # one has already replaced it. Never block motion/safety on display IO.
            with self._ctrl_bound_display_lock:
                if self._ctrl_bound_display_pending is None and not self._stop_evt.is_set():
                    self._ctrl_bound_display_pending = pending


    def _stage_ctrl_marker_datagram(self, packet: bytes, target: str) -> bool:
        """Coalesce the latest compact position marker onto bound UDP/5000.

        This is intentionally separate from DSP1 so live position sampling can be
        faster without increasing the large display/status packet cadence.
        """
        if not packet or not target or self._stop_evt.is_set():
            return False
        with self._ctrl_bound_display_lock:
            self._ctrl_bound_marker_pending = (bytes(packet), (str(target), SERVER_BIND_PORT))
        return True

    def _flush_ctrl_marker_datagram(self, sock) -> None:
        pending = None
        with self._ctrl_bound_display_lock:
            if self._ctrl_bound_marker_pending is not None:
                pending = self._ctrl_bound_marker_pending
                self._ctrl_bound_marker_pending = None
        if pending is None or self._stop_evt.is_set():
            return
        payload, target = pending
        try:
            sock.sendto(payload, target)
            self._ctrl_bound_marker_tx += 1
        except Exception:
            self._ctrl_bound_marker_tx_errors += 1
            with self._ctrl_bound_display_lock:
                if self._ctrl_bound_marker_pending is None and not self._stop_evt.is_set():
                    self._ctrl_bound_marker_pending = pending

    def _controller_worker(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", SERVER_BIND_PORT))
            # Service staged DSP1 at up to 40 Hz without creating a second owner
            # for the bound socket. CTRL heartbeats still receive immediate ACKs.
            sock.settimeout(0.025)
        except OSError as exc:
            self._log(f"[SRVR] Controller UDP bind failed 0.0.0.0:{SERVER_BIND_PORT} -> {exc}")
            return
        last_heartbeat_fw_reply = 0.0
        while not self._stop_evt.is_set():
            self._flush_ctrl_display_datagram(sock)
            self._flush_ctrl_marker_datagram(sock)
            try: data, addr = sock.recvfrom(2048)
            except socket.timeout: continue
            except OSError: break
            if self._stop_evt.is_set(): break
            if not data or (self.ctrl_ip and addr[0] != self.ctrl_ip): continue
            if data[0] == HEARTBEAT_CODE:
                try: sock.sendto(bytes([HEARTBEAT_ACK]), addr)
                except Exception: pass
                # Redundant release discovery on the proven CTRL heartbeat return
                # path. The standalone SRVR_FW worker remains the normal path, but
                # a lost/unroutable one-way beacon must never require a manual CTRL
                # reboot. Old/current CTRL firmware already understands SRVR_FW, so
                # this second datagram invalidates stale authority immediately while
                # using the same bound socket/path that just delivered HEARTBEAT_ACK.
                now_mono = time.monotonic()
                if (now_mono - last_heartbeat_fw_reply) >= FIRMWARE_BEACON_INTERVAL_S:
                    last_heartbeat_fw_reply = now_mono
                    try:
                        fw_packet = (
                            f"SRVR_FW|version={self._current_firmware_version()}|"
                            f"session={self._firmware_authority_session}|"
                            f"ts_allowed={1 if self._ctrl_ts_update_allowed_safe() else 0}\n"
                        ).encode("ascii", "ignore")
                        sock.sendto(fw_packet, addr)
                    except Exception as exc:
                        self._log(f"[FW COORD] heartbeat-return beacon recovered from error: {exc}")
                continue
            try:
                line_text = data.decode("ascii", "ignore").strip()
            except Exception:
                line_text = ""
            if line_text.startswith("HMI_STATUS|"):
                try:
                    self._handle_ctrl_hmi_status(line_text)
                except Exception as exc:
                    self._log(f"[CTRL] HMI_STATUS handler recovered from error: {exc}")
                continue
            if line_text.startswith("FW_PROGRESS|"):
                fields = self._parse_pipe_fields(line_text)
                if str(fields.get("device", "CTRL")).strip().upper() == "CTRL":
                    active = str(fields.get("active", "1")).strip().lower() in ("1", "true", "on")
                    self._set_fw_progress("ctrl", active, fields.get("phase", "Updating"), fields.get("pct", 0))
                continue
            msg = self._parse_control_packet(data)
            if not msg: continue
            now = time.time()
            flags_now = int(msg[0])
            # Edge-capture runs in the UDP receive thread, independently of the
            # Qt event loop. The UI/motion timer later drains this persistent
            # queue, so a 120-300 ms CTRL pulse cannot be missed during a UI stall.
            for aux_i, aux_bit in enumerate(CTRL_AUX_BITS):
                pressed = bool(flags_now & aux_bit)
                if pressed and not self._ctrl_aux_rx_last[aux_i]:
                    try:
                        # Preserve the joystick sample from the same CTRL packet
                        # as the AUX rising edge. Calibration must not later use a
                        # different axis value merely because the Qt thread stalled.
                        self._ctrl_aux_events.put_nowait((aux_i, float(msg[1]), now))
                    except queue.Full:
                        self._ctrl_aux_event_drops += 1
                self._ctrl_aux_rx_last[aux_i] = pressed
            cal_cancel_now = bool(flags_now & FLAG_CAL_CANCEL)
            if cal_cancel_now and not self._ctrl_cal_cancel_rx_last:
                self._ctrl_cal_cancel_pending = True
            self._ctrl_cal_cancel_rx_last = cal_cancel_now

            # The motion command itself still belongs to _motion_tick().  This
            # receive-thread path only keeps its short background refresh lease
            # alive while independent CTRL packets prove that the physical stick
            # has not moved and CTRL has no safety/interface fault. That prevents
            # a Qt rendering pause during a long Limit Calibration move from
            # manufacturing a VEL-watchdog stop, without relaxing W1P's 500 ms
            # watchdog or allowing a changed joystick to keep a stale command alive.
            refresh_unsafe = bool(flags_now & (
                FLAG_ESTOP_PRESSED | FLAG_ADS1115_FAULT |
                FLAG_CTRL_HMI_FAULT | FLAG_CTRL_FW_FAULT
            ))
            try:
                self.w1p.renew_velocity_refresh_from_controller(msg[1], unsafe=refresh_unsafe)
            except Exception:
                pass

            with self._lock:
                self._ctrl_last_seen = now
                self._ctrl_rx_times.append(now)
                self._ctrl_flags = flags_now
                self._ctrl_axis = msg[1]
        try: sock.close()
        except Exception: pass

    @staticmethod
    def _parse_control_packet(data):
        try:
            if data[0] == CONTROL_PACKET_CODE and len(data) >= 8:
                flags = int(data[1]); joy = struct.unpack("!f", data[2:6])[0]
            elif data[0] == 0xA7 and len(data) >= 10:
                flags = (int(data[1]) << 8) | int(data[2]); joy = struct.unpack("!f", data[3:7])[0]
            else: return None
            return flags, max(-1.0, min(1.0, float(joy)))
        except Exception: return None

    @staticmethod
    def _parse_pipe_fields(line: str) -> dict:
        fields = {}
        try:
            for item in str(line or "").strip().split("|")[1:]:
                if "=" in item:
                    key, value = item.split("=", 1)
                    fields[key.strip()] = value.strip()
        except Exception:
            pass
        return fields

    def _current_firmware_version(self) -> str:
        return "v" + str(self.version or "").lstrip("vV")

    def _firmware_version_matches_current(self, reported) -> bool:
        return str(reported or "").strip().lower().lstrip("v") == str(self.version or "").strip().lower().lstrip("v")

    @staticmethod
    def _firmware_version_parts(value):
        text = str(value or "").strip().lower().lstrip("v")
        parts = text.split(".")
        if len(parts) != 4 or any(not p.isdigit() for p in parts):
            return None
        return tuple(int(p) for p in parts)

    def _firmware_version_is_older(self, reported) -> bool:
        reported_parts = self._firmware_version_parts(reported)
        current_parts = self._firmware_version_parts(self._current_firmware_version())
        return bool(reported_parts is not None and current_parts is not None and reported_parts < current_parts)

    def _legacy_firmware_push_required(self, reported) -> bool:
        """Use the browser-upload bridge only for pre-authority field firmware.

        Modern CTRL/W1P releases understand SRVR_FW and must pull/verify their
        immutable authority image themselves. Pushing those releases through the
        blocking browser updater hides CTRL progress from CTRL-TS and races the
        ordered CTRL -> W1P -> CTRL-TS update coordinator.
        """
        parts = self._firmware_version_parts(reported)
        return bool(parts is not None and parts <= (26, 10, 1, 1))

    @staticmethod
    def _esp_reset_reason_name(reason: int) -> str:
        # Arduino-ESP32 esp_reset_reason() values. Keep the numeric value in the
        # log as the authoritative diagnostic and add a readable label for bench
        # work so PANIC/WDT/BROWNOUT can be distinguished from software reboot.
        names = {
            1: "POWERON", 2: "EXT", 3: "SOFTWARE", 4: "PANIC",
            5: "INT_WDT", 6: "TASK_WDT", 7: "WDT", 8: "DEEPSLEEP",
            9: "BROWNOUT", 10: "SDIO", 11: "USB", 12: "JTAG",
            13: "EFUSE", 14: "PWR_GLITCH", 15: "CPU_LOCKUP",
        }
        try:
            return names.get(int(reason), "UNKNOWN")
        except Exception:
            return "UNKNOWN"

    def _handle_ctrl_hmi_status(self, line: str):
        """Parse the proven CTRL HMI_STATUS relay packet.

        CTRL control packets remain the authoritative controller/safety stream.
        HMI_STATUS only reports CTRL-TS and the EdgeBox native analogue-input
        health for Setup diagnostics. The on-wire field remains ``ads`` for
        compatibility with the proven pre-EdgeBox protocol.
        """
        fields = self._parse_pipe_fields(line)
        now = time.time()
        self._ctrl_ts_last_seen = now
        self._ctrl_ts_connected_reported = str(fields.get("ctrl_ts", "0")).strip() == "1"
        self._ctrl_fw_version = str(fields.get("ctrl_version", self._ctrl_fw_version or ""))
        self._ctrl_fw_authority = str(fields.get("fw_authority", "unknown"))
        self._ctrl_fw_required = str(fields.get("fw_required", ""))
        # Never trust a field node's old-session fw_match=1 by itself. A CTRL that
        # matched a previous SRVR release may keep running while this newer SRVR
        # starts. The running CTRL version and the authority version it claims to
        # require must both equal this SRVR release before the match is accepted.
        reported_match = str(fields.get("fw_match", "0")).strip() == "1"
        version_current = self._firmware_version_matches_current(self._ctrl_fw_version)
        authority_current = self._firmware_version_matches_current(self._ctrl_fw_required)
        prev_ctrl_fw_match = bool(self._ctrl_fw_match)
        self._ctrl_fw_match = bool(reported_match and version_current and authority_current)
        if self._ctrl_fw_match and not prev_ctrl_fw_match:
            self._ctrl_fw_match_since = now
        elif not self._ctrl_fw_match:
            self._ctrl_fw_match_since = 0.0
        if (not self._ctrl_fw_match) and self._firmware_version_is_older(self._ctrl_fw_version):
            if not self._fw_mismatch_since["ctrl"]:
                self._fw_mismatch_since["ctrl"] = now
        else:
            self._fw_mismatch_since["ctrl"] = 0.0
        if reported_match and not self._ctrl_fw_match:
            self._ctrl_fw_authority = "stale_release_report"
        self._ctrl_ts_version = str(fields.get("version", ""))
        self._ctrl_ts_required_version = str(fields.get("required", self._ctrl_ts_required_version))
        self._ctrl_ts_fw_state = str(fields.get("fw_state", self._ctrl_ts_fw_state or "idle"))
        try:
            self._ctrl_ts_fw_pct = max(0, min(100, int(float(fields.get("fw_pct", self._ctrl_ts_fw_pct)))))
        except Exception:
            pass
        new_boot_id = str(fields.get("boot_id", "")).strip()
        try:
            new_reset_reason = int(float(fields.get("reset_reason", self._ctrl_ts_reset_reason)))
        except Exception:
            new_reset_reason = self._ctrl_ts_reset_reason
        def _mem_int(name, default=0):
            try: return max(0, int(float(fields.get(name, default))))
            except Exception: return max(0, int(default))
        reported_heap = _mem_int("ts_heap", self._ctrl_ts_heap_free)
        reported_min_heap = _mem_int("ts_min_heap", self._ctrl_ts_min_heap)
        reported_psram = _mem_int("ts_psram", self._ctrl_ts_psram_free)
        if new_boot_id and new_boot_id != "unknown" and new_boot_id != self._ctrl_ts_boot_id:
            reset_name = self._esp_reset_reason_name(new_reset_reason)
            mem_note = f"; pre-reset heap={reported_heap} min_heap={reported_min_heap} psram={reported_psram}" if self._ctrl_ts_boot_id else ""
            if self._ctrl_ts_boot_id:
                self._log(f"[CTRL-TS] reboot detected boot {self._ctrl_ts_boot_id} -> {new_boot_id}; reset_reason={new_reset_reason} ({reset_name}){mem_note}")
            else:
                self._log(f"[CTRL-TS] boot {new_boot_id}; reset_reason={new_reset_reason} ({reset_name})")
            self._ctrl_ts_boot_id = new_boot_id
        self._ctrl_ts_heap_free = reported_heap
        self._ctrl_ts_min_heap = reported_min_heap
        self._ctrl_ts_psram_free = reported_psram
        self._ctrl_ts_reset_reason = new_reset_reason
        try:
            event_id = max(0, int(float(fields.get("last_event_id", self._ctrl_ts_last_event_id))))
        except Exception:
            event_id = self._ctrl_ts_last_event_id
        event_cmd = str(fields.get("last_event_cmd", self._ctrl_ts_last_event_cmd or "")).strip()
        if event_id and (event_id != self._ctrl_ts_last_event_id or event_cmd != self._ctrl_ts_last_event_cmd):
            self._ctrl_ts_last_event_id = event_id
            self._ctrl_ts_last_event_cmd = event_cmd
            self._log(f"[CTRL-TS EVENT] CTRL accepted id={event_id} cmd={event_cmd or 'unknown'}")
        self._ctrl_ts_image_available = str(fields.get("image", "0")).strip() == "1"
        self._ctrl_ts_compatible_reported = str(fields.get("compatible", fields.get("ctrl_ts", "0"))).strip() == "1"
        try:
            self._ctrl_ts_age_ms = int(float(fields.get("age_ms", 999999)))
        except Exception:
            self._ctrl_ts_age_ms = 999999
        self._ctrl_ts_rs485_alive_reported = bool(0 <= self._ctrl_ts_age_ms <= int(HMI_STATUS_TIMEOUT_S * 1000.0))
        try:
            new_grant = int(float(fields.get("ts_grant", self._ctrl_ts_grant_reported)))
        except Exception:
            new_grant = self._ctrl_ts_grant_reported
        if new_grant != self._ctrl_ts_grant_reported:
            self._ctrl_ts_grant_reported = new_grant
            self._log(f"[FW COORD] CTRL reports CTRL-TS grant={new_grant} fw_state={self._ctrl_ts_fw_state or 'idle'} version={self._ctrl_ts_version or 'unknown'}")
        # RS485 diagnostics are cumulative monotonic counters. Never reset the
        # stored baseline after parsing them: doing so makes every non-zero value
        # look "new" on every 250 ms report and creates an unbounded Qt log storm.
        def _diag_int(name, default=0):
            try:
                return max(0, int(float(fields.get(name, default))))
            except Exception:
                return max(0, int(default))
        new_poll_timeouts = _diag_int("poll_timeouts", self._ctrl_ts_poll_timeouts)
        new_events_rejected = _diag_int("events_reject", self._ctrl_ts_events_rejected)
        new_queue_drops = _diag_int("ts_queue_drops", self._ctrl_ts_queue_drops)
        new_parser_crc = _diag_int("parser_crc", 0) + _diag_int("ts_parser_crc", 0)
        new_parser_resync = _diag_int("parser_resync", 0) + _diag_int("ts_parser_resync", 0)
        self._ctrl_ts_poll_timeouts = new_poll_timeouts
        self._ctrl_ts_events_rejected = new_events_rejected
        self._ctrl_ts_queue_drops = new_queue_drops
        self._ctrl_ts_parser_crc = new_parser_crc
        self._ctrl_ts_parser_resync = new_parser_resync

        # Fault diagnostics remain visible, but rate-limit them to one compact
        # summary every two seconds. The Log QML model is regenerated on each
        # logChanged signal, so repeated 4 Hz counter lines can otherwise starve
        # the same UI timer that owns motion/AUX processing.
        diag_now = (new_poll_timeouts, new_events_rejected, new_queue_drops, new_parser_crc, new_parser_resync)
        if diag_now != self._ctrl_ts_diag_last_logged and any(v > p for v, p in zip(diag_now, self._ctrl_ts_diag_last_logged)):
            if (now - self._ctrl_ts_diag_last_log_at) >= 2.0:
                prev = self._ctrl_ts_diag_last_logged
                delta = tuple(max(0, v - p) for v, p in zip(diag_now, prev))
                self._log(
                    "[CTRL-TS RS485] "
                    f"poll_timeouts={diag_now[0]} (+{delta[0]}), "
                    f"rejected={diag_now[1]} (+{delta[1]}), "
                    f"queue_drops={diag_now[2]} (+{delta[2]}), "
                    f"crc={diag_now[3]} (+{delta[3]}), "
                    f"resync={diag_now[4]} (+{delta[4]})"
                )
                self._ctrl_ts_diag_last_logged = diag_now
                self._ctrl_ts_diag_last_log_at = now
        self._ads1115_status_last_seen = now
        self._ads1115_connected_reported = str(fields.get("ads", fields.get("ads1115", "0"))).strip() == "1"

        # Any proven stale CTRL gets an immediate authority beacon from the RX
        # thread as well as the periodic background beacon. This closes the
        # window where a node can look connected yet wait for a reboot before it
        # notices a new SRVR release. No HTTP/flash work occurs in this RX path.
        if (not self._ctrl_fw_match) and self._firmware_version_is_older(self._ctrl_fw_version):
            self._send_ctrl_firmware_beacon(force=True)

        # A legacy CTRL can be alive and reporting its old version before the
        # normal UI timer has had a chance to service the compatibility bridge.
        # Start the asynchronous push immediately from this proven status packet
        # instead of depending on a device reboot to create a new update session.
        if self._legacy_firmware_push_required(self._ctrl_fw_version):
            self._try_start_legacy_firmware_push(
                "ctrl", str(self.ctrl_ip or "").strip(), self._ctrl_fw_version, True
            )

    def _joystick_min_cal_span(self) -> float:
        try:
            left = float(self.joystick_cal_left)
            centre = float(self.joystick_cal_centre)
            right = float(self.joystick_cal_right)
            return max(1e-6, min(abs(left-centre), abs(right-centre)))
        except Exception:
            return 1.0

    def _effective_joystick_centre(self) -> float:
        span = self._joystick_min_cal_span()
        bound = JOY_CENTRE_DRIFT_MAX_FRAC * span
        trim = max(-bound, min(bound, float(self._joystick_centre_trim_raw or 0.0)))
        return float(self.joystick_cal_centre) + trim

    def _reset_joystick_centre_drift(self) -> None:
        self._joystick_centre_trim_raw = 0.0
        self._joystick_centre_idle_since = 0.0
        self._joystick_centre_samples.clear()
        self._joystick_centre_last_update = time.monotonic()
        self._joystick_centre_warned = False

    def _update_joystick_centre_drift(self) -> None:
        """Slowly track small neutral-voltage drift only while safely stationary.

        This never changes saved calibration. A displacement larger than the
        bounded trim is reported rather than learned away, preserving the ability
        to detect a failing joystick/input that really needs recalibration.
        """
        now = time.monotonic()
        raw = max(-1.0, min(1.0, float(self._ctrl_axis or 0.0)))
        span = self._joystick_min_cal_span()
        centre = float(self.joystick_cal_centre)
        effective = self._effective_joystick_centre()
        capture = max(0.003, JOY_CENTRE_DRIFT_CAPTURE_FRAC * span)
        stable_range = max(0.0015, JOY_CENTRE_DRIFT_STABILITY_FRAC * span)
        eligible = bool(
            self._ctrl_connected()
            and not self.state.estop_active
            and not self.joystick_calibration_open
            and self.goto_target_m is None
            and not self._service_override_active()
            and not self._joystick_neutral_required
            and abs(float(self.requested_speed_mps or 0.0)) <= 0.001
            and abs(float(self.current_speed_mps or 0.0)) <= 0.03
            and abs(raw-effective) <= capture
        )
        if not eligible:
            self._joystick_centre_idle_since = 0.0
            self._joystick_centre_samples.clear()
            self._joystick_centre_last_update = now
            return

        if self._joystick_centre_idle_since <= 0.0:
            self._joystick_centre_idle_since = now
        self._joystick_centre_samples.append((now, raw))
        cutoff = now - JOY_CENTRE_DRIFT_SAMPLE_WINDOW_S
        while self._joystick_centre_samples and self._joystick_centre_samples[0][0] < cutoff:
            self._joystick_centre_samples.popleft()
        if (now - self._joystick_centre_idle_since) < JOY_CENTRE_DRIFT_IDLE_S or len(self._joystick_centre_samples) < 12:
            self._joystick_centre_last_update = now
            return

        vals = [v for _, v in self._joystick_centre_samples]
        if (max(vals) - min(vals)) > stable_range:
            self._joystick_centre_last_update = now
            return
        mean = sum(vals) / len(vals)
        max_trim = JOY_CENTRE_DRIFT_MAX_FRAC * span
        observed_trim = mean - centre
        desired_trim = max(-max_trim, min(max_trim, observed_trim))
        dt = max(0.0, min(0.25, now - float(self._joystick_centre_last_update or now)))
        self._joystick_centre_last_update = now
        alpha = 1.0 - math.exp(-dt / max(0.1, JOY_CENTRE_DRIFT_TAU_S))
        self._joystick_centre_trim_raw += (desired_trim - self._joystick_centre_trim_raw) * alpha
        self._joystick_centre_trim_raw = max(-max_trim, min(max_trim, self._joystick_centre_trim_raw))

        if abs(observed_trim) > max_trim * 1.15:
            if not self._joystick_centre_warned:
                pct = 100.0 * observed_trim / max(span, 1e-6)
                self._log(f"[CTRL] Joystick centre drift {pct:+.1f}% exceeds automatic trim range; recalibration recommended")
                self._joystick_centre_warned = True
        elif abs(observed_trim) < max_trim * 0.8:
            self._joystick_centre_warned = False

    @staticmethod
    def _normalise_joystick_calibration(raw: float, left: float, centre: float, right: float) -> float:
        """Piecewise-normalise one sample against explicit Left/Centre/Right captures."""
        raw = max(-1.0, min(1.0, float(raw)))
        left, centre, right = float(left), float(centre), float(right)
        lspan = left - centre
        rspan = right - centre
        if abs(lspan) < 1e-6 or abs(rspan) < 1e-6 or lspan * rspan >= 0.0:
            return raw
        if (raw - centre) * lspan >= 0.0:
            value = -((raw - centre) / lspan)
        else:
            value = (raw - centre) / rspan
        return max(-1.0, min(1.0, float(value)))

    def _calibrated_joystick(self, raw: float) -> float:
        """Normalise a live sample around the applied calibration/effective centre.

        The captured calibration remains authoritative. The only automatic
        adjustment is the tightly bounded runtime centre trim above; endpoints are
        never moved. Physical Left always maps to -1 and Right to +1, with the
        separate CTRL Direction setting applied afterwards.
        """
        return self._normalise_joystick_calibration(
            raw, self.joystick_cal_left, self._effective_joystick_centre(), self.joystick_cal_right
        )

    def _setup_preview_joystick(self) -> float:
        """Normalise the live sample using the Setup mirror calibration.

        Setup edits auto-commit, so this normally matches the live calibrated axis.
        Keeping the mirror-based helper preserves stable QML bindings during edits.
        """
        draft = getattr(self, "_setup_draft", {})
        cal = draft.get("joystick_calibration", {}) if isinstance(draft, dict) else {}
        try:
            left = float(cal.get("left", self.joystick_cal_left))
            centre = float(cal.get("centre", self.joystick_cal_centre))
            right = float(cal.get("right", self.joystick_cal_right))
        except Exception:
            left, centre, right = self.joystick_cal_left, self.joystick_cal_centre, self.joystick_cal_right
        return self._normalise_joystick_calibration(self._ctrl_axis, left, centre, right)

    def _operator_joystick_axis(self, value: float) -> float:
        """Return a stable operator readout without altering motion math.

        The calibrated axis can legitimately wander a few tenths of a percent
        around zero because the analogue stick and ADC are real devices. Motion
        already applies the configured deadband. Mirror that neutral semantics in
        operator readouts, with a small 0.5% floor, so a healthy centred stick
        displays 0.0% instead of distracting +/-0.1..0.3% noise.
        """
        value = max(-1.0, min(1.0, float(value)))
        neutral_pct = max(0.5, float(self.joystick_deadband_pct or 0.0))
        return 0.0 if abs(value * 100.0) <= neutral_pct else value

    def _ctrl_connected(self):
        now = time.time()
        while self._ctrl_rx_times and now - self._ctrl_rx_times[0] > CTRL_RX_WINDOW_S:
            self._ctrl_rx_times.popleft()
        return len(self._ctrl_rx_times) >= CTRL_RX_MIN_PKTS

    def _set_fw_progress(self, role: str, active: bool, phase: str = "Updating", pct: int = 0) -> None:
        key = "w1p" if str(role).lower().startswith("w1p") else "ctrl"
        state = self._fw_progress.setdefault(key, {"active": False, "phase": "Idle", "pct": 0})
        before = (bool(state.get("active", False)), str(state.get("phase", "Idle")), int(state.get("pct", 0) or 0))
        state["active"] = bool(active)
        state["phase"] = str(phase or ("Updating" if active else "Idle"))[:32]
        try:
            state["pct"] = max(0, min(100, int(float(pct))))
        except Exception:
            state["pct"] = 0
        if not active and state["pct"] >= 100:
            state["phase"] = "Complete"
        after = (bool(state["active"]), str(state["phase"]), int(state["pct"]))
        if after != before:
            # Progress may arrive from a UDP/background OTA thread. Qt signal
            # delivery is queued safely to the UI thread and keeps the single
            # Firmware value live without forcing synchronous UI work here.
            self.stateChanged.emit()

    # --- W1P parsing / motion ---
    def _invalidate_position_reference(self, reason: str) -> None:
        """Require a known-position reference after process/W1P power-session loss."""
        was_calibrated = not bool(self._not_calibrated)
        self._not_calibrated = True
        self._cancel_goto()
        if was_calibrated:
            self._log(f"[Calibration] Position reference invalidated: {reason}")
        self._sync_service_mode_to_winch(force=True)
        self.stateChanged.emit()

    def _invalidate_w1p_status(self):
        # A new peer/session or malformed STATUS must not inherit stale authority,
        # RS485 or safety state from the previous session. Ethernet liveness and
        # complete W1P STATUS freshness are intentionally separate concepts.
        self._w1p_status_last_seen = 0.0
        self._w1p_fw_match = False
        self._w1p_fw_authority = "unknown"
        self.winch_rs_status = "Disconnected"
        self.winch_drive_writes_enabled = False
        self.winch_sw_srvon = False
        self.winch_sw_srvon_ready = False
        self.winch_sw_srvon_ok = False
        self.winch_sw_srvon_inhibit = True
        self.winch_brake_released = False
        self._w1p_internal_safety = True

    def _reject_w1p_status(self, reason: str):
        # Reject one bad telemetry frame without erasing the last complete safety
        # snapshot. Authority expires naturally through WINCH_STATUS_TIMEOUT_S if
        # no valid STATUS follows. This prevents a single malformed datagram from
        # manufacturing a 25-50 ms E-stop/red flash.
        self._w1p_status_rejected += 1
        now = time.monotonic()
        if now - float(self._w1p_status_reject_last_log or 0.0) >= 2.0:
            self._w1p_status_reject_last_log = now
            self._log(f"[W1P STATUS] rejected frame #{self._w1p_status_rejected}: {reason}")

    def _w1p_status_fresh(self):
        return bool(self._w1p_status_last_seen > 0 and
                    time.time() - self._w1p_status_last_seen <= WINCH_STATUS_TIMEOUT_S)

    def _ctrl_authority_fresh(self):
        return bool(self._ctrl_ts_last_seen > 0 and
                    time.time() - self._ctrl_ts_last_seen <= HMI_STATUS_TIMEOUT_S)

    def _parse_w1p(self, line):
        line = str(line or "").strip()
        if line.startswith("W1PTS_AUX"):
            try:
                idx = int(line.replace("W1PTS_AUX", "").strip()) - 1
                # The proven W1P-TS transport currently emits AUX1..AUX4.
                # Accept a fifth index if a future firmware sends it because the
                # locked Setup UI already stores five assignment rows.
                if 0 <= idx < len(self.w1p_aux_assignments):
                    self._handle_aux_action(idx, source="w1p")
            except Exception as exc:
                self._log(f"[W1P AUX] invalid event {line!r}: {exc}")
            return
        if line.startswith("W1P_HMI_STATUS|"):
            fields = self._parse_pipe_fields(line)
            now = time.time()
            self._w1p_ts_last_seen = now
            self._w1p_ts_connected_reported = str(fields.get("w1p_ts", fields.get("w1pts", "0"))).strip() == "1"
            self._w1p_ts_version = str(fields.get("version", ""))
            try:
                self._w1p_ts_age_ms = int(float(fields.get("age_ms", 999999)))
            except Exception:
                self._w1p_ts_age_ms = 999999
            return
        if line.startswith("FW_PROGRESS|"):
            fields = self._parse_pipe_fields(line)
            active = str(fields.get("active", "1")).strip().lower() in ("1", "true", "on")
            self._set_fw_progress("w1p", active, fields.get("phase", "Updating"), fields.get("pct", 0))
            return
        if line.startswith("ERR"):
            self._log(f"[W1P] {line}"); return
        if line.startswith("PONG"):
            # PONG proves Ethernet liveness only. It must not erase a still-fresh,
            # fully validated STATUS safety snapshot.
            return
        if line.startswith("HELLO"):
            # HELLO represents a new W1P transport/power session. Never inherit a
            # position reference across that boundary: the cable may have moved
            # while W1P/drive power was absent. A Slip or Limit Calibration must
            # explicitly establish the new physical reference.
            self._invalidate_w1p_status()
            boot_id = ""
            for token in line.split()[1:]:
                if token.startswith("VER="):
                    self._w1p_fw_version = token.split("=", 1)[1].strip()
                elif token.startswith("BOOT_ID="):
                    boot_id = token.split("=", 1)[1].strip()
            if boot_id:
                self._w1p_boot_id = boot_id
            self._invalidate_position_reference("W1P session/boot changed")
            if not self.smoke_test:
                self._sync_w1p_settings()
            return
        if not line.startswith("STATUS"): return
        # Validate-then-commit: keep the previous complete snapshot authoritative
        # until this frame has all mandatory safety fields and parses successfully.
        fields = {}
        for p in line.split()[1:]:
            if "=" in p:
                k,v = p.split("=",1); fields[k]=v
        required_status = {
            "FW_MATCH", "ESTOP", "VEL_WD", "SERVICE_LOCK", "WRITE_EN",
            "SW_SRVON_INHIBIT", "BRAKE_OUT", "BRAKE_DO0", "RS_STAT", "LEAD_CFG",
            "MODBUS", "READY", "POS_READ", "IO_READ", "DO2_CFG",
            "DO3_CFG", "DO4_CFG", "DO5_CFG", "SRDY"
        }
        if not required_status.issubset(fields):
            missing = sorted(required_status.difference(fields))
            self._reject_w1p_status("missing " + ",".join(missing))
            return
        # Validate every token that can affect the live safety snapshot before
        # mutating any authoritative state. W1P emits these safety booleans as
        # literal 0/1 values; accepting arbitrary text here would turn a corrupt
        # token (for example ESTOP=x) into a real fail-safe transition instead of
        # rejecting the bad sample and retaining the previous fresh snapshot.
        strict_bits = (
            "FW_MATCH", "ESTOP", "VEL_WD", "SERVICE_LOCK", "WRITE_EN",
            "SW_SRVON_INHIBIT", "BRAKE_OUT", "BRAKE_DO0", "MODBUS", "READY",
            "POS_READ", "IO_READ", "DO2_CFG", "DO3_CFG", "DO4_CFG",
            "DO5_CFG", "SRDY",
        )
        for bit_key in strict_bits:
            if str(fields.get(bit_key, "")).strip() not in ("0", "1"):
                self._reject_w1p_status(f"invalid boolean field {bit_key}")
                return
        if str(fields.get("RS_STAT", "")).strip().upper() not in ("CONNECTED", "FAULT", "WAITING"):
            self._reject_w1p_status("invalid enum field RS_STAT")
            return
        if str(fields.get("LEAD_CFG", "")).strip().upper() not in ("OK", "MISMATCH", "READ_FAULT"):
            self._reject_w1p_status("invalid enum field LEAD_CFG")
            return
        try:
            for numeric_key in ("POS_M", "RAW_POS", "VEL_MPS", "DO2_ASSIGN", "DO3_ASSIGN", "DO4_ASSIGN", "DO5_ASSIGN"):
                if numeric_key in fields:
                    numeric_value = float(fields[numeric_key])
                    if not math.isfinite(numeric_value):
                        raise ValueError(f"{numeric_key} is non-finite")
        except Exception as exc:
            self._reject_w1p_status(f"invalid numeric field: {exc}")
            return
        try:
            boot_id = str(fields.get("BOOT_ID", "")).strip()
            if boot_id:
                if self._w1p_boot_id and boot_id != self._w1p_boot_id:
                    self._invalidate_position_reference("W1P boot identifier changed")
                self._w1p_boot_id = boot_id
            if "POS_M" in fields and self.position_source != "Virtual":
                new_pos = float(fields["POS_M"])
                if self._sanity_accept_winch_position(new_pos, fields):
                    self.state.pos_m = new_pos
            if "RAW_POS" in fields: self._last_raw_pos = int(float(fields["RAW_POS"]))
            if "VEL_MPS" in fields and self.position_source != "Virtual": self.current_speed_mps = float(fields["VEL_MPS"])
            if "FW" in fields: self._w1p_fw_version = str(fields["FW"])
            reported_w1p_match = str(fields.get("FW_MATCH", "0")).strip() == "1"
            self._w1p_fw_match = bool(reported_w1p_match and self._firmware_version_matches_current(self._w1p_fw_version))
            self._w1p_fw_authority = str(fields.get("FW_AUTH", "unknown"))
            if (not self._w1p_fw_match) and self._firmware_version_is_older(self._w1p_fw_version):
                if not self._fw_mismatch_since["w1p"]:
                    self._fw_mismatch_since["w1p"] = time.time()
            else:
                self._fw_mismatch_since["w1p"] = 0.0
            if reported_w1p_match and not self._w1p_fw_match:
                self._w1p_fw_authority = "stale_release_report"
            if "IP" in fields: self.w1p_reported_ip = str(fields["IP"])
            if "WRITE_EN" in fields: self.winch_drive_writes_enabled = fields["WRITE_EN"].lower() in ("1","true","on")
            if "SW_SRVON" in fields: self.winch_sw_srvon = fields["SW_SRVON"].lower() in ("1","true","on","ok")
            if "SW_SRVON_READY" in fields: self.winch_sw_srvon_ready = fields["SW_SRVON_READY"].lower() in ("1","true","on","ok","ready")
            if "SW_SRVON_OK" in fields: self.winch_sw_srvon_ok = fields["SW_SRVON_OK"].lower() in ("1","true","on","ok")
            if "SW_SRVON_INHIBIT" in fields: self.winch_sw_srvon_inhibit = fields["SW_SRVON_INHIBIT"].lower() in ("1","true","on")
            if "DO2_CFG" in fields: self.winch_do2_ready_config_ok = fields["DO2_CFG"].lower() in ("1","true","on","ok")
            if "DO2_ASSIGN" in fields:
                try: self.winch_do2_assignment = int(float(fields["DO2_ASSIGN"]))
                except Exception: self.winch_do2_assignment = None
            if "READY_OUT" in fields: self.winch_ready_output = fields["READY_OUT"].lower() in ("1","true","on","ready")
            if "DO3_CFG" in fields: self.winch_do3_enabled_config_ok = fields["DO3_CFG"].lower() in ("1","true","on","ok")
            if "DO3_ASSIGN" in fields:
                try: self.winch_do3_assignment = int(float(fields["DO3_ASSIGN"]))
                except Exception: self.winch_do3_assignment = None
            if "ENABLED_OUT" in fields: self.winch_enabled_output = fields["ENABLED_OUT"].lower() in ("1","true","on","enabled")
            if "DO4_CFG" in fields: self.winch_do4_brake_config_ok = fields["DO4_CFG"].lower() in ("1","true","on","ok")
            if "DO4_ASSIGN" in fields:
                try: self.winch_do4_assignment = int(float(fields["DO4_ASSIGN"]))
                except Exception: self.winch_do4_assignment = None
            # BRAKE_OUT is the EL7's logical BRK-OFF sequencing state; the actual
            # motor brake coil is now switched by W1P EdgeBox DO0. Present the
            # physical DO0 command as the brake state throughout SRVR/UI.
            if "BRAKE_DO0" in fields: self.winch_brake_released = fields["BRAKE_DO0"].lower() in ("1","true","on","released")
            if "DO5_CFG" in fields: self.winch_do5_fault_config_ok = fields["DO5_CFG"].lower() in ("1","true","on","ok")
            if "DO5_ASSIGN" in fields:
                try: self.winch_do5_assignment = int(float(fields["DO5_ASSIGN"]))
                except Exception: self.winch_do5_assignment = None
            if "FAULT_OUT" in fields: self.winch_fault_output = fields["FAULT_OUT"].lower() in ("1","true","on","fault")
            estop = fields.get("ESTOP","0").lower() not in ("0","false","off")
            src = fields.get("ESTOP_SRC","").upper()
            self._w1p_estop = bool(estop and src in ("","W1P","LOCAL"))
            self.winch_vel_watchdog_fault = fields.get("VEL_WD", "0") == "1"
            self.winch_service_safety_lock = fields.get("SERVICE_LOCK", "0") == "1"
            self._w1p_internal_safety = self.winch_vel_watchdog_fault or self.winch_service_safety_lock
            rs = fields.get("RS_STAT", fields.get("MODBUS","0")).upper()
            cfg = fields.get("LEAD_CFG","MISMATCH").upper()
            fb_ok = fields.get("MODBUS","0").upper() in ("1","OK","CONNECTED","TRUE","ON")
            ready = fields.get("READY","0").upper() in ("1","OK","READY","TRUE","ON")
            pos_ok = fields.get("POS_READ","0").upper() in ("1","OK","TRUE","ON")
            io_ok = fields.get("IO_READ","0").upper() in ("1","OK","TRUE","ON")
            do_ok = all(fields.get(key,"0").upper() in ("1","OK","TRUE","ON") for key in ("DO2_CFG","DO3_CFG","DO4_CFG","DO5_CFG"))
            brake_cfg_ok = fields.get("DO4_CFG","0").upper() in ("1","OK","TRUE","ON")
            srdy = fields.get("SRDY","0").upper() in ("1","OK","READY","TRUE","ON")
            if rs in ("1","OK","CONNECTED") and cfg == "OK" and fb_ok and ready and pos_ok and io_ok and do_ok and brake_cfg_ok and srdy:
                self.winch_rs_status = "Connected"
            elif rs in ("1","OK","CONNECTED") and cfg != "OK": self.winch_rs_status = "Configuration Fault"
            elif rs in ("1","OK","CONNECTED"): self.winch_rs_status = "Feedback Fault"
            else: self.winch_rs_status = "Disconnected"
            self._update_w1p_reported_config(fields)
            self._w1p_status_last_seen = time.time()
        except Exception as exc:
            self._reject_w1p_status(f"parse error: {exc}")

    def _sanity_accept_winch_position(self, new_pos_m: float, fields: dict) -> bool:
        """Fail closed on implausible W1P position jumps.

        Ported from the proven v26.06.26.25 backend. A deliberate Slip/SYNC_POS
        opens a short grace window so the new reference is accepted; otherwise
        stationary feedback is strict and active-motion feedback is bounded by
        the configured maximum speed and elapsed status interval.
        """
        try:
            new_pos = float(new_pos_m)
            if not math.isfinite(new_pos):
                return False
            old_pos = self.state.pos_m
            now = time.time()
            if old_pos is None:
                self._winch_last_pos_accept_t = now
                return True
            if now <= float(self._winch_position_accept_jump_until or 0.0):
                self._winch_last_pos_accept_t = now
                return True
            old_pos = float(old_pos)
            dt = now - float(self._winch_last_pos_accept_t or now)
            if dt <= 0.0 or dt > 1.0:
                dt = 0.075
            jump = abs(new_pos - old_pos)
            commanded = abs(float(self.last_winch_output or 0.0))
            max_speed = abs(float(self.max_speed_mps or 20.0))
            if commanded < 0.05 and self.goto_target_m is None:
                allowed_jump = 0.35
            else:
                allowed_jump = max(0.35, (max_speed + 2.0) * max(dt, 0.05) * 2.5)
            if not self._service_override_active():
                nl = float(self.state.near_limit.position_m or 0.0)
                fl = float(self.state.far_limit.position_m if self.state.far_limit.position_m is not None else nl + self.state.total_length_m)
                lo, hi = (nl, fl) if nl <= fl else (fl, nl)
                if new_pos < lo - 0.5 or new_pos > hi + 0.5:
                    jump = max(jump, allowed_jump + 1.0)
            if jump <= allowed_jump:
                self._winch_last_pos_accept_t = now
                return True
            if now - float(self._winch_last_pos_reject_log_t or 0.0) >= 2.0:
                self._winch_last_pos_reject_log_t = now
                self._log(f"[W1P-POS] Rejected implausible position jump {old_pos:.3f} -> {new_pos:.3f} m")
            return False
        except Exception as exc:
            self._log(f"[W1P-POS] Position validation failed closed: {exc}")
            return False

    def _desired_w1p_settings(self):
        """Return SRVR-authoritative W1P settings and their wire commands."""
        nl = float(self.state.near_limit.position_m or 0.0)
        fl = float(self.state.far_limit.position_m if self.state.far_limit.position_m is not None else 100.0)
        if fl < nl:
            nl, fl = fl, nl
        service = 1 if self._service_override_active() else 0
        accel_mode = "Speed" if self.acceleration_mode == "Speed" else "Power"
        return {
            "SERVICE": (service, f"SERVICE_MODE {service}"),
            "MOTOR_REV": (1 if self.reverse_motor else 0, f"SET_MOTOR_REVERSE {1 if self.reverse_motor else 0}"),
            "UPM": (float(self.winch_units_per_m), f"SET_UNITS_PER_M {self.winch_units_per_m:.1f}"),
            "ACC_MODE": (accel_mode, f"SET_ACCEL_MODE {'DYNAMIC' if accel_mode == 'Speed' else 'TRADITIONAL'}"),
            "ACCEL": (float(self.max_accel_mps2), f"SET_ACCEL {self.max_accel_mps2:.3f}"),
            "DECEL": (float(self.max_decel_mps2), f"SET_DECEL {self.max_decel_mps2:.3f}"),
            "CROSS": (float(self.max_crossover_mps2), f"SET_CROSSOVER {self.max_crossover_mps2:.3f}"),
            "STOP_DECEL": (float(self.max_stop_decel_mps2), f"SET_STOP_DECEL {self.max_stop_decel_mps2:.3f}"),
            "SPAN_M": (max(.1, fl - nl), f"SET_SPAN {max(.1, fl-nl):.3f}"),
            "NL": (nl, f"SET_LIMIT_NEAR {nl:.3f}"),
            "FL": (fl, f"SET_LIMIT_FAR {fl:.3f}"),
        }

    @staticmethod
    def _w1p_setting_matches(key, reported, desired) -> bool:
        if reported is None:
            return False
        if key == "ACC_MODE":
            return str(reported).strip().lower() == str(desired).strip().lower()
        if key in ("SERVICE", "MOTOR_REV"):
            try: return int(float(reported)) == int(desired)
            except Exception: return False
        try:
            tol = 0.15 if key == "UPM" else 0.0025
            return abs(float(reported) - float(desired)) <= tol
        except Exception:
            return False

    def _update_w1p_reported_config(self, fields: dict):
        for key in ("SERVICE", "MOTOR_REV", "UPM", "ACC_MODE", "ACCEL", "DECEL", "CROSS", "STOP_DECEL", "SPAN_M", "NL", "FL"):
            if key in fields:
                self._w1p_reported_config[key] = fields[key]
        desired = self._desired_w1p_settings()
        for key, (want, _cmd) in desired.items():
            if self._w1p_setting_matches(key, self._w1p_reported_config.get(key), want):
                self._w1p_settings_pending.discard(key)
            else:
                self._w1p_settings_pending.add(key)

    def _mark_w1p_settings_pending(self, keys=None):
        desired = self._desired_w1p_settings()
        self._w1p_settings_pending.update(desired.keys() if keys is None else keys)

    def _service_w1p_setting_sync(self):
        """Pace SET commands and retry until STATUS confirms convergence.

        UDP remains intentionally connectionless; reliability comes from W1P's
        repeated STATUS report.  At most one setting is emitted per service pass
        and a mismatched key is retried only after a bounded interval, preventing
        configuration bursts from delaying VEL/STOP traffic.
        """
        if self.smoke_test or not self._w1p_settings_pending or not self.w1p.connected:
            return
        now = time.monotonic()
        if now - self._w1p_setting_last_any_tx < self._w1p_setting_min_gap_s:
            return
        desired = self._desired_w1p_settings()
        order = ("SERVICE", "MOTOR_REV", "UPM", "ACC_MODE", "ACCEL", "DECEL", "CROSS", "STOP_DECEL", "SPAN_M", "NL", "FL")
        for key in order:
            if key not in self._w1p_settings_pending or key not in desired:
                continue
            want, cmd = desired[key]
            if self._w1p_setting_matches(key, self._w1p_reported_config.get(key), want):
                self._w1p_settings_pending.discard(key)
                continue
            last_value = self._w1p_setting_last_value.get(key)
            same_value_retry = self._w1p_setting_matches(key, last_value, want)
            if same_value_retry and now - float(self._w1p_setting_last_tx.get(key, 0.0)) < self._w1p_setting_retry_s:
                continue
            self.w1p.send(cmd)
            self._w1p_setting_last_tx[key] = now
            self._w1p_setting_last_value[key] = want
            self._w1p_setting_last_any_tx = now
            break

    def _sync_w1p_settings(self):
        """Request convergence of every persistent W1P setting.

        The old implementation sent an unverified UDP burst once.  A single lost
        datagram could leave W1P on an old value and its next STATUS would then
        overwrite SRVR's newly selected setting.  Keep SRVR authoritative and
        retry paced commands until W1P reports the same values.
        """
        if self.smoke_test:
            return
        self._mark_w1p_settings_pending()
        self._service_w1p_setting_sync()

    @staticmethod
    def _normalise_ipv4(value: str) -> str:
        try:
            ip = ipaddress.ip_address(str(value).strip())
        except ValueError as exc:
            raise ValueError(f"invalid IPv4 address: {value}") from exc
        if ip.version != 4 or ip.is_unspecified or ip.is_multicast:
            raise ValueError(f"invalid W1P IPv4 address: {value}")
        return str(ip)

    def _probe_w1p_address(self, host: str, timeout_s: float = 2.8) -> bool:
        """Prove that the configured SRVR host can reach W1P at ``host``.

        This is used only as recovery for a lost SET_NETWORK acknowledgement.
        W1P treats the first valid SRVR packet at a provisional address as the
        transaction commit; if no such packet arrives, W1P rolls itself back.
        """
        host = self._normalise_ipv4(host)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(0.12)
            deadline = time.monotonic() + max(0.5, float(timeout_s))
            next_probe = 0.0
            while time.monotonic() < deadline:
                now = time.monotonic()
                if now >= next_probe:
                    next_probe = now + 0.20
                    try:
                        sock.sendto(b"STATUS\n", (host, int(self.w1p_port)))
                    except OSError:
                        pass
                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    continue
                if not addr or addr[0] != host:
                    continue
                for raw in data.decode("ascii", "ignore").splitlines():
                    line = raw.strip()
                    if not line.startswith("STATUS"):
                        continue
                    fields = self._parse_pipe_fields(line)
                    try:
                        reported = self._normalise_ipv4(fields.get("IP", ""))
                    except ValueError:
                        continue
                    if reported == host:
                        return True
            return False
        finally:
            sock.close()

    def _request_w1p_readdress(self, new_ip: str, timeout_s: float = 2.2) -> bool:
        """Safely persist/reboot W1P onto ``new_ip`` before SRVR changes target.

        The request is sent to the currently connected W1P address and waits for
        the EdgeBox's post-safety-gate acknowledgement. If it cannot prove the
        change was accepted, the requested auto-save change is rejected rather than orphaning W1P.
        """
        new_ip = self._normalise_ipv4(new_ip)
        old_ip = self._normalise_ipv4(self.w1p_ip)
        if new_ip == old_ip:
            return True
        if self.smoke_test:
            return True
        if not self.w1p.connected:
            self._log(f"[Config] W1P IP change refused: current W1P {old_ip} is not connected")
            return False

        # Help the EdgeBox reach its verified stopped/braked service state before
        # asking it to persist the new address. The W1P command repeats and
        # independently verifies the same fail-safe conditions.
        self._send_safety_stop_limited(force=True)
        self._joystick_neutral_required = True
        self.w1p.send(f"SET_NETWORK|w1p_ip={new_ip}")
        deadline = time.monotonic() + max(0.5, float(timeout_s))
        while time.monotonic() < deadline:
            try:
                line = self._w1p_rx.get(timeout=0.05)
            except queue.Empty:
                continue
            text = str(line or "").strip()
            if text.startswith("OK SET_NETWORK"):
                self._log(f"[Config] W1P accepted IP change {old_ip} -> {new_ip}; rebooting")
                return True
            if text.startswith("ERR SET_NETWORK"):
                self._log(f"[Config] W1P IP change refused: {text}")
                return False
            self._parse_w1p(text)
        # UDP acknowledgements are not reliable. The W1P change is transactional:
        # after reboot it waits for a valid SRVR packet on the provisional address
        # and rolls back automatically if none arrives. Probe the requested address
        # before declaring failure so a lost ACK cannot strand the controller.
        if self._probe_w1p_address(new_ip):
            self._log(f"[Config] W1P SET_NETWORK acknowledgement was lost, but {new_ip} answered with its live IP; accepting readdress")
            return True
        self._log(f"[Config] W1P IP change could not be confirmed; W1P will roll back to {old_ip} if it rebooted provisionally")
        return False

    def _service_override_active(self) -> bool:
        """Service movement is allowed at reduced speed during calibration/battery work.

        This mirrors the working v26.06.26.25 behaviour: Not Calibrated is not an
        E-stop. It is a low-speed service state so the operator can actually move
        the skate to establish Near/Far/Reference positions.
        """
        return bool(
            self._not_calibrated
            or self.battery_change_mode
            or (self.calibration_open and self.calibration_type in ("Limit", "Winch"))
        )

    @staticmethod
    def _service_speed_limit_mps() -> float:
        # Proven service limit: 5 km/h.
        return 5.0 / 3.6

    def _sync_service_mode_to_winch(self, force: bool = False):
        enabled = 1 if self._service_override_active() else 0
        if (not force) and self._last_service_mode_sent == enabled:
            return
        self._last_service_mode_sent = enabled
        if not self.smoke_test:
            # SERVICE changes the permitted motion envelope itself. When a wizard
            # explicitly opens/closes, put that command on the wire immediately
            # rather than allowing an unrelated paced SET_* transaction to hold
            # the old Near/Far envelope for another cycle. The ordinary convergent
            # settings path remains armed below and retries until STATUS confirms it.
            if force and self.w1p.connected:
                now = time.monotonic()
                self.w1p.send(f"SERVICE_MODE {enabled}")
                self._w1p_setting_last_tx["SERVICE"] = now
                self._w1p_setting_last_value["SERVICE"] = enabled
                self._w1p_setting_last_any_tx = now
            self._mark_w1p_settings_pending(("SERVICE",))
            self._service_w1p_setting_sync()

    def _update_battery_change_auto_cancel(self):
        if not self.battery_change_mode or self.state.pos_m is None:
            return
        if self._not_calibrated or self.calibration_open:
            return
        try:
            pos = float(self.state.pos_m)
            nl = float(self.state.near_limit.position_m or 0.0)
            fl = float(self.state.far_limit.position_m if self.state.far_limit.position_m is not None else self.state.total_length_m)
            lo, hi = (nl, fl) if nl <= fl else (fl, nl)
            if pos < lo - 0.05 or pos > hi + 0.05:
                self._battery_change_went_outside_limits = True
                return
            if self._battery_change_went_outside_limits and (lo + 0.02) <= pos <= (hi - 0.02):
                self.battery_change_mode = False
                self._battery_change_went_outside_limits = False
                self._sync_service_mode_to_winch(force=True)
                self._save_config()
                self._refresh_setup_mirror()
                self.configChanged.emit()
                self._log("[SRVR] Battery Change auto-cancelled: skate returned inside limits")
        except Exception:
            pass

    @staticmethod
    def _predictive_speed_cap(remaining_m: float, decel_mps2: float) -> float:
        """Maximum line speed that can stop inside the remaining distance.

        Uses d = margin + v*t_reaction + v^2/(2a), solved for v. The deceleration
        passed here is already the active profile's conservative braking value.
        """
        d = max(0.0, float(remaining_m) - PREDICTIVE_LIMIT_MARGIN_M)
        a = max(0.10, float(decel_mps2) * PREDICTIVE_LIMIT_DECEL_FACTOR)
        t = max(0.0, float(PREDICTIVE_LIMIT_REACTION_S))
        if d <= 0.0:
            return 0.0
        at = a * t
        return max(0.0, math.sqrt(at*at + 2.0*a*d) - at)

    def _hard_limit_velocity(self, pos, req):
        """Apply ramp zones plus a reaction-aware predictive soft-limit envelope.

        Existing Near/Far positions remain absolute hard boundaries. This layer
        begins reducing permitted velocity early enough to stop before the end,
        while W1P independently repeats the stopping-distance cap locally.
        """
        nl = float(self.state.near_limit.position_m or 0.0)
        fl = float(self.state.far_limit.position_m if self.state.far_limit.position_m is not None else self.state.total_length_m)
        if fl < nl:
            nl, fl = fl, nl
        if abs(float(req)) <= 1e-9:
            return 0.0
        decel = max(0.10, min(float(self.max_decel_mps2), float(self.max_stop_decel_mps2)))
        span = max(0.0, fl - nl)
        if req < 0:
            rem = pos - nl
            allow = self._predictive_speed_cap(rem, decel)
            ramp = self._ramp_distance(self.state.near_limit, span)
            if ramp > 0.0 and pos < nl + ramp:
                allow = min(allow, abs(req) * max(0.0, min(1.0, rem / ramp)))
            return -min(abs(req), allow)
        rem = fl - pos
        allow = self._predictive_speed_cap(rem, decel)
        ramp = self._ramp_distance(self.state.far_limit, span)
        if ramp > 0.0 and pos > fl - ramp:
            allow = min(allow, abs(req) * max(0.0, min(1.0, rem / ramp)))
        return min(abs(req), allow)

    @staticmethod
    def _ramp_distance(lp, span):
        """Return the effective physical ramp length inside the current span.

        Distance and Percentage are only two representations of the same physical
        ramp boundary. Clamp the effective result to the live Near/Far span so
        motion limiting and every progress-bar renderer share one valid geometry.
        """
        span = max(0.0, float(span))
        raw = span * (float(lp.ramp_percentage) / 100.0) if lp.ramp_mode == "Percentage" else float(lp.ramp_distance_m)
        return max(0.0, min(span, raw))

    def _span_length_m(self) -> float:
        return max(0.0, abs(float(self.farLimit) - float(self.nearLimit)))

    def _sync_ramp_representations_for_span(self) -> None:
        """Keep metres/percentage representations equivalent after limit edits."""
        span = self._span_length_m()
        if span <= 1e-9:
            for lp in (self.state.near_limit, self.state.far_limit):
                lp.ramp_distance_m = 0.0
                lp.ramp_percentage = 0.0
            return
        for lp in (self.state.near_limit, self.state.far_limit):
            if lp.ramp_mode == "Percentage":
                lp.ramp_percentage = max(0.0, min(100.0, float(lp.ramp_percentage)))
                lp.ramp_distance_m = span * lp.ramp_percentage / 100.0
            else:
                lp.ramp_distance_m = max(0.0, min(span, float(lp.ramp_distance_m)))
                lp.ramp_percentage = 100.0 * lp.ramp_distance_m / span

    def _clamp_goto_target_inside_limits(self, target: float) -> float:
        if self._service_override_active():
            return float(target)
        nl = self.state.near_limit.position_m
        fl = self.state.far_limit.position_m
        if nl is None or fl is None:
            return float(target)
        lo, hi = (float(nl), float(fl)) if nl <= fl else (float(fl), float(nl))
        stand_off = 0.03
        if hi-lo <= 2*stand_off:
            return max(lo, min(hi, float(target)))
        return max(lo+stand_off, min(hi-stand_off, float(target)))

    def _start_goto_target(self, target_m: float):
        """Latch the intended approach direction so a Goto does not hunt across target."""
        try:
            target = self._clamp_goto_target_inside_limits(float(target_m))
        except Exception:
            return
        self.goto_target_m = target
        try:
            pos = float(self.state.pos_m if self.state.pos_m is not None else target)
            diff = target - pos
            self._goto_last_error_m = diff
            self._goto_approach_dir = 1.0 if diff >= 0.0 else -1.0
        except Exception:
            self._goto_last_error_m = 0.0
            self._goto_approach_dir = 0.0

    def _cancel_goto(self):
        self.goto_target_m = None
        self._goto_approach_dir = 0.0
        self._goto_last_error_m = 0.0

    def _goto_velocity_for_distance(self, distance_m: float, requested_max_mps: float) -> float:
        try:
            d = max(0.0, float(distance_m))
            vmax = max(0.02, float(requested_max_mps or 0.0))
            # Deliberately conservative predictive envelope. W1P still performs
            # the actual configured deceleration profile underneath this request.
            decel_plan = max(0.08, float(self.max_stop_decel_mps2) * 0.10)
            guard_m = max(0.08, min(0.90, 0.10 + 0.06 * abs(float(self.current_speed_mps or 0.0))))
            return min(vmax, math.sqrt(max(0.0, 2.0 * decel_plan * max(0.0, d - guard_m))))
        except Exception:
            return max(0.0, float(requested_max_mps or 0.0))

    def _goto_velocity(self, diff):
        """Predictive one-direction Goto with stop-before-reverse creep correction.

        This restores the proven v26.06.26.25 anti-overshoot behaviour: the
        original approach direction is latched, the winch is allowed to settle
        before any correction after crossing the target, and the final 2 m is a
        low-speed creep zone with a 1 cm completion window.
        """
        try:
            diff = float(diff)
            d = abs(diff)
            fb_signed = float(self.current_speed_mps or 0.0)
            fb = abs(fb_signed)
            vmax = max(0.02, float(self.goto_speed_mps or 0.0))
        except Exception:
            return 0.0, True

        target_window = 0.010
        stop_speed = 0.030
        if d <= target_window and fb <= stop_speed:
            return 0.0, True

        direction = 1.0 if diff >= 0.0 else -1.0
        last_dir = float(self._goto_approach_dir or 0.0)
        if last_dir == 0.0 or d > 1.50:
            self._goto_approach_dir = direction
            last_dir = direction

        # Target crossed: never reverse against momentum. Stop first, then only
        # use a very small creep correction once feedback is almost stationary.
        if direction != last_dir and d > target_window:
            if fb > 0.06:
                return 0.0, False
            creep_back = min(0.12, max(0.025, d * 0.25))
            return direction * min(vmax, creep_back), False

        if d <= 2.00:
            if d <= target_window:
                return 0.0, False
            allowed_creep = min(0.38, max(0.025, 0.18 * d + 0.025))
            if fb > max(0.12, allowed_creep * 1.8):
                return 0.0, False
            return last_dir * min(vmax, allowed_creep), False

        v_allowed = self._goto_velocity_for_distance(d, vmax)
        if d <= 8.0:
            v_allowed = min(v_allowed, max(0.38, d * 0.45))
        if fb > (v_allowed + 0.35) and d <= 10.0:
            return 0.0, False
        v_allowed = max(0.10, v_allowed)
        return last_dir * min(vmax, v_allowed), False

    @staticmethod
    def _normalise_position_source(value) -> str:
        return "Virtual" if str(value or "").strip().lower().startswith("virtual") else "Encoder"

    def _virtual_output_inhibit(self, force: bool = False):
        """Keep the physical W1P output fail-safe while SRVR is in demo mode."""
        if self.position_source != "Virtual":
            return
        now = time.monotonic()
        if not force and (now - float(self._virtual_inhibit_last_tx or 0.0)) < 1.0:
            return
        self._virtual_inhibit_last_tx = now
        # Virtual is deliberately a local SRVR simulation. Never rely on the
        # absence of VEL packets alone: positively stop W1P and inhibit software
        # Servo Enable whenever a physical W1P happens to be present.
        if not self.smoke_test:
            try:
                self.w1p.send("STOP")
                self.w1p.send("SW_SRVON 0")
            except Exception:
                pass
        self._safety_servo_inhibited = True

    def _apply_position_source_runtime(self, value, *, send_safety: bool = True):
        new_source = self._normalise_position_source(value)
        old_source = str(self.position_source)
        if new_source == old_source:
            return
        self._cancel_goto()
        self.requested_speed_mps = 0.0
        self.last_winch_output = 0.0
        self.last_sent_vel = 0.0
        self.current_speed_mps = 0.0
        self._virtual_velocity_mps = 0.0
        self._virtual_last_tick = time.monotonic()
        self.position_source = new_source
        if new_source == "Virtual":
            # The local safety state is part of the mode transition itself and
            # must not depend on whether hardware I/O is enabled (for example
            # smoke-test/CI mode). Real runs additionally transmit STOP +
            # SW_SRVON 0 through _virtual_output_inhibit() below.
            self._safety_servo_inhibited = True
            self._joystick_neutral_required = False
            if send_safety:
                self._virtual_output_inhibit(force=True)
            self._log("[SRVR] Position Source set to Virtual; physical W1P velocity output inhibited")
        else:
            # Leaving demo mode must not let a displaced joystick become a live
            # command. Keep Servo Enable inhibited until normal safety checks are
            # clear and the operator returns through neutral.
            self._joystick_neutral_required = True
            self._safety_servo_inhibited = True
            if send_safety and not self.smoke_test:
                try:
                    self.w1p.send("STOP")
                    self.w1p.send("SW_SRVON 0")
                except Exception:
                    pass
            self._log("[SRVR] Position Source set to Encoder; waiting for joystick neutral before W1P re-arm")

    def _virtual_motion_step(self):
        if self.position_source != "Virtual":
            self._virtual_last_tick = time.monotonic()
            return
        now = time.monotonic()
        dt = max(0.0, min(0.20, now - float(self._virtual_last_tick or now)))
        self._virtual_last_tick = now
        try:
            pos = float(self.state.pos_m or 0.0) + float(self._virtual_velocity_mps) * dt
            self.state.pos_m = pos
            self.current_speed_mps = float(self._virtual_velocity_mps)
        except Exception:
            self._virtual_velocity_mps = 0.0
            self.current_speed_mps = 0.0

    def _send_stop_command(self):
        try:
            self.w1p.clear_velocity_refresh()
        except Exception:
            pass
        self.last_sent_vel = 0.0
        self.requested_speed_mps = 0.0
        self.last_winch_output = 0.0
        self._virtual_velocity_mps = 0.0
        if self.position_source == "Virtual":
            self.current_speed_mps = 0.0
        self._cancel_goto()
        if not self.smoke_test:
            self.w1p.send("STOP")

    def _send_safety_stop_limited(self, force: bool = False):
        """Issue STOP + software Servo Enable OFF on a safety transition.

        The command pair is repeated at most once per second while a safety
        source remains active. Repetition makes a transient UDP loss fail-safe
        without creating the old STOP/status feedback flood. Servo Enable is not
        restored here; that is deliberately deferred until all safety sources are
        clear and the operator has returned the joystick through neutral.
        """
        now = time.monotonic()
        if force or (now - float(self._last_safety_stop_ts or 0.0)) >= 1.0:
            self._last_safety_stop_ts = now
            self._send_stop_command()
            self._safety_servo_inhibited = True
            if not self.smoke_test:
                try:
                    self.w1p.send("SW_SRVON 0")
                except Exception:
                    pass

    def _restore_servo_after_safety_neutral(self):
        """Restore software Servo Enable only after a safety-clear neutral check."""
        if not self._safety_servo_inhibited:
            return
        if self.position_source == "Virtual":
            # Demo mode must never restore the physical winch Servo Enable.
            self._virtual_output_inhibit(force=True)
            return
        # Keep W1P stopped while its PA4.00/SRV-ON path settles. W1P itself still
        # requires a fresh non-zero VEL before command writes can re-arm.
        self._send_stop_command()
        if not self.smoke_test:
            try:
                self.w1p.send("SW_SRVON 1")
            except Exception:
                return
        self._safety_servo_inhibited = False
        self._log("[Safety] Joystick neutral confirmed; software Servo Enable restore requested")

    def _send_velocity(self, vel: float, force: bool = False):
        vel = float(vel)
        if self.position_source == "Virtual":
            # Virtual mode is a local SRVR demo simulation. The operator may use
            # the real CTRL/CTRL-TS joystick and shortcuts, but a non-zero W1P VEL
            # packet is never emitted. Track requested motion locally instead.
            self.requested_speed_mps = vel
            self._virtual_velocity_mps = vel
            self.current_speed_mps = vel
            self.last_winch_output = 0.0
            self.last_sent_vel = 0.0
            try:
                self.w1p.clear_velocity_refresh()
            except Exception:
                pass
            self._virtual_output_inhibit()
            return

        cmd = "VEL 0" if abs(vel) < .001 else f"VEL {vel:.3f}"
        if not self.smoke_test:
            # Renew the short worker lease on every control-loop decision, even
            # when the ordinary 150 ms wire refresh is not yet due. This keeps a
            # brief macOS/Qt scheduling stall from tripping W1P, while lease expiry
            # still lets the unchanged 500 ms W1P watchdog stop an unhealthy SRVR.
            if abs(vel) < .001:
                self.w1p.clear_velocity_refresh()
            else:
                self.w1p.arm_velocity_refresh(cmd, source_axis=self._ctrl_axis)

        now = time.time()
        same = abs(vel-self.last_sent_vel) < .01
        if not force and same:
            if abs(vel) < .001 or (now-getattr(self, "_last_vel_tx", 0.0)) < VEL_KEEPALIVE_S:
                return
        self.last_sent_vel = vel
        self.requested_speed_mps = vel
        self.last_winch_output = vel
        self._last_vel_tx = now
        if self.smoke_test:
            return
        self.w1p.send(cmd)

    @staticmethod
    def _normalise_aux_action_name(action: str) -> str:
        text = str(action or "None").strip()
        aliases = {
            "Accel Mode": "Acceleration Mode",
            "Traditional/Dynamic": "Acceleration Mode",
            "Battery Change": "Battery Change Mode",
            "Start Calibration": "Limit Calibration",
        }
        return aliases.get(text, text)

    def _aux_action_label(self, index: int, source: str = "ctrl") -> str:
        assignments = self.w1p_aux_assignments if str(source).lower().startswith("w1p") else self.ctrl_aux_assignments
        if not (0 <= int(index) < len(assignments)):
            return "AUX"
        action = self._normalise_aux_action_name(assignments[int(index)])
        if action == "Acceleration Mode":
            return f"Accel Mode | {self.acceleration_mode}"
        if action == "Drive Mode":
            try: name = str(self.drive_modes[self.active_drive_mode].get("name", f"Mode {self.active_drive_mode+1}"))
            except Exception: name = f"Mode {self.active_drive_mode+1}"
            return f"Drive Mode | {name}"
        if action == "Battery Change Mode":
            return f"Battery Change | {'On' if self.battery_change_mode else 'Off'}"
        if action == "Limit Calibration":
            if self.calibration_open and self.calibration_type == "Limit":
                return str(self.calibration_title or "Limit Calibration")
            return "Limit Calibration"
        if action == "Winch Calibration":
            if self.calibration_open and self.calibration_type == "Winch":
                return str(self.calibration_title or "Winch Calibration")
            return "Winch Calibration"
        if action == "Joystick Calibration":
            if self.joystick_calibration_open:
                return str(self.joystick_calibration_title or "Joystick Calibration")
            return "Joystick Calibration"
        if action.startswith("Preset "):
            parts = action.split()
            try:
                n = int(parts[1])
                if 1 <= n <= len(self.preset_names):
                    name = self._preset_display_name(n-1)
                    if len(parts) >= 3:
                        return f"{name} {parts[2]}"
            except Exception:
                pass
        return action

    def _handle_aux_action(self, index: int, source: str = "ctrl", raw_axis=None):
        """Execute one configured physical/touchscreen AUX assignment.

        The action vocabulary matches the locked Setup page. AUX1..AUX4 remain
        compatible with v26.06.26.25; AUX5 is carried in the spare A7 16-bit flag.
        """
        src = "w1p" if str(source).lower().startswith("w1p") else "ctrl"
        assignments = self.w1p_aux_assignments if src == "w1p" else self.ctrl_aux_assignments
        if not (0 <= int(index) < len(assignments)):
            return
        action = self._normalise_aux_action_name(assignments[int(index)])
        if not action or action == "None":
            return
        label = f"{'W1P-TS' if src == 'w1p' else 'CTRL'} AUX{int(index)+1}"
        try:
            if action == "Drive Mode":
                self.setDriveMode(1 - int(self.active_drive_mode))
            elif action in ("Acceleration Mode", "Accel Mode"):
                self.setAccelerationMode("Power" if self.acceleration_mode == "Speed" else "Speed")
            elif action in ("Battery Change Mode", "Battery Change"):
                self.setBatteryChange(not bool(self.battery_change_mode))
            elif action == "Limit Calibration":
                # AUX is the touchscreen wizard's Confirm control. Once this
                # calibration is open, each subsequent confirmed AUX press must
                # advance the current step rather than reopening step 1.
                if self.calibration_open and self.calibration_type == "Limit":
                    self.calibrationNext()
                else:
                    self.openLimitCalibration()
            elif action == "Winch Calibration":
                if self.calibration_open and self.calibration_type == "Winch":
                    self.calibrationNext()
                else:
                    self.openWinchCalibration()
            elif action == "Joystick Calibration":
                if self.joystick_calibration_open:
                    self._joystick_calibration_next(raw_axis)
                else:
                    self.openJoystickCalibration()
            elif action.startswith("Preset "):
                parts = action.split()
                if len(parts) >= 3:
                    preset_i = int(parts[1]) - 1
                    verb = parts[2].lower()
                    if verb == "save":
                        self.savePreset(preset_i)
                    elif verb == "recall":
                        self.recallPreset(preset_i)
                    elif verb == "slip":
                        target = self._preset_absolute_position(preset_i)
                        if target is not None:
                            self._cancel_goto()
                            self._sync_position(float(target))
                            self._not_calibrated = False
                            self._sync_service_mode_to_winch(force=True)
                            self._save_config(); self._notify_config()
            else:
                limit_action = None
                for display, which in (("Near Limit", "Near"), ("Far Limit", "Far"), ("Ref Point", "Reference")):
                    if action.startswith(display + " "):
                        limit_action = (which, action[len(display)+1:].strip().lower())
                        break
                if limit_action:
                    which, verb = limit_action
                    if verb == "save": self.saveLimit(which)
                    elif verb == "recall": self.recallLimit(which)
                    elif verb == "slip": self.slipLimit(which)
            result = ""
            if action == "Drive Mode":
                try:
                    result = f" -> {self.drive_modes[self.active_drive_mode].get('name', f'Mode {self.active_drive_mode+1}')}"
                except Exception:
                    result = f" -> Mode {self.active_drive_mode+1}"
            elif action in ("Battery Change Mode", "Battery Change"):
                result = f" -> {'On' if self.battery_change_mode else 'Off'}"
            elif action in ("Acceleration Mode", "Accel Mode"):
                result = f" -> {self.acceleration_mode}"
            self._log(f"[AUX] {label}: {action}{result}")
        except Exception as exc:
            self._log(f"[AUX] {label} failed ({action}): {exc}")

    @staticmethod
    def _display_field(value, limit: int = 24, *, replace_comma: bool = True) -> str:
        text = str(value if value is not None else "").replace("|", "/").replace("\r", " ").replace("\n", " ").strip()
        # Commas delimit packed preset lists, but they are valid human-readable
        # punctuation in standalone fields such as calibration instructions.
        if replace_comma:
            text = text.replace(",", "/")
        return text[:max(1, int(limit))]

    def _estop_status_text(self) -> str:
        # Operator-facing source names are intentionally limited to SRVR/CTRL/W1P.
        ctrl_fault = bool(
            self._ctrl_estop
            or (self._ctrl_flags & (FLAG_ADS1115_FAULT | FLAG_CTRL_HMI_FAULT | FLAG_CTRL_FW_FAULT))
            or (not self._ctrl_connected())
            or (not self._ctrl_fw_match)
            or (not self._ctrl_authority_fresh())
        )
        w1p_fault = bool(
            self._w1p_estop
            or self._w1p_internal_safety
            or (not self.w1p.connected)
            or (not self._w1p_status_fresh())
            or (not self._w1p_fw_match)
            or (self.winch_rs_status != "Connected")
        )
        parts = []
        if self._srvr_estop:
            parts.append("SRVR")
        if ctrl_fault:
            parts.append("CTRL")
        if w1p_fault and self.position_source != "Virtual":
            parts.append("W1P")
        return "E-Stop | " + (" & ".join(parts) if parts else "SRVR")

    def _normal_motion_zone_status(self):
        """Return the normal-operation Near/Far/Ramping operator state, if any.

        This is presentation-only state derived from the same calibrated limits,
        ramp geometry already used by motion control. It never changes a limit,
        velocity command or safety decision.
        """
        try:
            if self.state.pos_m is None:
                return None
            pos = float(self.state.pos_m)
            near = float(self.state.near_limit.position_m)
            far = float(self.state.far_limit.position_m)
        except Exception:
            return None

        # Near/Far are more specific than Ramping. Use the requested 1 m window
        # and resolve pathological short spans by whichever endpoint is closer.
        near_d = abs(pos - near)
        far_d = abs(far - pos)
        within_near = near_d <= LIMIT_STATUS_DISTANCE_M
        within_far = far_d <= LIMIT_STATUS_DISTANCE_M
        if within_near or within_far:
            if within_near and within_far:
                return "System | Near Limit" if near_d <= far_d else "System | Far Limit"
            return "System | Near Limit" if within_near else "System | Far Limit"

        # Ramping is a position-zone state, not a motion-only state. Once the
        # skate is inside either configured end ramp, keep the yellow Ramping
        # indication even after velocity reaches zero. Near/Far Limit remain more
        # specific and therefore win inside their 1 m endpoint windows above.
        lo, hi = (near, far) if near <= far else (far, near)
        span = max(0.0, hi - lo)
        if span <= 1e-9:
            return None
        near_ramp = self._ramp_distance(self.state.near_limit, span)
        far_ramp = self._ramp_distance(self.state.far_limit, span)
        if near <= far:
            in_near_ramp = near_ramp > 0.0 and pos <= near + near_ramp
            in_far_ramp = far_ramp > 0.0 and pos >= far - far_ramp
        else:
            in_near_ramp = near_ramp > 0.0 and pos >= near - near_ramp
            in_far_ramp = far_ramp > 0.0 and pos <= far + far_ramp
        if in_near_ramp or in_far_ramp:
            return "System | Ramping"
        return None

    def _resolved_system_status(self):
        """One canonical status description for SRVR and CTRL-TS."""
        if self.state.estop_active:
            text = self._estop_status_text()
            source = text.split("|", 1)[1].strip() if "|" in text else ""
            return text, "red", source, 1
        if self.joystick_calibration_open:
            return "System | Joystick Calibration", "yellow", "", 0
        if self.calibration_open:
            kind = "Winch Calibration" if self.calibration_type == "Winch" else "Limit Calibration"
            return f"System | {kind}", "yellow", "", 0
        if self.battery_change_mode:
            return "System | Battery Change Mode", "yellow", "", 0
        if self._not_calibrated:
            return "System | Uncalibrated", "yellow", "", 0
        zone_status = self._normal_motion_zone_status()
        if zone_status:
            return zone_status, "yellow", "", 0
        return "System | Active", "green", "", 0

    def _set_ctrl_ts_gate_reason(self, reason: str) -> None:
        reason = str(reason or "waiting").strip() or "waiting"
        self._ctrl_ts_gate_reason = reason
        if reason != self._ctrl_ts_gate_log_reason:
            self._ctrl_ts_gate_log_reason = reason
            self._log(f"[FW COORD] CTRL-TS gate: {reason}")

    def _grant_ctrl_ts_update(self, reason: str) -> bool:
        if not self._ctrl_ts_grant_latched:
            self._ctrl_ts_grant_latched = True
            self._log(f"[FW COORD] CTRL-TS final stage granted: {reason}")
        self._ctrl_ts_gate_reason = "granted"
        return True

    def _ctrl_ts_update_allowed(self) -> bool:
        """Grant CTRL-TS after ordered firmware convergence with bounded recovery.

        CTRL must always converge first. W1P is then given the normal pull path,
        the modern HTTP fallback path, and a generous ordered wait. If a present
        W1P cannot enter safe idle, the independent CTRL-TS update is eventually
        released rather than remaining at Waiting forever; W1P stays fail-closed
        and continues retrying its own authority update. Once granted, the final
        stage is monotonic for this SRVR release, although a temporarily stale
        CTRL still suppresses the grant until CTRL authority is fresh again.
        """
        now_wall = time.time()
        if not (self._ctrl_fw_match and self._ctrl_authority_fresh()):
            self._set_ctrl_ts_gate_reason("waiting for CTRL authority")
            return False
        matched_since = float(self._ctrl_fw_match_since or 0.0)
        if not (matched_since and (now_wall - matched_since) >= 1.0):
            self._set_ctrl_ts_gate_reason("confirming CTRL")
            return False
        if self._ctrl_ts_grant_latched:
            return True

        w1p_version, w1p_match, w1p_authority, snapshot_at = self.w1p.firmware_snapshot()
        w1p_present = bool(self.w1p.connected)
        w1p_current = bool(self._firmware_version_matches_current(w1p_version) and w1p_match)
        now_mono = time.monotonic()
        snapshot_fresh = bool(snapshot_at and (now_mono - float(snapshot_at)) <= (WINCH_STATUS_TIMEOUT_S * 2.0))

        if not w1p_present and not snapshot_fresh and (now_wall - matched_since) < self._w1p_fw_discovery_grace_s:
            self._set_ctrl_ts_gate_reason("discovering W1P")
            return False

        if w1p_present and w1p_current:
            self._w1p_fw_order_pending = False
            self._w1p_fw_order_pending_since = 0.0
            return self._grant_ctrl_ts_update("CTRL and W1P verified")

        if (w1p_present or snapshot_fresh) and not w1p_current:
            if not self._w1p_fw_order_pending:
                self._w1p_fw_order_pending = True
                self._w1p_fw_order_pending_since = now_mono
            since = float(self._w1p_fw_order_pending_since or now_mono)
            wait_age = max(0.0, now_mono - since)
            authority = str(w1p_authority or self._w1p_fw_authority or "unknown").strip().lower()
            actively_flashing = bool(
                self._fw_progress["w1p"]["active"]
                or authority in ("updating", "rebooting")
                or self._w1p_fw_authority in ("updating", "rebooting")
            )
            if actively_flashing and wait_age < W1P_ACTIVE_UPDATE_WAIT_S:
                self._set_ctrl_ts_gate_reason("waiting for W1P update")
                return False
            if (not actively_flashing) and wait_age < W1P_FINAL_STAGE_WAIT_S:
                if authority == "update_waiting_safe_idle" or self._w1p_fw_authority == "update_waiting_safe_idle":
                    self._set_ctrl_ts_gate_reason("W1P waiting for safe idle")
                else:
                    self._set_ctrl_ts_gate_reason("waiting for W1P authority")
                return False

            # W1P remains a firmware/safety mismatch and therefore cannot enable
            # motion. Allow only the independent HMI final stage to proceed; the
            # W1P beacons/fallback worker continue until W1P itself converges.
            return self._grant_ctrl_ts_update("bounded W1P wait expired; W1P remains fail-closed")

        if self._w1p_fw_order_pending:
            since = float(self._w1p_fw_order_pending_since or now_mono)
            if (now_mono - since) < self._w1p_fw_order_absent_timeout_s:
                self._set_ctrl_ts_gate_reason("waiting for W1P reboot")
                return False
            self._w1p_fw_order_pending = False
            self._w1p_fw_order_pending_since = 0.0
            return self._grant_ctrl_ts_update("W1P absent after ordered reboot window")

        return self._grant_ctrl_ts_update("W1P not present")

    def _ctrl_ts_update_allowed_safe(self) -> bool:
        """Fail-safe wrapper so later-stage coordinator faults can never block CTRL release discovery."""
        try:
            return bool(self._ctrl_ts_update_allowed())
        except Exception as exc:
            # CTRL is stage 1 and must still hear the release. Later stages remain
            # fail-closed until the coordinator recovers. Rate-limit identical logs.
            now = time.monotonic()
            last = float(getattr(self, "_ctrl_ts_gate_exception_log_at", 0.0) or 0.0)
            if not last or (now - last) >= 5.0:
                self._ctrl_ts_gate_exception_log_at = now
                self._log(f"[FW COORD] CTRL-TS gate error; keeping final stage closed: {exc}")
            return False

    def _limit_calibration_display_position(self) -> float:
        """Return the operator-facing Limit Calibration coordinate.

        Before Near is captured, preserve the current live coordinate. After the
        Near capture, show distance from that staged point without mutating the
        authoritative live Near/Far/Ref calibration. Raw encoder delta is preferred
        on hardware so an old/mismatched logical origin cannot leak into the wizard;
        Virtual mode falls back to the staged position delta.
        """
        pos_now = float(self.state.pos_m or 0.0)
        if not (self.calibration_open and self.calibration_type == "Limit"):
            return pos_now
        if self._limit_cal_pending.get("near") is None:
            return pos_now
        cap = self._limit_cal_capture
        near_raw = cap.get("near_raw")
        raw_now = None if self.position_source == "Virtual" else getattr(self, "_last_raw_pos", None)
        if near_raw is not None and raw_now is not None:
            return abs(float(int(raw_now) - int(near_raw)) / max(1.0, float(self.winch_units_per_m)))
        near_pos = cap.get("near_pos")
        if near_pos is not None:
            return abs(pos_now - float(near_pos))
        return 0.0

    def _build_controller_display_packet(self) -> str:
        """Build the proven DSP1 SRVR->CTRL display/status packet.

        CTRL firmware rewrites DSP1 to HMI1 and forwards it to CTRL-TS. This is
        deliberately separate from the control/safety path.
        """
        near_abs = float(self.state.near_limit.position_m or 0.0)
        far_abs = float(self.state.far_limit.position_m if self.state.far_limit.position_m is not None else near_abs + self.state.total_length_m)
        if far_abs < near_abs:
            near_abs, far_abs = far_abs, near_abs
        pos_abs = float(self.state.pos_m if self.state.pos_m is not None else near_abs)
        pos_rel = pos_abs - near_abs
        far_rel = far_abs - near_abs
        ref_set = self.state.ref_point.position_m is not None
        ref_abs = float(self.state.ref_point.position_m if self.state.ref_point.position_m is not None else near_abs)
        ref_rel = ref_abs - near_abs
        # Keep the signed distances outside the calibrated safe span. In Battery
        # Change/service mode this makes an excursion past Near read negative To
        # Near while To Far continues increasing (and vice-versa past Far).
        to_near = pos_abs - near_abs
        to_far = far_abs - pos_abs
        ramp_near = self._ramp_distance(self.state.near_limit, max(0.001, far_rel))
        ramp_far = self._ramp_distance(self.state.far_limit, max(0.001, far_rel))
        ctrl_ok = self._ctrl_connected()
        w1p_ok = bool(self.w1p.connected)
        if self.position_source == "Virtual":
            w1p_state = "demo"
        elif not w1p_ok:
            w1p_state = "error"
        elif self.winch_rs_status != "Connected" or self._w1p_estop or self._w1p_internal_safety:
            w1p_state = "fault"
        else:
            w1p_state = "ok"

        status, level, source, estop = self._resolved_system_status()

        cal_active = bool(self.joystick_calibration_open or self.calibration_open)
        if self.joystick_calibration_open:
            cal_kind = "Joystick"
            cal_step = int(self.joystick_calibration_step)
            cal_title = str(self.joystick_calibration_title or "Joystick Calibration")
            cal_instruction = (
                "Hold Joystick Left, then Press Confirm" if cal_step == 0 else
                "Release Joystick to Centre, then Press Confirm" if cal_step == 1 else
                "Hold Joystick Right, then Press Confirm"
            )
        elif self.calibration_open:
            cal_kind = str(self.calibration_type or "Limit")
            cal_step = int(self.calibration_step)
            cal_title = str(self.calibration_title or f"{cal_kind} Calibration")
            if cal_kind == "Winch":
                cal_instruction = "Set zero position, then confirm" if cal_step == 0 else "Move to 20 m position, then confirm"
            else:
                cal_instruction = (
                    "Move skate to NEAR limit, then confirm" if cal_step == 0 else
                    "Move skate to FAR limit, then confirm" if cal_step == 1 else
                    "Move skate to REFERENCE point, then confirm"
                )
        else:
            cal_kind, cal_step, cal_title, cal_instruction = "", 0, "", ""

        # Limit-calibration telemetry is intentionally small and is also carried
        # through CTRL's priority HMI state. Once Near has been staged, the wizard
        # position is deliberately re-zeroed to that capture so the operator sees
        # actual travel away from Near while moving toward Far/Ref. The live
        # calibrated coordinate remains untouched until the final transactional
        # commit at Ref.
        cal_pos = self._limit_calibration_display_position() if (self.calibration_open and self.calibration_type == "Limit") else float(self.state.pos_m or 0.0)
        def _cal_value(name):
            value = self._limit_cal_pending.get(name)
            return "" if value is None else f"{float(value):.2f}"
        def _joy_cal_value(name):
            value = self._joystick_cal_pending.get(name)
            return "" if value is None else f"{float(value):.4f}"

        mode = self.drive_modes[self.active_drive_mode]
        max_mps = float(mode.get("max_speed_mps", self.max_speed_mps))
        mode_name = self._display_field(mode.get("name", f"Mode {self.active_drive_mode+1}"))
        # AUX labels may contain both an action and a user-defined value/name.
        # "Drive Mode | Practice Mode" is 26 characters, so the old default
        # 24-character field limit truncated it to "Practice Mo" before CTRL-TS
        # ever saw the packet. Keep a bounded but sufficient field width.
        labels = [self._display_field(self._aux_action_label(i, source="ctrl"), 40) for i in range(5)]
        preset_names, preset_pos, preset_abs, preset_vis = [], [], [], []
        for i in range(10):
            preset_names.append(self._display_field(self._preset_display_name(i), 24))
            rel = self.preset_positions[i]
            preset_pos.append("" if rel is None else f"{float(rel):.2f}")
            absolute = self._preset_absolute_position(i)
            preset_abs.append("" if absolute is None else f"{float(absolute):.2f}")
            preset_vis.append("1" if (rel is not None and bool(self.preset_visible[i])) else "0")

        # Keep direction on the wire for transport/debug semantics. Operator-facing
        # Current Speed is rendered as a positive magnitude by SRVR/CTRL-TS.
        speed = float(self.current_speed_mps or 0.0)
        fields = [
            "DSP1", f"pos={pos_rel:.2f}", f"to_near={to_near:.2f}", f"to_far={to_far:.2f}",
            f"speed_mps={speed:.2f}", f"speed_kmh={speed*3.6:.2f}",
            "near=0.00", f"ref={ref_rel:.2f}", f"far={far_rel:.2f}",
            f"pos_frac={self._span_fraction(pos_abs):.6f}", f"ref_frac={self._span_fraction(ref_abs):.6f}",
            f"ramp_near={ramp_near:.3f}", f"ramp_far={ramp_far:.3f}",
            f"ramp_near_frac={self.nearRampFraction:.6f}", f"ramp_far_frac={self.farRampFraction:.6f}",
            f"ref_vis={1 if ref_set else 0}", f"estop={estop}",
            f"estop_src={self._display_field(source)}", f"status={self._display_field(status, 40)}",
            f"status_level={level}", f"ctrl={1 if ctrl_ok else 0}", "srvr=1",
            f"srvr_fw={self._current_firmware_version()}", f"fw_session={self._firmware_authority_session}",
            f"fw_ctrl_active={1 if self._fw_progress['ctrl']['active'] else 0}",
            f"fw_ctrl_phase={self._display_field(self._fw_progress['ctrl']['phase'], 32)}",
            f"fw_ctrl_pct={int(self._fw_progress['ctrl']['pct'])}",
            f"fw_w1p_active={1 if self._fw_progress['w1p']['active'] else 0}",
            f"fw_w1p_phase={self._display_field(self._fw_progress['w1p']['phase'], 32)}",
            f"fw_w1p_pct={int(self._fw_progress['w1p']['pct'])}",
            # CTRL-TS is deliberately last. If W1P is physically absent it does
            # not block the display update; if present, it must first report the
            # current SRVR firmware release.
            f"fw_ts_allowed={1 if self._ctrl_ts_update_allowed_safe() else 0}",
            f"w1p={1 if w1p_ok else 0}", f"w1p_state={w1p_state}",
            f"service={1 if self._service_override_active() else 0}", f"flags={int(self._ctrl_flags)}",
            f"cal_active={1 if cal_active else 0}", f"cal_kind={self._display_field(cal_kind, 16)}",
            f"cal_step={cal_step}", f"cal_title={self._display_field(cal_title, 32)}",
            f"cal_instruction={self._display_field(cal_instruction, 64, replace_comma=False)}",
            f"cal_pos={cal_pos:.2f}", f"cal_near={_cal_value('near')}",
            f"cal_ref={_cal_value('ref')}", f"cal_far={_cal_value('far')}",
            f"cal_joy={float(self._ctrl_axis):.4f}",
            f"cal_left={_joy_cal_value('left')}", f"cal_centre={_joy_cal_value('centre')}",
            f"cal_right={_joy_cal_value('right')}",
            f"aux1={labels[0]}", f"aux2={labels[1]}", f"aux3={labels[2]}", f"aux4={labels[3]}", f"aux5={labels[4]}",
            f"max_mps={max_mps:.2f}", f"max_kmh={max_mps*3.6:.2f}", f"mode={mode_name}",
            f"drive_mode={mode_name}", f"accel_mode={self._display_field(self.acceleration_mode)}",
            f"battery_change={'On' if self.battery_change_mode else 'Off'}",
            f"srvr_time={time.strftime('%Y-%m-%d  %H:%M:%S')}", f"uptime={self.uptime}",
            f"ctrl_ip={self._display_field(self.ctrl_ip)}", f"w1p_ip={self._display_field(self.w1p_ip)}",
            f"preset_names={','.join(preset_names)}", f"preset_pos={','.join(preset_pos)}",
            f"preset_abs={','.join(preset_abs)}", f"preset_vis={','.join(preset_vis)}",
        ]
        return "|".join(fields) + "\n"

    def _build_controller_marker_packet(self) -> str:
        """Build compact real-position telemetry for the CTRL-TS marker only."""
        near_abs = float(self.state.near_limit.position_m or 0.0)
        far_abs = float(self.state.far_limit.position_m if self.state.far_limit.position_m is not None else near_abs + self.state.total_length_m)
        if far_abs < near_abs:
            near_abs, far_abs = far_abs, near_abs
        pos_abs = float(self.state.pos_m if self.state.pos_m is not None else near_abs)
        pos_frac = self._span_fraction(pos_abs)
        return f"DMP1|pos_frac={pos_frac:.6f}|speed_mps={float(self.current_speed_mps):.3f}\n"

    def _send_controller_marker_packet(self):
        if self.smoke_test:
            return
        target = str(self.ctrl_ip or "").strip()
        if not target:
            return
        now = time.monotonic()
        if (now - self._last_ctrl_marker_tx) < CTRL_MARKER_MIN_CHANGE_INTERVAL_S:
            return
        packet = self._build_controller_marker_packet().encode("ascii", "ignore")
        # Change-driven only: Encoder mode therefore cannot manufacture samples
        # faster than the verified W1P feedback; Virtual mode can expose the
        # newer SRVR state at the 20 Hz marker cadence.
        if packet == self._last_ctrl_marker_packet:
            return
        if self._stage_ctrl_marker_datagram(packet, target):
            self._last_ctrl_marker_packet = packet
            self._last_ctrl_marker_tx = now

    def _send_controller_display_packet(self, force: bool = False):
        if self.smoke_test:
            return
        target = str(self.ctrl_ip or "").strip()
        if not target:
            return
        now = time.time()
        # Building DSP1 walks a large amount of live/config state. CTRL forwards
        # bulk HMI at only 4 Hz, so rebuilding it at the 25 ms safety tick wastes
        # UI-thread time without increasing touchscreen responsiveness.
        if not force and (now - self._last_ctrl_display_build_at) < HMI_DISPLAY_MIN_CHANGE_INTERVAL_S:
            return
        self._last_ctrl_display_build_at = now
        packet = self._build_controller_display_packet().encode("ascii", "ignore")
        changed = packet != self._last_ctrl_display_packet
        if not force:
            if changed and (now - self._last_ctrl_display_change_tx) < HMI_DISPLAY_MIN_CHANGE_INTERVAL_S:
                return
            if (not changed) and (now - self._last_ctrl_display_keepalive_tx) < HMI_DISPLAY_KEEPALIVE_S:
                return
        # DSP1 must use the controller worker's bound UDP/5000 return path. The
        # joystick/control stream and heartbeat ACK already prove that path works;
        # staging the latest display snapshot there prevents a one-way unbound
        # socket/source-route mismatch from leaving CTRL-TS on fallback data.
        if self._stage_ctrl_display_datagram(packet, target):
            self._last_ctrl_display_packet = packet
            self._last_ctrl_display_keepalive_tx = now
            if changed:
                self._last_ctrl_display_change_tx = now

    def _send_ctrl_firmware_beacon(self, force: bool = False) -> None:
        """Advertise SRVR authority over CTRL's existing non-blocking UDP socket.

        This is independent of DSP1 layout/change throttling. A matched CTRL only
        compares the announced version/session and never performs HTTP until a
        mismatch has first put the node into its fail-closed authority path.
        """
        if self.smoke_test or self._stop_evt.is_set():
            return
        target = str(self.ctrl_ip or "").strip()
        if not target:
            return
        now = time.monotonic()
        if not force and now - float(self._last_ctrl_fw_beacon or 0.0) < FIRMWARE_BEACON_INTERVAL_S:
            return
        self._last_ctrl_fw_beacon = now
        packet = (
            f"SRVR_FW|version={self._current_firmware_version()}|"
            f"session={self._firmware_authority_session}|"
            f"ts_allowed={1 if self._ctrl_ts_update_allowed_safe() else 0}\n"
        ).encode("ascii", "ignore")
        try:
            with self._ctrl_presence_tx_lock:
                # shutdown sets _stop_evt before taking this same lock to send
                # SRVR_OFFLINE. Re-check under the lock so a worker already
                # waiting here can never emit SRVR_FW after the offline packet.
                if self._stop_evt.is_set():
                    return
                self._ctrl_display_sock.sendto(packet, (target, SERVER_BIND_PORT))
        except Exception:
            pass

    def _send_w1p_firmware_beacon(self, force: bool = False) -> None:
        """Advertise W1P authority only after CTRL is on this SRVR release.

        This makes the coordinated update order deterministic: CTRL first, W1P
        second, CTRL-TS last. A disconnected W1P does not block CTRL-TS later.
        """
        if self.smoke_test or self._stop_evt.is_set():
            return
        if not (self._ctrl_fw_match and self._ctrl_authority_fresh()):
            return
        now = time.monotonic()
        if not force and now - float(self._last_w1p_fw_beacon or 0.0) < FIRMWARE_BEACON_INTERVAL_S:
            return
        self._last_w1p_fw_beacon = now
        if self._stop_evt.is_set():
            return
        self.w1p.send(
            f"SRVR_FW|version={self._current_firmware_version()}|session={self._firmware_authority_session}"
        )

    def _legacy_firmware_push_worker(self, role: str, host: str) -> None:
        """Push the exact bundled EdgeBox image to a pre-beacon field node.

        v26.10.01.01 cannot understand the later SRVR release beacon once it has
        already marked an older SRVR session as matched. Its existing browser
        updater is the backwards-compatible bridge: the new SRVR uploads the
        already SHA-verified authority image from a background thread, so no HTTP
        work can stall the motion/UI loop.
        """
        role = str(role).lower()
        try:
            bundle = self._firmware_bundle
            image = getattr(bundle, "images", {}).get(role) if bundle is not None else None
            if image is None:
                self._log(f"[FW AUTO] {role.upper()} authority image unavailable; legacy push skipped")
                return
            payload = Path(image.path).read_bytes()
            if len(payload) != int(image.size):
                raise RuntimeError("authority image size changed after startup verification")
            token = "CTRL" if role == "ctrl" else "W1P"
            filename = f"HV_P2P_{token}_{self._current_firmware_version()}_FIRMWARE.bin"
            boundary = f"----HVP2P{int(time.time_ns()):x}"
            pre = (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode("ascii")
            post = f"\r\n--{boundary}--\r\n".encode("ascii")
            total_len = len(pre) + len(payload) + len(post)
            self._set_fw_progress(role, True, "Uploading", 0)
            conn = http.client.HTTPConnection(str(host), 80, timeout=12.0)
            try:
                conn.putrequest("POST", "/update/app")
                conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
                conn.putheader("Content-Length", str(total_len))
                conn.putheader("Connection", "close")
                conn.endheaders()
                conn.send(pre)
                sent_payload = 0
                chunk_size = 64 * 1024
                for off in range(0, len(payload), chunk_size):
                    chunk = payload[off:off+chunk_size]
                    conn.send(chunk)
                    sent_payload += len(chunk)
                    pct = int((100 * sent_payload) / max(1, len(payload)))
                    self._set_fw_progress(role, True, "Uploading", pct)
                conn.send(post)
                self._set_fw_progress(role, True, "Verifying", 100)
                resp = conn.getresponse()
                text = resp.read(512).decode("utf-8", "ignore").strip()
                status = int(resp.status)
            finally:
                conn.close()
            if 200 <= status < 300:
                self._set_fw_progress(role, False, "Complete", 100)
                self._log(
                    f"[FW AUTO] {token} legacy bridge accepted {self._current_firmware_version()}; "
                    "device reboot/update started"
                )
            else:
                self._set_fw_progress(role, False, "Failed", 100)
                self._log(f"[FW AUTO] {token} legacy bridge HTTP {status}: {text or 'update rejected'}")
        except Exception as exc:
            self._set_fw_progress(role, False, "Failed", 0)
            self._log(f"[FW AUTO] {role.upper()} legacy bridge failed: {exc}")
        finally:
            self._legacy_fw_push_active[role] = False

    def _try_start_legacy_firmware_push(self, role: str, host: str, reported: str, connected: bool, *, allow_modern_fallback: bool = False) -> bool:
        """Start one background verified OTA upload to an older field node.

        Pre-authority releases use this immediately as their compatibility bridge.
        Modern releases normally pull from SRVR themselves; ``allow_modern_fallback``
        is used only after a bounded mismatch grace period if that pull never starts.
        All HTTP/file I/O remains on the daemon worker, never the motion/UI thread.
        """
        role = "w1p" if str(role).lower().startswith("w1p") else "ctrl"
        host = str(host or "").strip()
        reported = str(reported or "").strip()
        if self.smoke_test or self._firmware_bundle is None or not host or not connected:
            return False
        legacy_required = self._legacy_firmware_push_required(reported)
        modern_fallback = bool(allow_modern_fallback and self._firmware_version_is_older(reported))
        if not reported or not (legacy_required or modern_fallback):
            return False
        now = time.monotonic()
        with self._lock:
            if self._legacy_fw_push_active.get(role):
                return False
            if now - float(self._legacy_fw_push_last_attempt.get(role, 0.0)) < 3.0:
                return False
            self._legacy_fw_push_last_attempt[role] = now
            self._legacy_fw_push_active[role] = True
        mode = "legacy-compatible" if legacy_required else "modern fallback"
        self._log(
            f"[FW AUTO] {role.upper()} {reported} != {self._current_firmware_version()}; "
            f"starting {mode} push"
        )
        threading.Thread(
            target=self._legacy_firmware_push_worker, args=(role, host),
            name=f"HVP2P-{role.upper()}-LegacyOTA", daemon=True,
        ).start()
        return True

    def _service_firmware_recovery_background(self) -> None:
        """Background-safe recovery when a modern node misses its pull update.

        This deliberately performs no GUI work and no direct motor decision. It
        only starts the already-existing asynchronous verified HTTP push after
        the same bounded mismatch grace used by the Qt path. W1P receives a STOP
        request and its VEL bridge is cleared before a fallback attempt; W1P's
        own web updater still refuses flash unless it independently proves the
        stopped/braked service state.
        """
        if self.smoke_test or self._firmware_bundle is None or self._stop_evt.is_set():
            return
        now_wall = time.time()

        ctrl_present = bool(self._ctrl_connected() or self._ctrl_authority_fresh())
        ctrl_version = str(self._ctrl_fw_version or "").strip()
        if ctrl_present and self._firmware_version_is_older(ctrl_version):
            if not self._fw_mismatch_since.get("ctrl", 0.0):
                self._fw_mismatch_since["ctrl"] = now_wall
            mismatch_since = float(self._fw_mismatch_since.get("ctrl", 0.0) or 0.0)
            pull_active = bool(self._fw_progress["ctrl"]["active"] or self._ctrl_fw_authority in ("updating", "rebooting"))
            if mismatch_since and (now_wall - mismatch_since) >= self._fw_modern_fallback_delay_s and not pull_active:
                self._try_start_legacy_firmware_push(
                    "ctrl", str(self.ctrl_ip or "").strip(), ctrl_version, True, allow_modern_fallback=True
                )
                return

        if not (self._ctrl_fw_match and self._ctrl_authority_fresh()):
            return
        w1p_version, w1p_match, w1p_authority, snapshot_at = self.w1p.firmware_snapshot()
        w1p_present = bool(self.w1p.connected)
        if not w1p_present or not self._firmware_version_is_older(w1p_version):
            return
        if not self._fw_mismatch_since.get("w1p", 0.0):
            self._fw_mismatch_since["w1p"] = now_wall
        mismatch_since = float(self._fw_mismatch_since.get("w1p", 0.0) or 0.0)
        authority = str(w1p_authority or self._w1p_fw_authority or "").strip().lower()
        pull_active = bool(self._fw_progress["w1p"]["active"] or authority in ("updating", "rebooting", "update_waiting_safe_idle"))
        if mismatch_since and (now_wall - mismatch_since) >= self._fw_modern_fallback_delay_s and not pull_active:
            try:
                self.w1p.clear_velocity_refresh()
                self.w1p.send("STOP")
            except Exception:
                pass
            self._try_start_legacy_firmware_push(
                "w1p", str(self.w1p_ip or "").strip(), str(w1p_version or "").strip(), True, allow_modern_fallback=True
            )

    def _service_legacy_firmware_push(self) -> None:
        """Bridge old matched firmware directly to the current SRVR release.

        This path is used only while a connected EdgeBox reports an older version.
        Current firmware continues to use the normal authority beacon/manifest path.
        Uploads run on their own thread and are rate-limited so telemetry, joystick
        processing and the 500 ms W1P freshness watchdog can never be blocked.
        """
        if self.smoke_test or self._firmware_bundle is None:
            return
        # A fresh HMI_STATUS proves CTRL is alive even if the high-rate control
        # datagram stream has just rolled across its timeout boundary. Treat either
        # signal as sufficient presence for the legacy firmware bridge.
        now = time.time()
        ctrl_present = bool(self._ctrl_connected() or self._ctrl_authority_fresh())
        ctrl_target = ("ctrl", str(self.ctrl_ip or "").strip(), str(self._ctrl_fw_version or "").strip(), ctrl_present)
        ctrl_older = self._firmware_version_is_older(ctrl_target[2])
        if ctrl_older:
            if not self._fw_mismatch_since.get("ctrl", 0.0):
                self._fw_mismatch_since["ctrl"] = now
            self._send_velocity(0.0, force=True)
            if self._legacy_firmware_push_required(ctrl_target[2]):
                self._try_start_legacy_firmware_push(*ctrl_target)
                return
            mismatch_since = float(self._fw_mismatch_since.get("ctrl", 0.0) or 0.0)
            pull_active = bool(self._fw_progress["ctrl"]["active"] or self._ctrl_fw_authority in ("updating", "rebooting"))
            if mismatch_since and (now - mismatch_since) >= self._fw_modern_fallback_delay_s and not pull_active:
                self._try_start_legacy_firmware_push(*ctrl_target, allow_modern_fallback=True)
                return

        # Never update W1P while CTRL is still converging.  Once CTRL is current,
        # W1P gets the same pull-first / bounded-push-fallback treatment.
        if not (self._ctrl_fw_match and self._ctrl_authority_fresh()):
            return
        w1p_target = ("w1p", str(self.w1p_ip or "").strip(), str(self._w1p_fw_version or "").strip(), bool(self.w1p.connected))
        w1p_older = self._firmware_version_is_older(w1p_target[2])
        if w1p_older:
            if not self._fw_mismatch_since.get("w1p", 0.0):
                self._fw_mismatch_since["w1p"] = now
            self._send_velocity(0.0, force=True)
            if self._legacy_firmware_push_required(w1p_target[2]):
                self._try_start_legacy_firmware_push(*w1p_target)
                return
            mismatch_since = float(self._fw_mismatch_since.get("w1p", 0.0) or 0.0)
            pull_active = bool(self._fw_progress["w1p"]["active"] or self._w1p_fw_authority in ("updating", "rebooting", "update_waiting_safe_idle"))
            if mismatch_since and (now - mismatch_since) >= self._fw_modern_fallback_delay_s and not pull_active:
                self._try_start_legacy_firmware_push(*w1p_target, allow_modern_fallback=True)

    def _motion_tick(self):
        self._virtual_motion_step()
        self._virtual_output_inhibit()
        connected = self._ctrl_connected()
        flags = self._ctrl_flags
        self._ctrl_estop = bool(flags & FLAG_ESTOP_PRESSED)

        # Encoder mode fail-safe sources include physical/link/RS485 faults plus
        # W1P local command/service watchdogs. Virtual is a deliberately local
        # SRVR simulation and does not require W1P/Leadshine presence.
        # Not-calibrated remains a yellow service state.
        ctrl_fw_ok = bool(self._ctrl_fw_match and self._ctrl_authority_fresh())
        w1p_fw_ok = bool(self._w1p_fw_match and self._w1p_status_fresh())
        ctrl_interface_fault = bool(flags & (FLAG_CTRL_HMI_FAULT | FLAG_CTRL_FW_FAULT))
        # Virtual is an SRVR-local motion simulation. It must remain usable with
        # no W1P/Leadshine hardware connected, while CTRL/SRVR input and safety
        # remain authoritative. Any W1P that is physically present is still held
        # stopped/inhibited by _virtual_output_inhibit().
        virtual_demo = (self.position_source == "Virtual")
        w1p_safety = bool(
            self._w1p_estop
            or self._w1p_internal_safety
            or (not self.w1p.connected)
            or (not self._w1p_status_fresh())
            or (not w1p_fw_ok)
            or (self.winch_rs_status != "Connected")
        )
        safety = bool(
            self._srvr_estop
            or self._ctrl_estop
            or bool(flags & FLAG_ADS1115_FAULT)
            or ctrl_interface_fault
            or (not connected)
            or (not ctrl_fw_ok)
            or ((not virtual_demo) and w1p_safety)
        )
        self.state.estop_active = safety

        if flags & FLAG_CANCEL_PRESSED:
            self._cancel_goto()

        # Calibration Cancel from CTRL-TS is edge-captured in the UDP worker so
        # it survives Qt/background scheduling stalls. In smoke tests, where the
        # worker is intentionally absent, retain deterministic direct flag edges.
        cal_cancel = False
        if self.smoke_test:
            cal_pressed = bool(flags & FLAG_CAL_CANCEL)
            cal_cancel = bool(cal_pressed and not self._ctrl_cal_cancel_last)
            self._ctrl_cal_cancel_last = cal_pressed
        elif self._ctrl_cal_cancel_pending:
            self._ctrl_cal_cancel_pending = False
            cal_cancel = True
        if cal_cancel:
            if self.joystick_calibration_open:
                self.cancelJoystickCalibration()
            elif self.calibration_open:
                self.cancelCalibration()

        mode_pressed = bool(flags & FLAG_MODE_TOGGLE)
        if mode_pressed and not self._mode_last:
            self.setDriveMode(1-self.active_drive_mode)
        self._mode_last = mode_pressed
        batt_pressed = bool(flags & FLAG_BATT_CHANGE_TOGGLE)
        if batt_pressed and not self._batt_last:
            self.setBatteryChange(not self.battery_change_mode)
        self._batt_last = batt_pressed
        # Runtime AUX actions are edge-captured by the UDP listener thread and
        # persist here until consumed. This removes the old dependency on the
        # Qt timer sampling a short CTRL pulse at exactly the right instant.
        if self.smoke_test:
            # Preserve deterministic unit-test/direct-call behaviour when no
            # listener thread is running.
            for aux_i, aux_bit in enumerate(CTRL_AUX_BITS):
                pressed = bool(flags & aux_bit)
                if pressed and not self._ctrl_aux_last[aux_i]:
                    self._handle_aux_action(aux_i, source="ctrl")
                self._ctrl_aux_last[aux_i] = pressed
        else:
            for _ in range(16):
                try:
                    aux_event = self._ctrl_aux_events.get_nowait()
                except queue.Empty:
                    break
                if isinstance(aux_event, tuple):
                    aux_i, aux_axis, _aux_time = aux_event
                else:
                    # Backward-safe for tests or an event queued before an in-app
                    # hot transition; normal runtime always uses the tuple above.
                    aux_i, aux_axis = aux_event, None
                self._handle_aux_action(int(aux_i), source="ctrl", raw_axis=aux_axis)
            for aux_i, aux_bit in enumerate(CTRL_AUX_BITS):
                self._ctrl_aux_last[aux_i] = bool(flags & aux_bit)

        self._sync_service_mode_to_winch()
        self._update_battery_change_auto_cancel()

        if safety:
            self._cancel_goto()
            self._send_safety_stop_limited(force=not bool(self._safety_active_last))
            self._safety_active_last = True
            return

        # A cleared E-stop/link/interface fault must never resume from a joystick
        # that was left displaced while the system was stopped. Require one
        # deliberate return through neutral before accepting manual motion again.
        if self._safety_active_last:
            # Reassert the inhibit once on the clear edge. W1P may have just
            # reconnected and locally cleared its peer-timeout inhibit, so this
            # closes the gap until the operator proves neutral.
            self._send_safety_stop_limited(force=True)
            self._joystick_neutral_required = True
            self._log("[Safety] Sources clear; waiting for joystick neutral before re-arm")
        self._safety_active_last = False
        if self.state.pos_m is None:
            self._send_velocity(0.0, force=True)
            return

        # Moving the stick is required by the calibration wizard. Never allow
        # those movements to command the winch while the overlay is open.
        if self.joystick_calibration_open:
            self._cancel_goto()
            self._send_velocity(0.0, force=abs(self.last_sent_vel) > .0001)
            return

        self._update_joystick_centre_drift()
        # _ctrl_axis already follows the physical Left=- / Right=+ convention.
        # Apply calibration first, then the optional user Invert exactly once.
        axis = self._calibrated_joystick(self._ctrl_axis) * (-1 if self.reverse_joystick else 1)
        deadband = max(0.0, min(25.0, float(self.joystick_deadband_pct)))
        if self._joystick_neutral_required:
            # A zero-percent operating deadband is valid, but the post-wizard
            # release interlock still needs a small practical neutral window so
            # ADC/joystick noise cannot latch motion off forever.
            neutral_band = max(1.0, deadband)
            if abs(axis*100) <= neutral_band:
                self._joystick_neutral_required = False
                self._restore_servo_after_safety_neutral()
            self._cancel_goto()
            self._send_velocity(0.0, force=abs(self.last_sent_vel) > .0001)
            return
        if abs(axis*100) < deadband:
            axis = 0.0
        if self.goto_target_m is not None and abs(axis*100) >= deadband:
            self._cancel_goto()

        service = self._service_override_active()
        if self.goto_target_m is not None:
            vel, reached = self._goto_velocity(self.goto_target_m-self.state.pos_m)
            if reached:
                self._cancel_goto()
                vel = 0.0
            if service:
                limit = self._service_speed_limit_mps()
                vel = max(-limit, min(limit, vel))
        else:
            vmax = self._service_speed_limit_mps() if service else self.max_speed_mps
            vel = axis*vmax

        # Service mode intentionally permits travel outside saved Near/Far limits
        # for calibration and battery-change work. Normal operation always uses
        # the predictive hard-limit envelope and programmed ramp zones.
        if not service:
            vel = self._hard_limit_velocity(float(self.state.pos_m), vel)
        self._send_velocity(vel)

    # --- Free-D ---
    def _start_freed_input(self):
        self._freed_in_stop.set()
        try:
            if self._freed_in_sock: self._freed_in_sock.close()
        except Exception: pass
        self._freed_in_sock=None
        if not self.freed_input_enabled: return
        self._freed_in_stop=threading.Event()
        try:
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            sock.bind((self.freed_input_bind_ip,self.freed_input_port)); sock.settimeout(.25); self._freed_in_sock=sock
            threading.Thread(target=self._freed_input_worker,args=(sock,),daemon=True).start()
        except Exception as exc: self._log(f"[Free-D] input bind failed: {exc}")

    def _freed_input_worker(self,sock):
        while not self._freed_in_stop.is_set():
            try: data,addr=sock.recvfrom(2048)
            except socket.timeout: continue
            except OSError: break
            if not data or len(data)<29 or data[0]!=0xD1: continue
            if not _freed_checksum_valid(data):
                continue
            now=time.time(); raw_pan=_s24_to_int(data[2:5]); raw_tilt=_s24_to_int(data[5:8]); raw_roll=_s24_to_int(data[8:11])
            rz=_u24_to_int(data[20:23]); rf=_u24_to_int(data[23:26])
            zoom_dec = self._decode_lens(rz)
            focus_dec = self._decode_lens(rf)
            self._remember_lens_auto("zoom", zoom_dec)
            self._remember_lens_auto("focus", focus_dec)
            with self._lock:
                self.freed_in_raw={"Cam ID":int(data[1]),"Pan":raw_pan,"Tilt":raw_tilt,"Roll":raw_roll,"Zoom":rz,"Focus":rf}
                self.freed_in={"Cam ID":int(data[1]),"Pan":raw_pan/32768.0,"Tilt":raw_tilt/32768.0,"Roll":raw_roll/32768.0,"Zoom":zoom_dec,"Focus":focus_dec}
                self.freed_input_last_rx=now; self._freed_in_times.append(now)
                recent=[t for t in self._freed_in_times if t>=now-1]
                self.freed_in_fps=(len(recent)-1)/(recent[-1]-recent[0]) if len(recent)>1 and recent[-1]>recent[0] else float(len(recent))

    @staticmethod
    def _decode_lens_for_type(u24, lens_type: str):
        t = str(lens_type).lower()
        u24 = int(u24) & 0xFFFFFF
        if t == "u24": return u24
        if t == "u16": return u24 & 0xffff
        if t == "i16":
            v = u24 & 0xffff
            return v - 0x10000 if v & 0x8000 else v
        return u24 - 0x1000000 if u24 & 0x800000 else u24

    def _input_sign(self, name: str, inverts=None) -> int:
        # Preserve the proven v26.06.26.25 native Focus correction while
        # keeping the visible user Invert checkbox OFF by default.
        native = -1 if str(name).strip().lower() == "focus" else 1
        inv = self.freed_input_inverts if inverts is None else dict(inverts)
        user = -1 if bool(inv.get(str(name), False)) else 1
        return native * user

    def _output_sign(self, name: str, inverts=None) -> int:
        inv = self.freed_output_inverts if inverts is None else dict(inverts)
        return -1 if bool(inv.get(str(name), False)) else 1

    def _decode_lens(self, u24):
        return self._decode_lens_for_type(u24, self.freed_lens_type)

    @staticmethod
    def _normalised_geometry(geometry):
        """Return sorted, de-duplicated geometry points with numeric X/Y/Z values."""
        pts = []
        for raw in list(geometry or []):
            if not isinstance(raw, dict):
                continue
            try:
                x = float(raw.get("x", 0.0))
                y = float(raw.get("y", 0.0))
            except Exception:
                continue
            z_raw = raw.get("z", None)
            try:
                z = None if z_raw is None else float(z_raw)
            except Exception:
                z = None
            pts.append({"x": x, "y": y, "z": z, "name": str(raw.get("name", ""))})
        pts.sort(key=lambda p: p["x"])
        dedup = []
        for point in pts:
            if dedup and abs(point["x"] - dedup[-1]["x"]) < 1e-9:
                dedup[-1] = point
            else:
                dedup.append(point)
        return dedup

    @classmethod
    def _smooth_geometry_y(cls, x, geometry):
        """Smooth C1 reference-height interpolation through P1..P5.

        The geometry points are operator-entered reference heights at arbitrary
        X positions within the Near/Far cable span.  P1 and P5 are therefore not
        cable supports. A cubic Hermite interpolation creates a smooth reference
        profile between points, and the endpoint tangents are extended to the
        actual Near/Far supports when the first/last geometry point is inboard.
        The physical whole-span sag model is applied separately afterwards.
        """
        pts = cls._normalised_geometry(geometry)
        if not pts:
            return 0.0
        if len(pts) == 1:
            return float(pts[0]["y"])
        xv = float(x)

        # Finite-difference tangents for a smooth, continuous curve.
        slopes = []
        for i, p in enumerate(pts):
            if i == 0:
                dx = max(1e-9, pts[1]["x"] - p["x"])
                slopes.append((pts[1]["y"] - p["y"]) / dx)
            elif i == len(pts) - 1:
                dx = max(1e-9, p["x"] - pts[i-1]["x"])
                slopes.append((p["y"] - pts[i-1]["y"]) / dx)
            else:
                dx = max(1e-9, pts[i+1]["x"] - pts[i-1]["x"])
                slopes.append((pts[i+1]["y"] - pts[i-1]["y"]) / dx)

        # P1/P5 may sit anywhere inside the actual span. Continue the reference
        # geometry to the Near/Far supports using the same endpoint tangent so
        # the cable path does not artificially become flat outside P1/P5.
        if xv <= pts[0]["x"]:
            return float(pts[0]["y"]) + slopes[0] * (xv - float(pts[0]["x"]))
        if xv >= pts[-1]["x"]:
            return float(pts[-1]["y"]) + slopes[-1] * (xv - float(pts[-1]["x"]))

        for i in range(len(pts) - 1):
            p0, p1 = pts[i], pts[i+1]
            if p0["x"] <= xv <= p1["x"]:
                h = max(1e-9, p1["x"] - p0["x"])
                t = max(0.0, min(1.0, (xv - p0["x"]) / h))
                t2, t3 = t*t, t*t*t
                h00 = 2*t3 - 3*t2 + 1
                h10 = t3 - 2*t2 + t
                h01 = -2*t3 + 3*t2
                h11 = t3 - t2
                return (h00*p0["y"] + h10*h*slopes[i] +
                        h01*p1["y"] + h11*h*slopes[i+1])
        return float(pts[-1]["y"])

    @classmethod
    def _geometry_z(cls, x, geometry):
        """Top-view Z uses P1/P5 to define a line across the whole cable span.

        P1 and P5 are reference points, not endpoints. The line is therefore
        extrapolated through them to Near/Far instead of clamping Z outside the
        P1..P5 interval.
        """
        raw = [p for p in list(geometry or []) if isinstance(p, dict)]
        if not raw:
            return 0.0
        # Z remains an intentionally two-point definition: P1 and P5. Do not
        # choose the lowest/highest-X geometry points here, because P2..P4 may
        # legitimately sit outside either reference point's X position.
        p0 = raw[0]
        p1 = raw[4] if len(raw) >= 5 else raw[-1]
        x0 = float(p0.get("x", 0.0))
        x1 = float(p1.get("x", x0 + 1.0))
        z0 = float(p0.get("z", 0.0) or 0.0)
        z1 = float(p1.get("z", 0.0) or 0.0)
        dx = x1 - x0
        if abs(dx) < 1e-9:
            return z0
        t = (float(x) - x0) / dx
        return z0 + (z1-z0)*t

    def _span_fraction(self, position) -> float:
        """Return one canonical Near->Far normalized coordinate for all UIs."""
        near = float(self.state.near_limit.position_m or 0.0)
        far = float(self.state.far_limit.position_m if self.state.far_limit.position_m is not None else near + self.state.total_length_m)
        if far < near:
            near, far = far, near
        span = far - near
        if span <= 1e-9:
            return 0.0
        try:
            value = float(position)
        except Exception:
            value = near
        return max(0.0, min(1.0, (value - near) / span))

    def _cable_span_bounds(self):
        """Return Free-D X bounds relative to the calibrated Near Limit."""
        near = float(self.state.near_limit.position_m or 0.0)
        far = float(self.state.far_limit.position_m or 0.0)
        return 0.0, max(0.1, far - near)

    def _cable_y_at(self, x, geometry, cable_weight, tension, skate_weight, highline,
                    skate_x, support0=None, support1=None):
        """Physical side-view cable height at X.

        The single canonical sag model deliberately uses *all four* operator
        inputs from the Free-D Geometry card:
          - Skate Weight: suspended camera/skate package mass.
          - Cable Weight: kg per 100 m, per individual highline cable.
          - Cable Tension: kgf, per individual highline cable (legacy SRVR rule).
          - Highline Mode: Single carries all Skate Weight; Dual shares it 50/50.

        Near/Far are the cable supports. P1..P5 are geometry/control points and
        may be anywhere between them. Cable self-weight is represented by the
        standard small-sag parabolic horizontal-tension approximation. The skate
        is a moving point load.
        With kg mass values and kgf tension, gravitational acceleration cancels
        in the load/tension ratio.  The result is subtracted from the smooth
        operator-entered P1..P5 reference-height profile.

        This exact function is used by both Run/Free-D Side View and by Free-D Y,
        so the visual arc and transmitted sag value cannot use different models.
        """
        pts = self._normalised_geometry(geometry)
        if len(pts) < 2:
            return self._smooth_geometry_y(x, pts)
        if support0 is None or support1 is None:
            support0, support1 = self._cable_span_bounds()
        support0 = float(support0)
        support1 = float(support1)
        span = max(0.1, support1-support0)
        xv = max(support0, min(support1, float(x)))
        rel_x = xv-support0
        left = rel_x
        right = span-rel_x

        rope_kg_m = max(0.0, float(cable_weight))/100.0
        # Cable weight and cable tension are entered per individual highline.
        # Dual Highline therefore does not halve the self-weight/tension ratio of
        # either cable; it only shares the suspended skate package between them.
        tension_per_line = max(0.01, float(tension))
        line_count = 2.0 if str(highline).strip().lower().startswith("dual") else 1.0
        skate_per_line = max(0.0, float(skate_weight)) / line_count

        # Uniform cable load: continuous parabola with zero drop at both ends.
        cable_drop = (rope_kg_m * left * right) / (2.0 * tension_per_line)

        # Point load at the LIVE skate position.  This is piecewise-linear in
        # horizontal-tension approximation and remains continuous at the skate.
        a = max(0.0, min(span, float(skate_x)-support0))
        if rel_x <= a:
            point_drop = (skate_per_line * rel_x * (span-a)) / (tension_per_line * span)
        else:
            point_drop = (skate_per_line * a * (span-rel_x)) / (tension_per_line * span)

        return self._smooth_geometry_y(xv, pts) - max(0.0, cable_drop + point_drop)

    def _cable_profile(self, snap=None, samples=121, moving_skate_path=False):
        """Return a calculated profile across the complete Near/Far span.

        Run uses the instantaneous cable shape with its point load at the live
        skate position, preserving the approved live-page behaviour. Free-D uses
        moving_skate_path=True so each sample answers "what is the cable/skate Y
        when the skate is at this X?". That full-run camera path remains useful
        while the rig is offline or parked at a support and makes all sag inputs
        visible while Free-D settings are edited.
        """
        cfg = snap if isinstance(snap, dict) else None
        geometry = [dict(p) for p in (cfg.get("geometry", self.geometry) if cfg else self.geometry)]
        cable_weight = float(cfg.get("cable_weight_kg100m", self.cable_weight_kg100m) if cfg else self.cable_weight_kg100m)
        tension = float(cfg.get("cable_tension_kg", self.cable_tension_kg) if cfg else self.cable_tension_kg)
        skate_weight = float(cfg.get("skate_weight_kg", cfg.get("static_weight_kg", self.skate_weight_kg)) if cfg else self.skate_weight_kg)
        highline = str(cfg.get("highline_mode", self.highline_mode) if cfg else self.highline_mode)
        pts = self._normalised_geometry(geometry)
        if len(pts) < 2:
            return []
        x0, x1 = self._cable_span_bounds()
        span = max(0.1, x1-x0)
        live_skate_x = float(self.state.pos_m or 0.0) - float(self.state.near_limit.position_m or 0.0)
        live_skate_x = max(x0, min(x1, live_skate_x))
        count = max(16, int(samples))
        result = []
        for i in range(count):
            x = x0 + span * i / max(1, count-1)
            load_x = x if moving_skate_path else live_skate_x
            result.append({
                "x": float(x),
                "y": float(self._cable_y_at(x, pts, cable_weight, tension,
                                             skate_weight, highline, load_x, x0, x1)),
                # Z is intentionally defined by the identities P1/P5, not by
                # whichever points become first/last after Y interpolation sorts X.
                "z": float(self._geometry_z(x, geometry)),
            })
        return result

    def _xyz(self, snap=None):
        """Calculate Free-D X/Y/Z from the same physical profile shown in the UI."""
        cfg = snap if isinstance(snap, dict) else None
        geometry = [dict(p) for p in (cfg.get("geometry", self.geometry) if cfg else self.geometry)]
        output_offsets = dict(cfg.get("output_offsets", self.freed_output_offsets) if cfg else self.freed_output_offsets)
        cable_weight = float(cfg.get("cable_weight_kg100m", self.cable_weight_kg100m) if cfg else self.cable_weight_kg100m)
        tension = float(cfg.get("cable_tension_kg", self.cable_tension_kg) if cfg else self.cable_tension_kg)
        skate_weight = float(cfg.get("skate_weight_kg", cfg.get("static_weight_kg", self.skate_weight_kg)) if cfg else self.skate_weight_kg)
        highline = str(cfg.get("highline_mode", self.highline_mode) if cfg else self.highline_mode)

        x = float(self.state.pos_m or 0.0) - float(self.state.near_limit.position_m or 0.0)
        pts = self._normalised_geometry(geometry)
        support0, support1 = self._cable_span_bounds()
        x = max(support0, min(support1, x))
        y = self._cable_y_at(x, pts, cable_weight, tension, skate_weight,
                             highline, x, support0, support1)
        z = self._geometry_z(x, geometry)
        return (
            x + float(output_offsets.get("X",0.0)),
            y + float(output_offsets.get("Y",0.0)),
            z + float(output_offsets.get("Z",0.0)),
        )

    def _send_freed(self):
        # Free-D edits auto-commit. Build each packet from the current live snapshot
        # so a committed adjustment is reflected without a separate Apply action.
        applied = self._freed_snapshot()
        if not bool(applied.get("output_enabled", self.freed_output_enabled)):
            return
        now = time.perf_counter()
        hz = max(1.0, min(100.0, float(applied.get("rate_hz", self.freed_rate_hz))))
        if now-self._last_freed_tx < 1.0/hz:
            return
        self._last_freed_tx = now
        x,y,z = self._xyz(applied)
        raw = self.freed_in_raw
        in_offsets = dict(applied.get("input_offsets", self.freed_input_offsets))
        in_inverts = dict(applied.get("input_inverts", self.freed_input_inverts))
        out_inverts = dict(applied.get("output_inverts", self.freed_output_inverts))
        lens_type = str(applied.get("lens_type", self.freed_lens_type))

        pan = float(self.freed_in.get("Pan",0.0)) * self._input_sign("Pan", in_inverts) + float(in_offsets.get("Pan",0.0))
        tilt = float(self.freed_in.get("Tilt",0.0)) * self._input_sign("Tilt", in_inverts) + float(in_offsets.get("Tilt",0.0))
        roll = float(self.freed_in.get("Roll",0.0)) * self._input_sign("Roll", in_inverts) + float(in_offsets.get("Roll",0.0))
        zoom_dec = self._decode_lens_for_type(int(raw.get("Zoom",0)), lens_type)
        focus_dec = self._decode_lens_for_type(int(raw.get("Focus",0)), lens_type)
        zoom = int(zoom_dec) * self._input_sign("Zoom", in_inverts)
        focus = int(focus_dec) * self._input_sign("Focus", in_inverts)
        ox = float(x) * self._output_sign("X", out_inverts)
        oy = float(y) * self._output_sign("Y", out_inverts)
        oz = float(z) * self._output_sign("Z", out_inverts)
        pos_scale = max(1.0, float(applied.get("pos_scale", self.freed_pos_scale)))
        payload = bytearray((0xD1, max(0,min(255,int(raw.get("Cam ID",1))))))
        for v in (pan,tilt,roll): payload.extend(_s24be(round(float(v)*32768)))
        for v in (ox,oy,oz): payload.extend(_s24be(round(float(v)*pos_scale)))
        payload.extend(_lens24be(int(zoom), lens_type)); payload.extend(_lens24be(int(focus), lens_type)); payload.extend(b"\x00\x00")
        payload.append((0x40-sum(payload[:28]))&0xff)
        try:
            self._freed_sock.sendto(bytes(payload),(str(applied.get("target_ip",self.freed_target_ip)), int(applied.get("target_port",self.freed_target_port))))
        except Exception:
            return
        t=time.perf_counter(); self._freed_out_times.append(t); recent=[q for q in self._freed_out_times if q>=t-1]
        self.freed_out_fps=(len(recent)-1)/(recent[-1]-recent[0]) if len(recent)>1 and recent[-1]>recent[0] else float(len(recent))

    # --- timer/state ---
    def _tick(self):
        try:
            for _ in range(100):
                try: self._parse_w1p(self._w1p_rx.get_nowait())
                except queue.Empty: break
            # Firmware authority beacons are deliberately NOT serviced here.
            # They are owned by _srvr_alive_worker so a stalled/background Qt
            # event loop cannot prevent CTRL/W1P/CTRL-TS release convergence.
            self._motion_tick(); self._service_w1p_setting_sync(); self._service_legacy_firmware_push(); self._send_freed(); self._send_controller_marker_packet(); self._send_controller_display_packet()
            # Keep the 25 ms control/safety cadence, but do not force the whole
            # QML property graph to re-evaluate at 40 Hz. 20 Hz is ample for the
            # desktop display and materially reduces Intel-mac UI load.
            now_ui = time.monotonic()
            if (now_ui - getattr(self, "_last_ui_state_emit", 0.0)) >= 0.05:
                self._last_ui_state_emit = now_ui
                self.stateChanged.emit()
        except Exception as exc: self._log(f"[SRVR] tick: {exc}")

    # --- config ---
    @staticmethod
    def _normalise_list(value, default, length):
        out = list(value) if isinstance(value, list) else list(default)
        if len(out) < length:
            out.extend(list(default)[len(out):length])
        return out[:length]

    def _normalise_drive_modes(self, modes):
        defaults = [
            {"name":"Mode 1", "max_speed_mps":25.0, "goto_speed_mps":7.5, "accel_mps2":5.0, "decel_mps2":5.0, "crossover_mps2":10.0, "stop_decel_mps2":7.5},
            {"name":"Mode 2", "max_speed_mps":25.0, "goto_speed_mps":7.5, "accel_mps2":5.0, "decel_mps2":5.0, "crossover_mps2":10.0, "stop_decel_mps2":7.5},
        ]
        src = modes if isinstance(modes, list) else []
        out = []
        for i in range(2):
            d = defaults[i].copy()
            if i < len(src) and isinstance(src[i], dict):
                d.update(src[i])
                # Migrate early Qt Quick and proven v26.06.26.25 key names.
                legacy_keys = {
                    "max_speed": "max_speed_mps",
                    "max_goto_speed_mps": "goto_speed_mps",
                    "max_accel_mps2": "accel_mps2",
                    "max_decel_mps2": "decel_mps2",
                    "max_crossover_mps2": "crossover_mps2",
                    "max_stop_decel_mps2": "stop_decel_mps2",
                }
                for old_key, new_key in legacy_keys.items():
                    if old_key in src[i] and new_key not in src[i]:
                        d[new_key] = src[i][old_key]
            d["name"] = str(d.get("name") or f"Mode {i+1}")
            for key in ("max_speed_mps","goto_speed_mps","accel_mps2","decel_mps2","crossover_mps2","stop_decel_mps2"):
                try: d[key] = max(0.01, float(d[key]))
                except Exception: d[key] = defaults[i][key]
            d = {
                "name": d["name"],
                "max_speed_mps": d["max_speed_mps"],
                "goto_speed_mps": d["goto_speed_mps"],
                "accel_mps2": d["accel_mps2"],
                "decel_mps2": d["decel_mps2"],
                "crossover_mps2": d["crossover_mps2"],
                "stop_decel_mps2": d["stop_decel_mps2"],
            }
            out.append(d)
        return out

    def _apply_active_drive_profile(self, sync=True):
        self.active_drive_mode = 0 if int(self.active_drive_mode) <= 0 else 1
        m = self.drive_modes[self.active_drive_mode]
        self.max_speed_mps = float(m["max_speed_mps"])
        self.goto_speed_mps = min(float(m["goto_speed_mps"]), self.max_speed_mps)
        self.max_accel_mps2 = float(m["accel_mps2"])
        self.max_decel_mps2 = float(m["decel_mps2"])
        self.max_crossover_mps2 = float(m["crossover_mps2"])
        self.max_stop_decel_mps2 = float(m["stop_decel_mps2"])
        if sync:
            self._sync_w1p_settings()

    @staticmethod
    def _kg_to_lb(value: float) -> float:
        return float(value) * 2.2046226218487757

    @staticmethod
    def _lb_to_kg(value: float) -> float:
        return float(value) / 2.2046226218487757

    def _freed_snapshot(self) -> dict:
        """Return the complete editable Free-D configuration in canonical form."""
        return {
            "input_enabled": bool(self.freed_input_enabled),
            "input_bind_ip": str(self.freed_input_bind_ip),
            "input_port": int(self.freed_input_port),
            "input_offsets": dict(self.freed_input_offsets),
            "input_inverts": dict(self.freed_input_inverts),
            "output_enabled": bool(self.freed_output_enabled),
            "target_ip": str(self.freed_target_ip),
            "target_port": int(self.freed_target_port),
            "rate_hz": float(self.freed_rate_hz),
            "output_offsets": dict(self.freed_output_offsets),
            "output_inverts": dict(self.freed_output_inverts),
            "pos_scale": float(self.freed_pos_scale),
            "lens_type": str(self.freed_lens_type),
            "lens_scale_mode": str(self.freed_lens_scale_mode),
            "lens_cal": dict(self.freed_lens_cal),
            "lens_auto_seen": dict(self._freed_lens_auto_seen),
            "geometry": [dict(p) for p in self.geometry],
            "skate_weight_kg": float(self.skate_weight_kg),
            "static_weight_kg": float(self.skate_weight_kg),  # legacy config compatibility
            "cable_weight_kg100m": float(self.cable_weight_kg100m),
            "cable_tension_kg": float(self.cable_tension_kg),
            "skate_weight_unit": str(self.skate_weight_unit),
            "static_weight_unit": str(self.skate_weight_unit),  # legacy config compatibility
            "cable_weight_unit": str(self.cable_weight_unit),
            "cable_tension_unit": str(self.cable_tension_unit),
            "highline_mode": str(self.highline_mode),
        }

    def _restore_freed_snapshot(self, snap: dict) -> None:
        if not isinstance(snap, dict):
            return
        self.freed_input_enabled = bool(snap.get("input_enabled", self.freed_input_enabled))
        self.freed_input_bind_ip = str(snap.get("input_bind_ip", self.freed_input_bind_ip))
        self.freed_input_port = max(1, min(65535, int(snap.get("input_port", self.freed_input_port))))
        self.freed_input_offsets = {k: float(v) for k, v in dict(snap.get("input_offsets", self.freed_input_offsets)).items() if k in ("Pan","Tilt","Roll")}
        for k in ("Pan","Tilt","Roll"):
            self.freed_input_offsets.setdefault(k, 0.0)
        self.freed_input_inverts = {k: bool(v) for k, v in dict(snap.get("input_inverts", self.freed_input_inverts)).items() if k in ("Pan","Tilt","Roll","Zoom","Focus")}
        for k in ("Pan","Tilt","Roll","Zoom","Focus"):
            self.freed_input_inverts.setdefault(k, False)
        self.freed_output_enabled = bool(snap.get("output_enabled", self.freed_output_enabled))
        self.freed_target_ip = str(snap.get("target_ip", self.freed_target_ip))
        self.freed_target_port = max(1, min(65535, int(snap.get("target_port", self.freed_target_port))))
        self.freed_rate_hz = max(1.0, min(100.0, float(snap.get("rate_hz", self.freed_rate_hz))))
        self.freed_output_offsets = {k: float(v) for k, v in dict(snap.get("output_offsets", self.freed_output_offsets)).items() if k in ("X","Y","Z")}
        for k in ("X","Y","Z"):
            self.freed_output_offsets.setdefault(k, 0.0)
        self.freed_output_inverts = {k: bool(v) for k, v in dict(snap.get("output_inverts", self.freed_output_inverts)).items() if k in ("X","Y","Z")}
        for k in ("X","Y","Z"):
            self.freed_output_inverts.setdefault(k, False)
        self.freed_pos_scale = max(1.0, float(snap.get("pos_scale", self.freed_pos_scale)))
        self.freed_lens_type = str(snap.get("lens_type", self.freed_lens_type)) if str(snap.get("lens_type", self.freed_lens_type)) in ("i16","u16","i24","u24") else "u16"
        self.freed_lens_scale_mode = self._normalise_lens_scale(snap.get("lens_scale_mode", self.freed_lens_scale_mode))
        cal = dict(snap.get("lens_cal", self.freed_lens_cal))
        for key in ("zoom_wide","zoom_tele","focus_near","focus_far"):
            try: self.freed_lens_cal[key] = float(cal.get(key, self.freed_lens_cal[key]))
            except Exception: pass
        seen = dict(snap.get("lens_auto_seen", self._freed_lens_auto_seen))
        self._freed_lens_auto_seen = {k: seen.get(k) for k in ("zoom_min","zoom_max","focus_min","focus_max")}
        geom = snap.get("geometry")
        if isinstance(geom, list) and len(geom) >= 5:
            self.geometry = [dict(geom[i]) for i in range(5)]
            for i, g in enumerate(self.geometry):
                g["name"] = f"P{i+1}"
                g["x"] = float(g.get("x", i*25.0))
                g["y"] = float(g.get("y", 0.0))
                g["z"] = float(g.get("z", 0.0) or 0.0) if i in (0,4) else None
        self.skate_weight_kg = max(0.0, float(snap.get("skate_weight_kg", snap.get("static_weight_kg", self.skate_weight_kg))))
        self.cable_weight_kg100m = max(0.0, float(snap.get("cable_weight_kg100m", self.cable_weight_kg100m)))
        self.cable_tension_kg = max(0.01, float(snap.get("cable_tension_kg", self.cable_tension_kg)))
        self.skate_weight_unit = "lbs" if str(snap.get("skate_weight_unit", snap.get("static_weight_unit", self.skate_weight_unit))).lower().startswith("lb") else "kg"
        self.cable_weight_unit = "lbs/100m" if str(snap.get("cable_weight_unit", self.cable_weight_unit)).lower().startswith("lb") else "kg/100m"
        self.cable_tension_unit = "lbs" if str(snap.get("cable_tension_unit", self.cable_tension_unit)).lower().startswith("lb") else "kg"
        self.highline_mode = "Dual Highline" if str(snap.get("highline_mode", self.highline_mode)).lower().startswith("dual") else "Single Highline"

    @staticmethod
    def _normalise_lens_scale(value) -> str:
        text = str(value or "Auto").strip().lower()
        if text.startswith("full"):
            return "Full Scale"
        if text.startswith("manual"):
            return "Manual"
        return "Auto"

    def _lens_limits(self):
        t = str(self.freed_lens_type).lower()
        if t == "u16": return 0.0, 65535.0
        if t == "i16": return -32768.0, 32767.0
        if t == "u24": return 0.0, 16777215.0
        return -8388608.0, 8388607.0

    def _lens_percent(self, field: str, value: float) -> float:
        field = "zoom" if str(field).lower().startswith("zoom") else "focus"
        mode = str(self.freed_lens_scale_mode)
        if mode == "Full Scale":
            lo, hi = self._lens_limits()
        elif mode == "Auto":
            lo = self._freed_lens_auto_seen.get(field+"_min")
            hi = self._freed_lens_auto_seen.get(field+"_max")
            if lo is None or hi is None or abs(float(hi)-float(lo)) < 1e-9:
                lo = float(self.freed_lens_cal["zoom_wide" if field == "zoom" else "focus_near"])
                hi = float(self.freed_lens_cal["zoom_tele" if field == "zoom" else "focus_far"])
        else:
            lo = float(self.freed_lens_cal["zoom_wide" if field == "zoom" else "focus_near"])
            hi = float(self.freed_lens_cal["zoom_tele" if field == "zoom" else "focus_far"])
        if abs(float(hi)-float(lo)) < 1e-9:
            return 0.0
        return max(0.0, min(100.0, (float(value)-float(lo)) * 100.0 / (float(hi)-float(lo))))

    def _remember_lens_auto(self, field: str, value: float) -> None:
        field = "zoom" if str(field).lower().startswith("zoom") else "focus"
        v = float(value)
        mn, mx = field+"_min", field+"_max"
        old_min, old_max = self._freed_lens_auto_seen.get(mn), self._freed_lens_auto_seen.get(mx)
        self._freed_lens_auto_seen[mn] = v if old_min is None else min(float(old_min), v)
        self._freed_lens_auto_seen[mx] = v if old_max is None else max(float(old_max), v)

    def _setup_snapshot(self) -> dict:
        return {
            "ctrl_ip": str(self.ctrl_ip),
            "w1p_ip": str(self.w1p_ip),
            "reverse_joystick": bool(self.reverse_joystick),
            "reverse_motor": bool(self.reverse_motor),
            "joystick_deadband_pct": float(self.joystick_deadband_pct),
            "joystick_calibration": {
                "left": float(self.joystick_cal_left),
                "centre": float(self.joystick_cal_centre),
                "right": float(self.joystick_cal_right),
            },
            "position_source": str(self.position_source),
            "units_per_m": float(self.winch_units_per_m),
            "drive_modes": [dict(x) for x in self.drive_modes],
            "active_drive_mode": int(self.active_drive_mode),
            "acceleration_mode": str(self.acceleration_mode),
            "battery_change_mode": bool(self.battery_change_mode),
            "ctrl_aux_assignments": list(self.ctrl_aux_assignments),
            "w1p_aux_assignments": list(self.w1p_aux_assignments),
        }

    def _restore_setup_snapshot(self, snap: dict) -> None:
        # Auto-save means this function can run for a single UI edit. Do not
        # disturb healthy controller links unless the edit actually changed a
        # network/W1P control setting. In particular, joystick calibration or a
        # label edit must never clear the live CTRL receive history.
        old_ctrl_ip = str(self.ctrl_ip)
        old_w1p_ip = str(self.w1p_ip)
        old_w1p_sync = (
            bool(self.reverse_motor), float(self.winch_units_per_m),
            copy.deepcopy(self.drive_modes), int(self.active_drive_mode),
            str(self.acceleration_mode), bool(self.battery_change_mode),
        )

        self.ctrl_ip = str(snap.get("ctrl_ip", self.ctrl_ip))
        self.w1p_ip = str(snap.get("w1p_ip", self.w1p_ip))
        self.reverse_joystick = bool(snap.get("reverse_joystick", self.reverse_joystick))
        self.reverse_motor = bool(snap.get("reverse_motor", self.reverse_motor))
        self.joystick_deadband_pct = max(0.0, min(25.0, float(snap.get("joystick_deadband_pct", self.joystick_deadband_pct))))
        joy_cal = snap.get("joystick_calibration", {}) if isinstance(snap.get("joystick_calibration", {}), dict) else {}
        try:
            left = float(joy_cal.get("left", self.joystick_cal_left))
            centre = float(joy_cal.get("centre", self.joystick_cal_centre))
            right = float(joy_cal.get("right", self.joystick_cal_right))
            if abs(left-centre) >= 0.05 and abs(right-centre) >= 0.05 and (left-centre)*(right-centre) < 0.0:
                changed_cal = (
                    abs(left-self.joystick_cal_left) > 1e-12 or
                    abs(centre-self.joystick_cal_centre) > 1e-12 or
                    abs(right-self.joystick_cal_right) > 1e-12
                )
                self.joystick_cal_left, self.joystick_cal_centre, self.joystick_cal_right = left, centre, right
                if changed_cal:
                    self._reset_joystick_centre_drift()
        except Exception:
            pass
        self._apply_position_source_runtime(snap.get("position_source", self.position_source), send_safety=not self.smoke_test)
        self.winch_units_per_m = max(1.0, float(snap.get("units_per_m", self.winch_units_per_m)))
        self.drive_modes = self._normalise_drive_modes(snap.get("drive_modes", self.drive_modes))
        self.active_drive_mode = 0 if int(snap.get("active_drive_mode", self.active_drive_mode)) <= 0 else 1
        self.acceleration_mode = "Power" if str(snap.get("acceleration_mode", self.acceleration_mode)).lower().startswith("power") else "Speed"
        self.battery_change_mode = bool(snap.get("battery_change_mode", self.battery_change_mode))
        self.ctrl_aux_assignments = [str(x) for x in self._normalise_list(snap.get("ctrl_aux_assignments"), self.ctrl_aux_assignments, 5)]
        self.w1p_aux_assignments = [str(x) for x in self._normalise_list(snap.get("w1p_aux_assignments"), self.w1p_aux_assignments, 5)]
        self._apply_active_drive_profile(sync=False)

        if self.ctrl_ip != old_ctrl_ip:
            self._ctrl_rx_times.clear()
        if self.w1p_ip != old_w1p_ip:
            self.w1p.reconfigure(self.w1p_ip, self.w1p_port)

        new_w1p_sync = (
            bool(self.reverse_motor), float(self.winch_units_per_m),
            copy.deepcopy(self.drive_modes), int(self.active_drive_mode),
            str(self.acceleration_mode), bool(self.battery_change_mode),
        )
        if not self.smoke_test and (self.w1p_ip != old_w1p_ip or new_w1p_sync != old_w1p_sync):
            self._sync_w1p_settings()
            self._sync_service_mode_to_winch(force=True)

    def _setup_snapshot_from_config(self, c: dict) -> dict:
        """Normalise a transferable config into a Setup draft without applying it."""
        snap = self._setup_snapshot()
        if not isinstance(c, dict):
            return snap
        snap["ctrl_ip"] = str(c.get("ctrl_ip", snap["ctrl_ip"]) or snap["ctrl_ip"])
        snap["w1p_ip"] = str(c.get("w1p_ip", snap["w1p_ip"]) or snap["w1p_ip"])
        snap["reverse_joystick"] = bool(c.get("reverse_joystick", snap["reverse_joystick"]))
        snap["reverse_motor"] = bool(c.get("reverse_motor", snap["reverse_motor"]))
        try: snap["joystick_deadband_pct"] = max(0.0, min(25.0, float(c.get("joystick_deadband_pct", snap["joystick_deadband_pct"]))))
        except Exception: pass
        joy = c.get("joystick_calibration") if isinstance(c.get("joystick_calibration"), dict) else {}
        if joy:
            try:
                left = float(joy.get("left", snap["joystick_calibration"]["left"]))
                centre = float(joy.get("centre", snap["joystick_calibration"]["centre"]))
                right = float(joy.get("right", snap["joystick_calibration"]["right"]))
                if abs(left-centre) >= 0.05 and abs(right-centre) >= 0.05 and (left-centre)*(right-centre) < 0.0:
                    snap["joystick_calibration"] = {"left":left, "centre":centre, "right":right}
            except Exception:
                pass
        snap["position_source"] = self._normalise_position_source(c.get("position_source", snap["position_source"]))
        try: snap["units_per_m"] = max(1.0, float(c.get("units_per_m", snap["units_per_m"])))
        except Exception: pass
        snap["drive_modes"] = self._normalise_drive_modes(c.get("drive_modes", snap["drive_modes"]))
        try: snap["active_drive_mode"] = 0 if int(c.get("active_drive_mode", snap["active_drive_mode"])) <= 0 else 1
        except Exception: snap["active_drive_mode"] = 0
        snap["acceleration_mode"] = "Power" if str(c.get("acceleration_mode", snap["acceleration_mode"])).lower().startswith("power") else "Speed"
        snap["battery_change_mode"] = bool(c.get("battery_change_mode", snap["battery_change_mode"]))
        snap["ctrl_aux_assignments"] = [str(x) for x in self._normalise_list(c.get("ctrl_aux_assignments"), snap["ctrl_aux_assignments"], 5)]
        snap["w1p_aux_assignments"] = [str(x) for x in self._normalise_list(c.get("w1p_aux_assignments"), snap["w1p_aux_assignments"], 5)]
        return snap

    def _freed_snapshot_from_config(self, c: dict) -> dict:
        """Normalise a transferable config into a Free-D draft without applying it."""
        snap = self._freed_snapshot()
        if not isinstance(c, dict):
            return snap
        fd = c.get("free_d") if isinstance(c.get("free_d"), dict) else {}
        snap["input_enabled"] = bool(fd.get("input_enabled", snap["input_enabled"]))
        snap["input_bind_ip"] = str(fd.get("input_bind_ip", snap["input_bind_ip"]))
        try: snap["input_port"] = max(1, min(65535, int(fd.get("input_port", snap["input_port"]))))
        except Exception: pass
        snap["output_enabled"] = bool(fd.get("output_enabled", snap["output_enabled"]))
        snap["target_ip"] = str(fd.get("target_ip", snap["target_ip"]))
        try: snap["target_port"] = max(1, min(65535, int(fd.get("target_port", snap["target_port"]))))
        except Exception: pass
        try: snap["rate_hz"] = max(1.0, min(100.0, float(fd.get("rate_hz", snap["rate_hz"]))))
        except Exception: pass
        try: snap["pos_scale"] = max(1.0, float(fd.get("pos_scale", snap["pos_scale"])))
        except Exception: pass
        for src_key, axes in (("input_offsets", ("Pan","Tilt","Roll")), ("output_offsets", ("X","Y","Z"))):
            vals = fd.get(src_key) if isinstance(fd.get(src_key), dict) else {}
            for key in axes:
                try: snap[src_key][key] = float(vals.get(key, snap[src_key][key]))
                except Exception: pass
        for src_key, axes in (("input_inverts", ("Pan","Tilt","Roll","Zoom","Focus")), ("output_inverts", ("X","Y","Z"))):
            vals = fd.get(src_key) if isinstance(fd.get(src_key), dict) else {}
            for key in axes:
                snap[src_key][key] = bool(vals.get(key, snap[src_key][key]))
        lt = str(fd.get("lens_type", snap["lens_type"]))
        snap["lens_type"] = lt if lt in ("i16","u16","i24","u24") else "u16"
        snap["lens_scale_mode"] = self._normalise_lens_scale(fd.get("lens_scale_mode", snap["lens_scale_mode"]))
        cal = fd.get("lens_cal") if isinstance(fd.get("lens_cal"), dict) else {}
        for key in ("zoom_wide","zoom_tele","focus_near","focus_far"):
            try: snap["lens_cal"][key] = float(cal.get(key, snap["lens_cal"][key]))
            except Exception: pass
        seen = fd.get("lens_auto_seen") if isinstance(fd.get("lens_auto_seen"), dict) else {}
        for key in ("zoom_min","zoom_max","focus_min","focus_max"):
            if key in seen: snap["lens_auto_seen"][key] = seen.get(key)
        geom = c.get("geometry") if isinstance(c.get("geometry"), list) else snap["geometry"]
        if len(geom) >= 5:
            out = []
            for i in range(5):
                src = geom[i] if isinstance(geom[i], dict) else snap["geometry"][i]
                d = dict(snap["geometry"][i]); d.update(src)
                d["name"] = f"P{i+1}"
                try: d["x"] = float(d.get("x", i*25.0))
                except Exception: d["x"] = float(i*25.0)
                try: d["y"] = float(d.get("y", 0.0))
                except Exception: d["y"] = 0.0
                if i in (0,4):
                    try: d["z"] = float(d.get("z", 0.0) or 0.0)
                    except Exception: d["z"] = 0.0
                else: d["z"] = None
                out.append(d)
            snap["geometry"] = out
        try: snap["skate_weight_kg"] = max(0.0, float(fd.get("skate_weight_kg", fd.get("static_weight_kg", snap["skate_weight_kg"]))))
        except Exception: pass
        try: snap["cable_weight_kg100m"] = max(0.0, float(fd.get("cable_weight_kg100m", snap["cable_weight_kg100m"])))
        except Exception: pass
        try: snap["cable_tension_kg"] = max(0.01, float(fd.get("cable_tension_kg", snap["cable_tension_kg"])))
        except Exception: pass
        snap["skate_weight_unit"] = "lbs" if str(fd.get("skate_weight_unit", fd.get("static_weight_unit", snap["skate_weight_unit"]))).lower().startswith("lb") else "kg"
        snap["cable_weight_unit"] = "lbs/100m" if str(fd.get("cable_weight_unit", snap["cable_weight_unit"])).lower().startswith("lb") else "kg/100m"
        snap["cable_tension_unit"] = "lbs" if str(fd.get("cable_tension_unit", snap["cable_tension_unit"])).lower().startswith("lb") else "kg"
        snap["highline_mode"] = "Dual Highline" if str(fd.get("highline_mode", snap["highline_mode"])).lower().startswith("dual") else "Single Highline"
        return snap

    @staticmethod
    def _dialog_path(value) -> Path:
        """Convert a Qt FileDialog URL/string into a native filesystem path.

        Qt returns Windows local files as file:///C:/path. urlparse exposes that
        as /C:/path, so the synthetic URI slash must be removed before Path sees
        it. UNC file://server/share paths are retained as //server/share.
        """
        text = str(value or "").strip()
        if text.startswith("file:"):
            parsed = urlparse(text)
            path_text = unquote(parsed.path)
            if parsed.netloc and parsed.netloc.lower() != "localhost":
                text = f"//{parsed.netloc}{path_text}"
            else:
                if len(path_text) >= 3 and path_text[0] == "/" and path_text[2] == ":" and path_text[1].isalpha():
                    path_text = path_text[1:]
                text = path_text
        return Path(text).expanduser()

    def _apply_imported_run_config(self, c: dict) -> None:
        """Apply transferable Run-only values during an automatic config import."""
        if not isinstance(c, dict):
            return
        # Imported Run files may carry legacy reference state, but position
        # authority is never transferable between sessions/machines.
        self._not_calibrated = True
        default_names = [f"P{i}" for i in range(1,11)]
        if "preset_names" in c:
            self.preset_names = [str(x or default_names[i]) for i,x in enumerate(self._normalise_list(c.get("preset_names"), default_names, 10))]
        if "preset_name_mode" in c:
            self.preset_name_mode = self._normalise_preset_name_mode(c.get("preset_name_mode"))
        if "preset_positions" in c:
            raw_pos = self._normalise_list(c.get("preset_positions"), [None]*10, 10)
            vals = []
            for v in raw_pos:
                try: vals.append(None if v is None else float(v))
                except Exception: vals.append(None)
            self.preset_positions = vals
        if "preset_visible" in c:
            self.preset_visible = [bool(x) for x in self._normalise_list(c.get("preset_visible"), [True]*10, 10)]
        lim = c.get("limits") if isinstance(c.get("limits"), dict) else None
        if lim is not None:
            try: self.state.near_limit.position_m = float(lim.get("near", self.state.near_limit.position_m or 0.0))
            except Exception: pass
            try: self.state.far_limit.position_m = float(lim.get("far", self.state.far_limit.position_m or 100.0))
            except Exception: pass
            try: self.state.ref_point.position_m = float(lim.get("ref", self.state.ref_point.position_m or 50.0))
            except Exception: pass
            raw = lim.get("raw") if isinstance(lim.get("raw"), dict) else {}
            for key in ("near","ref","far"):
                if key in raw:
                    try: self._limit_raw[key] = None if raw.get(key) is None else int(raw.get(key))
                    except Exception: self._limit_raw[key] = None
            for lp,key in ((self.state.near_limit,"nearRamp"),(self.state.far_limit,"farRamp")):
                r = lim.get(key) if isinstance(lim.get(key), dict) else None
                if r is None: continue
                lp.ramp_mode = "Percentage" if str(r.get("mode", lp.ramp_mode)).lower().startswith("percent") else "Distance"
                try: lp.ramp_distance_m = max(0.0, float(r.get("distance", lp.ramp_distance_m)))
                except Exception: pass
                try: lp.ramp_percentage = max(0.0, min(100.0, float(r.get("percentage", lp.ramp_percentage))))
                except Exception: pass

    def _finish_pending_import_if_handled(self) -> None:
        if self._pending_import_setup_handled and self._pending_import_freed_handled:
            self._pending_import_config = None

    def _migrate_config_dict(self, config: dict) -> tuple[dict, bool]:
        """Convert v26.06.26.25/early Update-4 configuration into canonical keys.

        Migration is deliberately non-destructive: canonical values already in a
        newer file always win. The returned object is safe for normal Setup and
        Free-D auto-save semantics and can be saved by the current release.
        """
        if not isinstance(config, dict):
            return {}, False
        c = copy.deepcopy(config)
        changed = False

        # v26.10.08.03 moves the installed joystick polarity correction into CTRL,
        # so physical Left/Right is consistent before SRVR calibration. Migrate
        # older saved captures exactly once. Untouched identity defaults stay as
        # identity; real captured values are sign-flipped to describe the same
        # physical Left/Centre/Right positions on the corrected transport axis.
        try:
            schema_version = int(c.get("config_schema_version", 0) or 0)
        except Exception:
            schema_version = 0
        def set_missing(key, value):
            nonlocal changed
            if key not in c and value is not None:
                c[key] = value
                changed = True

        set_missing("ctrl_ip", c.get("controller_ip_ref"))
        set_missing("w1p_ip", c.get("winch_host"))
        set_missing("units_per_m", c.get("winch_units_per_m"))
        if "joystick_calibration" not in c and isinstance(c.get("joy_cal"), dict):
            joy = c["joy_cal"]
            c["joystick_calibration"] = {
                "left": joy.get("min", -1.0),
                "centre": joy.get("center", 0.0),
                "right": joy.get("max", 1.0),
            }
            changed = True
        if schema_version < 3:
            jc = c.get("joystick_calibration") if isinstance(c.get("joystick_calibration"), dict) else None
            if jc:
                try:
                    vals = (float(jc.get("left", -1.0)), float(jc.get("centre", 0.0)), float(jc.get("right", 1.0)))
                    is_identity = all(abs(a-b) < 1e-6 for a,b in zip(vals, (-1.0, 0.0, 1.0)))
                    if not is_identity:
                        c["joystick_calibration"] = {"left": -vals[0], "centre": -vals[1], "right": -vals[2]}
                except Exception:
                    pass
            c["reverse_joystick"] = False
            c["config_schema_version"] = 3
            c["not_calibrated_mode"] = True
            c["position_reference_persistent"] = False
            changed = True
        if "acceleration_mode" not in c and "accel_type" in c:
            raw = str(c.get("accel_type", "Speed")).strip().lower()
            c["acceleration_mode"] = "Power" if raw.startswith(("power","trad")) else "Speed"
            changed = True

        # Mode names existed in three parallel forms in .25; keep whichever is
        # most explicit while converting all old numeric field names later.
        modes = copy.deepcopy(c.get("drive_modes")) if isinstance(c.get("drive_modes"), list) else []
        if not modes:
            modes = [
                {"max_speed_mps": c.get("max_speed_mps", 25.0), "max_goto_speed_mps": c.get("max_speed_mps", 7.5),
                 "max_accel_mps2": c.get("max_accel_mps2", 5.0), "max_decel_mps2": c.get("max_decel_mps2", 5.0),
                 "max_crossover_mps2": c.get("max_crossover_mps2", 10.0), "max_stop_decel_mps2": c.get("max_stop_decel_mps2", 7.5)},
                {},
            ]
            c["drive_modes"] = modes
            changed = True
        names = c.get("drive_mode_names") if isinstance(c.get("drive_mode_names"), list) else []
        fallback_names = [c.get("mode_a_name"), c.get("mode_b_name")]
        for i in range(min(2, len(modes))):
            if not isinstance(modes[i], dict):
                modes[i] = {}
            if not str(modes[i].get("name", "")).strip():
                name = names[i] if i < len(names) and str(names[i]).strip() else fallback_names[i]
                if name:
                    modes[i]["name"] = str(name)
                    changed = True
        c["drive_modes"] = modes

        def norm_action(value):
            return self._normalise_aux_action_name(value)
        if "ctrl_aux_assignments" not in c:
            vals = [norm_action(c.get(f"aux{i}_action", "None")) for i in range(1,6)]
            c["ctrl_aux_assignments"] = vals
            changed = True
        else:
            vals = [norm_action(x) for x in self._normalise_list(c.get("ctrl_aux_assignments"), self.ctrl_aux_assignments, 5)]
            if vals != c.get("ctrl_aux_assignments"):
                c["ctrl_aux_assignments"] = vals; changed = True
        if "w1p_aux_assignments" not in c:
            vals = [norm_action(c.get(f"w1pts_aux{i}_action", "None")) for i in range(1,6)]
            c["w1p_aux_assignments"] = vals
            changed = True

        # v26.06.26.25 stored limits as three top-level objects.
        if "limits" not in c and any(k in c for k in ("near_limit","far_limit","ref_point")):
            near = c.get("near_limit") if isinstance(c.get("near_limit"), dict) else {}
            far = c.get("far_limit") if isinstance(c.get("far_limit"), dict) else {}
            ref = c.get("ref_point") if isinstance(c.get("ref_point"), dict) else {}
            npos = float(near.get("position_m", 0.0) or 0.0)
            fpos = float(far.get("position_m", 100.0) or 100.0)
            span = max(0.001, abs(fpos-npos))
            def ramp(src):
                mode = "Percentage" if str(src.get("ramp_mode", "Distance")).lower().startswith("percent") else "Distance"
                dist = max(0.0, float(src.get("ramp_distance_m", 2.0) or 0.0))
                pct_raw = src.get("ramp_percentage")
                pct = (dist/span*100.0) if pct_raw is None else float(pct_raw)
                return {"mode":mode, "distance":dist, "percentage":max(0.0,min(100.0,pct))}
            c["limits"] = {
                "near": npos, "far": fpos, "ref": float(ref.get("position_m", (npos+fpos)/2.0) or (npos+fpos)/2.0),
                "raw": {"near":None,"ref":None,"far":None},
                "nearRamp": ramp(near), "farRamp": ramp(far),
            }
            changed = True
        if "preset_positions" not in c and isinstance(c.get("presets"), list):
            c["preset_positions"] = list(c.get("presets", []))
            changed = True

        # Legacy Free-D field names and P1..P5 height points.
        fd = copy.deepcopy(c.get("free_d")) if isinstance(c.get("free_d"), dict) else {}
        fd_changed = False
        if "output_enabled" not in fd and "enabled" in fd:
            fd["output_enabled"] = bool(fd.get("enabled")); fd_changed = True
        if "cable_weight_kg100m" not in fd and "weight_per_100m_kg" in fd:
            fd["cable_weight_kg100m"] = fd.get("weight_per_100m_kg"); fd_changed = True
        if "cable_tension_kg" not in fd and "sag_tension_kgf" in fd:
            fd["cable_tension_kg"] = fd.get("sag_tension_kgf"); fd_changed = True
        if "geometry" not in c and isinstance(fd.get("height_points"), list) and len(fd["height_points"]) >= 5:
            geom=[]
            for i, hp in enumerate(fd["height_points"][:5]):
                hp = hp if isinstance(hp, dict) else {}
                geom.append({"name":f"P{i+1}", "x":float(hp.get("y_m", i*25.0) or 0.0),
                             "y":float(hp.get("z_m", 0.0) or 0.0),
                             "z":float(hp.get("z_offset_m", 0.0) or 0.0) if i in (0,4) else None})
            c["geometry"] = geom
            changed = True
        if fd_changed:
            c["free_d"] = fd; changed = True

        return c, changed

    def _load_config(self):
        recovered_from_backup = False
        try:
            if not self._config_path.exists():
                self._apply_active_drive_profile(sync=False)
                return
            try:
                c = json.loads(self._config_path.read_text(encoding="utf-8"))
                if not isinstance(c, dict):
                    raise ValueError("config root must be an object")
            except Exception as primary_exc:
                backup = self._config_path.with_suffix(self._config_path.suffix + ".bak")
                if not backup.exists():
                    raise
                try:
                    c = json.loads(backup.read_text(encoding="utf-8"))
                    if not isinstance(c, dict):
                        raise ValueError("backup config root must be an object")
                    recovered_from_backup = True
                    self._log(f"[Config] primary config invalid; recovered previous-good backup ({primary_exc})")
                except Exception:
                    raise primary_exc
            c, migrated = self._migrate_config_dict(c)

            self.ctrl_ip = str(c.get("ctrl_ip", self.ctrl_ip) or self.ctrl_ip)
            self.w1p_ip = str(c.get("w1p_ip", self.w1p_ip) or self.w1p_ip)
            self.reverse_joystick = bool(c.get("reverse_joystick", self.reverse_joystick))
            self.reverse_motor = bool(c.get("reverse_motor", self.reverse_motor))
            self.joystick_deadband_pct = max(0.0, min(25.0, float(c.get("joystick_deadband_pct", self.joystick_deadband_pct))))
            joy_cal = c.get("joystick_calibration", {}) if isinstance(c.get("joystick_calibration", {}), dict) else {}
            try:
                left = float(joy_cal.get("left", self.joystick_cal_left))
                centre = float(joy_cal.get("centre", self.joystick_cal_centre))
                right = float(joy_cal.get("right", self.joystick_cal_right))
                if abs(left-centre) >= 0.05 and abs(right-centre) >= 0.05 and (left-centre)*(right-centre) < 0.0:
                    self.joystick_cal_left, self.joystick_cal_centre, self.joystick_cal_right = left, centre, right
                    self._reset_joystick_centre_drift()
            except Exception:
                pass
            # Encoder is the physical source; Virtual is an SRVR-only demo source
            # that never emits a non-zero W1P velocity command.
            self.position_source = self._normalise_position_source(c.get("position_source", self.position_source))
            self._virtual_velocity_mps = 0.0
            self._virtual_last_tick = time.monotonic()
            self.ctrl_aux_assignments = [str(x) for x in self._normalise_list(c.get("ctrl_aux_assignments"), self.ctrl_aux_assignments, 5)]
            self.w1p_aux_assignments = [str(x) for x in self._normalise_list(c.get("w1p_aux_assignments"), self.w1p_aux_assignments, 5)]
            self.winch_units_per_m = max(1.0, float(c.get("units_per_m", self.winch_units_per_m)))

            self.drive_modes = self._normalise_drive_modes(c.get("drive_modes"))
            try: self.active_drive_mode = 0 if int(c.get("active_drive_mode", 0)) <= 0 else 1
            except Exception: self.active_drive_mode = 0
            self.acceleration_mode = "Power" if str(c.get("acceleration_mode", "Speed")).lower().startswith("power") else "Speed"
            self.battery_change_mode = bool(c.get("battery_change_mode", False))
            # Position reference is deliberately session-only. Every SRVR start is
            # uncalibrated regardless of the previous saved state.
            self._not_calibrated = True
            self._apply_active_drive_profile(sync=False)

            default_names = [f"P{i}" for i in range(1,11)]
            self.preset_names = [str(x or default_names[i]) for i,x in enumerate(self._normalise_list(c.get("preset_names"), default_names, 10))]
            self.preset_name_mode = self._normalise_preset_name_mode(c.get("preset_name_mode", self.preset_name_mode))
            raw_pos = self._normalise_list(c.get("preset_positions"), [None]*10, 10)
            self.preset_positions = []
            for v in raw_pos:
                try: self.preset_positions.append(None if v is None else float(v))
                except Exception: self.preset_positions.append(None)
            self.preset_visible = [bool(x) for x in self._normalise_list(c.get("preset_visible"), [True]*10, 10)]

            lim = c.get("limits", {}) if isinstance(c.get("limits", {}), dict) else {}
            self.state.near_limit.position_m = float(lim.get("near", 0.0))
            self.state.far_limit.position_m = float(lim.get("far", 100.0))
            self.state.ref_point.position_m = float(lim.get("ref", 50.0))
            raw = lim.get("raw", {}) if isinstance(lim.get("raw", {}), dict) else {}
            for key in ("near", "ref", "far"):
                try:
                    self._limit_raw[key] = None if raw.get(key) is None else int(raw.get(key))
                except Exception:
                    self._limit_raw[key] = None
            for lp,key in ((self.state.near_limit,"nearRamp"),(self.state.far_limit,"farRamp")):
                r = lim.get(key, {}) if isinstance(lim.get(key, {}), dict) else {}
                lp.ramp_mode = "Percentage" if str(r.get("mode", "Distance")).lower().startswith("percent") else "Distance"
                lp.ramp_distance_m = max(0.0, float(r.get("distance", 2.0)))
                lp.ramp_percentage = max(0.0, min(100.0, float(r.get("percentage", 10.0))))

            default_geometry = [
                {"name":"P1","x":0.0,"y":0.0,"z":0.0},
                {"name":"P2","x":25.0,"y":5.0,"z":None},
                {"name":"P3","x":50.0,"y":8.0,"z":None},
                {"name":"P4","x":75.0,"y":5.0,"z":None},
                {"name":"P5","x":100.0,"y":0.0,"z":0.0},
            ]
            g = c.get("geometry") if isinstance(c.get("geometry"), list) else default_geometry
            self.geometry = []
            for i in range(5):
                src = g[i] if i < len(g) and isinstance(g[i], dict) else default_geometry[i]
                d = default_geometry[i].copy(); d.update(src)
                d["name"] = f"P{i+1}"
                d["x"] = float(d.get("x", default_geometry[i]["x"]))
                d["y"] = float(d.get("y", default_geometry[i]["y"]))
                if i in (0,4): d["z"] = float(d.get("z", 0.0) or 0.0)
                else: d["z"] = None
                self.geometry.append(d)

            fd = c.get("free_d", {}) if isinstance(c.get("free_d", {}), dict) else {}
            self.freed_input_enabled = bool(fd.get("input_enabled", self.freed_input_enabled))
            self.freed_input_bind_ip = str(fd.get("input_bind_ip", self.freed_input_bind_ip))
            self.freed_input_port = max(1, min(65535, int(fd.get("input_port", self.freed_input_port))))
            self.freed_output_enabled = bool(fd.get("output_enabled", self.freed_output_enabled))
            self.freed_target_ip = str(fd.get("target_ip", self.freed_target_ip))
            self.freed_target_port = max(1, min(65535, int(fd.get("target_port", self.freed_target_port))))
            self.freed_rate_hz = max(1.0, min(100.0, float(fd.get("rate_hz", self.freed_rate_hz))))
            self.freed_pos_scale = max(1.0, float(fd.get("pos_scale", self.freed_pos_scale)))
            self.freed_input_offsets = {k: float(v) for k,v in dict(fd.get("input_offsets", self.freed_input_offsets)).items() if k in ("Pan","Tilt","Roll")}
            for k in ("Pan","Tilt","Roll"): self.freed_input_offsets.setdefault(k, 0.0)
            self.freed_input_inverts = {k: bool(v) for k,v in dict(fd.get("input_inverts", self.freed_input_inverts)).items() if k in ("Pan","Tilt","Roll","Zoom","Focus")}
            for k in ("Pan","Tilt","Roll","Zoom","Focus"): self.freed_input_inverts.setdefault(k, False)
            self.freed_output_offsets = {k: float(v) for k,v in dict(fd.get("output_offsets", self.freed_output_offsets)).items() if k in ("X","Y","Z")}
            for k in ("X","Y","Z"): self.freed_output_offsets.setdefault(k, 0.0)
            self.freed_output_inverts = {k: bool(v) for k,v in dict(fd.get("output_inverts", self.freed_output_inverts)).items() if k in ("X","Y","Z")}
            for k in ("X","Y","Z"): self.freed_output_inverts.setdefault(k, False)
            self.freed_lens_type = str(fd.get("lens_type", self.freed_lens_type)) if str(fd.get("lens_type", self.freed_lens_type)) in ("i16","u16","i24","u24") else "u16"
            self.freed_lens_scale_mode = self._normalise_lens_scale(fd.get("lens_scale_mode", self.freed_lens_scale_mode))
            lens_cal = dict(fd.get("lens_cal", self.freed_lens_cal))
            for key in ("zoom_wide","zoom_tele","focus_near","focus_far"):
                try: self.freed_lens_cal[key] = float(lens_cal.get(key, self.freed_lens_cal[key]))
                except Exception: pass
            seen = dict(fd.get("lens_auto_seen", self._freed_lens_auto_seen))
            self._freed_lens_auto_seen = {k: seen.get(k) for k in ("zoom_min","zoom_max","focus_min","focus_max")}
            self.skate_weight_kg = max(0.0, float(fd.get("skate_weight_kg", fd.get("static_weight_kg", self.skate_weight_kg))))
            self.cable_weight_kg100m = max(0.0, float(fd.get("cable_weight_kg100m", self.cable_weight_kg100m)))
            self.cable_tension_kg = max(0.01, float(fd.get("cable_tension_kg", self.cable_tension_kg)))
            self.skate_weight_unit = "lbs" if str(fd.get("skate_weight_unit", fd.get("static_weight_unit", self.skate_weight_unit))).lower().startswith("lb") else "kg"
            self.cable_weight_unit = "lbs/100m" if str(fd.get("cable_weight_unit", self.cable_weight_unit)).lower().startswith("lb") else "kg/100m"
            self.cable_tension_unit = "lbs" if str(fd.get("cable_tension_unit", self.cable_tension_unit)).lower().startswith("lb") else "kg"
            self.highline_mode = "Dual Highline" if str(fd.get("highline_mode", self.highline_mode)).lower().startswith("dual") else "Single Highline"
            if migrated or recovered_from_backup:
                # Rewrite migrations and recovered backup state once in canonical
                # form. When recovering, do not replace the known-good .bak with
                # the corrupt primary file we just rejected.
                self._save_config(include_staged_freed=True, make_backup=not recovered_from_backup)
                if migrated:
                    self._log("[Config] migrated legacy configuration to schema 2")
                if recovered_from_backup:
                    self._log("[Config] restored primary config atomically from previous-good backup")
        except Exception as exc:
            self._log(f"[Config] load failed: {exc}")
            self.drive_modes = self._normalise_drive_modes(self.drive_modes)
            self._apply_active_drive_profile(sync=False)

    def _config_write_worker(self):
        """Persist auto-save snapshots off the Qt/UI thread.

        The queue intentionally keeps only the latest pending snapshot. Rapid
        slider/text edits therefore coalesce instead of issuing a backup + file
        fsync + directory fsync for every intermediate value.
        """
        while not self._config_write_stop.is_set() or not self._config_write_queue.empty():
            try:
                payload, make_backup = self._config_write_queue.get(timeout=0.10)
            except queue.Empty:
                continue
            # Coalesce any edits that arrived while this job was waiting.
            while True:
                try:
                    payload, make_backup = self._config_write_queue.get_nowait()
                except queue.Empty:
                    break
            try:
                _atomic_write_text(self._config_path, payload, make_backup=make_backup)
            except Exception as exc:
                self._log(f"[Config] save failed: {exc}")

    def _queue_config_write(self, payload: str, make_backup: bool = True):
        if self.smoke_test or not self._config_async_ready:
            _atomic_write_text(self._config_path, payload, make_backup=make_backup)
            return
        job = (str(payload), bool(make_backup))
        try:
            self._config_write_queue.put_nowait(job)
            return
        except queue.Full:
            pass
        try:
            self._config_write_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self._config_write_queue.put_nowait(job)
        except queue.Full:
            # A writer race can refill the single-slot queue; the in-flight write
            # still contains a very recent complete snapshot, and the next edit
            # will enqueue again. Never block the UI thread here.
            pass

    def _stop_config_writer(self):
        if not getattr(self, "_config_write_thread", None):
            return
        self._config_write_stop.set()
        try:
            self._config_write_thread.join(timeout=2.0)
        except Exception:
            pass

    def _save_config(self, include_staged_freed: bool = False, make_backup: bool = True):
        try:
            # Setup/Free-D are auto-save pages. Persist the current live Free-D
            # snapshot on every config save. The legacy argument is retained for
            # compatibility with older internal callers/tests.
            freed_snap = self._freed_snapshot()
            c = {
                "config_schema_version": 3,
                "not_calibrated_mode": True,
                "position_reference_persistent": False,
                "ctrl_ip": self.ctrl_ip,
                "w1p_ip": self.w1p_ip,
                "reverse_joystick": self.reverse_joystick,
                "reverse_motor": self.reverse_motor,
                "joystick_deadband_pct": self.joystick_deadband_pct,
                "joystick_calibration": {
                    "left": self.joystick_cal_left,
                    "centre": self.joystick_cal_centre,
                    "right": self.joystick_cal_right,
                },
                "position_source": self.position_source,
                "ctrl_aux_assignments": self.ctrl_aux_assignments,
                "w1p_aux_assignments": self.w1p_aux_assignments,
                "units_per_m": self.winch_units_per_m,
                "drive_modes": self.drive_modes,
                "active_drive_mode": self.active_drive_mode,
                "acceleration_mode": self.acceleration_mode,
                "battery_change_mode": self.battery_change_mode,
                "preset_names": self.preset_names,
                "preset_name_mode": self.preset_name_mode,
                "preset_positions": self.preset_positions,
                "preset_visible": self.preset_visible,
                "limits": {
                    "near": self.state.near_limit.position_m,
                    "far": self.state.far_limit.position_m,
                    "ref": self.state.ref_point.position_m,
                    "raw": dict(self._limit_raw),
                    "nearRamp": {"mode":self.state.near_limit.ramp_mode,"distance":self.state.near_limit.ramp_distance_m,"percentage":self.state.near_limit.ramp_percentage},
                    "farRamp": {"mode":self.state.far_limit.ramp_mode,"distance":self.state.far_limit.ramp_distance_m,"percentage":self.state.far_limit.ramp_percentage},
                },
                "geometry": [dict(p) for p in freed_snap.get("geometry", self.geometry)],
                "free_d": {
                    "input_enabled": bool(freed_snap.get("input_enabled", self.freed_input_enabled)),
                    "input_bind_ip": str(freed_snap.get("input_bind_ip", self.freed_input_bind_ip)),
                    "input_port": int(freed_snap.get("input_port", self.freed_input_port)),
                    "output_enabled": bool(freed_snap.get("output_enabled", self.freed_output_enabled)),
                    "target_ip": str(freed_snap.get("target_ip", self.freed_target_ip)),
                    "target_port": int(freed_snap.get("target_port", self.freed_target_port)),
                    "rate_hz": float(freed_snap.get("rate_hz", self.freed_rate_hz)),
                    "pos_scale": float(freed_snap.get("pos_scale", self.freed_pos_scale)),
                    "input_offsets": dict(freed_snap.get("input_offsets", self.freed_input_offsets)),
                    "input_inverts": dict(freed_snap.get("input_inverts", self.freed_input_inverts)),
                    "output_offsets": dict(freed_snap.get("output_offsets", self.freed_output_offsets)),
                    "output_inverts": dict(freed_snap.get("output_inverts", self.freed_output_inverts)),
                    "lens_type": str(freed_snap.get("lens_type", self.freed_lens_type)),
                    "lens_scale_mode": str(freed_snap.get("lens_scale_mode", self.freed_lens_scale_mode)),
                    "lens_cal": dict(freed_snap.get("lens_cal", self.freed_lens_cal)),
                    "lens_auto_seen": dict(freed_snap.get("lens_auto_seen", self._freed_lens_auto_seen)),
                    "skate_weight_kg": float(freed_snap.get("skate_weight_kg", freed_snap.get("static_weight_kg", self.skate_weight_kg))),
                    "static_weight_kg": float(freed_snap.get("skate_weight_kg", freed_snap.get("static_weight_kg", self.skate_weight_kg))),  # legacy
                    "cable_weight_kg100m": float(freed_snap.get("cable_weight_kg100m", self.cable_weight_kg100m)),
                    "cable_tension_kg": float(freed_snap.get("cable_tension_kg", self.cable_tension_kg)),
                    "skate_weight_unit": str(freed_snap.get("skate_weight_unit", freed_snap.get("static_weight_unit", self.skate_weight_unit))),
                    "static_weight_unit": str(freed_snap.get("skate_weight_unit", freed_snap.get("static_weight_unit", self.skate_weight_unit))),  # legacy
                    "cable_weight_unit": str(freed_snap.get("cable_weight_unit", self.cable_weight_unit)),
                    "cable_tension_unit": str(freed_snap.get("cable_tension_unit", self.cable_tension_unit)),
                    "highline_mode": str(freed_snap.get("highline_mode", self.highline_mode)),
                },
            }
            self._queue_config_write(json.dumps(c, indent=2) + "\n", make_backup=make_backup)
        except Exception as exc:
            self._log(f"[Config] save failed: {exc}")

    # --- QML properties ---
    @Property(bool, notify=stateChanged)
    def ctrlConnected(self): return self._ctrl_connected()
    @Property(bool, notify=stateChanged)
    def w1pConnected(self): return bool(self.w1p.connected and self._w1p_status_fresh())
    @Property(bool, notify=stateChanged)
    def freeDActive(self): return bool(self.freed_input_last_rx and time.time()-self.freed_input_last_rx<2.0)
    @Property(float, notify=stateChanged)
    def freeDFps(self): return float(self.freed_in_fps)
    def _firmware_display_value(self, role: str, version: str) -> str:
        key = "w1p" if str(role).lower().startswith("w1p") else "ctrl"
        state = self._fw_progress.get(key, {})
        if bool(state.get("active", False)):
            phase = str(state.get("phase", "Updating") or "Updating")
            try: pct = max(0, min(100, int(float(state.get("pct", 0)))))
            except Exception: pct = 0
            return f"{phase} {pct}%"
        return str(version or "—")

    @Property(str, notify=stateChanged)
    def ctrlFirmwareVersion(self): return str(self._ctrl_fw_version or "—")
    @Property(str, notify=stateChanged)
    def ctrlFirmwareDisplay(self): return self._firmware_display_value("ctrl", self._ctrl_fw_version)
    @Property(str, notify=stateChanged)
    def w1pFirmwareVersion(self): return str(self._w1p_fw_version or "—")
    @Property(str, notify=stateChanged)
    def w1pFirmwareDisplay(self): return self._firmware_display_value("w1p", self._w1p_fw_version)
    @Property(bool, notify=stateChanged)
    def ctrlEStopActive(self): return bool(self._ctrl_estop)
    @Property(bool, notify=stateChanged)
    def w1pEStopActive(self): return bool(self._w1p_estop)
    @Property(bool, notify=stateChanged)
    def ctrlTsConnected(self):
        return bool(self._ctrl_connected() and self._ctrl_ts_connected_reported and
                    self._ctrl_ts_last_seen > 0 and time.time() - self._ctrl_ts_last_seen <= HMI_STATUS_TIMEOUT_S)
    @Property(bool, notify=stateChanged)
    def ctrlTsRs485Active(self):
        return bool(self._ctrl_connected() and self._ctrl_ts_rs485_alive_reported and
                    self._ctrl_ts_last_seen > 0 and time.time() - self._ctrl_ts_last_seen <= HMI_STATUS_TIMEOUT_S)
    @Property(str, notify=stateChanged)
    def ctrlTsVersion(self): return str(self._ctrl_ts_version or "—")
    @Property(str, notify=stateChanged)
    def ctrlTsRequiredVersion(self):
        # SRVR is the release authority. Do not display an old CTRL's embedded
        # requirement as current when a newer SRVR has just started.
        return self._current_firmware_version()
    @Property(str, notify=stateChanged)
    def ctrlTsFirmwareState(self):
        raw = str(self._ctrl_ts_fw_state or "idle")
        current = self._firmware_version_matches_current(self._ctrl_ts_version)
        authority_current = bool(self._ctrl_fw_match)
        states = {
            "starting": "Starting update",
            "transferring": "Updating",
            "verifying": "Verifying",
            "rebooting": "Rebooting",
            "safe_reboot": "Restarting in safe update mode",
            "image_missing": "Image not staged",
            "manual_bootstrap": "Manual USB bootstrap required",
        }
        if raw == "idle":
            if not self.ctrlTsRs485Active:
                return "Idle"
            return "Up to date" if current and authority_current and self.ctrlTsConnected else "Update required"
        return states.get(raw, raw)
    @Property(int, notify=stateChanged)
    def ctrlTsFirmwareProgress(self): return int(max(0, min(100, self._ctrl_ts_fw_pct)))
    @Property(str, notify=stateChanged)
    def ctrlTsFirmwareDisplay(self):
        raw = str(self._ctrl_ts_fw_state or "idle")
        if raw in ("starting", "transferring", "verifying", "rebooting", "safe_reboot"):
            return f"{self.ctrlTsFirmwareState} {self.ctrlTsFirmwareProgress}%"
        return str(self._ctrl_ts_version or "—")
    @Property(str, notify=stateChanged)
    def ctrlTsBootId(self): return str(self._ctrl_ts_boot_id or "—")
    @Property(int, notify=stateChanged)
    def ctrlTsResetReason(self): return int(self._ctrl_ts_reset_reason)
    @Property(float, notify=stateChanged)
    def positionFraction(self): return float(self._span_fraction(self.position))
    @Property(float, notify=stateChanged)
    def refFraction(self): return float(self._span_fraction(self.refPoint))
    @Property(bool, notify=stateChanged)
    def ctrlTsImageAvailable(self): return bool(self._ctrl_ts_image_available)
    @Property(bool, notify=stateChanged)
    def ctrlTsCompatible(self):
        return bool(self._ctrl_ts_compatible_reported and self._ctrl_ts_last_seen > 0 and
                    time.time() - self._ctrl_ts_last_seen <= HMI_STATUS_TIMEOUT_S and
                    self._firmware_version_matches_current(self._ctrl_ts_version) and self._ctrl_fw_match)
    def _joystick_input_connected(self):
        if not self._ctrl_connected() or bool(self._ctrl_flags & FLAG_ADS1115_FAULT):
            return False
        # Prefer the explicit HMI_STATUS ads= field when available. ``ads`` and
        # FLAG_ADS1115_FAULT are retained wire names; on EdgeBox they mean the
        # onboard SGM58031 / AI1 joystick-input health, not an external ADS1115.
        if self._ads1115_status_last_seen > 0 and time.time() - self._ads1115_status_last_seen <= HMI_STATUS_TIMEOUT_S:
            return bool(self._ads1115_connected_reported)
        return True
    @Property(bool, notify=stateChanged)
    def joystickInputConnected(self): return self._joystick_input_connected()
    @Property(bool, notify=stateChanged)
    def ads1115Connected(self): return self._joystick_input_connected()  # legacy QML/API alias
    @Property(bool, notify=stateChanged)
    def w1pTsConnected(self):
        return bool(self.w1p.connected and self._w1p_ts_connected_reported and
                    self._w1p_ts_last_seen > 0 and time.time() - self._w1p_ts_last_seen <= HMI_STATUS_TIMEOUT_S)
    @Property(bool, notify=stateChanged)
    def rs485Connected(self): return bool(self.w1p.connected and self._w1p_status_fresh() and self._w1p_fw_match and self.winch_rs_status == "Connected")
    @Property(float, notify=stateChanged)
    def joystickValue(self): return float(self._operator_joystick_axis(self._calibrated_joystick(self._ctrl_axis)))
    @Property(float, notify=stateChanged)
    def joystickPercentage(self):
        # Calibrated physical stick position: Left=-100%, Centre=0%, Right=+100%.
        # Direction inversion is a downstream motion-command setting and deliberately
        # does not change this calibration readout. Neutral display uses the same
        # deadband semantics as operation; raw calibration data remains untouched.
        return float(self._operator_joystick_axis(self._calibrated_joystick(self._ctrl_axis)) * 100.0)
    @Property(float, notify=stateChanged)
    def joystickRawValue(self): return float(self._ctrl_axis)
    @Property(float, notify=stateChanged)
    def setupJoystickValue(self): return float(self._operator_joystick_axis(self._setup_preview_joystick()))
    @Property(float, notify=stateChanged)
    def setupJoystickPercentage(self): return float(self._operator_joystick_axis(self._setup_preview_joystick()) * 100.0)
    @Property(float, notify=stateChanged)
    def joystickCentreTrimPercentage(self):
        span = self._joystick_min_cal_span()
        return float(100.0 * self._joystick_centre_trim_raw / max(span, 1e-6))
    @Property(int, notify=stateChanged)
    def systemStatusLevel(self):
        # 2=red safety/fault, 1=yellow service/unreferenced, 0=green ready.
        _text, level, _source, _estop = self._resolved_system_status()
        return 2 if level == "red" else (1 if level == "yellow" else 0)
    @Property(bool, notify=stateChanged)
    def systemReady(self): return self.systemStatusLevel == 0
    @Property(str, notify=stateChanged)
    def bannerText(self):
        text, _level, _source, _estop = self._resolved_system_status()
        return text
    @Property(float, notify=stateChanged)
    def position(self): return float(self.state.pos_m or 0.0)
    @Property(float, notify=stateChanged)
    def currentSpeed(self): return abs(float(self.current_speed_mps))
    @Property(float, notify=stateChanged)
    def maxSpeed(self): return float(self.max_speed_mps)
    @Property(float, notify=stateChanged)
    def toNear(self): return self.position-float(self.state.near_limit.position_m or 0.0)
    @Property(float, notify=stateChanged)
    def toFar(self): return float(self.state.far_limit.position_m or 100.0)-self.position
    @Property(float, notify=stateChanged)
    def nearLimit(self): return float(self.state.near_limit.position_m or 0.0)
    @Property(float, notify=stateChanged)
    def farLimit(self): return float(self.state.far_limit.position_m or 100.0)
    @Property(float, notify=stateChanged)
    def refPoint(self): return float(self.state.ref_point.position_m or 0.0)
    @Property(float, notify=stateChanged)
    def spanLength(self): return float(self._span_length_m())
    @Property(float, notify=stateChanged)
    def nearRampDistance(self):
        return float(self._ramp_distance(self.state.near_limit, self._span_length_m()))
    @Property(float, notify=stateChanged)
    def farRampDistance(self):
        return float(self._ramp_distance(self.state.far_limit, self._span_length_m()))
    @Property(float, notify=stateChanged)
    def nearRampFraction(self):
        span = self._span_length_m()
        return 0.0 if span <= 1e-9 else float(self.nearRampDistance / span)
    @Property(float, notify=stateChanged)
    def farRampFraction(self):
        span = self._span_length_m()
        return 0.0 if span <= 1e-9 else float(self.farRampDistance / span)
    @Property(str, notify=configChanged)
    def nearRampMode(self): return str(self.state.near_limit.ramp_mode)
    @Property(str, notify=configChanged)
    def farRampMode(self): return str(self.state.far_limit.ramp_mode)
    @Property(float, notify=configChanged)
    def nearRampValue(self):
        return float(self.state.near_limit.ramp_percentage if self.state.near_limit.ramp_mode == "Percentage" else self.nearRampDistance)
    @Property(float, notify=configChanged)
    def farRampValue(self):
        return float(self.state.far_limit.ramp_percentage if self.state.far_limit.ramp_mode == "Percentage" else self.farRampDistance)
    @Property(str, notify=configChanged)
    def driveModeName(self): return str(self.drive_modes[self.active_drive_mode].get("name",f"Mode {self.active_drive_mode+1}"))
    @Property(int, notify=configChanged)
    def activeDriveMode(self): return int(self.active_drive_mode)
    @Property(str, notify=configChanged)
    def driveMode1Name(self): return str(self.drive_modes[0].get("name", "Mode 1"))
    @Property(str, notify=configChanged)
    def driveMode2Name(self): return str(self.drive_modes[1].get("name", "Mode 2"))
    @Property(str, notify=configChanged)
    def accelerationMode(self): return self.acceleration_mode
    @Property(bool, notify=configChanged)
    def batteryChange(self): return self.battery_change_mode
    @staticmethod
    def _normalise_preset_name_mode(value) -> str:
        return "Long Names" if str(value or "").strip().lower().startswith("long") else "Short Names"

    def _preset_display_name(self, i: int) -> str:
        if not (0 <= int(i) < 10):
            return ""
        short_name = f"P{int(i)+1}"
        if self.preset_name_mode == "Long Names":
            return str(self.preset_names[int(i)] or short_name).strip() or short_name
        return short_name

    @Property(str, notify=configChanged)
    def presetNameMode(self): return str(self.preset_name_mode)
    @Property('QVariantList', notify=configChanged)
    def presets(self):
        return [{
            "index": i,
            "label": f"P{i+1}",
            "shortName": f"P{i+1}",
            "longName": str(self.preset_names[i] or f"P{i+1}"),
            "name": str(self.preset_names[i] or f"P{i+1}"),
            "displayName": self._preset_display_name(i),
            "position": self.preset_positions[i] if self.preset_positions[i] is not None else 0.0,
            "set": self.preset_positions[i] is not None,
            "visible": self.preset_visible[i],
        } for i in range(10)]
    @Property('QVariantList', notify=configChanged)
    def geometryPoints(self): return self.geometry
    @Property('QVariantList', notify=stateChanged)
    def cableProfile(self):
        # Run always uses the last-applied Free-D geometry/sag configuration.
        # Cache by only the inputs that affect the profile so Top/Side consumers
        # share one calculation for each live state.
        geometry_key = tuple((str(p.get("name", "")), p.get("x"), p.get("y"), p.get("z")) for p in self.geometry)
        key = (
            self.state.pos_m, self.state.near_limit.position_m, self.state.far_limit.position_m,
            geometry_key, float(self.cable_weight_kg100m), float(self.cable_tension_kg),
            float(self.skate_weight_kg), str(self.highline_mode),
        )
        if key != self._cable_profile_cache_key:
            self._cable_profile_cache_key = key
            self._cable_profile_cache_value = self._cable_profile(moving_skate_path=False)
        return self._cable_profile_cache_value
    @Property('QVariantMap', notify=stateChanged)
    def freeDInput(self):
        r=self.freed_in_raw; d=self.freed_in
        pan = float(d["Pan"]) * self._input_sign("Pan") + float(self.freed_input_offsets.get("Pan", 0.0))
        tilt = float(d["Tilt"]) * self._input_sign("Tilt") + float(self.freed_input_offsets.get("Tilt", 0.0))
        roll = float(d["Roll"]) * self._input_sign("Roll") + float(self.freed_input_offsets.get("Roll", 0.0))
        zoom = float(d["Zoom"]) * self._input_sign("Zoom")
        focus = float(d["Focus"]) * self._input_sign("Focus")
        return {
            "cam":int(r["Cam ID"]),"panRaw":int(r["Pan"]),"pan":pan,
            "tiltRaw":int(r["Tilt"]),"tilt":tilt,"rollRaw":int(r["Roll"]),"roll":roll,
            "zoomRaw":int(r["Zoom"]),"zoom":zoom,"focusRaw":int(r["Focus"]),"focus":focus,
            "zoomPct":self._lens_percent("zoom", zoom),"focusPct":self._lens_percent("focus", focus),
            "fps":float(self.freed_in_fps)
        }
    @Property('QVariantMap', notify=stateChanged)
    def freeDOutput(self):
        x,y,z=self._xyz()
        return {
            "x":float(x)*self._output_sign("X"),
            "y":float(y)*self._output_sign("Y"),
            "z":float(z)*self._output_sign("Z"),
            "fps":float(self.freed_out_fps),
            "targetFps":float(self.freed_rate_hz),
        }

    # Editable Setup / Free-D configuration uses a slower configChanged signal so
    # live CTRL telemetry updates cannot steal focus or reset text while typing.
    @Property(str, notify=configChanged)
    def ctrlIp(self): return str(self.ctrl_ip)
    @Property(str, notify=configChanged)
    def w1pIp(self): return str(self.w1p_ip)
    @Property(bool, notify=configChanged)
    def ctrlInverted(self): return bool(self.reverse_joystick)
    @Property(bool, notify=configChanged)
    def w1pInverted(self): return bool(self.reverse_motor)
    @Property(float, notify=configChanged)
    def unitsPerM(self): return float(self.winch_units_per_m)
    @Property(float, notify=configChanged)
    def joystickDeadband(self): return float(self.joystick_deadband_pct)
    @Property(str, notify=configChanged)
    def positionSource(self): return str(self.position_source)
    @Property('QVariantList', notify=configChanged)
    def driveModes(self): return [dict(x) for x in self.drive_modes]
    @Property('QVariantList', notify=configChanged)
    def ctrlAuxAssignments(self): return list(self.ctrl_aux_assignments)
    @Property('QVariantList', notify=configChanged)
    def w1pAuxAssignments(self): return list(self.w1p_aux_assignments)
    @Property('QVariantMap', notify=configChanged)
    def setupDraft(self):
        snap = copy.deepcopy(getattr(self, "_setup_draft", self._setup_snapshot()))
        return snap

    @Property('QVariantMap', notify=configChanged)
    def freeDDraft(self):
        snap = copy.deepcopy(getattr(self, "_freed_draft", self._freed_snapshot()))
        snap["skate_weight_value"] = self._kg_to_lb(snap["skate_weight_kg"]) if snap.get("skate_weight_unit") == "lbs" else float(snap["skate_weight_kg"])
        snap["cable_weight_value"] = self._kg_to_lb(snap["cable_weight_kg100m"]) if snap.get("cable_weight_unit") == "lbs/100m" else float(snap["cable_weight_kg100m"])
        snap["cable_tension_value"] = self._kg_to_lb(snap["cable_tension_kg"]) if snap.get("cable_tension_unit") == "lbs" else float(snap["cable_tension_kg"])
        return snap

    def _lens_percent_snapshot(self, field: str, value: float, snap: dict) -> float:
        field = "zoom" if str(field).lower().startswith("zoom") else "focus"
        mode = str(snap.get("lens_scale_mode", "Auto"))
        lens_type = str(snap.get("lens_type", "u16"))
        if lens_type == "u16": limits = (0.0, 65535.0)
        elif lens_type == "i16": limits = (-32768.0, 32767.0)
        elif lens_type == "u24": limits = (0.0, 16777215.0)
        else: limits = (-8388608.0, 8388607.0)
        cal = dict(snap.get("lens_cal", {}))
        seen = dict(snap.get("lens_auto_seen", {}))
        if mode == "Full Scale":
            lo, hi = limits
        elif mode == "Auto":
            lo, hi = seen.get(field+"_min"), seen.get(field+"_max")
            if lo is None or hi is None or abs(float(hi)-float(lo)) < 1e-9:
                lo = float(cal.get("zoom_wide" if field == "zoom" else "focus_near", 0.0))
                hi = float(cal.get("zoom_tele" if field == "zoom" else "focus_far", 32767.0))
        else:
            lo = float(cal.get("zoom_wide" if field == "zoom" else "focus_near", 0.0))
            hi = float(cal.get("zoom_tele" if field == "zoom" else "focus_far", 32767.0))
        if abs(float(hi)-float(lo)) < 1e-9: return 0.0
        return max(0.0, min(100.0, (float(value)-float(lo))*100.0/(float(hi)-float(lo))))

    @Property('QVariantMap', notify=stateChanged)
    def freeDInputPreview(self):
        snap = getattr(self, "_freed_draft", self._freed_snapshot())
        r = self.freed_in_raw
        pan = float(self.freed_in.get("Pan",0.0))*self._input_sign("Pan", snap.get("input_inverts",{})) + float(snap.get("input_offsets",{}).get("Pan",0.0))
        tilt = float(self.freed_in.get("Tilt",0.0))*self._input_sign("Tilt", snap.get("input_inverts",{})) + float(snap.get("input_offsets",{}).get("Tilt",0.0))
        roll = float(self.freed_in.get("Roll",0.0))*self._input_sign("Roll", snap.get("input_inverts",{})) + float(snap.get("input_offsets",{}).get("Roll",0.0))
        zoom = float(self._decode_lens_for_type(int(r.get("Zoom",0)), snap.get("lens_type","u16")))*self._input_sign("Zoom", snap.get("input_inverts",{}))
        focus = float(self._decode_lens_for_type(int(r.get("Focus",0)), snap.get("lens_type","u16")))*self._input_sign("Focus", snap.get("input_inverts",{}))
        return {"cam":int(r.get("Cam ID",1)),"panRaw":int(r.get("Pan",0)),"pan":pan,
                "tiltRaw":int(r.get("Tilt",0)),"tilt":tilt,"rollRaw":int(r.get("Roll",0)),"roll":roll,
                "zoomRaw":int(r.get("Zoom",0)),"zoom":zoom,"focusRaw":int(r.get("Focus",0)),"focus":focus,
                "zoomPct":self._lens_percent_snapshot("zoom",zoom,snap),"focusPct":self._lens_percent_snapshot("focus",focus,snap),
                "fps":float(self.freed_in_fps)}

    @Property('QVariantMap', notify=stateChanged)
    def freeDOutputPreview(self):
        snap = getattr(self, "_freed_draft", self._freed_snapshot())
        x,y,z = self._xyz(snap)
        inv = snap.get("output_inverts",{})
        return {"x":float(x)*self._output_sign("X",inv), "y":float(y)*self._output_sign("Y",inv),
                "z":float(z)*self._output_sign("Z",inv), "fps":float(self.freed_out_fps),
                "targetFps":float(snap.get("rate_hz",self.freed_rate_hz))}

    @Property('QVariantList', notify=stateChanged)
    def freeDPreviewCableProfile(self):
        snap = getattr(self, "_freed_draft", self._freed_snapshot())
        geometry = snap.get("geometry", self.geometry)
        geometry_key = tuple((str(p.get("name", "")), p.get("x"), p.get("y"), p.get("z")) for p in geometry)
        key = (
            geometry_key, float(snap.get("cable_weight_kg100m", self.cable_weight_kg100m)),
            float(snap.get("cable_tension_kg", self.cable_tension_kg)),
            float(snap.get("skate_weight_kg", snap.get("static_weight_kg", self.skate_weight_kg))),
            str(snap.get("highline_mode", self.highline_mode)),
        )
        if key != self._freed_profile_cache_key:
            self._freed_profile_cache_key = key
            self._freed_profile_cache_value = self._cable_profile(snap, moving_skate_path=True)
        return self._freed_profile_cache_value

    @Property('QVariantMap', notify=configChanged)
    def calibrationSummary(self):
        def item(lp, raw_key):
            is_set = lp.position_m is not None
            return {
                "set": bool(is_set),
                "position": float(lp.position_m or 0.0),
                "raw": "—" if self._limit_raw.get(raw_key) is None else str(self._limit_raw.get(raw_key)),
            }
        return {
            "near": item(self.state.near_limit, "near"),
            "ref": item(self.state.ref_point, "ref"),
            "far": item(self.state.far_limit, "far"),
        }
    @Property(bool, notify=configChanged)
    def freeDInputEnabled(self): return bool(self.freed_input_enabled)
    @Property(str, notify=configChanged)
    def freeDInputIp(self): return str(self.freed_input_bind_ip)
    @Property(int, notify=configChanged)
    def freeDInputPort(self): return int(self.freed_input_port)
    @Property(bool, notify=configChanged)
    def freeDOutputEnabled(self): return bool(self.freed_output_enabled)
    @Property(str, notify=configChanged)
    def freeDOutputIp(self): return str(self.freed_target_ip)
    @Property(int, notify=configChanged)
    def freeDOutputPort(self): return int(self.freed_target_port)
    @Property(float, notify=configChanged)
    def freeDOutputRate(self): return float(self.freed_rate_hz)
    @Property('QVariantMap', notify=configChanged)
    def freeDInputOffsets(self): return dict(self.freed_input_offsets)
    @Property('QVariantMap', notify=configChanged)
    def freeDInputInverts(self): return dict(self.freed_input_inverts)
    @Property('QVariantMap', notify=configChanged)
    def freeDOutputOffsets(self): return dict(self.freed_output_offsets)
    @Property('QVariantMap', notify=configChanged)
    def freeDOutputInverts(self): return dict(self.freed_output_inverts)
    @Property(str, notify=configChanged)
    def lensType(self): return str(self.freed_lens_type)
    @Property(str, notify=configChanged)
    def lensScale(self): return str(self.freed_lens_scale_mode)
    @Property('QVariantMap', notify=configChanged)
    def lensCalibration(self): return dict(self.freed_lens_cal)
    @Property(float, notify=configChanged)
    def skateWeightValue(self): return self._kg_to_lb(self.skate_weight_kg) if self.skate_weight_unit == "lbs" else float(self.skate_weight_kg)
    @Property(str, notify=configChanged)
    def skateWeightUnit(self): return str(self.skate_weight_unit)
    # Legacy aliases retained so an older QML/config package can still bind safely.
    @Property(float, notify=configChanged)
    def staticWeightValue(self): return self.skateWeightValue
    @Property(str, notify=configChanged)
    def staticWeightUnit(self): return self.skateWeightUnit
    @Property(float, notify=configChanged)
    def cableWeightValue(self): return self._kg_to_lb(self.cable_weight_kg100m) if self.cable_weight_unit == "lbs/100m" else float(self.cable_weight_kg100m)
    @Property(str, notify=configChanged)
    def cableWeightUnit(self): return str(self.cable_weight_unit)
    @Property(float, notify=configChanged)
    def cableTensionValue(self): return self._kg_to_lb(self.cable_tension_kg) if self.cable_tension_unit == "lbs" else float(self.cable_tension_kg)
    @Property(str, notify=configChanged)
    def cableTensionUnit(self): return str(self.cable_tension_unit)
    @Property(str, notify=configChanged)
    def highlineMode(self): return str(self.highline_mode)
    @Property(str, notify=logChanged)
    def logText(self):
        with self._lock: return "\n".join(self._logs)
    @Property(int, notify=logChanged)
    def logRevision(self): return int(self._log_revision)
    @Property(int, notify=logChanged)
    def logCount(self):
        with self._lock: return len(self._log_entries)
    @Slot(str, str, str, result='QVariantList')
    def filteredLogEntries(self, view, severity, search):
        view = str(view or "Live")
        severity = str(severity or "All")
        needle = str(search or "").strip().casefold()
        sev_map = {"Info":"INFO", "Warning":"WARN", "Fault":"FAULT"}
        wanted_level = sev_map.get(severity)
        with self._lock:
            entries = [dict(x) for x in self._log_entries]
        out = []
        for entry in entries:
            if view != "Live" and entry.get("view") != view:
                continue
            if wanted_level and entry.get("level") != wanted_level:
                continue
            if needle:
                hay = " ".join(str(entry.get(k, "")) for k in ("time", "level", "source", "message")).casefold()
                if needle not in hay:
                    continue
            out.append(entry)
        return out
    @Property(str, notify=calibrationChanged)
    def calibrationType(self): return self.calibration_type
    @Property(int, notify=calibrationChanged)
    def calibrationStep(self): return self.calibration_step
    @Property(bool, notify=calibrationChanged)
    def calibrationOpen(self): return self.calibration_open
    @Property(str, notify=calibrationChanged)
    def calibrationTitle(self): return self.calibration_title
    @Property(float, notify=stateChanged)
    def limitCalibrationPosition(self):
        return float(self._limit_calibration_display_position())
    @Property('QVariantMap', notify=stateChanged)
    def limitCalibrationCaptures(self):
        def shown(name):
            value = self._limit_cal_pending.get(name)
            return "—" if value is None else f"{float(value):.2f} m"
        return {
            "near": shown("near"),
            "ref": shown("ref"),
            "far": shown("far"),
            "current": f"{self._limit_calibration_display_position():.2f} m",
        }
    @Property(bool, notify=joystickCalibrationChanged)
    def joystickCalibrationOpen(self): return bool(self.joystick_calibration_open)
    @Property(int, notify=joystickCalibrationChanged)
    def joystickCalibrationStep(self): return int(self.joystick_calibration_step)
    @Property(str, notify=joystickCalibrationChanged)
    def joystickCalibrationTitle(self): return str(self.joystick_calibration_title)
    @Property(str, notify=joystickCalibrationChanged)
    def joystickCalibrationError(self): return str(self.joystick_calibration_error)
    @Property('QVariantMap', notify=joystickCalibrationChanged)
    def joystickCalibrationCaptures(self):
        return {
            "left": "—" if self._joystick_cal_pending.get("left") is None else f"{float(self._joystick_cal_pending['left']):.4f}",
            "centre": "—" if self._joystick_cal_pending.get("centre") is None else f"{float(self._joystick_cal_pending['centre']):.4f}",
            "right": "—" if self._joystick_cal_pending.get("right") is None else f"{float(self._joystick_cal_pending['right']):.4f}",
        }
    @Property(str, notify=stateChanged)
    def srvrTime(self): return time.strftime("%Y-%m-%d  %H:%M:%S")
    @Property(str, notify=stateChanged)
    def uptime(self):
        s=int(time.time()-self.started); return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"

    def _emit_config_changed(self):
        self._config_notify_pending = False
        self.configChanged.emit()

    def _notify_config(self):
        # Return from the QML ComboBox/field callback first so the popup can close
        # immediately. Multiple edits in the same Qt turn coalesce into one config
        # invalidation; live telemetry remains on the independent 20 Hz state tick.
        if self._config_notify_pending:
            return
        self._config_notify_pending = True
        QTimer.singleShot(0, self._emit_config_changed)

    # --- QML actions ---
    def _position_relative_to_near(self, pos=None) -> float:
        if pos is None:
            pos = self.state.pos_m
        nl = float(self.state.near_limit.position_m or 0.0)
        return float(pos or 0.0) - nl

    def _preset_absolute_position(self, i: int):
        if not (0 <= i < 10) or self.preset_positions[i] is None:
            return None
        return float(self.state.near_limit.position_m or 0.0) + float(self.preset_positions[i])

    @Slot(int,str)
    def setPresetName(self,i,name):
        if 0 <= i < 10:
            self.preset_names[i] = str(name).strip() or f"P{i+1}"
            self._save_config(); self._notify_config()

    @Slot(str)
    def setPresetNameMode(self, mode):
        new_mode = self._normalise_preset_name_mode(mode)
        if new_mode == self.preset_name_mode:
            return
        self.preset_name_mode = new_mode
        self._save_config()
        self._notify_config()
        self._send_controller_display_packet(force=True)

    @Slot(int,float)
    def setPresetPosition(self,i,value):
        # User-facing preset distances are relative to the Near end of the span.
        # Keep manually entered presets inside the current saved cable span.
        if 0 <= i < 10:
            span = max(0.0, abs(float(self.farLimit) - float(self.nearLimit)))
            self.preset_positions[i] = max(0.0, min(span, float(value))) if span > 0 else 0.0
            self._save_config(); self._notify_config()

    @Slot(int)
    def savePreset(self,i):
        if 0 <= i < 10 and self.state.pos_m is not None:
            self.preset_positions[i] = self._position_relative_to_near(self.state.pos_m)
            self._save_config(); self._notify_config()

    @Slot(int)
    def recallPreset(self,i):
        target = self._preset_absolute_position(i)
        if target is not None:
            self._start_goto_target(target)

    @Slot(int)
    def togglePresetVisible(self,i):
        if 0 <= i < 10:
            self.preset_visible[i] = not self.preset_visible[i]
            self._save_config(); self._notify_config()

    @Slot(str)
    def saveLimit(self,which):
        """Save current feedback position as Near/Far/Reference.

        A simple Save does not clear Not-Calibrated: only a Slip (known physical
        point) or completion of the Limit Calibration wizard establishes the
        position reference safely.
        """
        if self.state.pos_m is None:
            return
        lp = self._limit(which)
        lp.position_m = float(self.state.pos_m)
        key = "near" if lp is self.state.near_limit else "far" if lp is self.state.far_limit else "ref"
        raw = getattr(self, "_last_raw_pos", None)
        self._limit_raw[key] = None if raw is None else int(raw)
        if key in ("near", "far"):
            self._sync_ramp_representations_for_span()
        self._save_config(); self._sync_w1p_settings(); self._notify_config()

    @Slot(str)
    def recallLimit(self,which):
        lp = self._limit(which)
        if lp.position_m is not None:
            self._start_goto_target(float(lp.position_m))

    @Slot(str)
    def slipLimit(self,which):
        """Re-reference W1P position at a known point after cable/pulley slip."""
        lp = self._limit(which)
        if lp.position_m is None:
            return
        target = float(lp.position_m)
        self._cancel_goto()
        self._sync_position(target)
        self._not_calibrated = False
        self._sync_service_mode_to_winch(force=True)
        self._save_config(); self._notify_config()

    def _limit(self,which):
        w = str(which).lower()
        return self.state.near_limit if w.startswith("near") else self.state.far_limit if w.startswith("far") else self.state.ref_point

    @Slot(str,str,float)
    def setRamping(self,which,mode,value):
        """Set a ramp value while keeping Distance and Percentage equivalent.

        The physical ramp point never jumps merely because the operator changes
        units. Both representations are maintained from the same cable span.
        """
        lp = self._limit(which)
        if lp is self.state.ref_point:
            return
        span = max(0.001, abs(float(self.farLimit) - float(self.nearLimit)))
        new_mode = "Percentage" if str(mode).lower().startswith("percent") else "Distance"
        v = max(0.0, float(value))
        if new_mode == "Percentage":
            pct = max(0.0, min(100.0, v))
            lp.ramp_percentage = pct
            lp.ramp_distance_m = span * pct / 100.0
        else:
            dist = min(span, v)
            lp.ramp_distance_m = dist
            lp.ramp_percentage = max(0.0, min(100.0, dist * 100.0 / span))
        lp.ramp_mode = new_mode
        self._sync_ramp_representations_for_span()
        self._save_config(); self._notify_config()

    @Slot(str,str)
    def changeRampingMode(self, which, mode):
        """Convert the existing ramp to the newly selected representation."""
        lp = self._limit(which)
        if lp is self.state.ref_point:
            return
        span = max(0.001, abs(float(self.farLimit) - float(self.nearLimit)))
        physical_distance = self._ramp_distance(lp, span)
        new_mode = "Percentage" if str(mode).lower().startswith("percent") else "Distance"
        lp.ramp_distance_m = max(0.0, min(span, physical_distance))
        lp.ramp_percentage = max(0.0, min(100.0, lp.ramp_distance_m * 100.0 / span))
        lp.ramp_mode = new_mode
        self._sync_ramp_representations_for_span()
        self._save_config(); self._notify_config()

    @Slot(int)
    def setDriveMode(self,i):
        self.active_drive_mode = 0 if int(i) <= 0 else 1
        self._apply_active_drive_profile(sync=True)
        self._save_config(); self._notify_config()

    @Slot(int,str)
    def renameDriveMode(self,i,name):
        if i in (0,1):
            self.drive_modes[i]["name"] = str(name).strip() or f"Mode {i+1}"
            self._save_config(); self._notify_config()

    @Slot(str)
    def setAccelerationMode(self,mode):
        self.acceleration_mode = "Power" if str(mode).lower().startswith("power") else "Speed"
        self._sync_w1p_settings(); self._save_config(); self._refresh_setup_mirror(); self._notify_config()

    @Slot(bool)
    def setBatteryChange(self,on):
        self.battery_change_mode = bool(on)
        self._battery_change_went_outside_limits = False
        self._sync_service_mode_to_winch(force=True)
        self._save_config(); self._refresh_setup_mirror(); self._notify_config()

    @Slot()
    def toggleSrvrEStop(self):
        """Toggle the SRVR software E-stop latch from the status banner.

        Engaging the latch immediately requests hard STOP + software Servo Enable
        OFF. Clearing the latch does not re-enable torque immediately: the common
        safety-clear path first requires the joystick to return through neutral,
        then requests SW_SRVON 1. Other live safety sources remain authoritative.
        """
        self._srvr_estop = not bool(self._srvr_estop)
        self._cancel_goto()
        if self._srvr_estop:
            self._send_safety_stop_limited(force=True)
        else:
            # Keep the drive stopped/inhibited until _motion_tick sees every
            # source clear and the neutral-return interlock has been satisfied.
            # Set the neutral latch here as well so even an engage/clear action
            # occurring between two 25 ms motion ticks cannot bypass the interlock.
            self._joystick_neutral_required = True
            self._send_safety_stop_limited(force=True)
        self._log("[SRVR E-Stop] " + ("ACTIVE" if self._srvr_estop else "CLEAR - neutral required"))
        self.stateChanged.emit()

    @Slot()
    def openLimitCalibration(self):
        # Limit calibration is transactional. Captures are staged from raw encoder
        # deltas/current position and the existing valid Near/Far/Ref calibration
        # remains untouched until the final Reference confirmation commits all
        # three points together. This makes Cancel genuinely non-destructive.
        self.calibration_type = "Limit"
        self.calibration_open = True
        self.calibration_step = 0
        self.calibration_title = "Set Near Limit"
        self._limit_cal_pending = {"near": None, "ref": None, "far": None}
        self._limit_cal_capture = {"near_raw": None, "far_raw": None, "ref_raw": None,
                                   "near_pos": None, "far_pos": None, "ref_pos": None,
                                   "pending_reverse_motor": bool(self.reverse_motor)}
        if self.position_source == "Virtual" and self.state.pos_m is None:
            self.state.pos_m = 0.0
        self._cancel_goto()
        self._send_velocity(0.0, force=True)
        self._sync_service_mode_to_winch(force=True)
        self._log("[Calibration] Limit calibration started (transaction staged; existing calibration preserved until Ref commit)")
        self.calibrationChanged.emit(); self.stateChanged.emit()

    @Slot()
    def openWinchCalibration(self):
        self.calibration_type = "Winch"
        self.calibration_open = True
        self.calibration_step = 0
        self.calibration_title = "Set Zero"
        self._cancel_goto()
        self._winch_cal_zero_raw = None
        self._sync_service_mode_to_winch(force=True)
        self.calibrationChanged.emit(); self.stateChanged.emit()

    @Slot()
    def cancelCalibration(self):
        was_limit = bool(self.calibration_open and self.calibration_type == "Limit")
        self.calibration_open = False
        self._cancel_goto()
        self._send_velocity(0.0, force=True)
        # A Cancel may be pressed while the joystick is displaced. Do not let
        # service-mode exit turn that held stick into normal-speed motion.
        self._joystick_neutral_required = True
        self._sync_service_mode_to_winch(force=True)
        if was_limit:
            self._limit_cal_pending = {"near": None, "ref": None, "far": None}
            self._limit_cal_capture = {"near_raw": None, "far_raw": None, "ref_raw": None,
                                       "near_pos": None, "far_pos": None, "ref_pos": None,
                                       "pending_reverse_motor": None}
            self._log("[Calibration] Limit calibration cancelled; previous calibration retained")
        else:
            self._log("[Calibration] Calibration cancelled")
        self.calibrationChanged.emit(); self.configChanged.emit(); self.stateChanged.emit()

    def _sync_position(self, pos_m: float):
        self.state.pos_m = float(pos_m)
        self._winch_position_accept_jump_until = time.time() + 2.0
        self._winch_last_pos_accept_t = 0.0
        self._send_velocity(0.0, force=True)
        if not self.smoke_test and self.position_source != "Virtual":
            self.w1p.send(f"SYNC_POS {float(pos_m):.3f}")

    @Slot()
    def calibrationNext(self):
        # Calibration confirmation is edge/event driven from both SRVR and
        # CTRL-TS. Once a wizard has completed/closed, ignore any delayed or
        # duplicate Confirm event rather than re-entering the terminal capture
        # branch. The three-step Limit wizard completes on the Ref capture.
        if not self.calibration_open:
            return
        if self.calibration_type == "Limit":
            raw_now = None if self.position_source == "Virtual" else getattr(self, "_last_raw_pos", None)
            raw_now = None if raw_now is None else int(raw_now)
            pos_now = float(self.state.pos_m or 0.0)
            cap = self._limit_cal_capture
            if self.calibration_step == 0:
                cap["near_raw"] = raw_now
                cap["near_pos"] = pos_now
                self._limit_cal_pending["near"] = 0.0
                self.calibration_step = 1
                self.calibration_title = "Set Far Limit"
                self._log(f"[Calibration] Near staged raw={raw_now} pos={pos_now:.3f}; existing live limits unchanged")
            elif self.calibration_step == 1:
                cap["far_raw"] = raw_now
                cap["far_pos"] = pos_now
                near_raw = cap.get("near_raw")
                near_pos = cap.get("near_pos")
                if near_raw is not None and raw_now is not None:
                    raw_delta = int(raw_now) - int(near_raw)
                    sign = -1.0 if bool(self.reverse_motor) else 1.0
                    signed_travel = sign * (float(raw_delta) / max(1.0, float(self.winch_units_per_m)))
                else:
                    signed_travel = pos_now - float(near_pos if near_pos is not None else pos_now)
                if abs(signed_travel) < 0.01:
                    self._log("[Calibration] Far capture rejected: Near-to-Far travel is too small")
                    self.calibrationChanged.emit(); self.stateChanged.emit()
                    return
                span = abs(float(signed_travel))
                pending_reverse = bool(self.reverse_motor) ^ bool(signed_travel < 0.0)
                cap["pending_reverse_motor"] = pending_reverse
                self._limit_cal_pending["far"] = span
                self.calibration_step = 2
                self.calibration_title = "Set Reference Point"
                self._log(f"[Calibration] Far staged span={span:.3f} m; Winch Invert commit={'On' if pending_reverse else 'Off'}")
            elif self.calibration_step == 2:
                cap["ref_raw"] = raw_now
                cap["ref_pos"] = pos_now
                span = float(self._limit_cal_pending.get("far") or 0.0)
                if span < 0.01:
                    self._log("[Calibration] Reference capture rejected: Far span has not been staged")
                    return
                near_raw = cap.get("near_raw")
                near_pos = cap.get("near_pos")
                if near_raw is not None and raw_now is not None:
                    ref = abs((float(int(raw_now) - int(near_raw))) / max(1.0, float(self.winch_units_per_m)))
                else:
                    ref = abs(pos_now - float(near_pos if near_pos is not None else pos_now))
                ref = min(max(0.0, ref), span)
                self._limit_cal_pending["ref"] = ref

                # Commit point: all operator-facing calibration and motor direction
                # change together. No partial Near/Far values were live before here.
                new_reverse = bool(cap.get("pending_reverse_motor"))
                reverse_changed = new_reverse != bool(self.reverse_motor)
                self.reverse_motor = new_reverse
                self.state.near_limit.position_m = 0.0
                self.state.far_limit.position_m = span
                self.state.ref_point.position_m = ref
                self.state.total_length_m = span
                self._limit_raw["near"] = cap.get("near_raw")
                self._limit_raw["far"] = cap.get("far_raw")
                self._limit_raw["ref"] = cap.get("ref_raw")
                self._sync_ramp_representations_for_span()
                self._not_calibrated = False
                self.battery_change_mode = False
                self._battery_change_went_outside_limits = False
                self._cancel_goto()
                self._send_velocity(0.0, force=True)

                if self.position_source == "Virtual":
                    self.state.pos_m = ref
                elif not self.smoke_test:
                    # Preserve exact command ordering through W1P's single TX queue:
                    # direction/limits first, then establish the new Reference
                    # coordinate, then leave service mode. The convergence layer
                    # remains armed afterwards to retry any lost UDP setting.
                    self.w1p.send(f"SET_MOTOR_REVERSE {1 if self.reverse_motor else 0}")
                    self.w1p.send(f"SET_SPAN {span:.3f}")
                    self.w1p.send("SET_LIMIT_NEAR 0.000")
                    self.w1p.send(f"SET_LIMIT_FAR {span:.3f}")
                    self.w1p.send(f"SYNC_POS {ref:.3f}")
                    self.w1p.send("SERVICE_MODE 0")
                    self._winch_position_accept_jump_until = time.time() + 2.0
                    self.state.pos_m = ref

                self.calibration_open = False
                self.calibration_step = 2
                self.calibration_title = "Set Reference Point"
                self._last_service_mode_sent = 0
                self._mark_w1p_settings_pending()
                self._sync_w1p_settings()
                self._save_config()
                self._refresh_setup_mirror()
                self._log(
                    f"[Calibration] Limit calibration committed Near=0.000 Far={span:.3f} Ref={ref:.3f}"
                    + ("; Winch Invert changed" if reverse_changed else "")
                )
            else:
                self.calibration_open = False
                self._sync_service_mode_to_winch(force=True)
        else:
            raw = int(getattr(self, "_last_raw_pos", 0) or 0)
            if self.calibration_step == 0:
                self._winch_cal_zero_raw = raw
                self.calibration_step = 1
                self.calibration_title = "Set 20 m"
            elif self.calibration_step == 1:
                zero = int(self._winch_cal_zero_raw or 0)
                delta = abs(raw-zero)
                if delta <= 0:
                    self._log("[Calibration] Winch calibration failed: raw position did not change")
                else:
                    self.winch_units_per_m = max(1.0, delta/20.0)
                    self._sync_w1p_settings()
                    self._save_config()
                self.calibration_step = 2
                self.calibration_title = "Done"
            else:
                self.calibration_open = False
                self._sync_service_mode_to_winch(force=True)
        self.calibrationChanged.emit(); self.configChanged.emit(); self.stateChanged.emit()

    @Slot()
    def calibrationBack(self):
        if self.calibration_step > 0:
            self.calibration_step -= 1
        if self.calibration_type == "Limit":
            # Back means the later staged capture is no longer authoritative.
            # Clear it (and any derived direction decision) so a subsequent Next
            # always derives from the newly recaptured physical point.
            if self.calibration_step == 0:
                self._limit_cal_pending = {"near": None, "ref": None, "far": None}
                self._limit_cal_capture.update({
                    "near_raw": None, "far_raw": None, "ref_raw": None,
                    "near_pos": None, "far_pos": None, "ref_pos": None,
                    "pending_reverse_motor": bool(self.reverse_motor),
                })
            elif self.calibration_step == 1:
                self._limit_cal_pending["far"] = None
                self._limit_cal_pending["ref"] = None
                self._limit_cal_capture.update({
                    "far_raw": None, "ref_raw": None,
                    "far_pos": None, "ref_pos": None,
                    "pending_reverse_motor": bool(self.reverse_motor),
                })
            self.calibration_title = ("Set Near Limit","Set Far Limit","Set Reference Point")[min(self.calibration_step,2)]
        else:
            self.calibration_title = ("Set Zero","Set 20 m","Done")[min(self.calibration_step,2)]
        self.calibrationChanged.emit()

    @Slot(str,str)
    def setNetwork(self,which,value):
        if which == "CTRL":
            self.ctrl_ip = str(value).strip()
            self._ctrl_rx_times.clear()
        elif which == "W1P":
            self.w1p_ip = str(value).strip()
            self.w1p.reconfigure(self.w1p_ip,self.w1p_port)
        self._save_config(); self._notify_config()

    @Slot(str,bool)
    def setDirection(self,which,inverted):
        if which == "CTRL":
            self.reverse_joystick = bool(inverted)
        elif which == "W1P":
            self.reverse_motor = bool(inverted)
            self._sync_w1p_settings()
        self._save_config(); self._notify_config()

    @Slot(float)
    def setUnitsPerM(self,v):
        self.winch_units_per_m = max(1.0,float(v))
        self._sync_w1p_settings(); self._save_config(); self._notify_config()

    def _refresh_setup_mirror(self) -> None:
        self._saved_setup_snapshot = self._setup_snapshot()
        self._setup_draft = copy.deepcopy(self._saved_setup_snapshot)
        self._setup_draft_dirty = False

    def _refresh_freed_mirror(self) -> None:
        self._saved_freed_snapshot = self._freed_snapshot()
        self._freed_draft = copy.deepcopy(self._saved_freed_snapshot)
        self._freed_draft_dirty = False

    def _commit_setup_draft(self, *, notify: bool = True) -> bool:
        """Validate, apply and persist the current Setup mirror immediately."""
        draft = copy.deepcopy(self._setup_draft)
        try:
            new_w1p_ip = self._normalise_ipv4(draft.get("w1p_ip", self.w1p_ip))
            new_ctrl_ip = self._normalise_ipv4(draft.get("ctrl_ip", self.ctrl_ip))
        except ValueError as exc:
            self._log(f"[Config] Setup change refused: {exc}")
            self._refresh_setup_mirror()
            if notify: self._notify_config()
            return False
        if new_w1p_ip == new_ctrl_ip:
            self._log("[Config] Setup change refused: CTRL and W1P cannot use the same IP address")
            self._refresh_setup_mirror()
            if notify: self._notify_config()
            return False
        draft["w1p_ip"], draft["ctrl_ip"] = new_w1p_ip, new_ctrl_ip
        if new_w1p_ip != self.w1p_ip and not self._request_w1p_readdress(new_w1p_ip):
            self._log("[Config] Setup change refused because W1P local IP was not safely changed")
            self._refresh_setup_mirror()
            if notify: self._notify_config()
            return False
        self._restore_setup_snapshot(draft)
        self._save_config()
        self._refresh_setup_mirror()
        if notify: self._notify_config()
        return True

    def _commit_freed_draft(self, *, restart_input: bool = False, notify: bool = True) -> bool:
        """Apply and persist the current Free-D mirror immediately."""
        self._restore_freed_snapshot(copy.deepcopy(self._freed_draft))
        self._refresh_freed_mirror()
        self._save_config()
        if restart_input and not self.smoke_test:
            self._start_freed_input()
        if notify: self._notify_config()
        return True

    @Slot()
    def beginSetupEdit(self):
        """Refresh Setup controls from the current live auto-saved state."""
        self._refresh_setup_mirror()
        self._notify_config()

    @Slot()
    def beginFreeDEdit(self):
        """Refresh Free-D controls from the current live auto-saved state."""
        self._refresh_freed_mirror()
        self._notify_config()

    # Legacy slots retained for compatibility with old integrations. The current
    # UI has no Apply/Reset buttons because each edit already commits itself.
    @Slot()
    def applySetupSettings(self):
        self._commit_setup_draft()

    @Slot()
    def resetSetupSettings(self):
        self._refresh_setup_mirror(); self._notify_config()

    @Slot(str, result=str)
    def exportConfigFile(self, value):
        """Export the currently APPLIED full configuration to a transferable JSON file."""
        try:
            path = self._dialog_path(value)
            if not str(path): return ""
            if path.suffix.lower() != ".json":
                path = Path(str(path) + ".hvp2p.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            self._save_config(include_staged_freed=False)
            payload = json.loads(self._config_path.read_text(encoding="utf-8"))
            payload["_meta"] = {"format":"HV P2P SRVR Config", "version":self.version}
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self._log(f"[Config] exported: {path}")
            return str(path)
        except Exception as exc:
            self._log(f"[Config] export failed: {exc}")
            return ""

    @Slot(str, result=bool)
    def stageConfigFile(self, value):
        """Load, validate, immediately apply and persist a transferable config."""
        try:
            path = self._dialog_path(value)
            c = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(c, dict):
                raise ValueError("config root must be an object")
            c, migrated = self._migrate_config_dict(c)
            setup = self._setup_snapshot_from_config(c)
            freed = self._freed_snapshot_from_config(c)
            new_w1p_ip = self._normalise_ipv4(setup.get("w1p_ip", self.w1p_ip))
            new_ctrl_ip = self._normalise_ipv4(setup.get("ctrl_ip", self.ctrl_ip))
            if new_w1p_ip == new_ctrl_ip:
                raise ValueError("CTRL and W1P cannot use the same IP address")
            setup["w1p_ip"], setup["ctrl_ip"] = new_w1p_ip, new_ctrl_ip
            if new_w1p_ip != self.w1p_ip and not self._request_w1p_readdress(new_w1p_ip):
                raise ValueError("W1P local IP was not safely changed")
            self._restore_setup_snapshot(setup)
            self._apply_imported_run_config(c)
            self._restore_freed_snapshot(freed)
            self._refresh_setup_mirror()
            self._refresh_freed_mirror()
            self._pending_import_config = None
            self._pending_import_setup_handled = True
            self._pending_import_freed_handled = True
            self._save_config()
            if not self.smoke_test:
                self._start_freed_input()
            self._log(f"[Config] imported, applied and saved: {path}")
            self._notify_config()
            return True
        except Exception as exc:
            self._refresh_setup_mirror(); self._refresh_freed_mirror()
            self._log(f"[Config] transfer load failed: {exc}")
            self._notify_config()
            return False

    # Legacy internal save/load slots retained for compatibility. They operate on
    # the app's private config.json, not the transferable file-picker actions.
    @Slot()
    def saveConfig(self):
        self._save_config(include_staged_freed=False)
        self._saved_setup_snapshot = self._setup_snapshot()
        self._saved_freed_snapshot = self._freed_snapshot()
        self._setup_draft = copy.deepcopy(self._saved_setup_snapshot)
        self._freed_draft = copy.deepcopy(self._saved_freed_snapshot)
        self._setup_draft_dirty = False
        self._freed_draft_dirty = False
        self._log("[Config] configuration saved")
        self._notify_config()

    @Slot()
    def loadConfig(self):
        self._load_config()
        self._saved_setup_snapshot = self._setup_snapshot()
        self._saved_freed_snapshot = self._freed_snapshot()
        self._setup_draft = copy.deepcopy(self._saved_setup_snapshot)
        self._freed_draft = copy.deepcopy(self._saved_freed_snapshot)
        self._pending_import_config = None
        self._pending_import_setup_handled = True
        self._pending_import_freed_handled = True
        self._setup_draft_dirty = False
        self._freed_draft_dirty = False
        self.w1p.reconfigure(self.w1p_ip, self.w1p_port)
        if not self.smoke_test:
            self._sync_w1p_settings(); self._sync_service_mode_to_winch(force=True); self._start_freed_input()
        self._log("[Config] configuration loaded")
        self._notify_config()

    # Legacy live-edit slots retained for compatibility with older internal
    # callers/tests and external integrations. Current Setup QML uses setSetup*
    # methods, which auto-commit through the same persistent configuration.
    @Slot(float)
    def setJoystickDeadband(self, value):
        self.joystick_deadband_pct = max(0.0, min(25.0, float(value)))
        self._save_config(); self._notify_config()

    @Slot(str)
    def setPositionSource(self, value):
        self._apply_position_source_runtime(value, send_safety=not self.smoke_test)
        self._save_config(); self._notify_config()

    @Slot(int, str, float)
    def setDriveModeValue(self, index, key, value):
        i, key = int(index), str(key)
        allowed = {"max_speed_mps", "goto_speed_mps", "accel_mps2", "decel_mps2", "crossover_mps2", "stop_decel_mps2"}
        if i not in (0, 1) or key not in allowed:
            return
        v = max(0.01, float(value))
        self.drive_modes[i][key] = v
        if key == "max_speed_mps":
            self.drive_modes[i]["goto_speed_mps"] = min(float(self.drive_modes[i]["goto_speed_mps"]), v)
        elif key == "goto_speed_mps":
            self.drive_modes[i][key] = min(v, float(self.drive_modes[i]["max_speed_mps"]))
        if i == self.active_drive_mode:
            self._apply_active_drive_profile(sync=True)
        self._save_config(); self._notify_config()

    @Slot(str, int, str)
    def setAuxAssignment(self, which, index, value):
        i = int(index)
        if not 0 <= i < 5:
            return
        target = self.ctrl_aux_assignments if str(which).upper().startswith("CTRL") else self.w1p_aux_assignments
        target[i] = str(value)
        self._save_config(); self._notify_config()

    @Slot(str,str)
    def setSetupNetwork(self, which, value):
        key = "ctrl_ip" if str(which).upper().startswith("CTRL") else "w1p_ip"
        self._setup_draft[key] = str(value).strip()
        self._commit_setup_draft()

    @Slot(str,bool)
    def setSetupDirection(self, which, inverted):
        key = "reverse_joystick" if str(which).upper().startswith("CTRL") else "reverse_motor"
        self._setup_draft[key] = bool(inverted)
        self._commit_setup_draft()

    @Slot(float)
    def setSetupUnitsPerM(self, value):
        self._setup_draft["units_per_m"] = max(1.0, float(value))
        self._commit_setup_draft()

    @Slot(float)
    def setSetupJoystickDeadband(self, value):
        self._setup_draft["joystick_deadband_pct"] = max(0.0, min(25.0, float(value)))
        self._commit_setup_draft()

    @Slot(str)
    def setSetupPositionSource(self, value):
        self._setup_draft["position_source"] = self._normalise_position_source(value)
        self._commit_setup_draft()

    @Slot(int,str)
    def renameSetupDriveMode(self, index, name):
        i = int(index)
        if i in (0,1):
            self._setup_draft["drive_modes"][i]["name"] = str(name).strip() or f"Mode {i+1}"
            self._commit_setup_draft()

    @Slot(int,str,float)
    def setSetupDriveModeValue(self, index, key, value):
        i, key = int(index), str(key)
        allowed = {"max_speed_mps", "goto_speed_mps", "accel_mps2", "decel_mps2", "crossover_mps2", "stop_decel_mps2"}
        if i not in (0,1) or key not in allowed: return
        dm = self._setup_draft["drive_modes"][i]
        v = max(0.01, float(value))
        dm[key] = v
        if key == "max_speed_mps": dm["goto_speed_mps"] = min(float(dm["goto_speed_mps"]), v)
        elif key == "goto_speed_mps": dm[key] = min(v, float(dm["max_speed_mps"]))
        self._commit_setup_draft()

    @Slot(str)
    def setSetupAccelerationMode(self, mode):
        self._setup_draft["acceleration_mode"] = "Power" if str(mode).lower().startswith("power") else "Speed"
        self._commit_setup_draft()

    @Slot(bool)
    def setSetupBatteryChange(self, on):
        self._setup_draft["battery_change_mode"] = bool(on)
        self._commit_setup_draft()

    @Slot(str,int,str)
    def setSetupAuxAssignment(self, which, index, value):
        i = int(index)
        if not 0 <= i < 5: return
        key = "ctrl_aux_assignments" if str(which).upper().startswith("CTRL") else "w1p_aux_assignments"
        self._setup_draft[key][i] = str(value)
        self._commit_setup_draft()

    @Slot()
    def openJoystickCalibration(self):
        # The joystick must be moved to both endpoints, so hold winch output at
        # zero for the complete wizard and capture raw CTRL values only.
        self.calibration_open = False
        # If another service calibration was open programmatically, immediately
        # restore the W1P service-mode state before starting joystick capture.
        # Joystick calibration itself never enables service movement.
        self._sync_service_mode_to_winch(force=True)
        self._reset_joystick_centre_drift()
        self.joystick_calibration_open = True
        self._joystick_neutral_required = True
        self.joystick_calibration_step = 0
        self.joystick_calibration_title = "Set Joystick Left"
        self.joystick_calibration_error = ""
        self._joystick_cal_pending = {"left": None, "centre": None, "right": None}
        self._cancel_goto()
        self._send_velocity(0.0, force=True)
        self._log("[Calibration] Joystick calibration started")
        self.joystickCalibrationChanged.emit(); self.calibrationChanged.emit()

    @Slot()
    def cancelJoystickCalibration(self):
        self.joystick_calibration_open = False
        self.joystick_calibration_error = ""
        self._joystick_cal_pending = {"left": None, "centre": None, "right": None}
        self._joystick_neutral_required = True
        self._cancel_goto()
        self._send_velocity(0.0, force=True)
        self._log("[Calibration] Joystick calibration cancelled; saved calibration retained")
        self.joystickCalibrationChanged.emit(); self.calibrationChanged.emit(); self.stateChanged.emit()

    @Slot()
    def joystickCalibrationBack(self):
        if self.joystick_calibration_step > 0:
            self.joystick_calibration_step -= 1
        self.joystick_calibration_title = (
            "Set Joystick Left", "Set Joystick Centre", "Set Joystick Right"
        )[self.joystick_calibration_step]
        self.joystick_calibration_error = ""
        self.joystickCalibrationChanged.emit()

    def _joystick_calibration_next(self, raw_override=None):
        raw_source = self._ctrl_axis if raw_override is None else raw_override
        raw = max(-1.0, min(1.0, float(raw_source)))
        if self.joystick_calibration_step == 0:
            self._joystick_cal_pending["left"] = raw
            self.joystick_calibration_step = 1
            self.joystick_calibration_title = "Set Joystick Centre"
        elif self.joystick_calibration_step == 1:
            self._joystick_cal_pending["centre"] = raw
            self.joystick_calibration_step = 2
            self.joystick_calibration_title = "Set Joystick Right"
        else:
            self._joystick_cal_pending["right"] = raw
            left = float(self._joystick_cal_pending["left"])
            centre = float(self._joystick_cal_pending["centre"])
            right = float(self._joystick_cal_pending["right"])
            lspan, rspan = left-centre, right-centre
            if abs(lspan) < 0.05 or abs(rspan) < 0.05 or lspan*rspan >= 0.0:
                self.joystick_calibration_error = "Invalid calibration range. Left and Right must be on opposite sides of Centre."
                self._log("[Calibration] Joystick calibration rejected: invalid Left/Centre/Right range")
                self.joystickCalibrationChanged.emit()
                return
            self.joystick_calibration_error = ""
            self.joystick_calibration_open = False
            self._reset_joystick_centre_drift()
            # Completing the wizard is the commit point: make the captured range
            # live immediately and persist it, with no separate Setup Apply step.
            self._setup_draft["joystick_calibration"] = {"left":left, "centre":centre, "right":right}
            self._commit_setup_draft(notify=False)
            self._log(f"[Calibration] Joystick calibration saved L={left:.4f} C={centre:.4f} R={right:.4f}")
        self._cancel_goto()
        self._send_velocity(0.0, force=True)
        self.joystickCalibrationChanged.emit(); self.configChanged.emit()

    @Slot()
    def joystickCalibrationNext(self):
        self._joystick_calibration_next()

    @Slot(str,bool)
    def setFreeDEnabled(self, which, enabled):
        is_input = str(which).lower().startswith("in")
        key = "input_enabled" if is_input else "output_enabled"
        self._freed_draft[key] = bool(enabled)
        self._commit_freed_draft(restart_input=is_input)

    @Slot(str,str,str)
    def setFreeDNetwork(self, which, field, value):
        which, field = str(which).lower(), str(field).lower()
        restart_input = False
        try:
            if which.startswith("in"):
                if field == "ip": self._freed_draft["input_bind_ip"] = str(value).strip() or "0.0.0.0"
                elif field == "port": self._freed_draft["input_port"] = max(1, min(65535, int(float(value))))
                else: return
                restart_input = True
            else:
                if field == "ip": self._freed_draft["target_ip"] = str(value).strip()
                elif field == "port": self._freed_draft["target_port"] = max(1, min(65535, int(float(value))))
                elif field in ("fps","rate"): self._freed_draft["rate_hz"] = max(1.0, min(100.0, float(value)))
                else: return
        except Exception as exc:
            self._log(f"[Free-D] invalid {which} {field}: {value} ({exc})")
            self._refresh_freed_mirror(); self._notify_config(); return
        self._commit_freed_draft(restart_input=restart_input)

    @Slot(str,str,float)
    def setFreeDOffset(self, side, axis, value):
        if str(side).lower().startswith("in"):
            axis = str(axis).title()
            if axis not in ("Pan","Tilt","Roll"): return
            self._freed_draft["input_offsets"][axis] = float(value)
        else:
            axis = str(axis).upper()
            if axis not in ("X","Y","Z"): return
            self._freed_draft["output_offsets"][axis] = float(value)
        self._commit_freed_draft()

    @Slot(str,str,bool)
    def setFreeDInvert(self, side, axis, enabled):
        if str(side).lower().startswith("in"):
            axis = str(axis).title()
            if axis not in ("Pan","Tilt","Roll","Zoom","Focus"): return
            self._freed_draft["input_inverts"][axis] = bool(enabled)
        else:
            axis = str(axis).upper()
            if axis not in ("X","Y","Z"): return
            self._freed_draft["output_inverts"][axis] = bool(enabled)
        self._commit_freed_draft()

    @Slot(int,str,float)
    def setGeometryPoint(self, index, axis, value):
        i, axis = int(index), str(axis).lower()
        if not 0 <= i < 5 or axis not in ("x","y","z"): return
        if axis == "z" and i not in (0,4): return
        v = float(value)
        if axis == "x":
            span0, span1 = self._cable_span_bounds()
            v = max(span0, min(span1, v))
        self._freed_draft["geometry"][i][axis] = v
        self._commit_freed_draft()

    @Slot(str,float)
    def setWeightValue(self, which, value):
        which, v = str(which).lower(), max(0.0, float(value))
        if which.startswith("skate") or which.startswith("static"):
            self._freed_draft["skate_weight_kg"] = self._lb_to_kg(v) if self._freed_draft.get("skate_weight_unit") == "lbs" else v
        elif which.startswith("cable"):
            self._freed_draft["cable_weight_kg100m"] = self._lb_to_kg(v) if self._freed_draft.get("cable_weight_unit") == "lbs/100m" else v
        elif which.startswith("tension"):
            kg = self._lb_to_kg(v) if self._freed_draft.get("cable_tension_unit") == "lbs" else v
            self._freed_draft["cable_tension_kg"] = max(0.01, kg)
        else: return
        self._commit_freed_draft()

    @Slot(str,str)
    def setWeightUnit(self, which, unit):
        which, unit = str(which).lower(), str(unit)
        if which.startswith("skate") or which.startswith("static"):
            self._freed_draft["skate_weight_unit"] = "lbs" if unit.lower().startswith("lb") else "kg"
        elif which.startswith("cable"):
            self._freed_draft["cable_weight_unit"] = "lbs/100m" if unit.lower().startswith("lb") else "kg/100m"
        elif which.startswith("tension"):
            self._freed_draft["cable_tension_unit"] = "lbs" if unit.lower().startswith("lb") else "kg"
        else: return
        self._commit_freed_draft()

    @Slot(str)
    def setHighlineMode(self, mode):
        self._freed_draft["highline_mode"] = "Dual Highline" if str(mode).lower().startswith("dual") else "Single Highline"
        self._commit_freed_draft()

    @Slot(str,float)
    def setLensCalibration(self, which, value):
        key = str(which)
        if key in self._freed_draft["lens_cal"]:
            self._freed_draft["lens_cal"][key] = float(value)
            self._commit_freed_draft()

    # Legacy slots retained for compatibility; current Free-D UI auto-saves.
    @Slot()
    def applyFreeDSettings(self):
        self._commit_freed_draft(restart_input=True)

    @Slot()
    def resetFreeDSettings(self):
        self._refresh_freed_mirror(); self._notify_config()

    @Slot(result=str)
    def saveLog(self):
        try:
            log_dir = self._config_path.parent / "Logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / ("HV_P2P_SRVR_Log_" + time.strftime("%Y%m%d_%H%M%S") + ".txt")
            with self._lock:
                path.write_text("\n".join(self._logs) + "\n", encoding="utf-8")
            self._log(f"[SRVR] Log saved: {path}")
            return str(path)
        except Exception as exc:
            self._log(f"[SRVR] Log save failed: {exc}")
            return ""

    @Slot()
    def clearLog(self):
        with self._lock:
            self._logs.clear()
            self._log_entries.clear()
            self._log_revision += 1
        self.logChanged.emit()

    @Slot(str)
    def setLensType(self,t):
        t = str(t)
        if t in ("i16","u16","i24","u24"):
            self._freed_draft["lens_type"] = t
            self._commit_freed_draft()

    @Slot(str)
    def setLensScale(self,s):
        self._freed_draft["lens_scale_mode"] = self._normalise_lens_scale(s)
        self._commit_freed_draft()

    @Slot(str,float)
    def captureLens(self,which,value):
        key = str(which)
        if key in self._freed_draft["lens_cal"]:
            self._freed_draft["lens_cal"][key] = float(value)
            self._commit_freed_draft()

    def _send_srvr_offline(self):
        target = str(self.ctrl_ip or "").strip()
        if not target:
            return
        try:
            with self._ctrl_presence_tx_lock:
                for _ in range(3):
                    self._ctrl_display_sock.sendto(b"SRVR_OFFLINE\n", (target, SERVER_BIND_PORT))
        except Exception:
            pass

    @Slot()
    def shutdown(self):
        # Safety transmission is deliberately FIRST. Do not wait for config flush,
        # Qt teardown, queued W1P traffic or worker joins before commanding stop,
        # Servo Enable inhibit and telling CTRL that SRVR is offline.
        if self._stop_evt.is_set(): return
        try: self.w1p.emergency_stop()
        except Exception: pass
        # Stop the listener before the explicit offline datagrams so a heartbeat
        # already arriving during teardown cannot be ACKed after SRVR_OFFLINE.
        self._stop_evt.set(); self._freed_in_stop.set()
        try: self._send_srvr_offline()
        except Exception: pass
        try:
            if hasattr(self, "timer"):
                self.timer.stop()
        except Exception:
            pass
        self._stop_config_writer()
        self.w1p.close()
        try:
            if self._freed_in_sock: self._freed_in_sock.close()
            self._freed_sock.close()
            self._ctrl_display_sock.close()
        except Exception: pass
