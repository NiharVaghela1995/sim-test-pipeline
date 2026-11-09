"""System under test: a pure-pursuit lane keeper with a curvature limit.
Randomness W is explicit and seeded: perception noise, control latency, gust phase and period.
Reproduction rates in this pipeline measure this injected W, not real-vehicle nondeterminism."""
import collections
import math
import numpy as np
from dataclasses import dataclass


@dataclass(frozen=True)
class SutConfig:
    wheelbase: float = 2.7
    ay_max: float = 6.0          # lateral acceleration limit, m/s^2
    kappa_rate: float = 0.25     # curvature rate limit, 1/m/s
    lookahead_time: float = 0.8  # s
    lookahead_min: float = 6.0   # m
    noise_sd: float = 0.15       # perception noise on the lateral target, m
    delay_steps: tuple = (5, 25) # control latency, in 20 ms steps, drawn per run


class LaneKeeper:
    def __init__(self, cfg: SutConfig, rng: np.random.Generator):
        self.c, self.r = cfg, rng; self.kappa = 0.0
        self.delay = int(rng.integers(cfg.delay_steps[0], cfg.delay_steps[1] + 1))
        self.buf = collections.deque([0.0] * self.delay, maxlen=self.delay)

    def lookahead(self, v):
        return max(self.c.lookahead_min, self.c.lookahead_time * v)

    def step(self, target_x, target_y, v, dt):
        y = target_y + self.r.normal(0, self.c.noise_sd)
        d2 = max(target_x ** 2 + y ** 2, 1e-3)
        cmd = 2.0 * y / d2
        lim = self.c.ay_max / max(v ** 2, 1e-3)
        self.buf.append(float(np.clip(cmd, -lim, lim)))
        want = self.buf[0]
        self.kappa += float(np.clip(want - self.kappa, -self.c.kappa_rate * dt, self.c.kappa_rate * dt))
        return self.kappa
