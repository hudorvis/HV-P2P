# HV P2P v26.09.29.01 Change Summary

## Basis
v26.09.29.01 is built directly from the authoritative user-supplied
**HV P2P v26.09.27.01** source. It closes confirmed defects found by the full
source audit and real-hardware commissioning logs/photos from CTRL and CTRL-TS.
The approved SRVR Run and Setup QML designs remain unchanged.

## Confirmed control/safety fixes
- **SRVR/W1P STATUS contract:** removed the invalid `DO1_CFG` requirement. W1P
  deliberately leaves DO1 spare and transmits DO2/DO3/DO4/DO5 configuration
  state. SRVR now requires the actual safety-relevant DO2..DO5 fields.
- **PR0 stale-velocity prevention:** W1P now requires a positively acknowledged
  P09.03 velocity write before it can issue the PR0 trigger. A failed velocity
  transaction cannot trigger the previously stored velocity.
- **Modbus exception handling:** FC06 and FC16 now accept the legal five-byte
  Modbus exception response, retain the EL7 exception code and count the
  CRC-valid reply as physical-link success rather than a timeout.
- **RS485 hysteresis:** higher-level motion helpers no longer call the link-health
  accounting functions a second time after the low-level Modbus transaction.
- **Best-effort emergency stop:** W1P no longer suppresses a bounded PR emergency
  stop attempt merely because the previous transactions already marked the
  RS485 link unhealthy.

## CTRL <-> CTRL-TS session/reconnect fixes
- CTRL records the outstanding normal POLL sequence and ignores stale EVENT
  replies with a different sequence.
- CTRL clears the previously reported CTRL-TS hardware/version/SHA/protocol when
  the HMI link times out, so SRVR cannot present an old version as current.
- A freshly rebooted CTRL-TS refuses normal POLL traffic until that boot has
  completed HELLO/COMPATIBLE. This forces CTRL to revalidate hardware, protocol,
  version and SHA after every fast TS reset.

## CTRL-TS boot/update display fixes
- Firmware transfer owns the splash status while active; the 50 ms boot-state
  ticker cannot overwrite `Updating CTRL-TS firmware` with `Waiting for CTRL`.
- Added a real 0-100% LVGL firmware progress bar.
- Added explicit `Verifying`, `verified`, and `restarting` states.
- Removed repeated foreground shuffling of the status overlay during JPEG/status
  refreshes to reduce visible redraw jitter.
- Added PSRAM diagnostics before LCD startup.
- Missing/undersized PSRAM or a missing/incorrect 800x480 LVGL display now enters
  **headless RS485 firmware recovery mode** rather than blindly reaching the
  splash and panicking. The UART firmware receiver remains serviceable.

## CTRL-TS Run screen fit
The approved 800-pixel-wide content and arrangement are unchanged. Only the
vertical panel geometry was expanded to use the actual 800x480 panel:
- top margin remains 8 px;
- panel gap 6 -> 7 px;
- header 43 -> 45 px;
- E-stop banner 32 -> 34 px;
- AUX row 76 -> 83 px;
- travel row 83 -> 91 px;
- information row 126 -> 141 px;
- footer 31 -> 35 px.

The footer now ends at Y=472, leaving an 8 px bottom margin matching the top,
instead of the unintended ~51 px empty strip seen on v26.09.27.01 hardware.

## Partition/build correction
The CTRL and W1P native build FQBN now explicitly selects
`PartitionScheme=custom`, guaranteeing that the sketch-local 16 MB dual-OTA
`partitions.csv` is used. Manual Arduino commissioning must also select
**Partition Scheme: Custom**. The CTRL-TS native build already selected Custom.

## Regression coverage
A new `tools/test_audit_regressions.py` locks the above producer/consumer,
Modbus, safety, HMI session, splash progress, headless recovery, vertical-fit and
EdgeBox partition contracts. It is part of `run_all_source_checks.py`.
