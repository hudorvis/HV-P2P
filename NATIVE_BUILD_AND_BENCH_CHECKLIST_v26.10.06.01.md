# HV P2P v26.10.06.01 native-build and bench checklist

## 1. GitHub build gates

1. Replace the repository contents with this complete source tree.
2. Run the normal GitHub Actions workflow.
3. In `Source/protocol regression suite`, require `BACKEND_TEST_DOUBLE_CONTRACT_0601_PASS`.
4. Require native firmware compilation/staging in the established order: CTRL-TS -> staged CTRL -> W1P.
5. Require the matched SRVR firmware-authority bundle to be generated from those GitHub-built images.
6. Require macOS Intel, macOS Apple Silicon and Windows desktop jobs/smoke tests to pass.
7. Specifically confirm `python -m tools.test_backend_logic` passes on every desktop runner; the prior `.05.11` `FakeW1P.firmware_snapshot` AttributeError must not recur.
8. Do not substitute locally fabricated firmware binaries.

## 2. Automatic update regression

Starting condition: CTRL/W1P/CTRL-TS running a supported older authority release.

1. Launch the GitHub-built `v26.10.06.01` SRVR normally. Do not reboot an ESP32 manually.
2. Confirm CTRL automatically detects and installs the release, then returns matched.
3. If W1P is connected, confirm W1P updates only after CTRL is matched and returns matched before the final touchscreen stage.
4. Confirm CTRL-TS starts only after the preceding stages, goes black/headless only during its own flash write, then autonomously reboots into `v26.10.06.01`.
5. Confirm final Setup firmware diagnostics show CTRL, W1P and CTRL-TS at the required release/matched state.

## 3. macOS background/update scheduling

Repeat the automatic update test with SRVR unfocused/behind another application.

Expected:

- CTRL remains connected;
- release discovery continues automatically;
- W1P order state advances from the network-thread STATUS/FW_PROGRESS snapshot;
- CTRL-TS receives its final-stage grant without window focus.

## 4. Same-version SRVR restart authority check

After all nodes are on `v26.10.06.01`:

1. Close and reopen the same SRVR build.
2. CTRL and W1P briefly re-verify the new authority session.
3. Exact current images return to matched without reflashing.
4. Motion remains fail-closed until normal firmware/safety gates are healthy.

## 5. CTRL-TS final reboot

- Verify image transfer reaches FW_RESULT success.
- Verify REBOOT ACK alone does not finish the CTRL transaction.
- Verify CTRL remains in reboot-confirmation/discovery until the new application identity is proven.
- Confirm autonomous fallback still restarts the verified image if the final REBOOT exchange is lost.

## 6. Preserved UI/calibration regression checks

- Limit Calibration: from a non-zero old position, capture Near and confirm Current Winch Position becomes 0.00 m; travel toward Far and verify Near-relative distance.
- Run -> Shortcuts -> System controls remain fully inside their panel and match the Limits control height/style.
- CTRL-TS displays `Drive Mode | Practice Mode` completely.
- Joystick/Limit Calibration uncaptured values show `-` and Cancel exits without partial commit.

## 7. Preserved safety checks

- W1P non-zero VEL freshness watchdog remains 500 ms.
- Normal SRVR non-zero VEL refresh remains approximately 150 ms.
- Genuine communication loss still stops motion and requires joystick neutral before re-arm.
- AI0 E-stop and AI1 joystick remain correctly mapped.
- Hard limits and predictive/dynamic stopping remain authoritative outside defined service/Battery Change exceptions.

## 8. Result capture if anything fails

Save the complete GitHub job log or bench serial log, including at least 20 seconds before and after the first unexpected state. For updater issues capture `FW`, `FW_MATCH`, `FW_AUTH`, W1P `FW_PROGRESS`, CTRL `HMI_STATUS`, CTRL-TS `boot_id/reset_reason`, and SRVR firmware progress/authority diagnostics.
