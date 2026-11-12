# HV P2P SYS v26.11.12.05 port migration review

Baseline HV-P2P-v26.11.12.04-GitHub.zip.

The required authority listener is TCP 5760. Older TCP listeners are attempted independently and a bind failure is recorded in the Log. A blocked primary listener continues to display the recovery window.

CTRL and W1P control endpoints moved to UDP 5760. The legacy CTRL and W1P beacon path delivers release updates without carrying motion commands. Legacy W1P telemetry can indicate presence and OTA activity but cannot claim a firmware match or update the live control queue. A detected legacy W1P prevents the isolated-bench PDM permit. The normal PDM idle gate and the current W1P safety checks are retained.

The PDM monitor keeps the last working HTTP port and tries the other supported ports after a transport failure. PDM update authority identity, digest and safe-idle checks remain in place. WSI uses the updated API contract on TCP 5760 and still needs sensor firmware.

See TEST_RESULTS and the commissioning checklist for the verification scope.
