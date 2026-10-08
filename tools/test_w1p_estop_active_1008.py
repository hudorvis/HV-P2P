#!/usr/bin/env python3
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.08.02'
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
assert 'PIN_LOCAL_ESTOP = 4' in W and 'LOCAL_ESTOP_HEALTHY_LEVEL = HIGH' in W
update=func(W,'updateLocalInputs')
for tok in ('digitalRead(PIN_LOCAL_ESTOP)','raw != LOCAL_ESTOP_HEALTHY_LEVEL','driveStopNow();','g.drive_writes_enabled = false','requestSoftwareSrvonInhibit(true, "W1P_ESTOP")'):
    assert tok in update,tok
start=func(W,'edgeboxBrakeReleaseStartAllowed')
assert 'if (g.local_estop) return false;' in start
shutdown=func(W,'edgeboxBrakeShutdownSequencingRequested')
assert 'g.local_estop' in shutdown
setup=func(W,'setup')
assert 'pinMode(PIN_LOCAL_ESTOP, INPUT);' in setup
assert 'HIGH=healthy, LOW/open=E-Stop' in setup
print('W1P_ESTOP_ACTIVE_1008_PASS')
