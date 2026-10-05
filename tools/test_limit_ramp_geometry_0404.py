#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B=(ROOT/'SRVR_GitHub_v26.10.05.03'/'backend.py').read_text()
Q=(ROOT/'SRVR_GitHub_v26.10.05.03'/'qml'/'pages'/'SetupPage.qml').read_text()
M=(ROOT/'SRVR_GitHub_v26.10.05.03'/'qml'/'Main.qml').read_text()
S=(ROOT/'SRVR_GitHub_v26.10.05.03'/'qml'/'components'/'SpanDiagram.qml').read_text()
T=(ROOT/'HV_P2P_CTRL_TS_v26.10.05.03'/'HV_P2P_CTRL_TS_v26.10.05.03.ino').read_text()

# Settings ComboBoxes must have persistent live bindings so AUX/external changes
# re-select the visible value even after the control has been used locally.
assert 'id:accelerationModeCombo' in Q and 'target:accelerationModeCombo' in Q
assert 'value:root.idx(accelerationModeCombo.model,backend.accelerationMode)' in Q
assert 'id:batteryChangeModeCombo' in Q and 'target:batteryChangeModeCombo' in Q
assert 'value:backend.batteryChange?1:0' in Q

# Signed distance contract: inside the span ToNear+ToFar equals span; outside
# Battery Change one side becomes negative while the opposite side grows.
assert 'def toNear(self): return self.position-float(self.state.near_limit.position_m or 0.0)' in B
assert 'def toFar(self): return float(self.state.far_limit.position_m or 100.0)-self.position' in B

# One SRVR-authoritative effective ramp geometry. Distance is clamped to the
# current span, Percentage is converted from the same span, and both stored
# representations are re-synchronised after limit/ramp edits.
ramp=B[B.index('def _ramp_distance'):B.index('def _clamp_goto_target_inside_limits')]
assert 'min(span, raw)' in ramp
assert 'def _sync_ramp_representations_for_span' in ramp
assert 'lp.ramp_distance_m = span * lp.ramp_percentage / 100.0' in ramp
assert 'lp.ramp_percentage = 100.0 * lp.ramp_distance_m / span' in ramp
assert 'def nearRampFraction' in B and 'def farRampFraction' in B
assert 'ramp_near_frac={self.nearRampFraction:.6f}' in B
assert 'ramp_far_frac={self.farRampFraction:.6f}' in B

# Every SRVR SpanDiagram gets the same normalized ramp boundaries, independent
# of whether the Settings representation is metres or percentage.
assert M.count('nearRampFraction:backend.nearRampFraction') >= 4
assert M.count('farRampFraction:backend.farRampFraction') >= 4
assert 'property real nearRampFraction: -1' in S and 'property real farRampFraction: -1' in S
assert 'var nrFrac=root.nearRampFraction>=0' in S
assert 'var frFrac=root.farRampFraction>=0' in S
assert 'var nrX=left+nrFrac*(right-left)' in S
assert 'var frX=right-frFrac*(right-left)' in S

# CTRL-TS consumes the same normalized ramp fractions and centres all travel
# markers exactly on the Near/Far endpoint coordinate at 0/100%.
assert 'g_ramp_near_frac=-1.0f' in T and 'g_ramp_far_frac=-1.0f' in T
assert 'getFieldFloat(line, "ramp_near_frac"' in T and 'getFieldFloat(line, "ramp_far_frac"' in T
assert 'g_ramp_near_frac >= 0.0f ? constrain(g_ramp_near_frac' in T
assert 'center_x = (int)lroundf(bar_left + frac * (float)(bar_right - bar_left))' in T
assert 'bar_right - marker_w/2' in T

print('LIMIT_RAMP_GEOMETRY_0404_PASS')
