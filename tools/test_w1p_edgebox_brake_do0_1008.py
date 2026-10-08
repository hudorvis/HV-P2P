#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VER = '26.10.08.03'
W = (ROOT / f'HV_P2P_W1P_EDGEBOX_v{VER}' / f'HV_P2P_W1P_EDGEBOX_v{VER}.ino').read_text()
B = (ROOT / f'SRVR_GitHub_v{VER}' / 'backend.py').read_text()


def func(src: str, name: str) -> str:
    m = re.search(rf'(?m)^\s*(?:static\s+)?[\w:<>&* ]+\b{re.escape(name)}\s*\([^;]*?\)\s*\{{', src)
    assert m, f'missing function {name}'
    i = src.find('{', m.start(), m.end())
    depth = 0
    state = 'code'
    quote = ''
    j = i
    while j < len(src):
        c = src[j]
        d = src[j+1] if j+1 < len(src) else ''
        if state == 'code':
            if c == '/' and d == '/': state = 'line'; j += 2; continue
            if c == '/' and d == '*': state = 'block'; j += 2; continue
            if c in ('"', "'"): state = 'str'; quote = c; j += 1; continue
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0: return src[m.start():j+1]
            j += 1; continue
        if state == 'line':
            if c == '\n': state = 'code'
            j += 1; continue
        if state == 'block':
            if c == '*' and d == '/': state = 'code'; j += 2
            else: j += 1
            continue
        if c == '\\': j += 2; continue
        if c == quote: state = 'code'
        j += 1
    raise AssertionError(f'unclosed function {name}')

# Physical EdgeBox mapping and fail-safe polarity.
assert 'PIN_EDGEBOX_BRAKE_DO0 = 40' in W
assert 'pin 1=DO_24V, pin 3=DO_GND, pin 5=DO0' in W
assert 'EDGEBOX_BRAKE_RELEASE_ACTIVE_HIGH = true' in W
setup = func(W, 'setup')
first_brake_low = setup.index('digitalWrite(PIN_EDGEBOX_BRAKE_DO0, LOW);')
assert first_brake_low < setup.index('Serial.begin(115200);')
assert first_brake_low < setup.index('initEthernetStatic()')

# A new release requires healthy, fresh EL7 feedback plus native logical BRK-OFF.
start = func(W, 'edgeboxBrakeReleaseStartAllowed')
for token in (
    '!g_srvrFirmwareMatched', '!g.client_connected', '!g.rs_link_ok',
    '!g.communication_config_ok', '!g.drive_feedback_ok',
    '!softwareServoEnableReady()', '!g.servo_enabled_output',
    '!g.do4_brake_assignment_ok', '!g.brake_output_released',
    'g.fault_output_active', 'g.no_motion_feedback_fault',
):
    assert token in start, f'missing brake release gate {token}'

# Once released, an orderly Servo-OFF must preserve Leadshine brake timing rather
# than forcing the spring brake on before BRK-OFF clears.
hold = func(W, 'edgeboxBrakeReleaseHoldAllowed')
assert 'return g.brake_output_released;' in hold
assert 'edgeboxBrakeShutdownSequencingRequested()' in hold
assert 'EDGEBOX_BRAKE_STATUS_STALE_MS' in hold
inhibit = func(W, 'requestSoftwareSrvonInhibit')
assert 'setEdgeboxBrakeRelease(false' not in inhibit, 'Servo inhibit must not pre-empt EL7 BRK-OFF timing'
assert 'writeLeadshineSoftwareSrvonAssignment(false' in inhibit

# Only the brake-status register gets the faster transition poll; normal 10 Hz
# position/feedback polling stays unchanged.
assert 'MODBUS_POLL_MS = 100' in W
assert 'EDGEBOX_BRAKE_TRANSITION_POLL_MS = 25' in W
transition = func(W, 'serviceLeadshineBrakeTransitionStatus')
assert 'REG_OUTPUT_IO_STATUS' in transition and 'modbusReadU16' in transition
assert 'REG_MOTOR_POSITION_H' not in transition and 'modbusReadFeedbackBlock' not in transition
assert 'g.brake_output_released = ((outputIo & OUTPUT_DO4_MASK) != 0);' in transition
loop = func(W, 'loop')
assert loop.index('pollLeadshineFeedback();') < loop.index('serviceLeadshineBrakeTransitionStatus();') < loop.index('serviceEdgeboxBrakeOutput();')

# OTA/service operations must prove the command path stopped, native BRK-OFF off,
# and EdgeBox DO0 itself off before proceeding.
service = func(W, 'hvPrepareSafeServiceState')
assert 'requestSoftwareSrvonInhibit(true, "WEB_SERVICE")' in service
assert 'serviceEdgeboxBrakeOutput();' in service
assert '!servoEnabled && !brakeReleased && !g.edgebox_brake_released' in service
assert 'stableSamples >= 2' in service

# Telemetry separates EL7 logical sequencing from the physical EdgeBox command,
# and SRVR uses the physical command for the operator-facing brake state.
status = func(W, 'sendStatusLine')
assert 'BRAKE_OUT=' in status and 'BRAKE_DO0=' in status
assert '"BRAKE_OUT", "BRAKE_DO0"' in B
assert 'if "BRAKE_DO0" in fields: self.winch_brake_released' in B

print('W1P_EDGEBOX_BRAKE_DO0_1008_PASS')
