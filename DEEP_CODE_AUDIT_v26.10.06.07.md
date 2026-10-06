# HV P2P v26.10.06.07 deep code audit

## Scope

Locked baseline: `v26.10.06.06`.

Audit scope is restricted to the two reported regressions:

1. automatic firmware convergence requiring manual CTRL/CTRL-TS reboot;
2. CTRL-TS flashing between Home and the Waiting splash after SRVR closes.

## Root cause A — release discovery had only one practical running-node trigger

A running CTRL exits `serviceSrvrFirmwareAuthority()` immediately while `g_srvrFirmwareMatched` is true. This is intentional: healthy motion must not perform periodic blocking HTTP checks. Therefore a newer release must first invalidate that match through the UDP `SRVR_FW` announcement.

The background SRVR comms worker already sends that announcement every 500 ms, but if that one-way datagram is missed, CTRL can remain matched to the old running release indefinitely. A manual reboot initializes `g_srvrFirmwareMatched=false`, so boot-time HTTP manifest discovery succeeds and makes rebooting appear to be required.

### Correction

The controller RX worker now sends a redundant `SRVR_FW` datagram on the exact heartbeat return path after the existing ACK, rate-limited by `FIRMWARE_BEACON_INTERVAL_S`. Heartbeat traffic already proves that UDP route bidirectionally. The standalone background beacon remains unchanged.

## Root cause B — local CTRL-TS recovery depended on the same optional token that could be missing

The 12-second CTRL-local fallback correctly required exact CTRL authority match, SRVR online, repeated approved CTRL-TS mismatch and safe OTA capability. It also required a non-empty `g_srvrFirmwareSession`. If the release beacon itself was not received, that token could be absent even after CTRL boot-time authority verification, preventing the fallback from ever arming.

### Correction

The session-token prerequisite is removed only from the bounded local CTRL-TS final-stage recovery and its mismatch timer. Exact CTRL authority verification plus live SRVR presence remain mandatory.

## Root cause C — CTRL progress completion was one-shot across reboot

The final external CTRL `active=0 / Complete` firmware status is sent close to `ESP.restart()`. If that final frame is lost, CTRL-TS retains `g_fw_row_active[CTRL]=true`, so the firmware dashboard can remain at 100% forever.

### Correction

A `HELLO_REQ` from a rebooted CTRL is now treated as definitive evidence that the prior CTRL OTA execution has ended. Any stale active CTRL progress row is converted to `Complete | 100%` and normal dashboard-release timing proceeds.

## Root cause D — splash/home arbitration had two stale-state races

`service_fw_screen_release()` previously loaded the main screen unconditionally before ordinary connection arbitration ran on the next loop. Also, HMI1/HMS1 could write `g_srvr_ok=true` even immediately after a live POLL reported `srvr=0`.

### Correction

- Firmware-screen release now chooses Main only when both CTRL link and SRVR state are live; otherwise it directly loads the resident boot splash with `Waiting for CTRL` or `Waiting for SRVR`.
- Once a POLL health hint has been seen, that hint is the freshest SRVR-presence authority. Negative HMI status is always accepted; positive HMI status cannot override a current negative POLL hint.

## Production lineage

Normalized `.06.06 -> .06.07` functional changes are limited to:

- SRVR `backend.py`: redundant heartbeat-return release beacon;
- CTRL firmware: session-independent bounded CTRL-TS fallback;
- CTRL-TS firmware: stale CTRL-progress recovery + stable splash arbitration.

W1P firmware is unchanged apart from release identity. Motion/calibration/limit/Leadshine/UI behavior is unchanged.

## Verification

The complete source/static regression suite passes, including:

- 370 EdgeBox integration checks;
- all historical RS485/update/safe-updater tests;
- `.06.03/.06.04` auto-update recovery contracts;
- `.06.05/.06.06` bench/CI contracts;
- new `.06.07` firmware/splash recovery contract;
- 53 build-pipeline checks;
- Modbus/wire/speed/motion contracts;
- release consistency, source hygiene, Python syntax and SRVR preflight.

Native firmware and frozen desktop compilation remain GitHub Actions gates.
