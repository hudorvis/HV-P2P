# HV P2P 26.08.31 Native-Build Revision History

- **v26.08.31.01** — commissioning/native-build baseline.
- **v26.08.31.02** — generated LVGL configuration and required font set for CI.
- **v26.08.31.03** — ESP32 Arduino 3.3.8 / LVGL compile compatibility corrections.
- **v26.08.31.04** — CTRL-TS OTA block-handler const-correctness and `Update.write` compatibility.
- **v26.08.31.05** — `Waveshare_ST7262_LVGL` / `ESP32_IO_Expander 0.0.3` CH422G address-symbol compatibility patch; CI fails closed if the expected vendor API is absent.
- **v26.08.31.06** — unified root GitHub Actions workflow builds the complete matched release: native CTRL-TS/CTRL/W1P firmware, macOS Intel SRVR app, and combined complete-release artifact. This is the audited authoritative pre-fix baseline.
- **v26.08.31.07** — first audit safety/build hardening set: independent 650 ms W1P VEL-command deadman; fail-closed W1P OTA/reboot/NVS safe-service gate; CTRL/W1P app OTA content-role verification; exact Waveshare dependency commit pin. Approved SRVR/CTRL-TS visual design unchanged.
- **v26.08.31.08** — completes remaining v26.08.31.06 audit recommendations: transactional safe W1P local-IP readdress from the existing SRVR Setup field, including lost-ACK verification and automatic previous-IP rollback; atomic/recoverable SRVR `config.json`; true Free-D `u24` lens output; incoming Free-D checksum validation; stable/versioned macOS bundle metadata; and exact Complete Release ZIP/SRVR-ZIP preservation with internal/external SHA-256 manifests. Approved SRVR/CTRL-TS visual design unchanged.
- **v26.08.31.09** — locked SRVR Run/Setup operator revision: two-line HV P2P/SRVR logo, five-second two-step confirmation for Run Save/Recall/Slip actions, corrected Run System/Position alignment, revised Setup diagnostics/CTRL-TS presentation and evenly spaced Motion Profiles divider, plus a fail-safe SRVR Virtual Position Source for CTRL/CTRL-TS demonstrations with physical W1P velocity output and software Servo Enable inhibited. CTRL/W1P firmware now report their actual firmware identity to SRVR Setup. Free-D, Log and CTRL-TS operator layouts remain unchanged.
