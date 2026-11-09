"""Physical encoder position plausibility — telemetry only, never motion authority.

The 3000 RPM allowance in the SRVR caller is a tolerant *validation* limit.
W1P's independent 2500 RPM command ceiling and all interlocks are untouched.
"""
from __future__ import annotations
import math

ENCODER_UNITS_PER_REV = 10000.0


def uint32_elapsed_ms(current: int, previous: int) -> int:
    return (int(current) - int(previous)) & 0xFFFFFFFF


def is_newer_sequence(current: int, previous: int) -> bool:
    delta = uint32_elapsed_ms(current, previous)
    return 0 < delta < 0x80000000


def position_step_allowed(old_m: float, new_m: float, elapsed_s: float,
                          units_per_m: float, *, rpm_allowance: float = 3000.0) -> tuple[bool, float]:
    """Bound a measured move by encoder counts/s and actual SAMPLE interval.

    20% physical-speed tolerance plus 0.20 m accommodates quantisation, minor
    timestamp jitter and scaling variations, but not large corrupt jumps.
    Nothing here clamps measured location to Near/Far or changes the VEL path.
    """
    if not all(map(math.isfinite, (old_m, new_m, elapsed_s, units_per_m, rpm_allowance))):
        return False, 0.0
    if elapsed_s <= 0 or units_per_m <= 0 or rpm_allowance <= 0:
        return False, 0.0
    max_mps = rpm_allowance * ENCODER_UNITS_PER_REV / (60.0 * units_per_m)
    allowance = max_mps * elapsed_s * 1.20 + 0.20
    return abs(new_m - old_m) <= allowance, allowance
