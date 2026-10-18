# HV P2P v26.10.19.01 — focused encoder-feedback correction

**Source baseline:** approved v26.10.16.02. **Release date:** 19 October 2026.

## Confirmed root cause

1. SRVR `_sanity_accept_winch_position` used the constant **0.35 m per accepted packet** whenever `last_winch_output < 0.05`. Leadshine MotionStudio drives the motor independently, so `last_winch_output` stays zero even when the motor moves; a valid position delta at 500 RPM is roughly **0.393 m per 100 ms** with the supplied 10,000-count/revolution and 21,220.7-count/metre calibration. Once a packet was rejected, comparison to the last accepted position caused a self-perpetuating freeze. A dropped/delayed packet can also trip the threshold at lower RPM.
2. SRVR also rejected position readings farther than **0.5 m outside Near/Far**. On the default 100 m span, legitimate MotionStudio travel past 100.5 m was hidden, giving a second independent freeze mode. This was an incorrect presentation-layer constraint: the independent SRVR and W1P soft-limit motor-command gates must remain in place.
3. W1P combined Modbus P08.44/P08.45 as signed 32-bit, but subtracted successive signed values and converted them directly to metres. A signed wrap caused a false multi-billion-count velocity/position discontinuity. Calibration read raw signed counts, with the same discontinuity. Rollover is not expected during a typical 1,000 m run at the supplied units/metre, but is a genuine long-run and position-offset defect.

## Corrections

- **SRVR `backend.py` / `position_feedback.py`:** physical encoder-count/RPM-derived step envelope using W1P's elapsed Modbus sample time; no dependency on SRVR command, software speed limit, or Near/Far soft bounds; rejects nonfinite, physically implausible, stale, duplicated and out-of-order samples; allows recovery after telemetry interruptions, boot/session reset and explicit slip; calibrates only using accepted, integer-precision extended counts.
- **W1P EdgeBox:** extends encoder counts to a signed 64-bit accumulation using modulo-2^32 deltas; computes displayed position from double-precision intermediate calculations; uses wrap-safe deltas in drive speed and stopped/braked verification. Adds four optional `STATUS` fields: `RAW_POS_EXT`, `POS_SEQ`, `POS_T_MS`, and `POS_AGE_MS`. The original 32-bit `RAW_POS` and existing Modbus registers/protocol remain intact.
- **No new motion permissions:** calibrated bounds, W1P predictive motion-limit enforcement, safety E-stops, watchdog, DO0 brake, servo inhibit, and drive maximum RPM command ceiling remain unchanged.
- **Release integration:** coordinated version bump for SRVR, W1P, CTRL and CTRL-TS; desktop native staging includes `position_feedback.py`; macOS bundle metadata, GitHub workflows, source validators, checksums and release documents updated.

## Coverage and caveats

Host simulation exercises 125/250/500/2500 RPM, the permissive 3000 RPM telemetry-only ceiling, >1,100 m travel, wrap in both directions, Near/Far overshoot, invalid jumps and delayed/duplicated Modbus/UDP feedback. **2,500 RPM is the ceiling in the existing W1P firmware, not independent confirmation of the fitted motor's rating**. Motor nameplate, motor parameters and connected drive commissioning must be verified on the bench.

The existing 0–100% **progress fraction** intentionally saturates at calibrated endpoints (including CTRL-TS); raw position and signed distance readouts continue beyond them. Saturation is expected and is not a telemetry freeze. All approved UI layouts and ramp/preset/cable drawing geometry are retained.

The source-only package does not contain native ESP32 binaries or frozen SRVR executables. Physical motor feedback/Modbus timing, independent motion protections and OTA convergence still require native GitHub Actions and bench tests.
