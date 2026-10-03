# HV P2P v26.10.03.02 — CTRL ↔ CTRL-TS RS485 deep audit

Authoritative base: `HV P2P v26.10.02.05 - GitHub Ready Source.zip`.

## Confirmed .02.05 root causes

1. CTRL set `g_hmiPollOutstanding`, but did not test it before issuing the next 50 ms POLL. A delayed valid EVENT could therefore arrive after `g_hmiPollSeq` had been overwritten and be rejected as stale.
2. CTRL's display-forward path ran later in the same main-loop iteration and did not test the outstanding POLL state. CTRL could begin a large TEXT frame while CTRL-TS was entering its 2.5 ms turnaround and preparing the EVENT response to the preceding POLL. This was a genuine half-duplex collision window.
3. Normal POLL/EVENT traffic had no per-transaction response timeout; the 3 s HMI link timeout was only a link-health timeout.
4. CTRL-TS removed an event from its queue before successful delivery was proven. A corrupt, collided, delayed or rejected EVENT therefore permanently lost the AUX action.
5. Full display state could be sent every 100 ms. A roughly 900-byte packet consumes about 78 ms at 115200 8N1, leaving insufficient deterministic margin for POLL/EVENT, discovery, configuration and turnaround traffic.
6. CTRL-TS stored queued commands in dynamic `String` objects and created another dynamic `String` for the AUX command. This was unnecessary heap activity in the high-value operator input path.
7. Parser CRC/header/inter-byte failures were silently reset, which hid physical/protocol corruption from diagnostics.
8. Existing tests verified stale EVENT rejection but did not verify that the master scheduler prevented the stale condition or serialized the bus.

## v26.10.03.02 transport changes

- Normal HMI traffic is now single-flight. While `g_hmiPollOutstanding` is true, CTRL sends no POLL, HELLO or normal TEXT/display packet.
- `HMI_POLL_RESPONSE_TIMEOUT_MS` is 35 ms. A timed-out transaction is abandoned explicitly and counted before the bus can be reused.
- POLL cadence is 40 ms when idle; EVENT responses therefore get first opportunity and no sequence can be overwritten by another POLL.
- Full display forwarding is reduced from 100 ms minimum spacing to 250 ms (maximum 4 Hz when state is continuously changing). Existing changed-packet suppression and 3 s keepalive remain.
- CTRL-TS events now use a fixed-size queue containing a 16-bit event ID and fixed `char` payload. AUX1..AUX5 creation uses a fixed local buffer and no dynamic `String` allocation.
- CTRL-TS now **peeks** the queued event for a POLL and retains it until CTRL sends an explicit ACK containing the same event ID.
- If EVENT delivery or its ACK is lost, CTRL-TS resends the same event ID. CTRL deduplicates the replay, ACKs it again, and does not execute the AUX action twice.
- The event envelope places `cmd=` last and CTRL parses the remainder verbatim so commands containing pipe delimiters, including `CFG1|...`, are not truncated.
- CTRL-TS firmware transfer remains exclusive on the RS485 bus while active. Normal display/POLL traffic cannot run during it.
- CTRL's own firmware-authority progress display also uses the normal bus gate and can no longer pre-empt a pending POLL/EVENT exchange.
- Parser counters were added for CRC failures and resynchronisations.
- HMI diagnostics now include polls sent, poll timeouts, accepted/duplicate/rejected events, parser CRC/resync counters, total HMI TX, display TX, CTRL-TS queue drops, and CTRL-TS parser counters. SRVR logs increases in fault counters.
- CTRL-TS boot ID/reset reason reporting is retained unchanged so a genuine ESP32 reboot remains distinguishable from a bad/corrupt display update.

## Preserved safety/control architecture

No workaround was made in W1P. The independent 500 ms velocity freshness watchdog remains. SRVR non-zero velocity refresh remains ~150 ms. AI0 E-stop / AI1 joystick mapping, hard limits, predictive stopping/dynamic soft limits, Leadshine velocity architecture, firmware authority, E-stop protections and approved UI behaviour remain intact.

## Regression coverage added

`tools/test_hmi_bus_serialization_contract.py` explicitly proves:

- a second POLL cannot replace an outstanding POLL sequence;
- bulk display traffic is blocked during POLL/EVENT response time;
- a stale EVENT is rejected without releasing the current valid transaction;
- a lost ACK causes a duplicate EVENT to be ACKed but not re-executed;
- a lost EVENT is released only by explicit response timeout and can be retried on a later transaction;
- CTRL firmware-authority progress cannot bypass the same normal traffic gate;
- the CTRL-TS event queue is fixed-size and no longer uses `String` storage;
- embedded-pipe commands are preserved by the EVENT envelope.

Native Arduino compilation and binary staging remain GitHub Actions authority. No local firmware binary is fabricated by the source audit.
