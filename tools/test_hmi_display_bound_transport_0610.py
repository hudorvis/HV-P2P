#!/usr/bin/env python3
"""v26.10.06.10 regression: DSP1 must use the proven bound CTRL UDP path."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'SRVR_GitHub_v26.10.06.10' / 'backend.py'
src = BACKEND.read_text(encoding='utf-8')

# The display sender must stage/coalesce rather than send DSP1 through the
# independent unbound socket. That unbound path is retained only for lightweight
# presence/firmware/shutdown compatibility traffic.
assert 'def _stage_ctrl_display_datagram' in src
assert 'def _flush_ctrl_display_datagram' in src
send_start = src.index('    def _send_controller_display_packet')
send_end = src.index('    def _send_ctrl_firmware_beacon', send_start)
send_block = src[send_start:send_end]
assert 'self._stage_ctrl_display_datagram(packet, target)' in send_block
assert 'self._ctrl_display_sock.sendto(packet' not in send_block

# The controller worker owns UDP/5000 and must flush staged DSP1 from that same
# bound socket before returning to receive work. The short timeout bounds display
# handoff latency while heartbeat ACKs remain immediate in the same worker.
worker_start = src.index('    def _controller_worker')
worker_end = src.index('    @staticmethod\n    def _parse_control_packet', worker_start)
worker = src[worker_start:worker_end]
assert 'sock.bind(("0.0.0.0", SERVER_BIND_PORT))' in worker
assert 'sock.settimeout(0.025)' in worker
assert 'self._flush_ctrl_display_datagram(sock)' in worker
assert 'sock.sendto(bytes([HEARTBEAT_ACK]), addr)' in worker

flush_start = src.index('    def _flush_ctrl_display_datagram')
flush_end = src.index('    def _controller_worker', flush_start)
flush = src[flush_start:flush_end]
assert 'sock.sendto(payload, target)' in flush
assert 'self._ctrl_bound_display_pending = pending' in flush, 'failed send must retain latest DSP1 for retry'

# Keep the fallback semantics unchanged: if fresh DSP1 is genuinely absent CTRL
# may still present a neutral display, but .10 must fix the transport rather than
# altering fallback operator data or motion/safety behavior.
ctrl = (ROOT / 'HV_P2P_CTRL_EDGEBOX_v26.10.06.10' / 'HV_P2P_CTRL_EDGEBOX_v26.10.06.10.ino').read_text(encoding='utf-8')
assert 'static String buildFallbackDisplayPacket' in ctrl
for token in ('|aux1=AUX 1', '|aux5=AUX 5', '|max_mps=0.00', '|preset_names='):
    assert token in ctrl
assert 'FLAG_CTRL_HMI_FAULT' in ctrl

print('HMI_DISPLAY_BOUND_TRANSPORT_0610_PASS')
