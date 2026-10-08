#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
W=(ROOT/'HV_P2P_W1P_EDGEBOX_v26.10.08.03/HV_P2P_W1P_EDGEBOX_v26.10.08.03.ino').read_text()
for tok in ('RS485_BAUD = 38400','DRIVE_MODBUS_ID = 1','SERIAL_8N2','MODBUS_INTERFRAME_GAP_US = 2000','W1P_VEL_COMMAND_TIMEOUT_MS = 500'):
    assert tok in W,tok
for tok in ('EXPECTED_RS485_MODE = 5','EXPECTED_RS485_BAUD_CODE = 4','EXPECTED_RS485_ADDRESS = 1'):
    assert tok in W,tok
assert 'P05.29, expected 5 = 8N2 (factory default)' in W
assert 'P05.30, expected 4 = 38400 (factory default)' in W
assert 'configReadContinue' in W and 'if(!transportAlive){ ok = false; return false; }' in W
assert 'if(g.last_modbus_exception != 0) return true;' in W and 'transportAlive = false;' in W
for tok in ('leadshineFactoryProbeSafe','115200, SERIAL_8N1','probing prior HV setting 115200 8N1 read-only','startDriveSerialConfig(RS485_BAUD, SERIAL_8N2)','g.rs_link_ok = savedLink','FACTORY_COMMS='):
    assert tok in W,tok
safe=W[W.index('static bool leadshineFactoryProbeSafe'):W.index('static void startDriveSerialConfig')]
for tok in ('!g.drive_writes_enabled','g.software_srvon_inhibit','!hvServiceOperationActive','g.vel_request_mps','g.vel_profile_mps','g.vel_cmd_mps','g.vel_actual_mps'):
    assert tok in safe,tok
probe=W[W.index('static void serviceLeadshineFactoryCommsProbe'):W.index('static void pollLeadshineFeedback')]
assert probe.index('startDriveSerialConfig(115200, SERIAL_8N1)') < probe.index('startDriveSerialConfig(RS485_BAUD, SERIAL_8N2)')
assert 'g.rs_link_ok = savedLink;' in probe
assert 'P05.29=5, P05.30=4, P05.31=1' in probe
print('LEADSHINE_COMMISSIONING_CONTRACT_PASS')
