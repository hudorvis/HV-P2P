# HV P2P v26.10.05.11 native-build and bench checklist

## 1. GitHub build gates

1. Replace the repository contents with this complete source tree.
2. Run the normal GitHub Actions workflow.
3. Require native firmware compilation/staging in the existing order: CTRL-TS -> staged CTRL -> W1P.
4. Require the matched SRVR firmware-authority bundle to be generated from those GitHub-built images.
5. Require macOS Intel, macOS Apple Silicon and Windows desktop jobs/smoke tests to pass.
6. Do not substitute locally fabricated firmware binaries.

## 2. Automatic update regression — primary `.05.11` proof

Starting condition: SRVR `.05.10` closed; CTRL/W1P/CTRL-TS running `.05.10` (or another supported older authority release).

1. Launch the GitHub-built `.05.11` SRVR normally. **Do not reboot any ESP32 manually.**
2. Confirm CTRL automatically detects `.05.11`, enters firmware authority update and reboots to `.05.11`.
3. If W1P is connected, confirm it updates only after CTRL has converged, while stopped/braked, and returns matched on `.05.11`.
4. Confirm CTRL-TS begins only after the required previous stages. Its display may show update preparation, then must intentionally go black/headless while writing flash.
5. Confirm CTRL-TS autonomously reboots and reports `.05.11`; no manual touchscreen reset/power-cycle is permitted for a pass.
6. Confirm final Setup/firmware diagnostics show CTRL, W1P and CTRL-TS at the required `.05.11` release/match state.

## 3. macOS background/update scheduling

Repeat the automatic update test while placing SRVR behind another application / leaving it unfocused during the discovery phase.

Expected:

- CTRL remains connected from background `SRVR_ALIVE` traffic.
- The release still begins automatically because `SRVR_FW` is also background-serviced.
- W1P order state continues to advance from the network-thread STATUS/FW_PROGRESS firmware snapshot, including while its OTA download pauses ordinary STATUS output.
- CTRL-TS receives the final-stage grant without requiring SRVR window focus.

## 4. Graceful close ordering

With the system connected and no update active:

1. Close SRVR normally.
2. Confirm W1P receives the immediate safety stop / Servo Enable inhibit path.
3. Confirm CTRL sees explicit SRVR offline and CTRL-TS immediately returns to Waiting/Splash.
4. Leave the nodes powered for several seconds and verify no late background firmware/presence packet makes CTRL-TS leave Waiting again.

## 5. Same-version SRVR restart authority check

After all nodes are on `.05.11`:

1. Close and reopen the same `.05.11` SRVR.
2. CTRL and W1P should briefly re-verify the new SRVR authority session fail-closed.
3. Exact `.05.11` images must return to matched without reflashing.
4. Motion must not resume until the normal firmware/safety gates are healthy.

## 6. CTRL-TS final reboot

- Verify image transfer reaches FW_RESULT success.
- Verify REBOOT ACK alone does not complete the CTRL transaction.
- Verify CTRL remains in reboot-confirmation/discovery until the new application identity is proven.
- Confirm autonomous fallback still restarts the verified image if the final REBOOT command/ACK is lost.

## 7. `.05.10` UI/calibration regression checks

- Limit Calibration: begin from a non-zero old position, capture Near and confirm Current Winch Position immediately becomes 0.00 m; travel toward Far and confirm it reports distance from the staged Near point.
- Run -> Shortcuts -> System: Power/Speed, Off/On, mode/calibration/preset controls must remain entirely inside the tab and match the Limits control height/style.
- CTRL-TS AUX: `Drive Mode | Practice Mode` must render completely, not `Practice Mo`.

## 8. Preserved safety checks

- W1P non-zero VEL freshness watchdog remains 500 ms.
- Normal SRVR non-zero VEL refresh remains ~150 ms.
- A genuine communication loss still stops motion and requires joystick neutral before re-arm.
- AI0 E-stop and AI1 joystick remain correctly mapped.
- Hard limits and predictive/dynamic stopping remain authoritative outside the defined service/Battery Change exceptions.
- Limit Calibration reduced service speed and transactional Cancel/rollback remain intact.

## 9. Result capture if anything fails

Save the complete GitHub job log or bench serial log, including at least 20 seconds before and after the first unexpected state. Useful firmware fields are `FW`, `FW_MATCH`, `FW_AUTH`, CTRL `HMI_STATUS`, CTRL-TS `boot_id/reset_reason`, and SRVR firmware progress/authority diagnostics.
