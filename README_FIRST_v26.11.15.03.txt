HV P2P SYS v26.11.15.03
======================
15 November 2026

SYS baseline  HV-P2P-v26.11.15.02-GitHub-Complete.zip
PDM baseline  HV_P2P_PDM_v26.11.09.01.zip

Extract to the repository root and replace the previous versioned component
folders. Include all five v26.11.15.03 source folders, tools, documentation
and .github/workflows/complete-build.yml. Run HV P2P Complete Build v26.11.15.03
after committing the source. The GitHub artifact includes the four native
firmware images and the matching macOS Intel, macOS Apple Silicon and Windows
x64 SRVR releases.

The firmware and complete-release packaging jobs use Ubuntu 24.04.
The firmware job uses Python 3.12.10. It configures the Arduino data and download paths
before restoring the cache and installing ESP32 core 3.3.8.
GitHub release downloads can retry through the release-assets API.

For the Olimex USB upload, see PDM_BOOTSTRAP_v26.11.15.03.md.
Choose the preserving upload to retain settings or the clean-install
procedure to reset settings. Keep the microSD card and its existing logs.
After bootstrap, confirm the Ethernet address under Monitoring → PDM →
Settings. The PDM browser dashboard and API use standard HTTP on
port 80. The browser page uses SRVR's Monitoring layout with LAN and Wifi
Settings. SRVR requests checks from the configured PDM Ethernet address
even while Monitoring is closed. Compatible PDMs pull the verified newer
release independently of motion and E-stop state, then reconnect and
verify it. Older PDMs use their saved
SRVR IP for the first update. The Olimex uses a separate AP subnet and
stops Wi-Fi if the AP configuration fails. The SRVR update authority and current
control use port 5760. Quit older SRVR
instances before cutover. SRVR serves updates to older nodes on TCP 5000
and 5088 when the respective port is available. The PDM bootstrap guide
covers the first upgrade, including the AirPlay Receiver case. The
W1P download waits for a fresh CTRL firmware verification report. The PDM
continues to host its dashboard and log history. See WSI_INTERFACE.md
for the TCP 5760 API and pending WSI sensor firmware.

Log → Save Log writes the timestamped text file beside the running SRVR app.
If the folder is read-only or access is denied, SRVR shows the folder and
filesystem error. Choose Folder saves that export in a location you select.

Check the source with sha256sum -c CHECKSUMS_SHA256.txt. The local
verification and remaining checks are in TEST_RESULTS_v26.11.15.03.txt,
SOURCE_REGRESSION_LOG_v26.11.15.03.txt and
NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.11.15.03.md.
