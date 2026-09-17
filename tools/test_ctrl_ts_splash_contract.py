#!/usr/bin/env python3
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
ts = (ROOT/'HV_P2P_CTRL_TS_v26.09.17.02'/'HV_P2P_CTRL_TS_v26.09.17.02.ino').read_text()

required = [
    'SPLASH_CANVAS_W = 800',
    'SPLASH_CANVAS_H = 480',
    'boot_rotate_90 = (boot_src_h > boot_src_w) && (boot_w > boot_h)',
    'Aspect-preserving contain fit',
    'boot_draw_x = (boot_w - boot_draw_w) / 2',
    'boot_draw_y = (boot_h - boot_draw_h) / 2',
    'lx = boot_src_h - 1 - sy',
    'ly = sx',
]
for token in required:
    assert token in ts, f'missing splash contract token: {token}'

W,H = 800,480

def fit(sw,sh):
    assert sw>0 and sh>0
    rotate = (sh>sw) and (W>H)
    lw,lh = (sh,sw) if rotate else (sw,sh)
    if lw*H >= lh*W:
        dw=W
        dh=max(1, lh*W//lw)
    else:
        dh=H
        dw=max(1, lw*H//lh)
    dx=(W-dw)//2; dy=(H-dh)//2
    return rotate,lw,lh,dw,dh,dx,dy

cases=[
    (800,480,False),
    (480,800,True),
    (1920,1080,False),
    (1080,1920,True),
    (1024,1024,False),
    (320,240,False),
    (240,320,True),
]
for sw,sh,expected_rotate in cases:
    rotate,lw,lh,dw,dh,dx,dy=fit(sw,sh)
    assert rotate == expected_rotate, (sw,sh,rotate)
    assert 1 <= dw <= W and 1 <= dh <= H
    assert 0 <= dx and 0 <= dy and dx+dw <= W and dy+dh <= H
    # Integer contain-fit can differ by less than one destination pixel. Cross multiply.
    err = abs(dw*lh - dh*lw)
    assert err <= max(lw,lh), (sw,sh,dw,dh,err)
    if sw==800 and sh==480:
        assert (dw,dh,dx,dy)==(800,480,0,0)
    if sw==480 and sh==800:
        assert (dw,dh,dx,dy)==(800,480,0,0)

# Pixel mapping endpoints for portrait rotation must cover the full logical canvas.
rotate,lw,lh,dw,dh,dx,dy=fit(480,800)
pts=[]
for sx,sy in [(0,0),(479,0),(0,799),(479,799)]:
    lx = 800-1-sy
    ly = sx
    x0 = dx + lx*dw//lw
    x1 = dx + (lx+1)*dw//lw
    y0 = dy + ly*dh//lh
    y1 = dy + (ly+1)*dh//lh
    assert 0 <= x0 < x1 <= W
    assert 0 <= y0 < y1 <= H
    pts.append((x0,y0,x1,y1))
assert min(p[0] for p in pts)==0 and max(p[2] for p in pts)==W
assert min(p[1] for p in pts)==0 and max(p[3] for p in pts)==H

print('CTRL_TS_SPLASH_CONTRACT_PASS cases=%d canvas=%dx%d' % (len(cases),W,H))
