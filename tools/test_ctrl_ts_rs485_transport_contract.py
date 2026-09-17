#!/usr/bin/env python3
"""Static/mathematical contract for the physical CTRL <-> CTRL-TS RS485 transport.

The bench failure in v26.09.15.02 showed that HELLO could work while the OTA
handshake stalled. This check protects the transport margins that matter on the
real EdgeBox/Waveshare pair without pretending to emulate the transceivers.
"""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
VER='26.09.17.02'
ctrl=(ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}'/f'HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text(errors='replace')
ts=(ROOT/f'HV_P2P_CTRL_TS_v{VER}'/f'HV_P2P_CTRL_TS_v{VER}.ino').read_text(errors='replace')
hdr=(ROOT/f'HV_P2P_CTRL_TS_v{VER}'/'HV_P2P_RS485_Frame.h').read_text(errors='replace')

def intval(src,name):
    m=re.search(rf'\b{name}\s*=\s*(\d+)',src)
    assert m, f'missing numeric constant {name}'
    return int(m.group(1))

baud=int(re.search(r'#define\s+HMI_BAUD\s+(\d+)',ctrl).group(1))
block=intval(ctrl,'HMI_FW_BLOCK_DATA')
ctrl_rx=intval(ctrl,'HMI_RX_BUFFER_BYTES')
ts_rx=intval(ts,'HMI_RX_BUFFER_BYTES')
master_us=intval(ctrl,'HMI_MASTER_TURNAROUND_US')
slave_us=intval(ts,'RS485_SLAVE_TURNAROUND_US')
reply_ms=intval(ctrl,'HMI_FW_REPLY_TIMEOUT_MS')
rx_timeout_ms=intval(ts,'FW_RX_TIMEOUT_MS')
max_payload=intval(hdr,'MAX_PAYLOAD')

assert baud == 115200
assert block == 1024, f'expected conservative 1024-byte OTA blocks, got {block}'
assert block + 4 <= max_payload, 'FW block plus offset exceeds frame payload bound'
# Wire frame = magic/header 10 + payload(offset+data) + crc 4.
wire_bytes=10 + 4 + block + 4
assert wire_bytes < ts_rx, 'one full OTA frame does not fit the Waveshare RX ring buffer'
assert ctrl_rx >= 4096 and ts_rx >= 4096
assert 2000 <= master_us <= 10000
assert 2000 <= slave_us <= 10000
assert 1500 <= reply_ms < rx_timeout_ms, 'master must retry before receiver abandons active OTA session'
# At 8N1, each byte occupies ~10 bits. A complete block should arrive well below
# the parser's 250ms inter-byte watchdog even if serviced in chunks.
wire_ms = wire_bytes * 10 * 1000 / baud
assert wire_ms < 120, f'OTA frame wire time unexpectedly high: {wire_ms:.1f}ms'
assert 'RX_INTERBYTE_TIMEOUT_MS = 250' in hdr
# The previous 50ms splash service cadence can accumulate ~576 wire bytes; the
# enlarged ring gives >7x that margin before the application drains it.
bytes_per_50ms = baud / 10 * 0.050
assert ts_rx > bytes_per_50ms * 7

# Pin contracts are verified against the two hardware-specific UARTs.
assert '#define HMI_UART_RX EDGEBOX_RS485_RX' in ctrl and '#define EDGEBOX_RS485_RX 18' in ctrl
assert '#define HMI_UART_TX EDGEBOX_RS485_TX' in ctrl and '#define EDGEBOX_RS485_TX 17' in ctrl
assert '#define EDGEBOX_RS485_RTS 8' in ctrl and 'UART_MODE_RS485_HALF_DUPLEX' in ctrl
assert '#define HMI_UART_RX 15' in ts and '#define HMI_UART_TX 16' in ts

# Buffer sizing must happen before begin() on both peers.
assert ctrl.index('HMI.setRxBufferSize(HMI_RX_BUFFER_BYTES)') < ctrl.index('HMI.begin(HMI_BAUD')
assert ts.index('HMI.setRxBufferSize(HMI_RX_BUFFER_BYTES)') < ts.index('HMI.begin(HMI_BAUD')

# Every slave response type used by OTA is routed through the guarded helper.
for tok in ('FW_READY','FW_ACK','FW_RESULT','ERROR_MSG'):
    assert f'fw_send_text(HVP2PRS485::{tok}' in ts, f'{tok} bypasses guarded firmware response helper'
assert 'fw_send_text(HVP2PRS485::ACK, frame.seq, "rebooting")' in ts
assert 'rs485_slave_turnaround_guard();\n  const bool sent = HVP2PRS485::sendText' in ts

# Firmware convergence happens inside setup()/splash, so service must not depend
# on loop() starting. The boot loop must service RX, OTA timeout, and OTA reboot.
boot=ts[ts.index('static void show_boot_splash()'):ts.index('static bool is_valid_hmi_packet')]
for tok in ('boot_service_uart();','fw_service_timeout();','fw_service_reboot();'):
    assert tok in boot, f'boot convergence omits {tok}'

# Master waits for each correlated response and inserts a quiet slot before the
# next request/block after receiving a reply.
for state in ('HMI_FW_WAIT_READY','HMI_FW_WAIT_BLOCK_ACK','HMI_FW_WAIT_RESULT'):
    assert state in ctrl
assert ctrl.count('hmiMasterTurnaroundGuard();') >= 4
assert 'frame.seq != g_hmiFwSeq' in ctrl
assert 'HMI_FW_WAIT_REBOOT_SETTLE' in ctrl and 'HMI_FW_REBOOT_SETTLE_MS = 2000' in ctrl
assert 'fw_reboot_pending' in ts and 'fw_downgrade_blocked' in ts

# Reconnect display state must track delivery, not attempted delivery. While the
# peer is incompatible hmiSendText() deliberately refuses normal display traffic;
# that refused packet must not be cached as already delivered or the first full
# HMI refresh can be delayed until the periodic keepalive.
assert 'static bool forwardDisplayPacketToHmi' in ctrl
assert 'return hmiSendText(line);' in ctrl
assert 'if(forwardDisplayPacketToHmi(nextDisplay)) {' in ctrl
refresh_block = ctrl[ctrl.index('if(match && !g_hmiCompatible) {'):ctrl.index('} else if(!match)', ctrl.index('if(match && !g_hmiCompatible) {'))]
for tok in ('g_lastForwardedDisplayPacket = "";','g_lastHmiDisplayKeepaliveMs = 0;','lastDisplayForward = 0;'):
    assert tok in refresh_block, f'reconnect path does not force immediate HMI refresh: {tok}'

print(f'CTRL_TS_RS485_TRANSPORT_PASS baud={baud} block={block} wire_ms={wire_ms:.1f} ctrl_rx={ctrl_rx} ts_rx={ts_rx} master_guard_us={master_us} slave_guard_us={slave_us}')
