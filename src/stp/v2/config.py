"""Campaign v2 configuration, fixed in docs/v2/PLAN.md. v1 modules stay untouched."""
import dataclasses
import math
from ..sut import SutConfig

LATENCY_STEPS = 10  # 200 ms, 20 ms per step
LEVELS = {
    "low": SutConfig(noise_sd=0.05, delay_steps=(LATENCY_STEPS, LATENCY_STEPS), gust_period=(2.5, 3.0), gust_phase_span=math.pi / 4),
    "medium": SutConfig(noise_sd=0.15, delay_steps=(LATENCY_STEPS, LATENCY_STEPS), gust_period=(1.5, 4.0)),
    "high": SutConfig(noise_sd=0.30, delay_steps=(LATENCY_STEPS, LATENCY_STEPS), gust_period=(1.0, 6.0)),
}
# Tried in this order; the first that passes every gate is frozen.
CANDIDATES = {
    "A": dict(xl=[8.0, 0.002, -0.020, 0.0], xu=[24.0, 0.020, 0.020, 1.0]),
    "B": dict(xl=[8.0, 0.002, -0.020, 0.0], xu=[24.0, 0.020, 0.020, 1.5]),
    "C": dict(xl=[8.0, 0.002, -0.016, 0.0], xu=[24.0, 0.016, 0.016, 1.0]),
    "D": dict(xl=[8.0, 0.002, -0.020, 0.0], xu=[22.0, 0.020, 0.020, 1.0]),
    "E": dict(xl=[8.0, 0.002, -0.020, 0.0], xu=[26.0, 0.020, 0.020, 1.0]),
}
G0_LATENCY_STEPS = (5, 10, 15, 18, 20, 23)  # 100, 200, 300, 360, 400, 460 ms


def cfg_for(key):
    """'medium' or 'medium@15' (latency override, 20 ms steps)."""
    name, _, lat = key.partition("@")
    return dataclasses.replace(LEVELS[name], delay_steps=(int(lat), int(lat))) if lat else LEVELS[name]
