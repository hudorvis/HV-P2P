HV P2P v26.09.04.03 — GITHUB-READY SOURCE RELEASE
====================================================

WINDOWS CI PROBE CORRECTION
---------------------------
v26.09.04.03 supersedes v26.09.04.02 after the Windows x64 job successfully found and launched dumpbin but failed its own preflight because `dumpbin /?` returned a non-zero help-mode exit status. The application/firmware behaviour and locked Run/Setup UI are unchanged.

Windows CI now validates dumpbin by running `/headers` against the runner's real `cmd.exe`, checks the completed process exit code, and requires recognizable PE/x64 header output. The existing pinned Nuitka 4.2 and `--assume-yes-for-downloads` non-interactive Dependency Walker handling remain in place.

MOTION CONTROL
--------------
No Power/Speed behaviour is retuned. Speed remains W1P DYNAMIC closed cable-speed hold with bounded PI correction around the profiled target. Power remains the existing TRADITIONAL direct velocity-profile response. Physical load testing remains a commissioning gate.

CROSS-PLATFORM SRVR
-------------------
GitHub must build and verify:
- macOS Intel / x86_64;
- macOS Apple Silicon / arm64;
- Windows x64 / AMD64.

COMPLETE RELEASE
----------------
The final release must preserve these original nested archives:
- HV P2P SRVR v26.09.04.03 macOS Intel.zip
- HV P2P SRVR v26.09.04.03 macOS Apple Silicon.zip
- HV P2P SRVR v26.09.04.03 Windows x64.zip

Upload this ZIP's contents at repository root and run `.github/workflows/complete-build.yml`. A successful compile is not powered-motion commissioning approval.

SOURCE VALIDATION
-----------------
Integrated source validation: 316 checks PASS.
Build-pipeline validation: 46 checks PASS.
Speed-mode control contract: PASS.
Full tools/run_all_source_checks.py: PASS.
Workflow YAML parse: PASS.

