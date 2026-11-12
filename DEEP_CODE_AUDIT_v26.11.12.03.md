# HV P2P SYS v26.11.12.03 source review

Baseline HV-P2P-v26.11.12.02-GitHub.zip.

- Both SRVR authority listeners serve the same immutable firmware bundle and PDM idle-window check. The bind failure identifies the affected port. The isolated desktop smoke uses an ephemeral authority port.
- CTRL, W1P and PDM use TCP 5000 for authority HTTP. CTRL/W1P retain their control UDP transport. PDM dashboard assets and OTA partition layout are carried forward.
- SRVR negotiates the existing PDM dashboard on TCP 80 when the standard port is unreachable. Settings writes use the active port. The WSI API uses TCP 5000.
- Voltage extrema use the calibrated chart series, which preserves the extrema of each history bucket. Channel updates use the PDM's existing validation and storage rules.
- The PDM sends the firmware phase and its saved SRVR IP to SRVR. The application correlates recent firmware manifest requests by PDM source IP. The reported field issue remains dependent on the actual Olimex address, Ethernet route and firewall.

See the regression log and commissioning checklist for verification scope.
