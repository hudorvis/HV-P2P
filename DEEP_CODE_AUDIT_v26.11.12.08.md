# HV P2P SYS v26.11.12.08 source audit

Baseline `HV-P2P-v26.11.12.07-GitHub-Complete.zip`. This revision contains SRVR, CTRL, W1P, CTRL-TS and PDM.

## PDM dashboard and Monitoring changes

- Verify the web listener uses TCP 80 and the PDM firmware worker continues to use TCP 5760. The live API reports the firmware authority port separately. Compatibility tests cover the older PDM ports and an unrelated service responding on port 80.
- The offscreen SRVR fixture verifies that live data and firmware progress are shown independently. Firmware diagnostics appear on hover. The same fixture checks each voltage card, red alarm colours, popup button order and the IP field's placement.
- The PDM Settings fixture covers offline address validation, duplicate WSI address rejection, Cancel, and persistence on Apply. Log settings stay associated with the device from which they were loaded. Applying an address reconnects SRVR, then log settings can be loaded from that address.

## Prior audit corrections included in v26.11.12.07

| Finding | Correction and verification |
|---|---|
| W1P could request its image on a cold boot before CTRL verified the release. The HTTP endpoint allowed the transfer independently of beacon order. | Every authority listener now returns HTTP 409 for W1P image downloads until the configured CTRL has sent a fresh report for the exact bundled CTRL SHA-256. The asynchronous W1P upload fallback uses the same gate. The manifest remains available for installed-image verification. Loopback tests cover missing, wrong, expired and renewed CTRL proof and switching the selected CTRL. |
| SRVR validated CTRL and W1P firmware on startup, then reopened the files for later downloads and fallback uploads. Changing a file after startup could change what SRVR served. | SRVR verifies the app size, ESP image marker, embedded role, board and release, and SHA-256, then serves the verified in-memory bytes on all paths. HTTP tests change or remove files after startup. The fallback test captures the actual uploaded bytes. An absent or rejected PDM image remains isolated from the required CTRL and W1P images. |
| Repeated announcements for the same mismatched release could reset CTRL's download backoff. | CTRL resets its retry schedule on a release or SRVR session change. The host test compiles the production beacon handler and exercises repeated beacons, release changes and session changes. |
| A failed CTRL or W1P transfer could leave update progress active, suppressing fallback or extending CTRL-TS's ordered wait. | Both nodes emit an inactive failure result. SRVR also reconciles progress from the next status report if a terminal datagram is missed. Tests cover failed transfers and the existing ordered recovery. |
| A long channel label retained from a standalone PDM could prevent SRVR from opening its channel settings. | SRVR can display and edit the retained label. New names still follow the device's 128-byte UTF-8 limit. The offscreen Qt test opens a real HTTP-backed settings dialog and renames the channel. |

## Coverage by component

| Component | Source and host checks |
|---|---|
| SRVR | UDP and HTTP dispatch, verified startup and port-conflict recovery, motion readiness, position sample freshness and ordering, configuration round trips, joystick and limit calibration, presets and AUX, Free-D, Monitoring graphs, settings and Qt page startup. |
| CTRL and W1P | Authority pull and fallback sequencing, newer-version protection and update identity checks, W1P Modbus timestamps and feedback diagnostics, watchdog, E-stop, Servo Enable, brake and service interlocks. The suite includes host Modbus and wire-protocol cases. |
| CTRL-TS | RS485 frame integrity, approved device and safe-updater capability, correlated acknowledgements and offsets, final SHA and reboot proof, display-off transfer, retries and bounded recovery. |
| PDM | Optional authority route and safe-idle lease, wrong target and hash rejection, interrupted and stalled staging, simulated reboot into the verified image, embedded web assets, history pagination during logging, deduplication, calibration, gaps and reconnect behavior. |
| WSI | SRVR live and history graphs, hover readout, independent log settings and the web shortcut configuration. Source tests use a WSI HTTP fixture. This release includes the interface specification for the WSI sensor node. |
| Release | Arduino install and cache orchestration with fixtures, firmware build order and packaging, workflow and version checks, source and Qt smoke tests and source archive integrity. |

See `NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.11.12.08.md` for the GitHub native build and installed-system checks. The source checks use fixtures for flash, network devices and drive feedback. Native executables and physical results are separate commissioning evidence.
