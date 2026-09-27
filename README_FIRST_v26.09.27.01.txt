HV P2P v26.09.27.01 - GITHUB READY SOURCE

PURPOSE
This is the current reconstructed source release for GitHub Actions. The prior
v26.09.20.01 generated attachment expired and its exact bytes were no longer
recoverable. To avoid issuing different bytes under the same version identity,
this reconstruction is honestly versioned v26.09.27.01.

RECONSTRUCTION BASIS
- surviving user-uploaded v26.09.04.03 source baseline;
- preserved project handoff/audit requirements from later revisions;
- reconstructed SRVR-authoritative CTRL/W1P Ethernet OTA;
- reconstructed v26.09.17.02 CTRL <-> CTRL-TS RS485 hardening;
- reconstructed v26.09.20.01 W1P <-> Leadshine RS485 hardening;
- fresh source/protocol/build audit on v26.09.27.01.

IMPORTANT
GitHub Actions is the authoritative native compiler. This source package does
NOT contain fabricated ESP32 .bin files, Windows .exe files, or macOS .app
bundles. The workflow builds those natively and only creates COMPLETE_RELEASE
after firmware, macOS Intel, macOS Apple Silicon, and Windows x64 gates pass.

FIRST COMMISSIONING FLASH
For the first v26.09.27.01 hardware test, use the GitHub-produced
FIRMWARE/STAGED_SOURCE sketch folders. Manually flash CTRL-TS first, then CTRL.
That proves the repaired RS485 updater from a known matching bootstrap. W1P may
subsequently converge from SRVR only if its existing dual-OTA layout and the
stopped/braked service gate are already valid; otherwise manually flash W1P from
STAGED_SOURCE as the commissioning baseline.

See INITIAL_BOOTSTRAP_v26.09.27.01.md and
NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.09.27.01.md before hardware testing.
