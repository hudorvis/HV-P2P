#!/usr/bin/env python3
"""Source-extracted SRVR position filter + W1P modular 32-bit C++ regression.

Exercises production method through AST, without importing Qt. Real drive,
Modbus, UDP and frozen GUI tests remain independent CI/hardware gates.
"""
from pathlib import Path
import ast
import math
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / 'SRVR_GitHub_v26.10.19.01'
W1P = ROOT / 'HV_P2P_W1P_EDGEBOX_v26.10.19.01' / 'HV_P2P_W1P_EDGEBOX_v26.10.19.01.ino'
sys.path.insert(0, str(BACKEND_DIR))
sys.dont_write_bytecode = True
import position_feedback as pf

backend_src = (BACKEND_DIR / 'backend.py').read_text()
tree = ast.parse(backend_src)
fn = next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)
          and n.name == '_sanity_accept_winch_position')
fn.decorator_list = []
model_code = ast.Module(body=[fn], type_ignores=[])
ast.fix_missing_locations(model_code)

class Clock:
    def __init__(self): self.t=10000.0
    def time(self): return self.t
    def monotonic(self): return self.t
    def advance(self,dt): self.t += dt

clock=Clock()
ns={'math':math,'time':clock,
    'position_step_allowed':pf.position_step_allowed,
    'is_newer_sequence':pf.is_newer_sequence,
    'uint32_elapsed_ms':pf.uint32_elapsed_ms}
exec(compile(model_code, 'backend.py', 'exec'), ns)
position_method=ns['_sanity_accept_winch_position']

class S: pass
class TestBackend:
    def __init__(self, pos=0.0):
        self.state=S(); self.state.pos_m=pos
        self.winch_units_per_m=21220.7
        self._winch_last_pos_accept_t=0.0
        self._winch_last_pos_sample_ms=None
        self._winch_last_pos_seq=None
        self._winch_last_pos_reject_log_t=0.0
        self._winch_position_accept_jump_until=0.0
        self.log=[]
        self._log=self.log.append
    def receive(self, pos, *, seq=1, timestamp_ms=1, age_ms=10, good=True):
        fields={'POS_SRC':'DRIVE', 'POS_READ':'1' if good else '0',
                'POS_T_MS':str(timestamp_ms & 0xffffffff), 'POS_SEQ':str(seq & 0xffffffff),
                'POS_AGE_MS':str(age_ms),'UPM':'21220.7'}
        ok=position_method(self,pos,fields)
        if ok:self.state.pos_m=pos
        return ok

# 50ms telemetry, no SRVR motion command, 125/250/500 and entire programmed
# 2500 RPM ceiling (plus 3000 RPM validation headroom), passing 1000m and beyond on 1000m calibrated spans.
for rpm in (125, 250, 500, 2500, 3000):
    b=TestBackend()
    dt=.05
    meters_per_poll=(rpm*10000/60/21220.7)*dt
    seq=1;ms=1000
    assert b.receive(0,seq=seq,timestamp_ms=ms)
    # 1100+ metres at every RPM; loop count is reasonable at 125 RPM.
    span_steps=int(1100/meters_per_poll)+2
    for i in range(span_steps):
        clock.advance(dt)
        seq+=1;ms+=50
        pos=(i+1)*meters_per_poll
        assert b.receive(pos,seq=seq,timestamp_ms=ms), (rpm, i, pos, b.log[-1:] )
        assert abs(b.state.pos_m-pos) < 1e-9
    assert b.state.pos_m>1000
    assert b.state.pos_m - 0 >1000      # signed To Near
    assert 1000 - b.state.pos_m < 0      # signed To Far (beyond Far)
    print('SIMULATED_ENCODER_TRAVEL_PASS',rpm,'RPM',round(b.state.pos_m,4),'m',span_steps,'samples')

# Near/Far boundaries: measured location must not be clipped by a software
# motion limit; unchanged limit/motion functions remain hash-guarded separately.
b=TestBackend(0); assert b.receive(0,seq=1,timestamp_ms=100)
clock.advance(.1)
assert b.receive(-.8,seq=2,timestamp_ms=200) and b.state.pos_m == -.8
clock.advance(.1)
assert b.receive(.8,seq=3,timestamp_ms=300) and b.state.pos_m == .8

# Stale Modbus position and duplicate/reordered UDP status cannot advance view.
clock.advance(.05)
assert not b.receive(1.0,seq=4,timestamp_ms=350,age_ms=501)
assert b.state.pos_m==.8
assert not b.receive(1.0,seq=3,timestamp_ms=350)
assert b.state.pos_m==.8
assert not b.receive(1.0,seq=4,timestamp_ms=350,good=False)
assert b.state.pos_m==.8

# Corrupt jump rejected; immediately following correct samples still recover.
clock.advance(.05)
assert not b.receive(90,seq=4,timestamp_ms=350)
assert b.state.pos_m==.8
clock.advance(.05)
assert b.receive(1.2,seq=5,timestamp_ms=400)
assert b.state.pos_m==1.2

# 1 s and 7 s disconnections: device timestamps, not compressed Qt queue
# timing, bound catch-up travel. No hard dt reset after one second.
clock.advance(1.0)
assert b.receive(20.0,seq=25,timestamp_ms=1400)
clock.advance(7.0)
assert b.receive(157.0,seq=165,timestamp_ms=8400)

