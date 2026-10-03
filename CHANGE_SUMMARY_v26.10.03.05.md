# HV P2P v26.10.03.05 change summary

Date: 2026-10-03

Authoritative lineage: `HV P2P v26.10.03.04 - GitHub Ready Source.zip` -> this `.03.05` whole-project communications audit.

## Why this revision exists

The `.03.04` bench cycle showed that improving the CTRL↔CTRL-TS collision scheduler alone was not enough. The complete SRVR↔CTRL↔CTRL-TS↔W1P audit found remaining reliability/latency issues at subsystem boundaries: runtime RS485 servicing could still wait behind LVGL, persistent W1P settings were one-shot UDP writes, SRVR was redundantly probing a W1P that already streams STATUS, W1P firmware progress was filtered before its parser, and W1P could autonomously clear its software Servo-Enable inhibit after E-stop/reconnect rather than waiting for SRVR's neutral-return interlock.

## CTRL ↔ CTRL-TS

- Preserves the single-flight half-duplex scheduler, 250 ms POLL response timeout, 300 ms late-response quiet period, ACK/retry-safe EVENT IDs, firmware-exclusive bus ownership and 4 Hz bulk HMI ceiling.
- Normal POLL cadence is 60 ms. This remains responsive for operator input while adding margin for the Waveshare/LVGL runtime.
- A successful normal TEXT/HMI transmission now restarts the POLL interval when the UART frame has fully drained. CTRL therefore does not immediately POLL a touchscreen that is still applying a ~900-byte display update.
- CTRL-TS drains/parses RS485 before entering the main LVGL critical section. POLL/EVENT response timing is no longer dependent on routine dashboard rendering.
- TEXT frames acquire the LVGL mutex only for their actual widget mutation; POLL responses leave the UART before any SRVR-health UI update.
- Idle EVENT responses are compact (`EV1|id=0|cmd=`). Full queue/CRC/resync/heap/min-heap/PSRAM diagnostics are still sent on every real event and at least once per second. This cuts repetitive RS485 occupancy without losing reset evidence.

## SRVR ↔ W1P settings reliability

- SRVR is now explicitly authoritative for persistent W1P configuration. W1P STATUS confirms settings; it no longer overwrites a newly selected SRVR span/limits/units value if a SET datagram was lost.
- Persistent settings use a convergent contract: SRVR marks changed settings pending, emits at most one SET command per paced opportunity, compares W1P STATUS feedback, and retries a mismatch after 350 ms until confirmed.
- Settings covered include Service Mode, motor reverse, units-per-metre, acceleration mode, accel/decel/crossover/stop-decel and span/Near/Far limits.
- SET traffic is separated from the real-time velocity path and paced at >=40 ms between setting writes, preventing a configuration burst from delaying VEL/STOP traffic.
- W1P's native 20 Hz STATUS remains authoritative live telemetry. SRVR's explicit STATUS probe is reduced from 20 Hz to 4 Hz because it is only needed for liveness/recovery.
- `FW_PROGRESS` is now admitted by the W1P receive thread so the existing SRVR firmware-progress parser can actually receive it.

## Safety ownership

- Clearing the W1P physical E-stop no longer clears the software Servo-Enable inhibit.
- Reconnecting SRVR no longer clears that inhibit either.
- Only SRVR's explicit `SW_SRVON 1`, after the existing neutral-return/safety checks, may restore software Servo Enable.
- The independent W1P 500 ms velocity freshness watchdog, SRVR ~150 ms non-zero VEL refresh, hard limits, predictive stopping/dynamic soft limits, AI0/AI1 mapping and Leadshine velocity architecture are unchanged.

## SRVR responsiveness

- Config notifications are deferred/coalesced to the next Qt event-loop turn. A ComboBox callback can return and close before the wider config binding graph is invalidated.
- Changed DSP1 construction/transmission is capped at 10 Hz in SRVR while CTRL keeps bulk CTRL-TS forwarding at 4 Hz. Critical state still uses the compact priority HMS1 path.
- Existing asynchronous config persistence, hidden-page work gating, log throttling and cable-profile caches remain.

## User-input contract checked

- All QML backend references/callable actions resolve to implemented backend properties/slots.
- CTRL AUX1..AUX5 event IDs remain ACK/retry-safe; accepted events become 300 ms CTRL flags and are edge-captured by SRVR's UDP receiver thread.
- Joystick Calibration retains the event-time joystick sample so UI delay cannot alter Left/Centre/Right capture.
- Drive Mode, Acceleration Mode, Battery Change Mode and calibration AUX actions use the same SRVR setters as desktop controls, giving one state/persistence path regardless of input source.

## Verification

A new `test_end_to_end_comm_contract_0305.py` locks the revised transport, setting convergence, W1P firmware-progress admission, Servo-Enable ownership and preserved watchdog timing. Native Arduino and frozen desktop compilation remain GitHub Actions gates; physical RS485/CTRL-TS reset/Leadshine motion verification remains a bench gate.
