#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
VER = "26.09.15.01"
CTRL_DIR = ROOT / f"HV_P2P_CTRL_EDGEBOX_v{VER}"
W1P_DIR = ROOT / f"HV_P2P_W1P_EDGEBOX_v{VER}"
SRVR_DIR = ROOT / f"SRVR_GitHub_v{VER}"
ctrl = (CTRL_DIR / f"HV_P2P_CTRL_EDGEBOX_v{VER}.ino").read_text(errors="replace")
w1p = (W1P_DIR / f"HV_P2P_W1P_EDGEBOX_v{VER}.ino").read_text(errors="replace")
hc = (CTRL_DIR / "HV_P2P_SRVR_Authority_OTA.h").read_text(errors="replace")
hw = (W1P_DIR / "HV_P2P_SRVR_Authority_OTA.h").read_text(errors="replace")
fa = (SRVR_DIR / "firmware_authority.py").read_text(errors="replace")
main = (SRVR_DIR / "main.py").read_text(errors="replace")
backend = (SRVR_DIR / "backend.py").read_text(errors="replace")

checks: list[tuple[str, bool]] = []
def ck(name: str, cond: bool) -> None:
    checks.append((name, bool(cond)))

# Shared transport/validation client.
ck("CTRL/W1P authority headers byte-identical", hc == hw)
ck("authority SHA helper avoids Arduino Print.h HEX macro collision", 'static const char* HEX =' not in hc and 'HEX_DIGITS' in hc)
ck("authority port pinned 8088", "HV_SRVR_FIRMWARE_PORT = 8088" in hc)
ck("manifest endpoint is role-specific", '"/firmware/" + roleLower + "/manifest"' in hc)
ck("manifest enforces SRVR authority/schema and EdgeBox target", 'out.schema != 1' in hc and 'out.authority != "HV_P2P_SRVR"' in hc and 'out.target != "EDGEBOX_ESP100"' in hc)
ck("manifest enforces release/role token", 'HV_P2P_FW_ROLE=' in hc and 'HV_P2P_FW_VERSION=' in hc)
ck("manifest enforces target token", 'HV_P2P_FW_TARGET=EDGEBOX_ESP100;' in hc)
ck("four-part numeric version comparator", "hvAuthorityCompareVersions" in hc and "uint32_t parts[4]" in hc)
ck("running partition exact-size SHA verification", "esp_ota_get_running_partition" in hc and "expectedSize" in hc and "hvAuthorityShaHex" in hc)
ck("download Content-Length exact", "http.getSize() != (int)manifest.size" in hc)
ck("download writes inactive OTA partition", "Update.begin(manifest.size, U_FLASH)" in hc)
ck("download verifies complete SHA before finalize", hc.find("hvAuthorityShaHex(digest) != manifest.sha256") < hc.find("Update.end(true)"))
ck("download verifies embedded role/version before finalize", hc.find("!identity.found") < hc.find("Update.end(true)"))
ck("download verifies embedded target before finalize", hc.find("!target.found") < hc.find("Update.end(true)"))
ck("invalid/interrupted image aborts", "Update.abort();" in hc and "image download interrupted/timeout" in hc)

# CTRL authority and CTRL->CTRL-TS sequencing.
ck("CTRL boots authority-unmatched", "g_srvrFirmwareMatched = false" in ctrl)
ck("CTRL/W1P retain EdgeBox target token for compiled-image verification", 'HV_UPDATE_TARGET_SIGNATURE = "HV_P2P_FW_TARGET=EDGEBOX_ESP100;"' in ctrl and 'Hardware target: %s\\n", HV_UPDATE_TARGET_SIGNATURE' in ctrl and 'Hardware target: %s\\n", HV_UPDATE_TARGET_SIGNATURE' in w1p)
ck("CTRL authority hold asserts existing E-stop flag", "if(!g_srvrFirmwareMatched) flags |= FLAG_ESTOP_PRESSED;" in ctrl)
ck("CTRL fetches CTRL-only manifest", 'hvAuthorityFetchManifest(server_IP, "CTRL"' in ctrl)
ck("CTRL refuses newer-to-older automatic downgrade", "automatic downgrade REFUSED" in ctrl and "newer_than_srvr" in ctrl)
ck("CTRL equal-version requires running SHA match", "hvAuthorityRunningImageSha(manifest.size" in ctrl and "runningSha == manifest.sha256" in ctrl)
ck("CTRL mismatched/older image uses authority downloader", "hvAuthorityDownloadAndStage(server_IP, manifest, reason)" in ctrl)
ck("CTRL-TS updater waits for SRVR match", "HV_CTRL_TS_IMAGE_AVAILABLE && g_srvrFirmwareMatched" in ctrl and "must first match the SRVR-authoritative" in ctrl)

