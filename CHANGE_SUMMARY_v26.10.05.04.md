# HV P2P v26.10.05.04 change summary

Date: 2026-10-05

Authoritative lineage: `HV P2P v26.10.05.03 - GitHub Ready Source.zip` -> this bench-fix revision.

## Bench issues addressed

1. Existing Near/Far limits could briefly catch motion when entering Limit Calibration, requiring a joystick toggle before the skate could move beyond the old calibration envelope.
2. CTRL-TS calibration overlays did not mirror the useful SRVR readout layout.
3. A successfully flashed CTRL-TS could remain black if the final CTRL `REBOOT` command was lost after verification.
4. Operator-facing Current Speed could show a negative sign for reverse motion.
5. CTRL-TS travel bar did not use the full available panel width.
6. SRVR Run > Shortcuts needed full-width Acceleration/Battery rows and a three-choice calibration row.
7. SRVR Settings calibration buttons needed alphabetical Joystick / Limit / Winch ordering.
8. SRVR AUX assignment choices needed alphabetical non-preset actions while preserving preset action groups at the bottom.

## Corrections

- Limit/Winch calibration service override now sends an immediate priority `SERVICE_MODE` command to W1P, while retaining the existing STATUS-confirmed retry/convergence mechanism. This removes the transient old-limit catch without weakening normal limit protection.
- CTRL-TS Limit Calibration now shows three Near / Ref / Far value boxes plus a dedicated `Current Winch Position` row. Joystick Calibration now mirrors that layout with Left / Centre / Right plus `Current Joystick Position`.
- SRVR wizard wording uses the same Current Winch/Joystick Position terminology.
- After a verified CTRL-TS firmware image is finalized, the headless updater now schedules an autonomous reboot fallback after 2.5 s. CTRL's explicit `REBOOT` remains preferred and shortens the delay when received. A lost final command therefore cannot leave a successfully updated touchscreen black indefinitely.
- Operator-facing speed readouts use speed magnitude. Signed direction remains internal to motion control and is not changed.
- CTRL-TS Near/Far travel geometry now spans almost the full 800 px display width (8 px to 772 px within the 780 px content panel).
- SRVR Run > Shortcuts now uses full-width two-button rows for Acceleration and Battery Change, and three equal calibration buttons: Joystick Calibration / Limit Calibration / Winch Calibration.
- SRVR Settings calibration buttons are ordered Joystick / Limit / Winch.
- AUX assignment choices are alphabetical for non-preset actions; Preset Save / Recall / Slip groups remain at the bottom.

## Preserved safety/transport behavior

- W1P independent 500 ms VEL freshness watchdog is unchanged.
- SRVR non-zero VEL refresh remains approximately 150 ms.
- AI0 E-stop / AI1 joystick mapping, W1P DI0 E-stop, hard limits, predictive/dynamic soft limits and Leadshine velocity architecture are unchanged.
- CTRL-TS self-flash remains intentionally headless/display-off while writing flash; this revision only guarantees automatic return to the application after a verified image if the final CTRL reboot command is lost.
- Existing automatic firmware-convergence/coordinator behavior from `.05.03` is retained.

## Verification

Added `test_bench_regression_0504.py` and updated stale layout/order regressions to enforce the new calibration presentation and alphabetical option order. The complete source/preflight suite must pass from the final `.05.04` layout before release. GitHub Actions/native compilation remains authoritative.
