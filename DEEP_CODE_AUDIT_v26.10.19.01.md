# HV P2P — source-to-screen encoder audit, v26.10.19.01

## Provenance and invariant locks

- Source base: user-supplied approved `HV P2P v26.10.16.02.zip`.
- Scope: SRVR position sanity and raw-count calibration, W1P Modbus feedback decoding/rollover/status freshness, minimum supporting test/build/release metadata. CTRL, CTRL-TS QML, safety wiring, I/O assignments and motion interlock pathways retain baseline behavior.
- `tools/validate_edgebox_integration.py` continues SHA-256 normalized-function locks for reviewed CRC, Modbus transport/write, W1P velocity command, predictive limits, motion watchdog, software SRV-ON inhibit, EdgeBox DO0 brake, local W1P AI0 E-stop and CTRL input paths. Four intentionally affected W1P functions are **re-baselined only for encoder-related edits**: `preserveDisplayedPositionForMotorDirectionChange`, `handleCommand` (SYNC_POS offset math), `sendStatusLine` (sample metadata) and `hvPrepareSafeServiceState` (rollover-safe stopped-braked velocity). Other protected hashes are unchanged.

## End-to-end path

| Hop | Reviewed function/behaviour | Outcome |
|---|---|---|
| Leadshine EL7 | P08.44 0x602C high, P08.45 0x602D low; P08.46/P08.47 I/O | Existing contiguous four-register Modbus read, CRC and native 115200 8N1 remain unchanged; device-specific verification still required |
| W1P Modbus | `modbusReadFeedbackBlock`; `serviceDriveFeedback` | 100 ms polling unchanged; new wrapped 64-bit counts and physical delta; DO2/SRDY, BRK-OFF and brake feedback preserved |
| W1P status UDP | `sendStatusLine` | 50 ms status cadence unchanged. Adds sample sequence/timestamp/age plus extended count; still emits `POS_M`, `RAW_POS`, `VEL_MPS` and all safety fields |
| SRVR UDP parser | `_parse_w1p` | Existing strict safety status validation preserved; uses optional new freshness/order/count metadata for positions only, with compatibility fallback when absent |
| SRVR sanity | `_sanity_accept_winch_position`, `position_feedback.position_step_allowed` | Tests physical encoder movement based on actual sample age, 10,000 counts/revolution, reported UPM and 3000 RPM validation allowance; no motion-command gating and no Near/Far telemetry clipping |
| Calibration | `_last_raw_pos` consumers | Validated `RAW_POS_EXT` integer used for captures/ramp and winch-cal delta calculations; reference still invalidated at W1P HELLO/power session |
| Free-D and QML | `state.pos_m`, `_span_fraction`, `toNear`, `toFar`, `SpanDiagram` | Original projection and measured-position wiring unchanged. Progress fraction remains within 0–1 by design; signed distances continue reporting actual out-of-range values |
| CTRL / CTRL-TS | DSP1 -> CTRL RS485 -> CTRL-TS | Existing 20 Hz status and marker-smoothing path retained; coordinated firmware release identities updated without other behavioral source changes |

## Technical details

At default `UPM = 21220.7`, encoder feedback is about 0.0491 / 0.0982 / 0.1964 / 0.9817 metres per **50 ms** at 125 / 250 / 500 / 2500 RPM, respectively. At 100 ms, 500 RPM already exceeds the old 0.35 m stationary threshold. A 125 RPM stream delayed four frames exceeds 0.35 m. The old fixed 0.5 m limit tolerance produces a separate 100.5 m stall on the supplied default 100 m calibrated span.

The new bound is `(3000 RPM × 10000 counts/rev ÷ 60 ÷ UPM) × elapsed_sample_seconds × 1.20 + 0.20 m`. Elapsed time is the W1P Modbus-sample timestamp modulo 2^32 milliseconds (monotonic host fallback for legacy status). Rejected position cannot mutate accepted calibration counts; out-of-order `POS_SEQ` cannot rewind position. The **3000 RPM figure is a telemetry validity margin**, not a changed operating limit or confirmed motor rating. The W1P command ceiling remains 2500 RPM.

Modulo signed encoder unwrap assumes less than 2^31 counts of absolute movement between consecutive successful polls, which is assured by the drive's maximum plausible RPM during normal operation. Crossing 32-bit boundaries is handled while W1P remains powered. A W1P power reboot invalidates its reference as before; a physical slip/calibration is required to recover absolute position across unknown movement during power loss. No unverified power-cycle persistence claim is made.

## Automated verification

- `python3 tools/test_encoder_position_feedback_101901.py`: executes source-extracted production SRVR method, tests steady 125, 250, 500, 2500 and 3000 RPM over >1,100 m, overshoot at both endpoints, invalid jump rejection/recovery, stale and duplicate/reordered packets, 1 s/7 s gaps, sequence/timestamp 32-bit rollover, session reset and nonfinite values. Compiles and runs actual W1P `wrappedPositionDelta`/`unwrapDrivePosition` with g++ for forward/reverse signed wrap.
- `python3 tools/run_all_source_checks.py`: complete hosted source/integration/transport/safety/OTA/encoder/release/static workflow validation. See `TEST_RESULTS_v26.10.19.01.txt` for actual results; no unconditional green result is claimed here.
- `tools/validate_edgebox_integration.py`: reviewed safety-critical implementation hash locks preserved except the four explicitly documented encoder-related updates.
- Native Arduino compilation, frozen Qt/Nuitka smoke, hardware serial timing and live motor/load tests cannot run from the source-only local environment and are GitHub Actions / bench gates.

## Remaining gates — no hardware movement clearance

1. Verify the actual fitted Leadshine motor model and its rated/maximum RPM and encoder scaling. The EL7-RS2000P drive supports multiple motor models; the hard-coded W1P `EL7_RATED_MAX_RPM=2500` is not a nameplate substitute.
2. Run pinned ESP32 3.3.8 Arduino CLI builds and host macOS Intel, macOS arm64, Windows x64 desktop builds with native smoke via the supplied GitHub Actions workflow. Do not treat a static CI workflow check as an executed cloud build.
3. Bench-check W1P genuine Modbus P08.44/P08.45 register order, pulse direction, 125/250/500/maximum RPM readback, maximum requested span and calibration at both ends. Compare MotionStudio raw values to W1P `RAW_POS_EXT` and SRVR position; verify Modbus delays, UDP reordering and an EL7 communication disconnect.
4. Prove local CTRL and W1P E-stops, 24 V holding-brake DO0 timing, software/physical travel stops, disconnected-controller/watchdog responses, power-cycle reference invalidation, auto-updating/recovery and CTRL-TS progress on physically isolated/safely restrained apparatus before field operation.
