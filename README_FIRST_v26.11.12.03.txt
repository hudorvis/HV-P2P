HV P2P SYS v26.11.12.03
======================
12 November 2026

SYS baseline  HV-P2P-v26.11.12.02-GitHub.zip
PDM baseline  HV_P2P_PDM_v26.11.09.01.zip

Extract to the repository root and replace the previous versioned component
folders. Include all five v26.11.12.03 source folders, tools, documentation
and .github/workflows/complete-build.yml. Run HV P2P Complete Build v26.11.12.03
after committing the source. The GitHub artifact includes the four native
firmware images and the matching macOS Intel, macOS Apple Silicon and Windows
x64 SRVR releases.

The firmware and complete-release packaging jobs use Ubuntu 24.04.
The firmware job uses Python 3.12.10. It configures the Arduino data and download paths
before restoring the cache and installing ESP32 core 3.3.8.
GitHub release downloads can retry through the release-assets API.

For the one-time Olimex USB upload, see PDM_BOOTSTRAP_v26.11.12.03.md.
After bootstrap, open Monitoring → PDM and confirm its Ethernet address.
Current network services use port 5000. Allow TCP 5088 on the SRVR host
while the older node firmware migrates. See the bootstrap guide for
checking the authority address, firewall and macOS AirPlay Receiver. The PDM
continues to host its dashboard and write its own history. Monitoring → WSI
is available for a separate device at its own address. See WSI_INTERFACE.md
for the API used by this revision and the pending WSI firmware work.

Check the source with sha256sum -c CHECKSUMS_SHA256.txt. The local
verification and remaining checks are in TEST_RESULTS_v26.11.12.03.txt,
SOURCE_REGRESSION_LOG_v26.11.12.03.txt and
NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.11.12.03.md.
