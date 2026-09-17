# HV P2P v26.09.17.02 Deep Code Audit

## Live evidence reviewed

Commissioning of v26.09.15.02 showed:

- CTRL could read CTRL-TS hardware/protocol/version via HELLO;
- SRVR therefore displayed matching Detected/Required versions;
- CTRL-TS still reported the bootstrap hash, so CTRL correctly attempted automatic RS485 convergence;
- CTRL-TS received `FW_BEGIN` and printed the expected version/size/SHA;
- CTRL then timed out waiting for the updater reply and retried;
- update progress remained at 0%;
- swapping A/B did not change the behavior.

This proves the basic physical RS485 path and polarity were not the primary fault. The defect was in updater transport robustness/timing.

## RS485 transport audit

The v26.09.15.02 design used firmware blocks larger than the default Arduino ESP32 UART RX buffer and relied on a much shorter turnaround interval than the real EdgeBox/Waveshare pair tolerated during updater traffic.

v26.09.17.02 now enforces:

- 4096-byte RX buffers on CTRL and CTRL-TS, allocated before UART begin;
- 1024-byte data blocks;
- 2500 us master and slave turnaround guards;
- 3000 ms CTRL response timeout;
- 5000 ms CTRL-TS active-transfer timeout;
- exclusive updater ownership of the half-duplex bus;
- exact sequence correlation;
- exact offset checking;
- idempotent duplicate-block and duplicate-final-result behavior;
- fail-closed wrong-target/protocol/version/downgrade handling;
- exact final size and SHA-256 verification before reboot;
- boot-time timeout/reboot servicing while the splash loop is still active.
- reconnect display delivery is transactional: a packet refused while CTRL-TS is incompatible is not cached as delivered, and compatibility restoration forces the current full HMI packet immediately.

Wire-time calculation: a 1024-byte block plus framing is approximately 90.5 ms at 115200 baud. This is well below the 3 s reply timeout and does not threaten the 4096-byte receiver capacity when the slave loop services the UART every ~50 ms.

## OTA/reboot audit

- `FW_BEGIN` restarts an incomplete receiver transaction safely from offset zero.
- A lost `FW_ACK` causes CTRL to resend the same block; CTRL-TS returns the already-advanced authoritative next offset without rewriting the block.
- `FW_END` is idempotent after successful verification, so a lost `FW_RESULT` cannot convert a completed update into failure.
- The reboot command is rejected unless the image has finalized successfully.
- Duplicate reboot requests do not extend the reboot deadline.
- Once finalized/reboot-pending, a new `FW_BEGIN` cannot erase the selected inactive partition.
- Identity metadata is committed transactionally per OTA partition. If metadata persistence fails, the running partition is restored as boot target.

## Splash audit

The previous splash path assumed direct rendering into an 800x480 canvas. The new implementation reads the JPEG dimensions, rotates portrait artwork for the landscape panel, computes an aspect-preserving contain fit, centers it, and maps all source pixels into bounded destination rectangles. Native 800x480 artwork retains a memcpy fast path.

`test_ctrl_ts_splash_contract.py` checks 800x480, 480x800, 1920x1080, 1080x1920, 1024x1024, 320x240 and 240x320 source geometries and verifies no mapped output is cropped outside the 800x480 canvas.

## Whole-project preservation audit

After revision-string normalization, production diffs from v26.09.15.02 are limited to CTRL and CTRL-TS sketches. W1P source, SRVR backend/runtime, firmware authority, Run QML, Setup QML, EdgeBox authority headers and shared RS485 framing remain byte-equivalent apart from revision paths/tokens where applicable.

Preservation guards continue to cover:

- locked Run/Main QML hash;
- locked Setup QML hash;
- W1P 650 ms VEL watchdog;
- W1P stopped/braked OTA gate;
- Servo Enable inhibition and E-stop protections;
- Power/Speed semantics;
- no automatic downgrade;
- SRVR firmware authority and CTRL-before-CTRL-TS sequencing.

## Validation status

Passing locally:

- release consistency;
- source-package hygiene;
- 335 EdgeBox integration checks;
- RS485 frame CRC/parser host contract;
- HMI firmware retry/idempotence contract;
- CTRL-TS RS485 transport contract;
- CTRL-TS splash contract;
- HMI target gate;
- embed/staged-header test;
- firmware-authority HTTP test;
- firmware-bundle builder test;
- 42/42 SRVR automatic OTA contract;
- 18/18 frozen firmware packaging contract;
- native build orchestration harness;
- backend regression;
- 69/69 build-pipeline validation;
- Modbus contract;
- SRVR wire contract;
- Speed-mode contract;
- Python syntax;
- SRVR project validation.

The all-in-one master wrapper completed successfully on the final v26.09.17.02 tree after the reconnect correction and printed `ALL_SOURCE_CHECKS_PASS`. GitHub Actions remains the authoritative native Arduino/macOS/Windows compile/frozen-runtime gate, followed by physical bench RS485/EL7/motion commissioning.
