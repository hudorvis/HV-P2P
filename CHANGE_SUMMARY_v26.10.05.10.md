# HV P2P v26.10.05.10 change summary

Date: 2026-10-05

Authoritative lineage: `v26.10.05.09` (itself rebuilt from the supplied authoritative `v26.10.05.06`) -> `v26.10.05.10`.

## Bench fixes in this revision

### 1. Limit Calibration current position now re-zeros at staged Near

Root cause: `.05.09` correctly staged Near/Far/Ref transactionally, but the `cal_pos` field sent to CTRL-TS still came directly from `state.pos_m`, which retained the previous live coordinate until the final Ref commit. Capturing Near therefore showed `Near = 0.00 m` while Current Winch Position could remain at an old value such as `9.51 m`.

Fix: a dedicated Limit Calibration display coordinate now uses the staged Near capture as a temporary zero. On hardware it prefers raw encoder delta divided by Units/m; in Virtual mode or when raw data is unavailable it uses the staged position delta. This coordinate is presentation-only and does not alter the existing live calibration until Ref is committed. The SRVR Limit Calibration popup and CTRL-TS use the same value.

### 2. Run -> Shortcuts -> System controls fit inside the panel

Root cause: five 32 px System rows plus 5 px inter-row spacing exceeded the vertical area remaining below the Shortcuts heading and tabs by about 8 px. The Limits controls use 31 px rows and tighter spacing, so they did not overflow.

Fix: all System rows now use the same 31 px control height as the Limits Save/Recall/Slip rows, with 2 px vertical spacing. Button/field components, colours, typography and horizontal layout remain unchanged.

### 3. CTRL-TS `Practice Mode` AUX value no longer truncates

Root cause: the touchscreen tile itself had sufficient width. SRVR truncated every AUX action/value field with `_display_field(..., 24)` before transmission. `Drive Mode | Practice Mode` is 26 characters, so the received value was already `Practice Mo`.

Fix: AUX fields use a bounded 40-character display-field limit. The existing delimiter-safe ` / ` wire representation, CTRL forwarding and CTRL-TS tile layout remain unchanged.

## Preserved `.05.09` fixes

The firmware reboot convergence, CTRL-TS Near/Far/preset layout, Settings `Link` wording, calibration `-` placeholders and Cancel/rollback transaction, validate-before-commit W1P STATUS arbitration, macOS background liveness, calibration motion reliability, single-flight CTRL↔CTRL-TS RS485 transport and safe headless touchscreen updater are preserved.

W1P's independent 500 ms VEL freshness watchdog and the normal ~150 ms SRVR non-zero VEL refresh remain unchanged. No Leadshine velocity-control, AI0/AI1, predictive-stop, dynamic soft-limit or hard-limit logic is changed in this revision.

## Verification

The source/static/regression/preflight suite passes, including 370 EdgeBox integration checks, all previous bench regressions and new `.05.10` coverage. Native Arduino and frozen desktop compilation remain GitHub Actions gates; no local firmware binaries are included.
