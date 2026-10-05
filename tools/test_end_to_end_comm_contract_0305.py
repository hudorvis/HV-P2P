#!/usr/bin/env python3
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.05.05'
B=(ROOT/f'SRVR_GitHub_v{VER}/backend.py').read_text()
C=(ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}/HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text()
T=(ROOT/f'HV_P2P_CTRL_TS_v{VER}/HV_P2P_CTRL_TS_v{VER}.ino').read_text()
W=(ROOT/f'HV_P2P_W1P_EDGEBOX_v{VER}/HV_P2P_W1P_EDGEBOX_v{VER}.ino').read_text()

# CTRL-TS runtime must service the half-duplex UART before taking the LVGL mutex.
loop=T[T.index('void loop(){'):]
assert loop.index('handle_hmi_rx();') < loop.index('lvgl_port_lock(-1);')
assert 'process_text_from_ctrl(line, false);' in T
assert 'const bool includeDiag = ev || !g_last_event_diag_ms || (now - g_last_event_diag_ms) >= 1000;' in T
assert 'snprintf(payload, sizeof(payload), "EV1|id=0|cmd=")' in T

# CTRL is still a one-transaction-at-a-time master. A completed normal TEXT TX
# deliberately postpones the next poll so the HMI can apply/render the frame.
assert '#define HMI_POLL_INTERVAL_MS 60' in C
send=C[C.index('static bool hmiSendText(const String &line)'):C.index('static void hmiAckEvent', C.index('static bool hmiSendText(const String &line)'))]
assert 'g_hmiPollOutstanding' in C and 'hmiNormalTxAllowed()' in send
assert 'g_lastHmiPollTxMs = millis();' in send
assert '#define HMI_POLL_RESPONSE_TIMEOUT_MS 250' in C
assert '#define HMI_POLL_RECOVERY_QUIET_MS 300' in C

# W1P telemetry already streams at 20 Hz; SRVR's active STATUS probe is only a
# liveness/recovery probe and must not double that traffic. Firmware progress is
# allowed through the receive filter to the parser that already handles it.
assert 'WINCH_PROBE_INTERVAL_S = 0.25' in B
assert '"FW_PROGRESS"' in B[B.index('class W1PClient'):B.index('class HVP2PBackend')]
assert 'if line.startswith("FW_PROGRESS|")' in B

# Persistent W1P settings are convergent/verified rather than a one-shot UDP burst.
for token in ('_w1p_reported_config', '_w1p_settings_pending', 'def _desired_w1p_settings',
              'def _service_w1p_setting_sync', 'def _update_w1p_reported_config'):
    assert token in B
sync=B[B.index('def _service_w1p_setting_sync'):B.index('@staticmethod\n    def _normalise_ipv4')]
assert 'at most one setting' in sync.lower()
assert 'self.w1p.send(cmd)' in sync
assert 'self._w1p_setting_retry_s = 0.35' in B
assert 'same_value_retry = self._w1p_setting_matches(key, last_value, want)' in B
assert 'self._w1p_setting_min_gap_s = 0.04' in B
# W1P-reported config confirms convergence; it must not overwrite SRVR authority.
parse=B[B.index('def _parse_w1p'):B.index('def _sanity_accept_winch_position')]
assert 'self.state.total_length_m = float(fields["SPAN_M"])' not in parse
assert 'self.state.near_limit.position_m = float(fields["NL"])' not in parse
assert 'self.state.far_limit.position_m = float(fields["FL"])' not in parse
assert 'self.winch_units_per_m = float(fields["UPM"])' not in parse
assert 'self._update_w1p_reported_config(fields)' in parse

# Configuration invalidation is deferred/coalesced so a ComboBox callback can
# close immediately rather than re-evaluating hidden pages synchronously.
notify=B[B.index('def _emit_config_changed'):B.index('# --- QML actions ---')]
assert 'QTimer.singleShot(0, self._emit_config_changed)' in notify
assert 'if self._config_notify_pending:' in notify
assert 'HMI_DISPLAY_MIN_CHANGE_INTERVAL_S = 0.10' in B
assert '< HMI_DISPLAY_MIN_CHANGE_INTERVAL_S' in B

# Clearing an E-stop or reconnecting SRVR may never autonomously restore Servo
# Enable. Only the explicit SW_SRVON 1 command is permitted to clear the inhibit.
assert 'requestSoftwareSrvonInhibit(false, "W1P_ESTOP_CLEAR")' not in W
assert 'requestSoftwareSrvonInhibit(false, "SRVR_HEARTBEAT_RESTORED")' not in W
assert 'requestSoftwareSrvonInhibit(false, "REMOTE_SW_SRVON_ON")' in W

# Preserve the independent real-time safety/watchdog architecture exactly.
assert 'static const uint32_t W1P_VEL_COMMAND_TIMEOUT_MS = 500;' in W
assert re.search(r'VEL_KEEPALIVE_S\s*=\s*0\.15', B)
assert '#define CONTROL_INTERVAL_MS   25' in C

print('END_TO_END_COMM_CONTRACT_0305_PASS')
