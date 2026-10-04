# HV P2P v26.10.04.07 deep code audit

Date: 2026-10-04

## Trigger

GitHub macOS Intel imported the SRVR backend successfully, then failed `python -m tools.test_backend_logic` at the Limit Calibration assertion that still required `calibration_step == 3` after the Ref capture.

## Root cause

The `.04.06` backend is a three-step Limit Calibration state machine with zero-based steps 0/1/2. The third confirmation captures Ref and closes the wizard immediately. The failing regression still represented the previous four-stage flow by expecting step 3 and sending another `Done` confirmation.

This was a stale test, not a failure of the new Limit Calibration capture logic.

## Secondary hardening

The backend previously allowed `calibrationNext()` to be called even after `calibration_open` had become false. A delayed event could therefore enter the terminal branch again. `.04.07` adds a top-level closed-wizard guard and regression coverage proving an extra post-close confirmation cannot change the saved reference.

## Preserved architecture

- Limit Calibration remains exactly three steps: Near, Far, Ref & Done.
- Completion still forces Battery Change Mode Off and exits calibration/service ownership.
- W1P 500 ms VEL freshness watchdog is unchanged.
- SRVR non-zero VEL refresh, predictive limits, hard limits, E-stop and Leadshine velocity architecture are unchanged.
- CTRL/CTRL-TS RS485 scheduling and AUX delivery are unchanged.
- Approved SRVR/CTRL-TS UI layout is unchanged.
