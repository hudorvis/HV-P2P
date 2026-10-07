# HV P2P v26.10.06.11 change summary

Date: 2026-10-06

Locked baseline: `v26.10.06.10`.

This revision changes only the CTRL-TS cable-position/progress display path plus directly related tests and release identity. W1P motion/control, Leadshine polling, safety/watchdogs, calibration, AUX behavior, firmware authority/updater, UI layout, ramp/limit states and all other approved behavior remain locked.

## Root cause and measured baseline rates

The CTRL-TS renderer was already capable of local interpolation, but the position it was given was effectively only a ~10 Hz sample stream. In addition, slower bulk `HMI1` packets could call the same interpolation update with the same target and restart a segment without adding any new verified position information.

Measured from the source:

- W1P healthy Leadshine feedback block: `MODBUS_POLL_MS = 100` -> 10 Hz genuinely new hardware position/velocity feedback.
- W1P STATUS datagram: `W1P_STATUS_INTERVAL_MS = 50` -> up to 20 Hz, but hardware position inside it only changes at the 10 Hz feedback poll.
- SRVR main timer / Virtual position state: 25 ms -> 40 Hz.
- SRVR desktop `stateChanged`: 50 ms -> 20 Hz Side/Top View presentation.
- SRVR full `DSP1`: 100 ms minimum change interval -> 10 Hz.
- CTRL `HMM1`: 80 ms minimum gate, but normally source-limited by 10 Hz DSP1.
- CTRL bulk `HMI1`: 250 ms minimum -> 4 Hz.
- CTRL-TS smoothing service: 16 ms gate, with the locked 20 ms main-loop delay -> approximately 50 Hz effective local rendering.

## Isolated correction

A dedicated marker-only stream was added rather than increasing the full DSP/HMI rate:

`SRVR DMP1 -> CTRL HMP1 -> CTRL-TS local interpolation`

It contains only canonical `pos_frac` and signed measured `speed_mps`, is change-driven, and is capped at 50 ms / 20 Hz. SRVR stages it through the same proven bound UDP/5000 controller-worker socket as the fixed DSP1 path.

In Encoder mode this does **not** manufacture new samples: genuinely new position remains limited by W1P's unchanged 100 ms Leadshine feedback poll. In Virtual mode SRVR has newer real simulated state every 25 ms, so the marker stream can provide verified position at 20 Hz, matching the desktop presentation cadence.

Full DSP1, HMI1 and HMM1 rates are unchanged.

## RS485 / half-duplex protection

CTRL forwards HMP1 using the existing framed RS485 protocol, compatibility gate, turnaround guard and single-owner bus rules. Unlike ordinary display TEXT frames, the tiny marker frame does not restart `g_lastHmiPollTxMs`; therefore the existing POLL/EVENT path can keep its normal priority and cadence.

State/geometry deltas remain ahead of the marker in the scheduler. Firmware transfer still exclusively owns the half-duplex bus while active, so marker traffic cannot compete with OTA blocks.

A conservative maximum HMP1 transaction at 115200 8N1, including 14 bytes of frame overhead and the existing 2.5 ms turnaround guard, consumes about 7.25 ms. At a continuous 20 Hz that is about 14.5% bus occupancy. Encoder mode is normally lower because unchanged position packets are not forwarded.

## Interpolation behavior

CTRL-TS continues to animate only toward already-received verified targets. It never extrapolates beyond the newest real sample.

Changes are limited to display timing:

- duplicate targets no longer restart an interpolation segment;
- observed sample intervals down to 35 ms are accepted, so a 20 Hz stream is handled naturally;
- segment duration converges to about 90% of observed sample spacing, bounded to 40–150 ms, so it reaches the verified target slightly before the expected next sample and holds rather than predicting ahead;
- the existing signed-speed direction clamp remains, preventing small opposite-direction encoder dither while moving;
- while HMP1 is live, slower HMM1/HMI1 copies are marker fallbacks only and cannot perturb the dedicated stream;
- the locked 20 ms touchscreen main loop remains unchanged, giving approximately 50 Hz marker rendering.

## Verification

A new `tools/test_ctrl_ts_marker_smoothness_0611.py` contract locks the source rates, marker-only transport, display-only authority boundary, poll priority, no-extrapolation interpolation rules and RS485 wire budget. It is included in `run_all_source_checks.py` alongside every historical updater, RS485, calibration, motion, safety and release contract.
