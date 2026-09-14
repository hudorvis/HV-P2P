# HV P2P v26.09.14.03 Deep Code Audit

## Scope

Deep reconciliation of the v26.09.14.02 GitHub-ready source after the first native v26.09.14.02 CI attempt, with emphasis on preventing the next failure from simply moving to a later job.

## CI evidence reviewed

- CTRL-TS native compilation succeeded under ESP32 Arduino core 3.3.8.
- Exact CTRL-TS binary staging/header verification succeeded.
- The prior CTRL compile blocker (`Print.h` macro `HEX`) was already corrected by the `HEX_DIGITS` change.
- All three SRVR desktop jobs reached and imported `backend.py`; all three failed at the identical backend regression assertion because the test fixture omitted `FW_MATCH`.

## Findings corrected in v26.09.14.03

1. **Backend regression fixture drift** — healthy simulated W1P packets now explicitly satisfy the firmware-authority contract.
2. **Stale W1P session health** — a new W1P `HELLO` now invalidates prior authority/RS485 health until a new full STATUS arrives.
3. **Generic-packet freshness ambiguity** — motion/RS485 readiness now depends on a fresh full STATUS sample, not generic peer traffic.
4. **Malformed STATUS transactional safety** — prior health is cleared before parsing and freshness is committed only after successful parsing.
5. **Late CI fan-out detection** — a Qt-independent backend regression gate is part of the master source suite and runs before Arduino/native build setup.
6. **Revision/path drift** — a release-consistency test rejects mixed active sketch/SRVR/workflow revision paths.

## Preservation checks

- Locked Run/Main QML SHA-256 remains `60edb4348c98827902f21006ffa4e4aa274e65d0527f32782f5f3de97bead93e`.
- Locked Setup QML SHA-256 remains `9cede2819a4c7d931247121711d2441e01537fdd05c804b0fc646caa5fded7fd`.
- CTRL/W1P authority header remains byte-identical between roles.
- W1P reviewed safety functions remain preservation-hash locked.
- Independent 650 ms VEL freshness watchdog remains keyed only from VEL freshness.
- `hvPrepareSafeServiceState()` remains the stopped/braked OTA service gate.
- Speed mode remains DYNAMIC cable-speed PI; Power remains TRADITIONAL.
- Virtual mode continues to inhibit real W1P non-zero output and physical Servo Enable.
- No-auto-downgrade behavior remains unchanged.

## Build/packaging checks

- Firmware job still builds CTRL-TS -> embeds exact CTRL-TS image -> builds CTRL -> builds W1P.
- Native app role/version/target tokens and SHA-256 remain verification gates.
- The immutable `SRVR_FIRMWARE_BUNDLE` remains the single CTRL/W1P payload consumed by Mac Intel, Mac Apple Silicon and Windows x64 SRVR builds.
- Windows MSVC x64, real-PE `dumpbin`, Nuitka 4.2, noninteractive dependency download, AMD64 verification and frozen smoke tests remain present.
- Complete Release remains gated on firmware plus all three native SRVR jobs.

## Additional deep-audit execution

- Entire Python source tree compiles with `py_compile`.
- GitHub workflow YAML parses successfully.
- Qt-independent backend regression completed 20 consecutive passes to catch timing/fixture flakiness.
- Active-release consistency gate passes for v26.09.14.03.
- CTRL and W1P authority headers remain byte-identical and retain the `HEX_DIGITS` Arduino-core collision fix.

## Local limitation

The local environment does not contain the authoritative Arduino/native macOS/Windows toolchains. No `.bin`, `.app` or `.exe` output is fabricated. GitHub Actions remains the compile/frozen-runtime authority, followed by physical bench commissioning for RS485/EL7/motion behavior.
