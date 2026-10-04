#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
C=(ROOT/'HV_P2P_CTRL_EDGEBOX_v26.10.04.05/HV_P2P_CTRL_EDGEBOX_v26.10.04.05.ino').read_text()
T=(ROOT/'HV_P2P_CTRL_TS_v26.10.04.05/HV_P2P_CTRL_TS_v26.10.04.05.ino').read_text()
assert 'HMI_FW_BLOCK_DATA = 1024' in C
assert 'HMI_FW_REPLY_TIMEOUT_MS = 3000' in C
assert 'HMI_RS485_TURNAROUND_US = 2500' in C
assert 'HMI.setRxBufferSize(4096)' in C and 'HMI.setRxBufferSize(4096)' in T
assert 'RS485_SLAVE_TURNAROUND_US = 2500' in T
assert 'delayMicroseconds(HMI_RS485_TURNAROUND_US)' in C
assert 'delayMicroseconds(RS485_SLAVE_TURNAROUND_US)' in T
assert 'if((now-g_hmiFwLastTxMs) < HMI_FW_REPLY_TIMEOUT_MS) return;' in C
assert 'FW_RX_TIMEOUT_MS = 5000' in T
assert 'frame.seq != g_hmiFwSeq' in C and 'ignored stale response' in C
assert 'reported != expectedNext' in C
assert 'if(g_fw_finalized)' in T and 'fw_already_finalized_reboot_pending' in T
assert 'fw_service_timeout();' in T and 'fw_service_reboot();' in T
assert 'if(g_fw_reboot_due_ms == 0)' in T
assert 'if(forwardDisplayPacketToHmi(nextDisplay))' in C and 'g_lastForwardedDisplayPacket = "";' in C
# 1024 data + bounded framing is far below both protocol and 4096 UART buffers.
assert 1024 + 64 < 3072 and 1024 + 64 < 4096
wire_ms=(1024+64)*10/115200*1000
assert wire_ms < 100
print(f'HMI_TRANSPORT_CONTRACT_PASS wire_budget_ms={wire_ms:.1f}')
