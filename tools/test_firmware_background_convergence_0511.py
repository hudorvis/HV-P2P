#!/usr/bin/env python3
"""v26.11.12.09 firmware convergence must not depend on the Qt event loop."""
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
VER = '26.11.12.09'
B = (ROOT/f'SRVR_GitHub_v{VER}/backend.py').read_text()
M = (ROOT/f'SRVR_GitHub_v{VER}/main.py').read_text()
C = (ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}/HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text()
W = (ROOT/f'HV_P2P_W1P_EDGEBOX_v{VER}/HV_P2P_W1P_EDGEBOX_v{VER}.ino').read_text()

# The authority HTTP endpoint must be up before backend network workers can emit
# the first release beacon.
assert M.index('authority = start_firmware_authority') < M.index('backend = HVP2PBackend')

# Presence and firmware discovery are one background comms responsibility.
assert 'FIRMWARE_BEACON_INTERVAL_S = 0.50' in B
worker = B[B.index('    def _srvr_alive_worker(self):'):B.index('    def _controller_worker(self):')]
for tok in ('b"SRVR_ALIVE\\n"', 'self._send_ctrl_firmware_beacon(force=True)',
            'self._send_w1p_firmware_beacon(force=True)', 'FIRMWARE_BEACON_INTERVAL_S'):
    assert tok in worker, tok

# The Qt tick must not be a prerequisite for firmware release discovery/order.
tick = B[B.index('    def _tick(self):'):B.index('    # --- config ---')]
assert '_send_ctrl_firmware_beacon' not in tick
assert '_send_w1p_firmware_beacon' not in tick

# The lightweight CTRL beacon retains release/session/final-stage coordinator data.
beacon = B[B.index('    def _send_ctrl_firmware_beacon'):B.index('    def _send_w1p_firmware_beacon')]
for tok in ('SRVR_FW|version=', 'session=', 'ts_allowed=', '_firmware_authority_session'):
    assert tok in beacon, tok

# W1P firmware state used for update ordering is parsed in its network thread,
# independently of Qt draining _w1p_rx.
client = B[B.index('class W1PClient'):B.index('class HVP2PBackend')]
for tok in ('def _update_firmware_snapshot', 'FW_MATCH', 'FW_AUTH', 'FW_PROGRESS|',
            'self._fw_authority = "updating" if active',
            'def firmware_snapshot', 'self._update_firmware_snapshot(line)'):
    assert tok in client, tok
allow = B[B.index('    def _ctrl_ts_update_allowed'):B.index('    def _limit_calibration_display_position')]
for tok in ('self.w1p.firmware_snapshot()', '(w1p_present or legacy_w1p_present or snapshot_fresh) and not w1p_current',
            '_w1p_fw_discovery_grace_s', '_w1p_fw_order_pending', '_w1p_fw_order_absent_timeout_s'):
    assert tok in allow, tok


# Normal present W1P discovery gets a bounded grace before the final CTRL-TS
# grant, preventing a startup race where CTRL converges before the first W1P
# STATUS. A genuinely absent W1P still releases the final stage automatically.
assert 'self._w1p_fw_discovery_grace_s = 3.0' in B
assert '(now_wall - matched_since) < self._w1p_fw_discovery_grace_s' in allow
assert 'snapshot_fresh' in allow

# Graceful SRVR shutdown must make SRVR_OFFLINE the last CTRL presence packet.
# A background firmware-beacon worker waiting on the TX lock re-checks stop under
# that same lock and therefore cannot resurrect the session after OFFLINE.
assert 'if self.smoke_test or self._stop_evt.is_set()' in beacon
assert 'with self._ctrl_presence_tx_lock:' in beacon
assert 'if self._stop_evt.is_set():\n                    return' in beacon
shutdown = B[B.index('    def _send_srvr_offline'):]
assert 'self._stop_evt.set(); self._freed_in_stop.set()' in shutdown
assert 'self._send_srvr_offline()' in shutdown
assert shutdown.index('self._stop_evt.set(); self._freed_in_stop.set()') < shutdown.index('self._send_srvr_offline()')

