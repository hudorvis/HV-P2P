# HV P2P v26.10.05.01 deep code audit

Date: 2026-10-05

## Scope

This audit starts from the authoritative `v26.10.04.07` source and follows the reported bench mismatches end-to-end through SRVR, CTRL and CTRL-TS: firmware authority/update ordering, system-status ownership, live motion cadence, geometry/state packet semantics and the Limit Calibration renderer.

## Confirmed root causes

### A. CTRL progress could be suppressed by an outstanding touchscreen transaction

CTRL's SRVR-authority updater is intentionally blocking while the HTTP image is downloaded/staged. If it entered that operation with a POLL outstanding, `reportCtrlAuthorityUpdateProgress()` correctly refused to transmit firmware status on the half-duplex bus. Because the updater was blocking, the delayed touchscreen response was not serviced, leaving progress suppressed for the transfer.

Correction: an explicit `g_ctrlAuthorityUpdatePending` state quiesces normal HMI HELLO/POLL work and defers the authority download until the outstanding transaction and recovery quiet period have cleared. Progress is rate-limited and can then use the free bus.

### B. CTRL-TS could be allowed to update before external nodes had converged

A fresh SRVR may hear CTRL before W1P's first STATUS packet. The coordinator now requires current/fresh CTRL firmware before advertising W1P authority and before granting `fw_ts_allowed`; if no W1P is present, a short CTRL-current discovery window is allowed before CTRL-TS is released. CTRL's HMI updater requires an explicit coordinator grant.

Legacy browser-push OTA is restricted to firmware `<= 26.10.01.01`; modern firmware uses the SRVR authority pull/verify path.

### C. Geometry packets caused false Active status

HMG1 does not carry system status, but the CTRL-TS parser previously ran the generic missing-status fallback on it. That fallback set Active. The next HMS1/HMI1 restored Uncalibrated, causing the observed alternating banner.

Correction: only state/bulk packets may change status. HMG1 and HMM1 are explicitly status-neutral.

### D. Human `|` separators conflict with the pipe-delimited transport

SRVR correctly escaped `|` to `/` for wire safety, but CTRL-TS then displayed or re-prefixed the slash form inconsistently. Long status text could also exceed the previous field allowance.

Correction: SRVR owns one canonical vocabulary; the wire form is escaped safely and CTRL-TS normalizes `System / ` and `E-Stop / ` back to the canonical display form. Status capacity is increased for the longest approved descriptions.

### E. CTRL-TS live position was limited by the 4 Hz bulk frame

The 4 Hz cap is appropriate for the ~900-byte HMI snapshot but too coarse for the visible moving marker. The new HMM1 packet carries only verified motion data at approximately 10-12.5 Hz. The touchscreen interpolates over 90 ms between received points; no predictive/extrapolated position is invented.

### F. Limit Calibration Side View was over-constrained

The full Side View geometry was rendered in a 64 px-high compact slot. Tower and cable geometry therefore competed for insufficient vertical space, producing the reported strong diagonal distortion and tower clipping.

Correction: the wizard keeps the approved Joystick-style 720x540 shell but gives the compact position graph an 84 px viewport with a reserved top band and fully bounded tower/cable geometry.

## Status precedence after correction

1. E-stop/fault -> `E-Stop | <source>` / red.
2. Joystick Calibration -> `System | Joystick Calibration` / yellow.
3. Limit or Winch Calibration -> corresponding `System | ...` / yellow.
4. Battery Change -> `System | Battery Change Mode` / yellow.
5. Not calibrated -> `System | Uncalibrated` / yellow.
6. Otherwise -> `System | Active` / green.

CTRL-TS consumes this status; HMG1/HMM1 cannot override it.

## RS485 bandwidth/scheduling review

- POLL cadence remains 60 ms.
- Normal POLL response timeout remains 250 ms.
- Late-response/recovery silence remains 300 ms.
- Bulk HMI remains 250 ms / 4 Hz maximum.
- HMM1 motion minimum interval is 80 ms, with 250 ms keepalive.
- Firmware transfer remains exclusive.
- No new POLL, state, geometry, motion or bulk frame may overlap an outstanding transaction.

The compact motion packet is materially smaller than the bulk dashboard and is scheduled through the same `hmiNormalTxAllowed()` single-flight arbiter.

## Preserved safety architecture

No change to W1P's independent 500 ms VEL freshness watchdog, SRVR's ~150 ms non-zero VEL refresh, physical E-stop mapping, hard limits, predictive stopping/dynamic soft limits, Leadshine velocity architecture or W1P Servo-Enable safety ownership.

## Remaining intentional updater limitation

The physical CTRL-TS cannot safely show its own live 0-100% flash percentage with the present safe updater because RGB/LVGL/PSRAM are deliberately not initialized during application-partition programming. It may show CTRL/W1P progress and the safe-updater handoff beforehand; during CTRL-TS self-flash the panel is intentionally black and SRVR is authoritative for percentage. Changing that would require a different resident updater architecture rather than re-enabling the previously unstable live-display flash path.
