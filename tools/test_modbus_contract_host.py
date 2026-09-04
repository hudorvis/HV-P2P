#!/usr/bin/env python3
from pathlib import Path
import re, subprocess, tempfile
ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'HV_P2P_W1P_EDGEBOX_v26.09.04.02'/'HV_P2P_W1P_EDGEBOX_v26.09.04.02.ino'
src=W.read_text()
# Extract exact CRC function from W1P source.
m=re.search(r'static uint16_t modbusCRC16\([^\{]+\{',src)
if not m: raise SystemExit('CRC function not found')
start=m.start(); brace=src.find('{',m.start(),m.end()); depth=0; i=brace
while i<len(src):
    if src[i]=='{': depth+=1
    elif src[i]=='}':
        depth-=1
        if depth==0:
            func=src[start:i+1]; break
    i+=1
else: raise SystemExit('CRC function unclosed')
with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    cpp='''#include <cstdint>\n#include <cstddef>\n#include <cstdio>\n#include <cassert>\n'''+func+r'''
int main(){
  const uint8_t q1[]={0x01,0x03,0x00,0x00,0x00,0x0A};
  // Standard Modbus example request: on-wire CRC C5 CD => numeric 0xCDC5.
  assert(modbusCRC16(q1,sizeof(q1))==0xCDC5);
  const uint8_t q2[]={0x01,0x06,0x00,0x01,0x00,0x03};
  uint16_t c=modbusCRC16(q2,sizeof(q2));
  std::printf("MODBUS_CRC_HOST_PASS q1=CDC5 q2=%04X\n",(unsigned)c);
}
'''
    (td/'t.cpp').write_text(cpp)
    exe=td/'t'
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',str(td/'t.cpp'),'-o',str(exe)],check=True)
    print(subprocess.check_output([str(exe)],text=True),end='')
