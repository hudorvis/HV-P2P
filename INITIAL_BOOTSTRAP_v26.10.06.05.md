# HV P2P v26.10.06.05 initial / recovery bootstrap

## Required recovery from v26.10.02.03 CTRL-TS

Do **not** ask a `.03` CTRL-TS to auto-install `.04`. `.03` is now classified as
`safe_ota=1`; `.04` requires `safe_ota=2` because bench testing found a reboot-
starvation race in the level-1 handoff.

Recommended recovery order:

1. Build v26.10.06.05 in GitHub Actions.
2. Update CTRL to the GitHub-produced `.04` firmware/staged source.
3. CTRL `.04` may report the `.03` touchscreen as **manual bootstrap required**;
   this is intentional and fail-safe.
4. Manually USB/Arduino flash CTRL-TS `.04` once using the matching GitHub build.
5. Power-cycle CTRL and CTRL-TS, then run SRVR `.04`.
6. Confirm CTRL-TS HELLO reports `safe_ota=2`, correct hardware/protocol/version,
   and normal UI returns.
7. A manual Arduino flash may initially have no stored exact image SHA. CTRL can
   therefore perform a same-version `.04` repair update after bootstrap; this is
   allowed and is the first useful bench test of the corrected safe updater.

From `.04` onward, future compatible releases may use the automatic headless
CTRL-TS updater.

## Expected safe self-update sequence after .04 bootstrap

- dashboard shows `Preparing safe updater - SRVR shows self-flash progress` for about 1.8 s;
- receiver acknowledges once and keeps the original 350 ms reboot deadline;
- CTRL suppresses HMI rediscovery for about 3.0 s;
- display is blanked/reset and the touchscreen software-restarts;
- headless boot does not initialize RGB/LVGL/PSRAM/touch/second CH422G path;
- CTRL resumes HELLO after the hold, sees `safe_ota=2`, and starts the real block
  transfer;
- image size and SHA-256 are verified, then CTRL-TS reboots normally.

If no transfer starts in headless mode for 60 s, CTRL-TS returns to its known-good
normal application.
