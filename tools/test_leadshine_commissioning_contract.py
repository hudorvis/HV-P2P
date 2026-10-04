#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
W=(ROOT/'HV_P2P_W1P_EDGEBOX_v26.10.04.06/HV_P2P_W1P_EDGEBOX_v26.10.04.06.ino').read_text()
for tok in ('RS485_BAUD = 115200','DRIVE_MODBUS_ID = 1','SERIAL_8N1','MODBUS_INTERFRAME_GAP_US = 2000','W1P_VEL_COMMAND_TIMEOUT_MS = 500'):
    assert tok in W,tok
for tok in ('EXPECTED_RS485_MODE = 4','EXPECTED_RS485_BAUD_CODE = 6','EXPECTED_RS485_ADDRESS = 1'):
    assert tok in W,tok
assert 'configReadContinue' in W and 'if(!transportAlive){ ok = false; return false; }' in W
assert 'if(g.last_modbus_exception != 0) return true;' in W and 'transportAlive = false;' in W
for tok in ('leadshineFactoryProbeSafe','38400, SERIAL_8N2','probing EL7 factory 38400 8N2 read-only','startDriveSerialConfig(RS485_BAUD, SERIAL_8N1)','g.rs_link_ok = savedLink','FACTORY_COMMS='):
    assert tok in W,tok
safe=W[W.index('static bool leadshineFactoryProbeSafe'):W.index('static void startDriveSerialConfig')]
for tok in ('!g.drive_writes_enabled','g.software_srvon_inhibit','!hvServiceOperationActive','g.vel_request_mps','g.vel_profile_mps','g.vel_cmd_mps','g.vel_actual_mps'):
    assert tok in safe,tok
# Factory probe is diagnostic and must restore saved health rather than promoting it.
probe=W[W.index('static void serviceLeadshineFactoryCommsProbe'):W.index('static void pollLeadshineFeedback')]
assert probe.index('startDriveSerialConfig(38400, SERIAL_8N2)') < probe.index('startDriveSerialConfig(RS485_BAUD, SERIAL_8N1)')
assert 'g.rs_link_ok = savedLink;' in probe
print('LEADSHINE_COMMISSIONING_CONTRACT_PASS')