# W1P fail-closed safety integration.
ck("W1P boots firmware authority hold", "bool firmware_authority_hold = true" in w1p)
ck("W1P boots software Servo Enable inhibited", "bool software_srvon_inhibit = true" in w1p)
ck("W1P refuses newer-to-older automatic downgrade", "automatic downgrade REFUSED" in w1p and "newer_than_srvr" in w1p)
ck("W1P update defers during any motion path", "deferred_motion" in w1p and "fabsf(g.vel_actual_mps) > 0.05f" in w1p)
ck("W1P OTA reuses stopped/braked service gate", "hvPrepareSafeServiceState(safeReason)" in w1p and "hvAuthorityDownloadAndStage(SRVR_IP, manifest, reason)" in w1p)
ck("W1P authority hold blocks auto drive enable", "if (g.firmware_authority_hold) return false;" in w1p)
ck("W1P authority hold blocks SW_SRVON command", "g.service_rearm_required || g.firmware_authority_hold || hvServiceOperationActive" in w1p)
ck("W1P authority hold participates in safety loss", "g.service_rearm_required || g.firmware_authority_hold || !g.client_connected" in w1p)
ck("W1P heartbeat cannot clear Servo inhibit during hold", "!g.local_estop && !g.firmware_authority_hold" in w1p)
ck("W1P independent 650ms VEL watchdog preserved", "W1P_VEL_COMMAND_TIMEOUT_MS = 650" in w1p and "lastVelocityCommandMs" in w1p)
ck("W1P status exposes authority hold", "FW_MATCH=" in w1p and "FW_AUTH=" in w1p and "FW_AUTHORITY" in w1p)
ck("SRVR treats missing/false W1P authority match fail-closed", 'fields.get("FW_MATCH", "0") != "1"' in backend and "self.winch_fw_authority_hold" in backend)
ck("SRVR clears stale W1P session health on HELLO", 'self.winch_fw_authority_state = "awaiting_status"' in backend and 'self._w1p_status_last_seen = 0.0' in backend and 'self.winch_rs_status = "Disconnected"' in backend)
ck("SRVR safety requires fresh full W1P STATUS", 'def _w1p_status_fresh(self)' in backend and 'or (not self._w1p_status_fresh())' in backend and 'def rs485Connected(self): return bool(self._w1p_status_fresh()' in backend)
ck("SRVR malformed W1P STATUS stays fail-closed", 'self.winch_fw_authority_state = "invalid_status"' in backend and 'Rejected malformed STATUS; safety hold retained' in backend)

# SRVR immutable authority runtime + locked UI preservation.
ck("SRVR runtime starts authority before backend", main.find("firmware_service.start()") < main.find("backend = HVP2PBackend"))
ck("SRVR startup fails closed without valid bundle", "FIRMWARE AUTHORITY STARTUP FAIL" in main and "return 4" in main)
ck("authority server exposes only exact immutable role routes", all(x in fa for x in ('/firmware/manifest','/firmware/{role.lower()}','path == prefix + "/manifest"','path == prefix + "/image"')))
locked = hashlib.sha256((SRVR_DIR / "qml" / "Main.qml").read_bytes()).hexdigest() == "60edb4348c98827902f21006ffa4e4aa274e65d0527f32782f5f3de97bead93e" and hashlib.sha256((SRVR_DIR / "qml" / "pages" / "SetupPage.qml").read_bytes()).hexdigest() == "9cede2819a4c7d931247121711d2441e01537fdd05c804b0fc646caa5fded7fd"
ck("approved Run and Setup UI byte hashes unchanged", locked)

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("OK  " if ok else "FAIL") + name)
if len(checks) != 42:
    raise SystemExit(f"OTA_CONTRACT_TEST_DEFINITION_ERROR expected 42 checks, got {len(checks)}")
if failed:
    raise SystemExit("SRVR_AUTOMATIC_OTA_CONTRACT_FAIL: " + ", ".join(failed))
print("SRVR_AUTOMATIC_OTA_CONTRACT_PASS (42/42)")
