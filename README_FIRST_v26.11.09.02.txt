HV P2P SYS v26.11.09.02
======================
9 November 2026

SYS baseline  HV-P2P-v26.11.08.02-GitHub.zip
PDM baseline  HV_P2P_PDM_v26.11.09.01.zip

Extract to the repository root and replace the previous versioned component
folders. Include all five v26.11.09.02 source folders, tools, documentation
and .github/workflows/complete-build.yml. Run HV P2P Complete Build v26.11.09.02
after committing the source. The GitHub artifact includes the four native
firmware images and the matching macOS Intel, macOS Apple Silicon and Windows
x64 SRVR releases.

For the one-time Olimex USB upload, see PDM_BOOTSTRAP_v26.11.09.02.md.
After bootstrap, open Power in SRVR and confirm the PDM address. The PDM
continues to host its dashboard and write its own history.

Check the source with sha256sum -c CHECKSUMS_SHA256.txt. The local
verification and remaining checks are in TEST_RESULTS_v26.11.09.02.txt,
SOURCE_REGRESSION_LOG_v26.11.09.02.txt and
NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.11.09.02.md.
