#!/usr/bin/env python3
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
CTRL = (ROOT/'HV_P2P_CTRL_EDGEBOX_v26.10.08.02'/'HV_P2P_CTRL_EDGEBOX_v26.10.08.02.ino').read_text()
TS = (ROOT/'HV_P2P_CTRL_TS_v26.10.08.02'/'HV_P2P_CTRL_TS_v26.10.08.02.ino').read_text()
W1P = (ROOT/'HV_P2P_W1P_EDGEBOX_v26.10.08.02'/'HV_P2P_W1P_EDGEBOX_v26.10.08.02.ino').read_text()
SRVR = (ROOT/'SRVR_GitHub_v26.10.08.02'/'backend.py').read_text()
RUNNER = (ROOT/'tools'/'run_all_source_checks.py').read_text()

# Locked source cadences: do not accelerate the Leadshine feedback/safety loop or bulk HMI traffic.
assert 'static const uint32_t MODBUS_POLL_MS = 100;' in W1P
assert 'static const uint32_t W1P_STATUS_INTERVAL_MS = 50;' in W1P
assert 'HMI_DISPLAY_MIN_CHANGE_INTERVAL_S = 0.10' in SRVR
assert '#define DISPLAY_FORWARD_MIN_MS 250' in CTRL
assert '#define HMI_MOTION_MIN_MS          80' in CTRL
assert 'delay(20);' in TS
assert '(now - g_progress_service_ms) < 16' in TS

# Dedicated position path: 20 Hz source staging, tiny DMP1/HMP1 frame, proven bound UDP/5000 route.
assert 'CTRL_MARKER_MIN_CHANGE_INTERVAL_S = 0.05' in SRVR
assert 'DMP1|pos_frac={pos_frac:.6f}|speed_mps={float(self.current_speed_mps):.3f}' in SRVR
assert '_stage_ctrl_marker_datagram(packet, target)' in SRVR
assert 'self._flush_ctrl_marker_datagram(sock)' in SRVR
assert 'self._send_controller_marker_packet(); self._send_controller_display_packet()' in SRVR
assert 'if(line.startsWith("DMP1|"))' in CTRL
assert 'nextMarker.replace("DMP1|", "HMP1|")' in CTRL
assert '#define HMI_MARKER_MIN_MS          50' in CTRL
assert 'line.startsWith("HMP1|")' in TS

# Display-only means the marker packet must not become a SRVR liveness/status authority.
dmp_block = CTRL.split('if(line.startsWith("DMP1|")) {',1)[1].split('if(line.startsWith("DSP1|")) {',1)[0]
assert 'srvrOnline = true' not in dmp_block
assert 'g_lastSrvrRxMs' not in dmp_block
assert 'applySrvrFirmwareBeacon' not in dmp_block

# HMP sends use the same framing/half-duplex guards, but cannot postpone POLL/EVENT service.
marker_send = CTRL.split('static bool hmiSendMarkerText',1)[1].split('static bool hmiSendFirmwareStatusText',1)[0]
assert 'hmiNormalTxAllowed()' in marker_send
assert 'hmiMasterTurnaroundGuard()' in marker_send
assert 'HVP2PRS485::sendText' in marker_send
assert 'g_lastHmiPollTxMs = millis()' not in marker_send
normal_send = CTRL.split('static bool hmiSendText(const String &line)',2)[-1].split('static bool hmiSendMarkerText',1)[0]
assert 'g_lastHmiPollTxMs = millis()' in normal_send
assert CTRL.index('g_hmiMarkerPacketPending') < len(CTRL)

# Interpolation remains verified-sample only: no extrapolation, duplicates do not restart,
# 20 Hz samples are accepted, and the target is reached slightly before the next expected sample.
assert 'fabsf(next_frac - g_motion_sample_frac) < 0.0000005f' in TS
assert 'constrain(sample_interval_ms, (uint32_t)35, (uint32_t)180)' in TS
assert '(sample_interval_ms * 9U) / 10U' in TS
assert '(uint32_t)40, (uint32_t)150' in TS
assert 'g_motion_sample_frac - g_progress_segment_start_frac' in TS
assert 'constrain(float(elapsed) / float(duration), 0.0f, 1.0f)' in TS
assert 'next_frac = g_progress_segment_start_frac' in TS  # monotonic clamp in measured direction
assert 'g_last_marker_packet_ms' in TS
assert '(marker_now - g_last_marker_packet_ms) > 500U' in TS

# Conservative HMP wire budget at 115200 8N1, including 14-byte frame overhead + 2.5 ms guard.
# This is an upper bound for the planned ASCII payload, not an average packet length.
max_payload = len('HMP1|pos_frac=1.000000|speed_mps=-100.000')
wire_bytes = max_payload + 14
wire_s = wire_bytes * 10.0 / 115200.0
transaction_s = wire_s + 0.0025
marker_bus_fraction_20hz = transaction_s * 20.0
assert marker_bus_fraction_20hz < 0.16, marker_bus_fraction_20hz

assert 'test_ctrl_ts_marker_smoothness_0611.py' in RUNNER
print(f'CTRL_TS_MARKER_SMOOTHNESS_0611_PASS marker20hz_bus_upper={marker_bus_fraction_20hz*100:.1f}%')
