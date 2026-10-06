# HV P2P v26.10.06.03 native-build and bench checklist

## GitHub build gate

1. Run the full GitHub Actions workflow from the `.06.03` source ZIP.
2. Confirm CTRL-TS, CTRL and W1P native firmware compilation succeeds.
3. Confirm macOS Intel, macOS Apple Silicon and Windows SRVR jobs pass their source/runtime/frozen smoke tests.
4. Confirm the complete release artifact contains matched `.06.03` firmware and SRVR bundles.

## Automatic-update bench test — no manual reboot

Start with CTRL, W1P and CTRL-TS on the previous release and the system stationary/safe.

1. Launch the GitHub-built `.06.03` SRVR.
2. Do **not** manually reboot any ESP32.
3. Confirm CTRL update starts automatically. If the normal node-pull path is missed, the SRVR fallback should start after the bounded grace without a reboot.
4. Confirm W1P is attempted second. If W1P is physically healthy it should converge before CTRL-TS.
5. Confirm CTRL-TS is attempted last and does not remain `Waiting` indefinitely.
6. If W1P is deliberately made unable to enter safe idle, verify CTRL-TS remains waiting during the 30 s ordered W1P recovery window, then proceeds automatically while W1P remains fail-closed.
7. Confirm CTRL-TS goes black only for its own headless self-flash and autonomously reboots to `.06.03`.
8. Confirm all three nodes report the exact `.06.03` release once their individual updates have converged.

## Regression checks from `.06.02`

- Long Limit Calibration travel remains continuous without spurious VEL-watchdog stops under normal fresh CTRL input.
- W1P 500 ms independent VEL watchdog remains unchanged.
- Run/System calibration captions remain `Joystick`, `Limit`, `Winch`.
- Settings AUX Assign keeps `None` first.
- CTRL-TS progress marker remains smooth while numeric position remains verified telemetry.
- Run/System layout remains aligned to the other Shortcut tabs.

## Safety checks

- Real CTRL/W1P/Leadshine/E-stop faults still take priority over calibration/update presentation.
- A W1P that has not matched the current SRVR image must remain fail-closed for motion even if the independent CTRL-TS final stage is released after the bounded wait.
- Verify joystick neutral is still required after a genuine safety interruption.
- Verify software/hard limits and Battery Change behavior remain unchanged.

GitHub Actions/native compilation is authoritative. Do not substitute locally fabricated firmware binaries.
