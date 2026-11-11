# HV P2P SYS v26.11.12.02 workflow review

Baseline HV-P2P-v26.11.12.01-GitHub.zip.

- The GitHub log reports Ubuntu 26.04 x64 and no Python 3.12.10 build for that image. The firmware job now targets Ubuntu 24.04, for which the official Actions Python manifest lists the 3.12.10 x64 archive.
- The complete-release packaging job also targets Ubuntu 24.04. The existing macOS and Windows runner and Python pins are retained.
- The regression checks cover the Linux runner labels and the Python version within the firmware job. Existing Arduino setup and archive verification still run in the same order.
- All application and firmware changes are release identifiers and the regenerated embedded dashboard assets containing those identifiers. The Monitoring, PDM and WSI implementation is carried forward.

The source checks exercise the workflow contracts locally. Native GitHub builds and physical validation are listed in the commissioning checklist.
