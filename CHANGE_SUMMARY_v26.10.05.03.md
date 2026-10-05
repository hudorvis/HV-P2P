# HV P2P v26.10.05.03 change summary

Date: 2026-10-05

Authoritative lineage: `HV P2P v26.10.05.02 - GitHub Ready Source.zip` -> this firmware-convergence hotfix.

## Bench failure addressed

Real hardware showed that starting a newer SRVR did not reliably begin CTRL/CTRL-TS firmware convergence until CTRL/CTRL-TS were manually rebooted. After CTRL reached the new release, CTRL-TS could remain on the older release showing `Waiting for CTRL` and never begin its staged RS485 update.

## Root causes corrected

1. **CTRL-TS final-stage permission depended on DSP1 timing.** CTRL read `fw_ts_allowed` only from the latest display packet and normally attempted `hmiFwStart()` while processing a mismatch HELLO. The coordinator grant and the mismatch identity could therefore exist at different times and leave the peer waiting.
2. **Modern CTRL/W1P pull OTA had no bounded fallback.** If a proven older modern node did not enter its pull/update state after SRVR startup, SRVR continued waiting instead of using the already-proven `/update/app` path. A node reboot could recreate the timing needed to start convergence, explaining the bench dependency on manual reboot.

## Corrections

- `SRVR_FW` now carries a repeated `ts_allowed=0/1` firmware-coordinator grant independent of bulk display traffic.
- CTRL stores that grant as dedicated firmware state, invalidates it on a new SRVR session, and still accepts the mirrored DSP1 field for compatibility.
- CTRL records fresh CTRL-TS HELLO identity and can proactively start the staged transfer when a fresh safe-OTA-capable mismatched peer and the final-stage grant are both present; it no longer requires those events to coincide in one packet cycle.
- CTRL reports `ts_grant` in `HMI_STATUS` for diagnostics.
- SRVR remains pull-first for modern CTRL/W1P firmware. If an older modern node remains mismatched for 4 seconds and has not entered its own updating/rebooting state, SRVR asynchronously uploads the already SHA-verified authority image through the existing `/update/app` endpoint. This is a bounded fallback, not the primary update path.
- Update order remains **CTRL -> W1P -> CTRL-TS**. W1P is never started before CTRL is current/fresh, and CTRL-TS is not granted until W1P is current or the existing no-W1P discovery rule allows the final stage.

## Preserved behavior

- CTRL-TS actual self-flash remains the safe headless/display-off updater; SRVR is the exact progress display during that phase.
- No CTRL-TS UI, AUX, calibration, geometry or live-motion behavior was intentionally changed.
- W1P 500 ms velocity freshness watchdog, SRVR ~150 ms non-zero VEL refresh, E-stop/hard-limit protections, predictive stopping/dynamic limits and Leadshine velocity architecture are unchanged.

## Verification

Added `test_firmware_coordinator_0503.py` and updated earlier updater regressions to require the dedicated coordinator grant and bounded modern fallback. Native Arduino and frozen desktop compilation remain GitHub Actions gates; physical update sequencing remains a bench gate.