# W1P boot/reset and explicit slip make a new position reference possible.
b._winch_last_pos_accept_t=0.0
b._winch_last_pos_sample_ms=None
b._winch_last_pos_seq=None
clock.advance(.05)
assert b.receive(-1000.5,seq=1,timestamp_ms=1)

# Signed sample millis and sequence may wrap at 2^32; ordering still correct.
b=TestBackend(); assert b.receive(0,seq=0xfffffffe,timestamp_ms=0xffffffda)
clock.advance(.050)
assert b.receive(.20,seq=0xffffffff,timestamp_ms=0x0000000c)
clock.advance(.050)
assert b.receive(.40,seq=0,timestamp_ms=0x0000003e)
assert not b.receive(.30,seq=0xffffffff,timestamp_ms=0x0000000c)
assert pf.is_newer_sequence(0,0xffffffff) and not pf.is_newer_sequence(0xffffffff,0)

# Pure numerical sanity: NaN/infinite, units/zero time, physically impossible
# 50ms jumps must fail; kilometer+ coordinates are accurate in Python double.
for bad in (float('nan'), float('inf'), -float('inf')):
    assert not pf.position_step_allowed(0,bad,.05,21220.7)[0]
assert not pf.position_step_allowed(0,1,0,21220.7)[0]
assert not pf.position_step_allowed(0,1,.1,0)[0]
assert not pf.position_step_allowed(999.0,1100,.05,21220.7)[0]
assert pf.position_step_allowed(123456.0,123456.50,.05,21220.7)[0]

# Verify telemetry packet schema and the protected Modbus feedback block are
# wired in the actual W1P source without accidentally modifying brake/E-stop.
w=W1P.read_text()
for token in ('REG_MOTOR_POSITION_H = 0x602C', 'REG_MOTOR_POSITION_L = 0x602D',
              'modbusReadFeedbackBlock(DRIVE_MODBUS_ID, rawPos, inio, outio)',
              'g.pos_m = rawUnitsToDisplayPositionM(unwrapDrivePosition(rawPos))',
              '++g_drive_position_sequence;', 'RAW_POS_EXT=', 'POS_SEQ=',
              'POS_T_MS=', 'POS_AGE_MS=', 'g.drive_feedback_ok = g.position_feedback_read_ok',
              'g.edgebox_brake_released', 'W1P_VEL_COMMAND_TIMEOUT_MS = 500'):
    assert token in w,token
for token in ('position_step_allowed', 'uint32_elapsed_ms', 'POS_AGE_MS', 'POS_SEQ',
              'RAW_POS_EXT', 'self._last_raw_pos = int(fields["RAW_POS_EXT"])'):
    assert token in backend_src,token

# Compile and execute the actual W1P wrapped counter logic under host C++.
# C++ functions are extracted from source, rather than a rewritten model.
def extract_cpp(name):
    m=re.search(r'(?m)^static\s+(?:int64_t|float)\s+'+name+r'\([^;]*?\)\s*\{',w)
    assert m,name
    i=w.index('{',m.start());depth=0
    for j in range(i,len(w)):
        if w[j]=='{':depth+=1
        if w[j]=='}':
            depth-=1
            if depth==0:return w[m.start():j+1]
    raise ValueError(name)

cpp='''#include <cstdint>\n#include <climits>\n#include <cassert>\n#include <cmath>\n'''
cpp+='''static int64_t g_drive_unwrapped_units = 0;
static int32_t g_drive_last_wrapped_units = 0;
static bool g_drive_unwrapped_valid = false;
'''
cpp+=extract_cpp('wrappedPositionDelta')+'\n'+extract_cpp('unwrapDrivePosition')+'\n'
cpp+='''int main(){
 assert(wrappedPositionDelta(INT32_MIN+4000,INT32_MAX-6000)==10001LL);
 assert(wrappedPositionDelta(INT32_MAX-4000,INT32_MIN+6000)==-10001LL);
 assert(unwrapDrivePosition(INT32_MAX-6000)==INT32_MAX-6000LL);
 assert(unwrapDrivePosition(INT32_MIN+4000)==int64_t(INT32_MAX)+4001LL);
 assert(unwrapDrivePosition(INT32_MIN+14000)==int64_t(INT32_MAX)+14001LL);
 g_drive_unwrapped_valid=false;
 assert(unwrapDrivePosition(INT32_MIN+6000)==int64_t(INT32_MIN)+6000LL);
 assert(unwrapDrivePosition(INT32_MAX-4000)==int64_t(INT32_MIN)-4001LL);
 return 0;
}'''
if shutil.which('g++'):
    with tempfile.TemporaryDirectory(prefix='hvp2p_encoder_cpp_') as td:
        src=Path(td)/'encoder_test.cpp';exe=Path(td)/'encoder_test';src.write_text(cpp)
        subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',str(src),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
    print('W1P_ACTUAL_CPP_ROLLOVER_PASS forward_and_reverse')
else:
    raise RuntimeError('g++ required for W1P rollover verification; not available')
print('SRVR_POSITION_FEEDBACK_101901_ALL_PASS')
