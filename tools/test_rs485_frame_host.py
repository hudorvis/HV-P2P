#!/usr/bin/env python3
from pathlib import Path
import subprocess, tempfile, textwrap, zlib, struct
ROOT=Path(__file__).resolve().parents[1]
HDR=ROOT/'HV_P2P_CTRL_EDGEBOX_v26.08.31.05'/'HV_P2P_RS485_Frame.h'
assert HDR.is_file()
with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    (td/'Arduino.h').write_text(r'''
#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <string>
using std::size_t;
static uint32_t __ms=1;
static inline uint32_t millis(){ return __ms++; }
class String {
  std::string s_;
public:
  String()=default; String(const char*s):s_(s?s:""){} String(const std::string&s):s_(s){}
  size_t length()const{return s_.size();} const char*c_str()const{return s_.c_str();}
  void reserve(size_t n){s_.reserve(n);} String& operator+=(char c){s_+=c;return *this;}
  operator std::string() const { return s_; }
};
class Stream {
public:
  virtual ~Stream()=default;
  virtual size_t write(const uint8_t*, size_t)=0;
  virtual void flush(){}
};
''')
    test=r'''
#include <cstdio>
#include <vector>
#include <cassert>
#include "HV_P2P_RS485_Frame.h"
class BufStream: public Stream {
public: std::vector<uint8_t> b; bool flushed=false;
 size_t write(const uint8_t*p,size_t n) override { b.insert(b.end(),p,p+n); return n; }
 void flush() override { flushed=true; }
};
int main(){
 using namespace HVP2PRS485;
 const uint8_t p[]={0x41,0x55,0x58,0x35};
 uint32_t c=frameCrc(PROTOCOL_VERSION, EVENT, 0x1234, sizeof(p), p);
 std::printf("crc=%08x\n",(unsigned)c);
 BufStream bs; assert(sendFrame(bs,EVENT,0x1234,p,sizeof(p))); assert(bs.flushed);
 assert(bs.b.size()==HEADER_SIZE+sizeof(p)+CRC_SIZE);
 assert(bs.b[0]=='H'&&bs.b[1]=='V'&&bs.b[2]=='P'&&bs.b[3]=='2');
 Parser parser; Frame f{}; bool got=false;
 for(uint8_t x:bs.b) if(parser.feed(x,f)) got=true;
 assert(got); assert(f.version==PROTOCOL_VERSION); assert(f.type==EVENT); assert(f.seq==0x1234); assert(f.length==4); assert(std::memcmp(f.payload,p,4)==0);
 // CRC corruption must not emit a frame.
 auto bad=bs.b; bad.back()^=0x01; Parser p2; Frame f2{}; got=false;
 for(uint8_t x:bad) if(p2.feed(x,f2)) got=true;
 assert(!got);
 // Oversized TX is rejected.
 std::vector<uint8_t> huge(MAX_PAYLOAD+1,0x55); BufStream bx;
 assert(!sendFrame(bx,TEXT,1,huge.data(),(uint16_t)huge.size()));
 std::puts("RS485_FRAME_HOST_PASS");
}
'''
    (td/'test.cpp').write_text(test)
    # copy current exact header
    (td/'HV_P2P_RS485_Frame.h').write_bytes(HDR.read_bytes())
    exe=td/'test'
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(td),str(td/'test.cpp'),'-o',str(exe)],check=True)
    out=subprocess.check_output([str(exe)],text=True)
    print(out,end='')
    line=[x for x in out.splitlines() if x.startswith('crc=')][0]
    got=int(line.split('=')[1],16)
    payload=bytes([1,0x12,0x12,0x34,0,4])+b'AUX5' # version,type,seq,len,payload
    want=zlib.crc32(payload)&0xffffffff
    if got!=want: raise SystemExit(f'CRC mismatch C++={got:08x} Python={want:08x}')
    print(f'PYTHON_CRC_CROSSCHECK_PASS {want:08x}')
