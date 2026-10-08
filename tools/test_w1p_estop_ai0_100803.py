#!/usr/bin/env python3
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.08.03'
W=(ROOT/f'HV_P2P_W1P_EDGEBOX_v{VER}'/f'HV_P2P_W1P_EDGEBOX_v{VER}.ino').read_text()

def func(src,name):
    m=re.search(rf'(?m)^\s*(?:static\s+)?[\w:<>&* ]+\b{re.escape(name)}\s*\([^;]*?\)\s*\{{',src); assert m
    i=src.find('{',m.start(),m.end()); depth=0; state='code'; quote=''; j=i
    while j<len(src):
        c=src[j]; d=src[j+1] if j+1<len(src) else ''
        if state=='code':
            if c=='/' and d=='/': state='line'; j+=2; continue
            if c=='/' and d=='*': state='block'; j+=2; continue
            if c in ('"',"'"): state='str'; quote=c; j+=1; continue
            if c=='{': depth+=1
            elif c=='}':
                depth-=1
                if depth==0:return src[m.start():j+1]
            j+=1; continue
        if state=='line':
            if c=='\n': state='code'
            j+=1; continue
        if state=='block':
            if c=='*' and d=='/': state='code'; j+=2
            else:j+=1
            continue
        if c=='\\': j+=2; continue
        if c==quote: state='code'
        j+=1
    raise AssertionError(name)

assert 'LOCAL_ESTOP_BYPASS' not in W
assert '#include <Wire.h>' in W
for tok in (
    'W1P_AI_ADC_ADDR = 0x48',
    'W1P_SGM_CONFIG_AI0_CONT_800SPS_6V144 = 0x40E3',
    'W1P_ESTOP_HEALTHY_MIN_V = 3.5f',
    'W1P_ESTOP_HEALTHY_MAX_V = 6.0f',
    'W1P_ESTOP_HEALTHY_CONFIRM_SAMPLES = 3',
    'W1P_ESTOP_SAMPLE_INTERVAL_MS = 10',
    'bool local_estop = true',
): assert tok in W,tok
assert 'PIN_LOCAL_ESTOP' not in W and 'LOCAL_ESTOP_HEALTHY_LEVEL' not in W

init=func(W,'initW1pEstopAI0')
for tok in ('g.local_estop = true','W1P_SGM_REG_CONFIG1','W1P_SGM_CONFIG_AI0_CONT_800SPS_6V144','waiting for 3 healthy samples'):
    assert tok in init,tok

update=func(W,'updateLocalInputs')
for tok in (
    'w1pSgmReadRegister(W1P_SGM_REG_CONFIG, cfg)',
    'w1pSgmReadConversion(raw)',
    'g_w1pEstopFieldV = adcV * 2.0f',
    'g_w1pEstopFieldV >= W1P_ESTOP_HEALTHY_MIN_V',
    'g_w1pEstopFieldV <= W1P_ESTOP_HEALTHY_MAX_V',
    'g_w1pEstopHealthySamples = 0',
    'active = true',
    'driveStopNow();',
    'g.drive_writes_enabled = false',
    'requestSoftwareSrvonInhibit(true, "W1P_ESTOP")',
): assert tok in update,tok
assert 'active = g_w1pEstopHealthySamples < W1P_ESTOP_HEALTHY_CONFIRM_SAMPLES' in update
assert 'initW1pEstopAI0()' in update  # bounded ADC recovery remains fail-closed until re-proven

start=func(W,'edgeboxBrakeReleaseStartAllowed')
assert 'if (g.local_estop) return false;' in start
shutdown=func(W,'edgeboxBrakeShutdownSequencingRequested')
assert 'g.local_estop' in shutdown
setup=func(W,'setup')
for tok in ('g.local_estop = true','Wire.begin(EDGEBOX_I2C_SDA, EDGEBOX_I2C_SCL)','initW1pEstopAI0();','AI0 pin 14 / AGND pin 12','open/low/mid-band/ADC fault unsafe'):
    assert tok in setup,tok
print('W1P_ESTOP_AI0_100803_PASS')

# Host-side threshold/debounce sanity for the exact firmware constants.
def step(field_v, healthy_count, active):
    healthy = 3.5 <= field_v <= 6.0
    if healthy:
        healthy_count = min(3, healthy_count + 1)
        active = healthy_count < 3
    else:
        healthy_count = 0
        active = True
    return healthy_count, active

cnt, active = 0, True
for _ in range(2):
    cnt, active = step(5.0, cnt, active)
    assert active
cnt, active = step(5.0, cnt, active)
assert not active and cnt == 3
cnt, active = step(0.0, cnt, active)
assert active and cnt == 0
for bad in (3.49, 6.01):
    cnt, active = step(bad, 3, False)
    assert active and cnt == 0
raw_for_5v_field = (5.0 / 2.0) / 6.144 * 32768.0
reconstructed = raw_for_5v_field * (6.144 / 32768.0) * 2.0
assert abs(reconstructed - 5.0) < 1e-6
print('W1P_ESTOP_AI0_SEMANTICS_PASS raw5v=%.1f' % raw_for_5v_field)
