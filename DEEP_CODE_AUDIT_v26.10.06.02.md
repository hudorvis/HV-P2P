# HV P2P v26.10.06.02 deep code audit

Date: 2026-10-06

## Scope lock

`v26.10.06.01` is the locked baseline. The audit was limited to the five requested fixes. A normalized production diff confirms only SRVR `backend.py`, Run `Main.qml`, Settings `SetupPage.qml`, and CTRL-TS firmware contain functional changes. CTRL and W1P production firmware are unchanged except for the release version token.

## Finding 1 — Limit Calibration stop / neutral-return sequence

The reported need to return the joystick to zero is not caused by the calibration distance itself. SRVR's service-mode path bypasses the normal calibrated Near/Far envelope while a Limit/Winch calibration wizard is active. The return-to-neutral requirement is asserted after a safety interruption.

The audited command path is:

1. Qt `_motion_tick()` computes the requested VEL.
2. Normal non-zero VEL is emitted about every 150 ms.
3. A background W1P worker may repeat the current VEL at 180 ms if the Qt producer briefly misses its cadence.
4. Before `.06.02`, that worker lease expired 220 ms after the last Qt motion decision.
5. W1P independently trips its unchanged `W1P_VEL_COMMAND_TIMEOUT_MS = 500` if command traffic then remains stale.
6. SRVR correctly reacts to that safety transition with STOP and subsequently requires physical joystick neutral before re-arm.

A long Qt scheduling pause therefore had a concrete route to the exact reported symptom even though network/status traffic continued.

### `.06.02` correction

The CTRL UDP receive thread, which is independent of Qt rendering, may renew only the existing VEL bridge lease. It does not calculate or change velocity. Renewal is permitted only when the fresh physical joystick sample is coherent with the sample used for the active command (tolerance 0.035) and no CTRL E-stop/ADC/HMI/firmware safety flag is present. A changed stick or unsafe flag clears the bridge state.

No watchdog or keepalive timeout is extended. W1P's 500 ms watchdog remains independent. This also means a lost CTRL stream cannot perpetuate motion.

A historical stop cannot be attributed with absolute certainty without the contemporaneous W1P/SRVR log, so the release notes do not claim the old 15 m/17 m locations were themselves special. The code contains no such service-mode distance stop.

## Finding 2 — System calibration labels

The Run/System tab used long calibration action names even though the backend methods are already unambiguous. Only the three visible button captions are shortened to `Joystick`, `Limit`, `Winch`; action methods and AUX assignment semantics are unchanged.

## Finding 3 — AUX `None` ordering

`SetupPage.qml` used a static shared `auxChoices` list with `None` after the calibration entries. Moving the same string to index zero changes presentation order only; stored assignment values and backend action decoding are unchanged.

## Finding 4 — CTRL-TS marker cadence

The compact HMM1 packet remains intentionally around 10 Hz to protect the 115200-baud half-duplex RS485 budget. The prior 90 ms LVGL animation restarted at each sample, which can look stepped at high line speed.

`.06.02` keeps authoritative telemetry and the wire rate unchanged. CTRL-TS caches the latest verified `pos_frac` plus signed measured `speed_mps`, then services only the graphical marker from its local UI loop. Prediction is capped at 180 ms and clamped to the verified Near/Far fraction range. Every HMM1 sample re-anchors the target. Numeric position remains `g_pos` from verified telemetry.

No interpolated value enters control, safety, limit or calibration calculations.

## Finding 5 — System shortcut grid mismatch

The System column used 31 px rows but retained 2 px column spacing, 7 px inner gaps and explicit 11 px overrides in the Drive Mode row. The neighbouring Preset/Limits controls use the standard component geometry. `.06.02` standardizes System to 31 px rows, 3 px row spacing, 5 px inner gaps and normal component fonts while retaining the approved 150 px label column and 70 px Mode buttons.

## Secondary regression review

Older static tests intentionally encoded the superseded 90 ms marker animation, old AUX list order and long System captions. Those assertions were updated to require the new requested behavior; unrelated assertions remain intact. SRVR preflight was similarly tightened to assert the new System grid and short captions rather than the superseded font override.

## Verification result

The full source runner passes. PySide6 and ESP32 native/frozen compilation are not available as local gates here and remain authoritative in GitHub Actions. Physical motion behavior, including the Limit Calibration long-travel test, remains a bench commissioning gate.
