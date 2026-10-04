# HV P2P v26.10.04.04 — Settings, Battery Change, firmware, Virtual and limit/ramp audit

Date: 2026-10-04

Authoritative base: `HV P2P v26.10.04.03 - GitHub Ready Source.zip`.

## 1. Battery Change Settings dropdown

The live backend state and Setup mirror were already synchronised in `.04.03`, but Qt Quick `ComboBox.currentIndex` is writable by the control itself. Relying only on an inline `currentIndex:` expression is unnecessarily fragile after local user interaction.

Correction: Battery Change and Acceleration Mode now use explicit live `Binding` objects targeting their ComboBox `currentIndex`. CTRL-TS AUX actions and automatic mode changes therefore always converge the visible dropdown to backend truth.

## 2. Battery Change semantics

Battery Change is a service override, not a second normal drive profile. It caps requested speed to 5 km/h and bypasses only the normal software Near/Far ramp/predictive envelope so the skate can deliberately travel beyond either saved limit for service. Independent E-stop/link/firmware/W1P-watchdog protections remain active.

Auto-cancel is stateful: the skate must first travel more than 50 mm outside the calibrated span. The mode stays active until it returns at least 20 mm inside. This prevents Battery Change from cancelling immediately when enabled while the skate begins inside the span.

The distance contract is signed: `To Near = Position - Near`, `To Far = Far - Position`. Therefore `To Near + To Far = Far - Near` at every position, including outside the span. A Near excursion makes `To Near` negative and increases `To Far`; a Far excursion behaves symmetrically.

## 3. Firmware readouts

CTRL and W1P use one version-or-progress value property. CTRL reports authority-update progress back to SRVR; W1P reports its existing `FW_PROGRESS`. CTRL-TS uses a single Firmware readout rather than separate Detected / Required / Update rows. Firmware authority and compatibility logic are unchanged.

## 4. Virtual mode

Virtual is intentionally independent of W1P presence. SRVR integrates the simulated position from the same requested velocity after normal joystick/deadband/drive-mode/ramp/predictive processing. `_send_velocity()` stores virtual velocity locally and never sends non-zero W1P VEL. `_virtual_output_inhibit()` positively sends STOP + SW_SRVON 0 to any physical W1P that happens to be connected.

Thus Virtual can test the normal end-limit/ramp behavior without W1P, and can also exercise Battery Change excursions outside limits without moving hardware.

## 5. Near/Far/ramping display audit

Before `.04.04`, SRVR sent physical ramp lengths and each renderer converted them to pixels/fractions separately. The conversion was mathematically similar, but it left multiple authorities and allowed stale Distance/Percentage secondary values after the calibrated span changed.

Correction:

1. `_ramp_distance()` now returns the effective physical distance clamped to the current span.
2. `_sync_ramp_representations_for_span()` keeps Distance and Percentage equivalent after ramp edits and after Near/Far limit edits/calibration.
3. `nearRampFraction` / `farRampFraction` are calculated once by SRVR from that effective geometry.
4. DSP/HMS state carries `ramp_near_frac` / `ramp_far_frac` to CTRL-TS.
5. Every SRVR SpanDiagram receives the same fractions.
6. CTRL-TS ramp wedges consume those fractions directly, with backward fallback to distance/span for an older packet.
7. CTRL-TS position/reference/preset centres use the same exact endpoint coordinate as SRVR: 0% = Near line, 100% = Far line.

This makes ramp zones identical whether the operator enters, for example, `10.00 m` on a 100 m span or `10.00 %`. Both resolve to the same 0.10 normalized boundary in all progress/travel displays.

## 6. Safety boundary

No W1P watchdog, Leadshine register/velocity architecture, AI0/AI1 mapping, physical E-stop behavior, predictive stopping constants, CTRL↔CTRL-TS single-flight scheduling or safe updater behavior was relaxed by this revision.

## Verification boundary

Static/regression coverage now includes persistent live Settings bindings, signed distance contract, effective ramp clamping/synchronisation, shared SRVR ramp fractions and CTRL-TS endpoint alignment. Native Arduino compilation and frozen PySide runtime remain GitHub Actions gates; physical movement remains a bench commissioning gate.
