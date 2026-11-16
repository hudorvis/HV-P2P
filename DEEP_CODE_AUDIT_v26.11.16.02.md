# HV P2P SYS v26.11.16.02 source audit

Baseline `HV-P2P-v26.11.16.01-GitHub-Complete.zip`. This source package
contains SRVR, CTRL, W1P, CTRL-TS and PDM.

## Log events and severity

- W1P's ordinary UDP writes and background velocity refresh continue through
  the same socket and retry paths. Expected host and network unreachable errors
  use the existing link-transition log. Repeated identical unexpected errors
  are rate-limited per operation. The shutdown safety write retains its direct
  error log.
- The link log reports validated STATUS, CTRL liveness, CTRL-TS transport and
  Leadshine telemetry independently of motion readiness. The monitoring
  worker logs connection, sustained loss, stale data and recovery for the
  configured PDM and WSI. A closed Monitoring page keeps low-rate presence
  checks and firmware discovery running.
- Accepted CTRL packets and validated W1P STATUS frames supply the physical
  E-Stop input transitions. SRVR batches them after preparing the existing
  display packet. The SRVR latch reports its state when operated. The Safety
  view and plain-text export identify the specific input. Activation is a
  Fault entry. Clearance is an Info entry and SRVR still requires joystick neutral.
- Firmware events report stage changes and continuing transfer progress in
  10% steps using the latest available report. The Firmware filter also shows
  verification and authority messages. Live status uses the reported progress.
- The live Log table follows new events at the 1,200-row limit with Auto-scroll on.

## CTRL-TS and app branding

- The three CTRL-TS cards use the Run page's layout at 800 × 480. LVGL draws
  the heading symbols with supported primitives and its settings glyph.
  Both speed columns share the same geometry. Distance values and units
  centre together as the reported digit count changes.
- The macOS iconset and Windows executable icon use the updated `HV P2P` /
  `SRVR` artwork through the existing deployment paths.

## Browser text and graphics

- The browser reports CSS geometry and device-pixel ratio per viewer. The
  Qt Quick layout uses CSS dimensions and the render target uses the browser's
  pixel density, subject to the physical render cap.
- Lossless PNG preserves thin strokes and text colours. Encoding stays on
  the worker. A change in dimensions or density invalidates the originating
  viewer's stale frame and queued input. The same input freshness and recall
  liveness checks continue to run.

## Browser layout inherited from v26.11.15.08

- The previous browser image used the desktop's Qt Quick geometry. When the
  proportions differed, browser fitting produced side or top margins.
- The desktop and browsers now instantiate the same SRVR QML interface.
  Each browser supplies its viewport dimensions and gets its own render and
  coordinate mapping. The physical-pixel frame cap applies at high DPI.
- Shared navigation commits the currently edited fields before changing
  pages. The views share system state and saved values through the same
  backend. File dialogs open in the initiating view and browse the SRVR
  host. The desktop view coordinates PDM and WSI history subscriptions.
- SRVR checks frame freshness against the originating browser's viewport
  and shared state. Resize cancels gestures in that browser. The per-browser
  recall heartbeat still governs STOP and joystick-neutral recovery.
- The Qt thread dispatches input and renders one requested view at a time.
  A worker encodes lossless PNG frames and hidden tabs pause frame capture.
- The firmware authority and the web views share TCP 5760. The current
  role, target, image verification and ordered update logic are exercised
  by the source regressions.

## Free-D Geometry

- X, Y and Z headings and entry fields share column sizes. The compact P1–P5
  label column leaves more width for editable values.
- Skate Weight, Cable Weight and Cable Tension use common value and unit
  widths. Qt regression coverage checks both the spacing and the existing
  read-only Z fields for intermediate points.

## Monitoring updates and browser dashboard from v26.11.15.03

- The field PDM connected after its AP subnet was corrected and successfully updated once the previous SRVR idle condition was satisfied. SRVR now issues the verified PDM permit based on the configured Ethernet peer. It applies the same rule to a verified optional WSI image. The address and image checks, SD flush before activation and the existing control-node update sequence remain in use.
- The previous version's permit wire format is supported for OTA migration. The old status string is displayed as Checking for update while the older PDM migrates. Source fixtures cover authorised and unauthorised requests, an address change, W1P ordering, an optional WSI image and a lost PDM permit before activation.
- The browser dashboard follows the SRVR Monitoring reference for the status panel, button order, channel layout, colours, trace axes and pointer readouts. It uses the device's existing APIs and retains the iOS bookmark. Channel edits use the same four fields as SRVR. The desktop and narrow layouts were exercised in a browser with simulated device data.

