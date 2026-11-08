HV P2P v26.11.08.02
===================
GitHub build revision | 8 November 2026
Source baseline — HV-P2P-v26.11.08.01-GitHub.zip

The archive opens at the repository root. Replace the prior versioned source
folders with the four v26.11.08.02 component folders and include the root
.github/workflows/complete-build.yml, tools and documentation. Commit the
replacement and run HV P2P Complete Build v26.11.08.02.

This revision hardens the ESP32 core setup. The workflow keeps Arduino CLI
1.5.1, Espressif's stable index and ESP32 core 3.3.8. It retries a failed index
refresh or package install up to three attempts, shows the failing command and
checks both board IDs before starting the firmware build.

For verification results, see TEST_RESULTS_v26.11.08.02.txt and
SOURCE_REGRESSION_LOG_v26.11.08.02.txt. Check source hashes with
sha256sum -c CHECKSUMS_SHA256.txt. The separate desktop build and physical
checks are listed in NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.11.08.02.md.
