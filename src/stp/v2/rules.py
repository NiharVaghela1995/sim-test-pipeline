"""Verdict rules of docs/v2/PLAN.md. Each rule has `apply(seq) -> (real, reruns used)` on an ordered rerun sequence
and `exact(p) -> (P(real), expected reruns)` for a true failure probability p."""
import math
from dataclasses import dataclass
from typing import Callable
import numpy as np
from scipy import stats

Z = 1.959964
CAP = 40


@dataclass(frozen=True)
class Rule:
    name: str
    apply: Callable
    exact: Callable


def wilson_low(k, n):
    if n == 0: return 0.0
    p = k / n; d = 1 + Z ** 2 / n
    return (p + Z ** 2 / (2 * n) - Z * math.sqrt(p * (1 - p) / n + Z ** 2 / (4 * n ** 2))) / d


def k_of_n(k, n, name=None):
    return Rule(name or f"{k}-of-{n}", lambda s: (int(np.sum(s[:n])) >= k, n), lambda p: (float(stats.binom.sf(k - 1, n, p)), float(n)))


def report_as_is():
    return Rule("report as-is", lambda s: (True, 0), lambda p: (1.0, 0.0))


def wilson(n, tau):
    def exact(p):
        return float(sum(stats.binom.pmf(k, n, p) for k in range(n + 1) if wilson_low(k, n) >= tau)), float(n)
    return Rule(f"Wilson bound, n={n}", lambda s: (wilson_low(int(np.sum(s[:n])), n) >= tau, n), exact)


def sprt(p0, p1, alpha, beta, tau, cap=CAP, name=None):
    """Wald SPRT of p <= p0 against p >= p1. Capped: at the cap the verdict is real if the rate is at least tau."""
    up, lo = math.log((1 - beta) / alpha), math.log(beta / (1 - alpha))
    hit, miss = math.log(p1 / p0), math.log((1 - p1) / (1 - p0))

    def decide(k, n):
        llr = k * hit + (n - k) * miss
        return True if llr >= up else False if llr <= lo else None

    def apply(seq):
        k = 0; n = 0
        for x in seq[:cap]:
            n += 1; k += int(x); d = decide(k, n)
            if d is not None: return d, n
        return (k / max(n, 1) >= tau), n

    def exact(p):
        alive = {0: 1.0}; real = 0.0; used = 0.0; n = 0
        while alive and n < cap:
            n += 1; nxt = {}
            for k, m in alive.items():
                for j, q in ((k + 1, p), (k, 1 - p)):
                    if q > 0: nxt[j] = nxt.get(j, 0.0) + m * q
            alive = {}
            for k, m in nxt.items():
                d = decide(k, n)
                if d is None: alive[k] = m
                else:
                    real += m * d; used += m * n
        for k, m in alive.items():
            real += m * (k / n >= tau); used += m * n
        return float(real), float(used)

    return Rule(name or f"SPRT {p0:g}/{p1:g}, a=b={alpha:g}", apply, exact)


def shortlist(tau):
    R = [report_as_is()]
    R += [k_of_n(1, n, f"any-of-{n}") for n in (1, 3, 5)]
    R += [k_of_n(2, 5), k_of_n(3, 10), k_of_n(4, 5)]
    R += [k_of_n(n // 2 + 1, n, f"majority-of-{n}") for n in (3, 5, 9, 19, 39)]
    R += [k_of_n(n, n, f"all-of-{n}") for n in (3, 5, 10)]
    R += [wilson(20, tau)]
    if tau == 0.5:
        R += [sprt(.3, .7, .05, .05, tau), sprt(.2, .8, .05, .05, tau), sprt(.4, .6, .05, .05, tau), sprt(.3, .7, .01, .01, tau)]
    elif tau == 0.2:
        R += [sprt(.05, .35, .05, .05, tau)]
    elif tau == 0.8:
        R += [sprt(.65, .95, .05, .05, tau)]
    return R


def grid():
    return [k_of_n(k, n) for n in (3, 5, 10, 20, 40) for k in range(1, n + 1)]
