# HV P2P v26.10.06.11 deep code audit

Date: 2026-10-06
Baseline: `v26.10.06.10`

## Scope lock

The only production behavior changed is CTRL-TS cable-progress presentation. W1P/Leadshine motion feedback/control, velocity commands, watchdogs, limits, E-stop/safety arbitration, calibration, AUX actions, firmware authority/update sequencing and the approved UI layout remain unchanged.

## End-to-end position cadence

### W1P / hardware Encoder

Healthy Leadshine feedback is polled every 100 ms (`MODBUS_POLL_MS = 100`), so genuinely new hardware position and actual velocity are available at 10 Hz. W1P STATUS can be transmitted every 50 ms, but alternate STATUS packets cannot contain a newer encoder position if no feedback poll has occurred. Increasing this feedback poll was rejected for this revision because it would change the locked W1P/Leadshine control and safety traffic rather than only the display path.

### Virtual / SRVR

SRVR's Qt timer runs every 25 ms. Virtual motion advances its authoritative simulated position on that timer, so Virtual position state is available at 40 Hz. Desktop property notification is intentionally throttled to 50 ms, giving the Side/Top View approximately 20 Hz new presentation state.

### Baseline SRVR -> CTRL -> CTRL-TS

Full DSP1 is built/transmitted at a minimum 100 ms change interval (10 Hz). CTRL derives HMM1 from DSP1; its 80 ms gate is therefore normally source-limited to ~10 Hz. Full HMI1 remains limited to 250 ms (4 Hz). CTRL-TS's local marker service has a 16 ms guard but the locked main loop sleeps 20 ms, so the practical local renderer is approximately 50 Hz.

The baseline interpolation had a second presentation issue: both HMM1 and bulk HMI1 called `update_progress_marker()`. A slower duplicate HMI1 snapshot could therefore restart interpolation toward the same verified target, creating an irregular pause/hesitation without adding position information.

## v26.10.06.11 correction

SRVR now builds a tiny marker-only `DMP1` packet containing `pos_frac` and signed `speed_mps`. It is change-driven with a 50 ms minimum interval (20 Hz) and is staged through the same bound UDP/5000 controller-worker socket already used for the proven CTRL return path.

CTRL rewrites it to `HMP1` and forwards it with the existing framed RS485 transport. The packet is explicitly display-only: receiving DMP1 does not set SRVR online, refresh the SRVR liveness timer, apply firmware authority, change calibration/status, or enter the control path.

HMP1 has its own 50 ms gate. It obeys the existing compatibility, firmware-active, outstanding-POLL and recovery-quiet gates and the existing 2.5 ms master turnaround guard. Unlike ordinary display frames, HMP1 does not move the next-POLL timestamp. This prevents a 20 Hz marker stream from postponing the established ~60 ms POLL/EVENT service.

## Bandwidth / ownership

RS485 is 115200 baud 8N1. The frame adds 10 header bytes plus 4 CRC bytes. A conservative HMP1 payload (`HMP1|pos_frac=1.000000|speed_mps=-100.000`) is 43 bytes; including framing and the 2.5 ms guard, one transaction is about 7.25 ms. At 20 Hz the upper-bound marker occupancy is about 14.5%.

This does not change firmware transfer bandwidth: while CTRL-TS firmware transfer is active, firmware traffic owns the half-duplex bus and normal HMI frames, including HMP1, are blocked by the existing gate. State/geometry deltas remain higher priority than HMP1, and the master POLL is serviced before the normal transmit scheduler.

## Verified-only smoothing

CTRL-TS still never predicts beyond a received position. A new HMP1 target starts from the marker's current rendered location and ends at the latest verified `pos_frac` only. The renderer runs at its unchanged ~50 Hz loop rate.

Duplicate targets are ignored so HMM1/HMI1 keepalives cannot restart an existing segment. With HMP1 live, HMM1/HMI1 are retained only as a >500 ms compatibility fallback for marker data. Observed sample spacing accepts 35–180 ms; segment duration converges to 90% of that spacing and is bounded to 40–150 ms. The marker can therefore reach an already-known target shortly before the next expected sample and hold, but cannot extrapolate or overshoot. The previous signed measured-speed monotonic clamp remains in force while travel direction is clear.

## Expected effective behavior

- Encoder: new verified source samples remain ~10 Hz; local CTRL-TS motion is interpolated at ~50 Hz with cleaner timing and no duplicate resets.
- Virtual: new verified marker samples can reach CTRL-TS at up to 20 Hz; local rendering remains ~50 Hz, closely matching the SRVR Side/Top View response.
- Full numeric HMM1 readouts and all other HMI/status traffic retain their existing cadences.

## Verification

`test_ctrl_ts_marker_smoothness_0611.py` locks the unchanged W1P/DSP/HMI cadences, dedicated bound marker path, display-only authority boundary, POLL priority, no-extrapolation behavior and <16% marker bus budget. All historical source contracts remain in the complete regression runner.