# New SRVR process/session is itself an authority boundary. Same-version stale
# matches must be re-verified by manifest+running-image SHA, not inherited.
apply = C[C.index('static bool applySrvrFirmwareBeacon'):C.index('static String buildHmiStatePacketFromSrvr')]
for tok in ('const bool newSession', 'const bool releaseChanged',
            'if(releaseChanged || newSession)', 'authority_session_changed',
            'g_srvrFirmwareMatched = false;', 'g_fwAuthorityLastAttemptMs = 0;'):
    assert tok in apply, tok

# Exercise the exact CTRL beacon handler with a host clock and verify that
# incoming keepalives do not reset the HTTP backoff of an unmatched node.
fixture = r'''
#include <cassert>
#include <cstdint>
#include <string>
struct String : std::string {
    using std::string::string;
    String() = default;
    String(const std::string& value) : std::string(value) {}
    bool startsWith(const char* value) const { return rfind(value, 0) == 0; }
};
static String hvGetPipeField(const String& line, const char* key) {
    const auto prefix = std::string("|") + key + "=";
    const auto start = line.find(prefix);
    if (start == String::npos) return "";
    const auto value = start + prefix.size();
    return line.substr(value, line.find('|', value) - value);
}
struct {
    template<typename... Args> void printf(const char*, Args...) {}
} Serial;
static String g_srvrFirmwareSession, g_srvrAdvertisedRelease, g_srvrFirmwareState;
static const char* HV_AUTH_VERSION = "v26.11.12.09";
static bool srvrOnline, g_hmiTsCoordinatorSeen, g_hmiTsUpdateAllowed;
static bool g_hmiSafeUpdateContinuation, g_srvrFirmwareMatched = true;
static uint32_t g_lastSrvrRxMs, g_hmiMismatchSinceMs;
static uint32_t g_fwAuthorityLastAttemptMs, g_fwAuthorityRetryDelayMs, g_fwAuthorityFastRetryUntilMs;
static uint32_t clockMs = 1000;
static uint32_t millis() { return clockMs; }
'''
cases = r'''
int main() {
    const String mismatched = "SRVR_FW|version=v26.11.12.05|session=abc|ts_allowed=0";
    assert(applySrvrFirmwareBeacon(mismatched));
    assert(!g_srvrFirmwareMatched && g_fwAuthorityRetryDelayMs == 0);
    assert(g_srvrFirmwareState == "authority_changed");
    g_fwAuthorityLastAttemptMs = 1000;
    g_fwAuthorityRetryDelayMs = 30000;
    clockMs = 1500;
    assert(applySrvrFirmwareBeacon(mismatched));
    assert(srvrOnline && g_lastSrvrRxMs == clockMs);
    assert(g_fwAuthorityLastAttemptMs == 1000 && g_fwAuthorityRetryDelayMs == 30000);
    assert(applySrvrFirmwareBeacon("SRVR_FW|version=v26.11.12.09|session=abc|ts_allowed=1"));
    assert(g_fwAuthorityLastAttemptMs == 0 && g_fwAuthorityRetryDelayMs == 0 && g_hmiTsUpdateAllowed);
    g_srvrFirmwareMatched = true;
    assert(applySrvrFirmwareBeacon("SRVR_FW|version=v26.11.12.09|session=def|ts_allowed=0"));
    assert(!g_srvrFirmwareMatched && !g_hmiTsUpdateAllowed);
}
'''
with TemporaryDirectory(prefix="hvp2p-ctrl-beacon-") as tmp:
    source = Path(tmp) / "beacon.cpp"
    binary = Path(tmp) / "beacon"
    source.write_text(fixture + apply + cases, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

wcmd = W[W.index('if (line.startsWith("SRVR_FW|"))'):W.index('if (line.startsWith("DSP1|"))')]
for tok in ('const bool newSession', 'const bool releaseChanged',
            '(releaseChanged || newSession)', 'authority_session_changed',
            'g_srvrFirmwareMatched = false;', 'driveStopNow();'):
    assert tok in wcmd, tok

# Existing independent safety boundaries remain unchanged.
assert 'static const uint32_t W1P_VEL_COMMAND_TIMEOUT_MS = 500;' in W
assert 'VEL_KEEPALIVE_S = 0.15' in B
assert 'SRVR_ALIVE_INTERVAL_S = 0.25' in B
assert '#define SRVR_PEER_TIMEOUT_MS     750' in C

print('FIRMWARE_BACKGROUND_CONVERGENCE_0511_PASS')