## PDM Ethernet and Wi-Fi AP startup

The reported Olimex serial output showed a configured Ethernet IP of `172.20.1.110` and a failed AP configuration with Wi-Fi still running at `172.20.1.1`. The PDM then failed to connect to the firmware authority on TCP 5760. The same-subnet AP can interfere with Ethernet route selection. The serial failure alone does not distinguish an incorrect route from a blocked connection on the equipment LAN.

Earlier firmware only checked subnet overlap before enabling NAPT and called `softAP` even after `softAPConfig` failed. PDM now verifies AP configuration before advertising, folds overlap detection into startup and DHCP lease handling, and stops Wi-Fi on failure. Recovery uses an alternate AP subnet without rewriting credentials or saved addresses. The host fixture compiles the production startup functions and checks the reported address pair, the second recovery subnet, a partially applied configuration failure, DHCP overlap with NAPT disabled, a distinct custom AP and wired-only operation.

## Log export from a read-only location

The previous release attempted to create the log beside the running SRVR app and showed a generic error when that write failed. SRVR now shows the filesystem error and attempted folder. On macOS, a failed write under `AppTranslocation` shows how to open the app from an installed, writable location. The dialog can also retry into an explicitly selected folder. Tests cover the regular app folder, a missing folder, a simulated read-only macOS launch path, cancel and save into the selected folder. Real Google Drive and Gatekeeper behaviour require a macOS check.

## PDM OTA and log export included in v26.11.14.01

- The attached SRVR v26.11.12.09 export showed the monitor reading PDM v26.11.12.07 at `172.20.1.110`. It had no recent firmware request from the PDM, whose saved destination was `172.20.1.100:5760`. The trace showed neither a permit denial nor a transfer attempt. The unavailable legacy TCP 5000 listener was separate from that saved destination.
- SRVR now checks its configured PDM on a background worker while Monitoring is closed. The PDM verifies the returning Ethernet peer, honours a manually saved authority and checks the peer's manifest. The host OTA fixture covers a newer release, safe-idle rejection, verified activation, exact-image verification, no downgrade, an expired offer, the AP and off-subnet restrictions, and saved-authority recovery. The Qt HTTP fixture verifies the request before Monitoring opens and another request after the PDM's boot ID changes.
- SRVR now reports a saved PDM authority address that is absent from its active IPv4 addresses. A matching address leaves device routing, inbound connectivity and the PDM's OTA worker as the next checks. The available log alone cannot confirm the physical unit's blocker.
- Save Log writes beside the running application. Backend tests exercise macOS, Windows and source paths, two saves in the same second and a failed write. The Qt fixture checks the Log page's write failure message and the PDM's address diagnostics.

## PDM OTA and settings included in v26.11.12.09

- The HTTP regression verifies that a browser can fetch the manifest while the selected PDM receives HTTP 409 for its permit. It tracks requests by peer, verifies successful image access after three seconds of continuous idle proof and rejects other peers. The SRVR Log presents this evidence in Monitoring sessions.
- The host fixture compiles the production OTA worker. It checks Ethernet selection, a permit network failure, a 409 before transfer, a lost permit after the writer pause, and an SD pause failure. It then verifies a successful stage and simulated reboot. The physical Olimex and equipment network remain bench checks.
- The Qt fixture verifies **Web UI** before **Settings**, **IP Address** in the popup, no firmware hover diagnostic and a separate **PDM OTA** Log source. An earlier PDM release can report its own image as Current. SRVR shows Current only when the reported version also matches the running SRVR release.

## PDM dashboard and Monitoring changes included in v26.11.12.08

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
| PDM | Peer-specific update permit and verified image, wrong target and hash rejection, interrupted and stalled staging, simulated reboot into the verified image, dashboard, retained history, deduplication, calibration, gaps and reconnect behavior. |
| WSI | Independent verified monitor firmware routes, SRVR live and history graphs, hover readout, log settings and the web shortcut. Source tests use a WSI HTTP fixture. Olimex sensor firmware is pending. |
| Release | Arduino install and cache orchestration with fixtures, firmware build order and packaging, workflow and version checks, source and Qt smoke tests and source archive integrity. |

See `NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.11.16.02.md` for the GitHub native build and installed-system checks. The source checks use fixtures for flash, network devices and drive feedback. Native executables and physical results are separate commissioning evidence.
