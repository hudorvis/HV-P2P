# HV P2P v26.09.14.01 Change Summary

v26.09.14.01 is the SRVR-authoritative automatic firmware-convergence revision built from the fully packaged v26.09.04.03 baseline.

## SRVR firmware authority

SRVR now starts a read-only firmware authority service before the control backend. Startup fails closed if the packaged firmware bundle is absent, invalid, for another release, or has failed size/SHA-256/role/target checks.

The immutable bundle contains exactly the final native `CTRL` and `W1P` application images, `manifest.json` and `SHA256SUMS.txt`. Role endpoints expose manifests/images for CTRL and W1P on the isolated control LAN. Runtime validation requires release identity, exact file set, image size/SHA-256, ESP application magic and embedded role/version/EdgeBox-target tokens.

## CTRL automatic Ethernet OTA

CTRL boots authority-unmatched and asserts the existing E-stop flag until the SRVR relation is established. It compares four-part release versions and its exact running application SHA-256:

- older -> update from SRVR;
- equal + exact SHA -> matched;
- equal + mismatch/unverifiable SHA -> fail-safe repair;
- newer -> warning/hold, no automatic downgrade.

Downloaded images are checked for exact Content-Length, complete SHA-256, ESP image magic, role/version identity and EdgeBox hardware target before `Update.end()` can finalize the inactive partition. Interrupted/invalid downloads are aborted.

CTRL's existing CTRL-TS updater is now sequenced behind this gate: CTRL must first exactly match SRVR, then the existing hardware/protocol/version/hash RS485 updater operates unchanged.

## W1P automatic Ethernet OTA and safety

W1P boots with both firmware-authority hold and software Servo Enable inhibition. The authority hold participates in automatic-drive enable, safety-loss handling, `SW_SRVON` rejection and SRVR heartbeat re-enable logic.

Before any W1P authority image is written, the existing `hvPrepareSafeServiceState()` gate is reused unchanged. It stops/locks the command path, inhibits software Servo Enable, obtains fresh post-stop EL7 feedback, requires two consecutive near-zero-speed samples, and verifies Servo Enable OFF and Brake Release OFF. The independent 650 ms VEL freshness watchdog is retained unchanged.

SRVR parses W1P `FW_MATCH`/`FW_AUTH`. A missing match field is fail-closed, preventing an older pre-bootstrap W1P from being trusted by this SRVR revision.

## GitHub build ordering

The workflow now enforces:

1. native CTRL-TS build;
2. exact CTRL-TS image/hash/version embedded into staged CTRL;
3. final CTRL build;
4. W1P build;
5. native role/target/version/size/SHA-256 verification;
6. immutable `SRVR_FIRMWARE_BUNDLE` creation and verification;
7. Mac Intel, Mac Apple Silicon and Windows x64 SRVR builds, all consuming the exact same firmware artifact;
8. Complete Release only if firmware and all three SRVR native jobs pass.

The prior Windows x64 hardening remains: MSVC x64 environment, real `dumpbin /headers` PE probe, Nuitka 4.2, non-interactive Dependency Walker acquisition, AMD64 machine verification and frozen-executable smoke testing.

## Preserved UI and motion behavior

The approved Run and Setup QML files are byte-identical to v26.09.04.03 and are protected by SHA-256 regression locks. Speed remains the existing W1P `DYNAMIC` cable-speed PI architecture; Power remains `TRADITIONAL`. Virtual mode's physical W1P output inhibition remains unchanged.

## Bootstrap and recovery

`INITIAL_BOOTSTRAP_v26.09.14.01.md` documents the one-time CTRL EdgeBox, W1P EdgeBox and CTRL-TS Waveshare installation and future SRVR-driven convergence. EdgeBox browser OTA remains a service fallback and USB/full-device flashing remains bootstrap/recovery.

## Validation policy

Host/source tests now include the firmware authority HTTP service, immutable bundle builder/validator, 38-check automatic-OTA contract, integrated EdgeBox safety/preservation regression, build-pipeline validation, protocol tests, Speed-mode contract and SRVR project preflight. Native Arduino/Qt frozen artifacts are not fabricated locally when those toolchains are unavailable; GitHub Actions remains the authoritative native gate.
