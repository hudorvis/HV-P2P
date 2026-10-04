#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
C=(ROOT/'HV_P2P_CTRL_EDGEBOX_v26.10.04.02/HV_P2P_CTRL_EDGEBOX_v26.10.04.02.ino').read_text()
T=(ROOT/'HV_P2P_CTRL_TS_v26.10.04.02/HV_P2P_CTRL_TS_v26.10.04.02.ino').read_text()

# Source contracts: single-flight POLL, explicit timeout, and bulk TX gate.
assert '#define HMI_POLL_RESPONSE_TIMEOUT_MS 250' in C
assert '#define HMI_POLL_RECOVERY_QUIET_MS 300' in C
assert '#define DISPLAY_FORWARD_MIN_MS 250' in C
assert '} else if(g_hmiPollOutstanding) {' in C
assert '(now - g_hmiPollStartedMs) >= HMI_POLL_RESPONSE_TIMEOUT_MS' in C
assert 'else if((now - g_lastHmiPollTxMs) >= HMI_POLL_INTERVAL_MS)' in C
assert 'return g_hmiCompatible && !hmiFwActive() && !g_hmiPollOutstanding && !hmiBusRecoveryQuiet();' in C
assert 'g_hmiBusQuietUntilMs = now + HMI_POLL_RECOVERY_QUIET_MS;' in C
assert '} else if(hmiBusRecoveryQuiet()) {' in C
assert 'if(!hmiPriorityStateSent && !bulk_suppressed && (changed || keepalive_due) && hmiNormalTxAllowed())' in C
assert 'if(hmiFwActive()) {' in C and 'Firmware transfer owns the half-duplex bus' in C

# Reliable EVENT contract: touchscreen retains event until explicit ACK and
# CTRL deduplicates a replayed event_id before acknowledging it again.
assert 'peek_hmi_event()' in T
assert 'ack_hmi_event(uint16_t eventId)' in T
assert 'frame.type == HVP2PRS485::ACK' in T
assert 'EV1|id=%u|drops=%lu|crc=%lu|resync=%lu|heap=%lu|minheap=%lu|psram=%lu|cmd=%s' in T
assert 'g_hmiHaveAcceptedEventId && eventId == g_hmiLastAcceptedEventId' in C
assert 'hmiAckEvent(frame.seq, eventId);' in C
assert 'payload.substring(cmdPos + 5)' in C  # preserves embedded pipes in CFG1 commands
assert 'pop_hmi_event' not in T
assert 'static String g_event_queue' not in T
assert 'char cmd[8];' in T and 'snprintf(cmd, sizeof(cmd), "AUX%u"' in T

# Minimal state-model regression for the failure that existed in .02.05.
class Master:
    def __init__(self):
        self.outstanding=False; self.seq=None; self.timeouts=0; self.executed=[]; self.last_event=None
    def poll(self, seq):
        if self.outstanding: return False
        self.outstanding=True; self.seq=seq; return True
    def display(self):
        return not self.outstanding
    def timeout(self):
        if self.outstanding:
            self.outstanding=False; self.seq=None; self.timeouts+=1
    def event(self, seq, event_id, cmd):
        if not self.outstanding or seq != self.seq: return 'reject'
        self.outstanding=False; self.seq=None
        if event_id and cmd and event_id != self.last_event:
            self.executed.append(cmd); self.last_event=event_id
        return 'ack'

m=Master()
assert m.poll(100)
assert not m.poll(101), 'a second POLL must never overwrite the outstanding sequence'
assert not m.display(), 'bulk display TX must be blocked during POLL/EVENT transaction'
assert m.event(99, 7, 'AUX1') == 'reject' and m.outstanding
assert m.event(100, 7, 'AUX1') == 'ack' and m.executed == ['AUX1']
# Lost ACK => slave resends same event on a later POLL; command executes once.
assert m.poll(101)
assert m.event(101, 7, 'AUX1') == 'ack' and m.executed == ['AUX1']
# Lost EVENT => timeout enters a master-silent recovery window before retry.
assert m.poll(102); m.timeout(); assert m.timeouts == 1 and not m.outstanding
assert m.poll(103); assert m.event(103, 8, 'AUX2') == 'ack'
assert m.executed == ['AUX1','AUX2']
print('HMI_BUS_SERIALIZATION_CONTRACT_PASS')

assert '(void)hmiSendFirmwareStatusText(msg);' in C
fw=C[C.index('static bool hmiSendFirmwareStatusText'):C.index('static void hmiAckEvent')]
for guard in ('hmiFwActive()', 'g_hmiPollOutstanding', 'hmiBusRecoveryQuiet()'):
    assert guard in fw  # firmware status may bypass compatibility, never bus ownership
