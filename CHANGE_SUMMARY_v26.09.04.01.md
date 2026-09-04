# HV P2P v26.09.04.01 Change Summary

This is the correctly dated release identity for the cross-platform revision that was initially packaged under the incorrect draft designation `v26.08.31.11`. There are **no functional code or UI changes** between that draft pack and v26.09.04.01; only the complete release/version identity has been corrected for 4 September 2026.

v26.09.04.01 is the cross-platform SRVR/build-hardening revision based directly on the corrected v26.08.31.10 source. It preserves the locked v26.08.31.09 Run/Setup design, Virtual Position Source behavior, and all inherited safety/control fixes.

## Motion-control audit: Power / Speed acceleration modes

No control tuning or motion semantics were changed in this revision.

- SRVR `Speed` continues to map to W1P `SET_ACCEL_MODE DYNAMIC`.
- W1P Dynamic/Speed mode keeps the Leadshine EL7 PR0 path in velocity mode and uses measured cable-speed feedback in a bounded PI outer correction loop.
- If measured cable speed is below the profiled requested speed, the correction raises the EL7 velocity command; if measured speed is above target, it lowers the command.
- PI correction is bounded, zero-target resets the integrator, and correction is prevented from reversing the requested direction.
- SRVR `Power` continues to map to W1P `TRADITIONAL`. Power remains the existing direct/traditional velocity-profile response without the W1P outer speed-hold PI correction; it is not changed into torque-mode or watts control.
- A new `tools/test_speed_mode_contract.py` regression locks these semantics and is part of `tools/run_all_source_checks.py`.

Physical commissioning must still prove Speed mode under real cable/load variation; this source audit does not replace that test.

## Cross-platform SRVR fixes

- SRVR private configuration storage is now native per OS:
  - macOS: `~/Library/Application Support/HV P2P SRVR/config.json`
  - Windows: `%LOCALAPPDATA%\\HV P2P SRVR\\config.json` (fallback `%APPDATA%`, then `AppData\\Local`)
  - Linux/other Unix: `$XDG_CONFIG_HOME/HV P2P SRVR/config.json` or `~/.config/HV P2P SRVR/config.json`
- Qt FileDialog `file:///C:/...` paths are normalized correctly for Windows drive-letter paths.
- UNC `file://server/share/...` paths are preserved.
- Runtime regression coverage now validates macOS, Windows and XDG path mapping plus Windows drive-letter/UNC FileDialog handling.

## Three-platform SRVR GitHub build

The Complete Build workflow now requires all of these native SRVR builds:

1. **macOS Intel** on `macos-15-intel`, verified `x86_64`.
2. **macOS Apple Silicon** on `macos-15`, verified `arm64`.
3. **Windows x64** on `windows-2025`, verified PE machine `0x8664` / AMD64.

Each platform performs source preflight, pinned PySide6 installation, backend runtime regression, isolated deployment staging, QML/resource validation, source smoke test, native freeze, frozen executable/app smoke test, and archive verification before upload.

The Complete Release is created only after firmware + both macOS architectures + Windows x64 pass. `COMPLETE_RELEASE/SRVR/` preserves exactly these three original nested archives:

- `HV P2P SRVR v26.09.04.01 macOS Intel.zip`
- `HV P2P SRVR v26.09.04.01 macOS Apple Silicon.zip`
- `HV P2P SRVR v26.09.04.01 Windows x64.zip`

The existing internal `SHA256SUMS.txt` and external Complete Release `.sha256` protection are retained.

## Locked operator design retained

The approved Run and Setup pages are unchanged. No QML layout or control-semantic redesign is part of v26.09.04.01.

## Validation status

- EdgeBox/SRVR integrated source validation: 316 checks PASS.
- Build-pipeline validation: 40 checks PASS.
- Dedicated Speed-mode contract: PASS.
- Full `tools/run_all_source_checks.py`: PASS.
- Backend runtime regression: PASS under the local QtCore compatibility harness; the real pinned PySide6 regression remains mandatory on each native GitHub SRVR runner.
- Native ESP32 and native desktop binaries are intentionally not fabricated in this source pack; GitHub Actions is the authoritative native build gate.
