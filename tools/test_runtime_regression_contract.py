#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B=(ROOT/'SRVR_GitHub_v26.10.05.04/backend.py').read_text()
C=(ROOT/'HV_P2P_CTRL_EDGEBOX_v26.10.05.04/HV_P2P_CTRL_EDGEBOX_v26.10.05.04.ino').read_text()
T=(ROOT/'HV_P2P_CTRL_TS_v26.10.05.04/HV_P2P_CTRL_TS_v26.10.05.04.ino').read_text()

# Cumulative HMI fault counters must retain their baseline; .03.02 accidentally
# zeroed them after every packet and generated a 4 Hz log/UI storm forever.
status_body = B[B.index('def _handle_ctrl_hmi_status'):B.index('def _joystick_min_cal_span')]
for bad in (
    'self._ctrl_ts_poll_timeouts = 0',
    'self._ctrl_ts_events_rejected = 0',
    'self._ctrl_ts_queue_drops = 0',
    'self._ctrl_ts_parser_crc = 0',
    'self._ctrl_ts_parser_resync = 0',
):
    assert bad not in status_body
assert '_ctrl_ts_diag_last_log_at' in B
assert '(now - self._ctrl_ts_diag_last_log_at) >= 2.0' in B
assert '[CTRL-TS RS485] ' in B
assert 'def _esp_reset_reason_name' in B and 'BROWNOUT' in B and 'TASK_WDT' in B

# Touch AUX edges are captured in the UDP listener thread and persisted in a
# queue, rather than relying on the Qt 25 ms timer sampling a short flag pulse.
assert 'self._ctrl_aux_events = queue.Queue(maxsize=32)' in B
assert 'self._ctrl_aux_events.put_nowait((aux_i, float(msg[1]), now))' in B
assert 'aux_event = self._ctrl_aux_events.get_nowait()' in B
assert 'if self.smoke_test:' in B

# Auto-save remains enabled, but expensive backup/file/directory fsync work is
# moved off the Qt UI thread and rapid edits coalesce to the latest snapshot.
assert 'target=self._config_write_worker' in B
assert 'self._queue_config_write(json.dumps(c, indent=2) + "\\n"' in B
assert 'self._config_write_queue = queue.Queue(maxsize=1)' in B
assert 'self._stop_config_writer()' in B

# QML invalidation cadence is decoupled from the safety/motion tick.
assert 'self.timer.setInterval(25)' in B
assert '>= 0.05' in B and 'self.stateChanged.emit()' in B

# Critical state changes get a compact priority path ahead of bulk telemetry.
assert 'buildHmiStatePacketFromSrvr' in C
assert 'g_hmiStatePacketPending' in C
assert 'if(g_hmiStatePacketPending && g_latestHmiStatePacket.length() && hmiNormalTxAllowed())' in C
assert 'line.startsWith("HMS1|")' in T
assert 'const bool state_only = line.startsWith("HMS1|")' in T

# SRVR presence rides every POLL, so a dead SRVR cannot remain latched "OK"
# merely because CTRL continues to poll the touchscreen while HMI1 is starved.
assert '"P1|srvr=%u"' in C
assert 'frame_bool_field(frame, "srvr", srvrHint)' in T
assert 'g_srvr_ok = srvrHint;' in T
assert 'boot_set_status("Waiting for SRVR")' in T


# A delayed EVENT must open a master-TX opportunity instead of triggering an
# immediate next POLL, and priority HMS1 must not be followed by a 900-byte HMI1
# in the same loop iteration.
assert 'g_lastHmiPollTxMs = millis();' in C
assert 'bool hmiPriorityPacketSent = false;' in C
assert 'if(!hmiPriorityPacketSent && !bulk_suppressed && (changed || keepalive_due) && hmiNormalTxAllowed())' in C

# Touch-originated AUX latches use the same 300 ms compatibility window as UDP
# AUX commands; the persistent SRVR listener queue is the authoritative edge hold.
for aux_i in range(5):
    assert f'g_virtualAuxUntil[{aux_i}] = millis() + 300' in C
assert 'g_virtualAuxUntil[0] = millis() + 120' not in C

print('RUNTIME_REGRESSION_CONTRACT_PASS')
