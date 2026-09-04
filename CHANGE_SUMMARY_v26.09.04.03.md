# HV P2P v26.09.04.03 Change Summary

v26.09.04.03 is a Windows CI probe-correction revision for v26.09.04.02. Application behaviour, firmware behaviour, Power/Speed motion semantics, locked Run/Setup UI, cross-platform SRVR behaviour, and release packaging are unchanged.

## Root cause corrected

The v26.09.04.02 Windows job successfully initialized the x64 MSVC developer environment and resolved `dumpbin.exe`, proving the tool was present. The job then invoked `dumpbin /?` and treated its non-zero help-mode exit status as a fatal usability failure. This stopped CI before `pyside6-deploy` even ran.

The Windows preflight now:

- resolves `dumpbin.exe` from the initialized x64 MSVC environment;
- selects the runner's real `cmd.exe` (`$env:ComSpec`) as a known PE probe target;
- runs `dumpbin /headers` against that binary and captures the process exit code only after dumpbin has completed;
- requires exit code 0 and recognizable PE/x64 header output;
- explicitly rejects the old brittle `dumpbin /?` probe in build-pipeline validation.

The existing Windows deployment hardening from v26.09.04.02 remains unchanged:

- Nuitka is pinned to 4.2;
- `--assume-yes-for-downloads` is injected into `pysidedeploy.spec`;
- the dry-run must prove that flag is present in the actual Nuitka command;
- PE/AMD64 verification, frozen executable smoke test, ZIP verification and Complete Release gating remain mandatory.

## Motion and UI

No motion-control or operator-interface behaviour is changed in this revision. Speed remains the W1P DYNAMIC closed cable-speed hold with bounded PI correction and Power remains the established TRADITIONAL direct velocity-profile path. The locked Run and Setup QML is unchanged apart from release identity where displayed.

## Three-platform release

A successful Complete Release still requires native firmware plus:

- `HV P2P SRVR v26.09.04.03 macOS Intel.zip`
- `HV P2P SRVR v26.09.04.03 macOS Apple Silicon.zip`
- `HV P2P SRVR v26.09.04.03 Windows x64.zip`

Native binaries remain GitHub CI outputs; they are not fabricated in this source pack.

## Validation status

- EdgeBox/SRVR integrated source validation: 316 checks PASS.
- Build-pipeline validation: 46 checks PASS.
- Dedicated Speed-mode contract: PASS.
- Full `tools/run_all_source_checks.py`: PASS.
- GitHub workflow YAML parse: PASS.
- Native Windows compilation remains the authoritative GitHub Actions gate.

