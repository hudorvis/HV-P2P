#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
T=(ROOT/'HV_P2P_CTRL_TS_v26.09.29.05/HV_P2P_CTRL_TS_v26.09.29.05.ino').read_text()
for tok in ('boot_render_splash_fit','const bool rotate = (boot_decode_h > boot_decode_w) && (boot_w > boot_h)','const float scale = sx < sy ? sx : sy','without crop','2200000ULL'):
    assert tok in T,tok

def fit(sw,sh,tw=800,th=480):
    rot=(sh>sw and tw>th); lw,lh=(sh,sw) if rot else (sw,sh)
    scale=min(tw/lw,th/lh); ow=max(1,min(tw,round(lw*scale))); oh=max(1,min(th,round(lh*scale)))
    return rot,ow,oh,(tw-ow)//2,(th-oh)//2
for sw,sh in [(800,480),(480,800),(1920,1080),(1080,1920),(1000,1000),(320,240),(2000,1000)]:
    rot,ow,oh,x,y=fit(sw,sh)
    assert 1<=ow<=800 and 1<=oh<=480 and x>=0 and y>=0 and x+ow<=800 and y+oh<=480
    src_ratio=(sh/sw if rot else sw/sh); out_ratio=ow/oh
    assert abs(src_ratio-out_ratio) < 0.01 + 2/max(ow,oh)
print('SPLASH_RENDER_CONTRACT_PASS')
