# HV P2P v26.10.05.08 deep code audit

Date: 2026-10-05

## Scope

Follow-up audit of the v26.10.05.07 GitHub native build failure, while preserving the full `.05.07` bench-fix set for updater reboot convergence, CTRL-TS layout/calibration, W1P status arbitration, macOS background liveness and calibration-motion reliability.

## GitHub failure boundary

The supplied GitHub Actions output proves the following sequence:

1. The native builder started with the pinned ESP32 3.3.8 / Waveshare environment.
2. CTRL-TS compilation ran and emitted warning-only diagnostics from the display libraries and several unused local symbols.
3. The pipeline proceeded into `HV_P2P_CTRL_EDGEBOX_v26.10.05.07` compilation.
4. CTRL itself reached global-scope unused-variable warnings.
5. `arduino-cli compile` then returned exit status 1, causing `native_build_firmware.py` to raise `CalledProcessError`.

The pasted Actions excerpt does **not** include the lower-level compiler/linker message that caused that final non-zero return, so this audit does not invent a linker-size, OOM or syntax diagnosis that is absent from the evidence.

The narrow build-path boundary is nevertheless clear: between successful native CTRL-TS compilation and CTRL compilation, the builder turns the complete HMI application into a generated carrier included in CTRL. `.05.07` did so as a multi-megabyte comma-separated `uint8_t` initializer in a header included by the main sketch. That produces millions of integer tokens in the primary translation unit and is avoidable compiler pressure.

## `.05.08` correction

`embed_ctrl_ts_firmware.py` now produces two staged files:

- a small `HV_P2P_CTRL_TS_Firmware_Image.h` containing hardware/protocol/version/SHA/size metadata plus an external declaration;
- `HV_P2P_CTRL_TS_Firmware_Image.cpp`, containing the exact binary bytes as concatenated escaped string literals.

The C++ carrier has one trailing string terminator, which is excluded by `HV_CTRL_TS_IMAGE_SIZE`; a `static_assert` requires the compiled object to equal native-image-size + 1. CTRL's existing block sender therefore still transmits only the exact native image length.

`verify_staged_hmi_header.py` reconstructs every generated `\\xNN` byte, checks the ESP image magic, exact byte count and SHA-256, and when given the native application compares the two byte-for-byte. The native build refuses a missing carrier source or a metadata header larger than 16 KiB before entering the CTRL compile.

## Build-path stress verification

A full-slot synthetic 0x380000-byte / 3.5 MiB image was passed through the new generator and verifier. The generated C++ translation unit then host-compiled successfully in approximately 0.26 s at roughly 68 MiB maximum RSS in this audit environment. This is not a substitute for the authoritative ESP32 GitHub build, but it verifies that the revised representation scales to the maximum supported CTRL-TS OTA image without the previous millions-of-integer-token parsing model.

A permanent `test_native_carrier_compile_0508.py` regression exercises a 1 MiB carrier during normal source checks.

## Preserved `.05.07` findings/fixes

### Final CTRL-TS reboot

A REBOOT ACK proves receipt only. CTRL retains the update transaction in `HMI_FW_WAIT_REBOOT_CONFIRM` until a HELLO shows a changed boot ID and exact required version/SHA. Bounded REBOOT enforcement and HELLO discovery continue while waiting, covering older safe-updater firmware that can ACK without autonomously restarting.

### CTRL-TS travel layout

The AUX row is slightly shorter and the travel panel taller. Near/Far readouts, REF, track/skate/ramp geometry and alternating preset label lanes occupy distinct vertical bands; Montserrat 10 remains the minimum operational font.

### Calibration

Uncaptured values use ASCII `-`. CTRL-TS emits `CAL_CANCEL`; CTRL carries the dedicated 16-bit event flag to SRVR. Limit Calibration stages Near/Far/Ref and pending motor direction without mutating the live valid calibration until the final Ref capture. Cancel sends STOP, requires joystick neutral before normal motion, exits service mode and discards the staged transaction without saving partial limits.

### False red state

A malformed/incomplete W1P STATUS no longer calls `_invalidate_w1p_status()` before validation. It is rejected and counted while the last complete safety snapshot remains authoritative until the normal freshness timeout. PONG likewise does not erase the last valid W1P safety state. Genuine stale status, W1P E-stop, drive/RS485 faults, firmware mismatch and watchdog faults remain safety-active.

### macOS background communications / random calibration stops

CTRL peer liveness is maintained by a dedicated 250 ms `SRVR_ALIVE` worker rather than solely by the Qt timer. The W1P networking thread can bridge a missed ordinary ~150 ms non-zero VEL refresh using a short 220 ms producer lease and ~180 ms bridge cadence. If the SRVR control producer actually stops renewing that lease, refresh stops and W1P's unchanged independent 500 ms watchdog still stops motion. This prevents a brief GUI scheduling stall from falsely tripping the neutral-return interlock during Limit Calibration while retaining the interlock for genuine safety interruptions.

## Safety conclusion

No `.05.08` change weakens the W1P watchdog, E-stop behavior, neutral-return requirement, hard limits, predictive stopping, servo/brake safety or RS485 serialization. `.05.08` is a native-build carrier representation correction layered on the full `.05.07` behavior set.
