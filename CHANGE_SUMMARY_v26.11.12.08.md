# HV P2P SYS v26.11.12.08

- The PDM web dashboard and API use TCP 80. SRVR connects on that port by default and detects older dashboard ports during migration. The PDM still fetches firmware from SRVR on TCP 5760.
- The PDM header shows the firmware version and available update progress. Routine discovery text is hidden, with firmware diagnostics available on hover.
- All four voltage cards place Settings above the live reading. Active voltage alarms appear in red.
- PDM Settings starts with PDM IP Address. The address can be saved while offline. Log interval and duration are editable once the selected PDM connects.
- Apply appears to the left of Cancel in the PDM and voltage settings dialogs.
