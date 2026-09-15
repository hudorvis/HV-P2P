# HV P2P v26.09.15.01 — One-Time Firmware Bootstrap and Future Automatic Convergence

## Purpose

v26.09.15.01 introduces the SRVR-authoritative firmware chain:

```text
SRVR
 ├── Ethernet OTA -> CTRL
 │                    └── RS485 OTA -> CTRL-TS
 └── Ethernet OTA -> W1P
```

CTRL and W1P need **one authority-aware bootstrap installation** before SRVR can update them automatically. CTRL-TS also needs a compatible one-time bootstrap so CTRL can use the existing RS485 version/hash updater. After that, normal release changes are delivered from the exact firmware bundle packaged with the matching SRVR build.

The first bootstrap is a commissioning/service operation. Keep the physical winch unable to move: motor power isolated where practical, local E-stop asserted/verified, requested velocity zero and brake engaged.

## 1. Obtain the authoritative build

Run `.github/workflows/complete-build.yml` from this source release. The firmware job must build in this order:

1. CTRL-TS;
2. embed that exact CTRL-TS application image/hash/version into staged CTRL source;
3. build final CTRL;
4. build W1P;
5. verify role/version/target/size/SHA-256;
6. create `SRVR_FIRMWARE_BUNDLE` from the exact final CTRL and W1P application binaries.

Use the resulting `HV-P2P-v26.09.15.01-Native-Firmware` artifact. Do not substitute an unrelated locally compiled binary for the SRVR firmware bundle.

The authoritative artifact contains `NATIVE_BUILD_MANIFEST.json`, `SHA256SUMS.txt`, `BINARIES/`, `STAGED_SOURCE/` and `SRVR_FIRMWARE_BUNDLE/`. Verify its hashes before installation.

## 2. One-time CTRL-TS Waveshare bootstrap

Use the v26.09.15.01 CTRL-TS source/build from the same native artifact. The GitHub build uses ESP32 Arduino core 3.3.8, the Waveshare ESP32-S3 16 MB/OPI-PSRAM configuration, and the checked-in dual-OTA `partitions.csv`.

For a full USB bootstrap, flash the device using the staged/source project and the same build settings used by CI rather than uploading only an application `.bin` to a blank or differently partitioned device. Confirm after reboot that CTRL-TS answers CTRL over RS485 as hardware `WS-ESP32S3-7`, protocol 1.

The bootstrap CTRL-TS may initially report a bootstrap/non-final image hash. That is acceptable: once CTRL itself has matched SRVR, CTRL's existing updater transfers the exact embedded CTRL-TS image and requires the post-reboot version/hash match before the HMI compatibility gate clears.

## 3. One-time W1P EdgeBox bootstrap

Install the v26.09.15.01 W1P authority-aware firmware using USB/full-device programming with the checked-in 16 MB dual-OTA partition map. CI builds it for:

`esp32:esp32:Edgebox-ESP-100:FlashSize=16M,FlashMode=qio,PSRAM=disabled,CPUFreq=240,CDCOnBoot=default,USBMode=default,UploadMode=default,UploadSpeed=921600`

After reboot, W1P starts with software Servo Enable inhibited and the firmware-authority hold active. If the installed application is byte-for-byte the one in SRVR's bundle, its running-image SHA-256 is accepted and the authority hold can clear subject to the existing safety state.

If W1P needs an automatic repair/update, it will not write flash until the existing fail-closed service gate proves all of the following: zero command path, fresh post-stop EL7 feedback showing near-zero speed, Servo Enable OFF, Brake Release OFF, drive writes locked and software Servo Enable inhibited. If EL7/RS485 feedback is unavailable, automatic W1P OTA intentionally remains blocked; use USB recovery/service rather than bypassing that gate.

## 4. One-time CTRL EdgeBox bootstrap

Install the **final staged CTRL build** from the same native firmware artifact. Do not remove or bypass the clean-source CTRL carrier `#error`; GitHub's native build first embeds the exact CTRL-TS image, then compiles CTRL.

Use the same EdgeBox 16 MB FQBN shown above and the checked-in dual-OTA partition map. On boot CTRL asserts its existing E-stop/safety path until its own version and running-image SHA-256 exactly match the SRVR authority manifest.

Only after CTRL reaches `matched` may its existing CTRL -> CTRL-TS version/hash update process begin.

## 5. First authority start-up

Connect SRVR, CTRL and W1P to the isolated control Ethernet network and run the **matching v26.09.15.01 SRVR native build**. The SRVR authority service listens on TCP port 8088 and serves only its verified packaged bundle.

Then reboot/power-cycle CTRL and W1P as part of the normal stopped start-up sequence. Expected policy is:

- installed version older than SRVR -> controlled automatic update;
- same version + exact running SHA-256 -> match and normal operation;
- same version + different/unverifiable SHA-256 -> fail-safe repair from SRVR;
- installed version newer than SRVR -> warning/safety hold; **no automatic downgrade**;
- missing/invalid manifest, interrupted transfer, wrong role/target, wrong size, bad SHA-256 or missing embedded identity -> inactive image is not activated.

W1P also reports `FW_MATCH`/`FW_AUTH`; SRVR treats a missing or false match as an internal W1P safety source. This deliberately blocks a pre-bootstrap W1P from being trusted by a v26.09.15.01 SRVR.

## 6. Future releases — no routine USB update

For later releases, install/run the new matching SRVR build first while the system is stopped and braked, then restart CTRL and W1P during the planned start-up/service window. Authority-aware EdgeBoxes only perform convergence while in their start-up authority hold; once an exact match has been accepted, they do not begin a surprise firmware update during an active running session.

The sequence is:

1. SRVR serves its packaged exact CTRL/W1P release;
2. CTRL converges over Ethernet and reboots if required;
3. W1P converges over Ethernet only behind its stopped/braked service gate and reboots if required;
4. after CTRL is confirmed matched, CTRL verifies/updates CTRL-TS over RS485;
5. normal motion remains inhibited until the existing safety/re-arm conditions clear.

## 7. Recovery paths retained

- **EdgeBox browser OTA** remains available as a service fallback for an already correctly partitioned CTRL/W1P. Use only the correct role image and keep the system in the same safe service state.
- **USB/full-device programming** remains the bootstrap and recovery path, including partition-map recovery.
- CTRL-TS retains its CTRL-driven RS485 OTA/recovery behavior; USB remains its manual recovery path.
- Never use an older SRVR to force a newer EdgeBox backward. The automatic path intentionally refuses downgrade.

A source/CI pass is not powered-motion approval. Complete the native-build and physical bench checklist before operational use.
