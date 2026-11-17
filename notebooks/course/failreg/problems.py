"""Test problems with a known failure region (the answer key).

Every problem lives on the unit cube [0, 1]^d. A run at x returns a margin y = f(x) + e, e ~ N(0, s(x)^2); the run fails
when y < tau. The failure probability is p(x) = Phi((tau - f(x)) / s(x)) and the target region is {x : p(x) >= alpha}.
For a deterministic problem (s = 0) that is simply {f(x) < tau}.

Functions as in the project-thesis review code (`benchmark_funcs.py`), rewritten here:
  branin         Branin-Hoo rescaled to [0, 1]^2; failure f <= 10 gives three disconnected regions
  four_branch    four-branch series system mapped from [-5, 5]^2; failure g <= 0, four disconnected regions
  car_following  minimum gap when the lead car stops and the ego brakes after a reaction time; zero contour in closed form
  noisy_car      car_following with input-dependent Gaussian noise; target {p(x) >= 0.10}
"""
from dataclasses import dataclass, field
from typing import Callable, Optional
import numpy as np
from scipy.stats import norm


def branin(U):
    U = np.atleast_2d(U)
    x1, x2 = 15 * U[:, 0] - 5, 15 * U[:, 1]
    b, c, t = 5.1 / (4 * np.pi ** 2), 5 / np.pi, 1 / (8 * np.pi)
    return (x2 - b * x1 ** 2 + c * x1 - 6) ** 2 + 10 * (1 - t) * np.cos(x1) + 10


def four_branch(U, k=6.0):
    U = np.atleast_2d(U)
    u1, u2 = 10 * U[:, 0] - 5, 10 * U[:, 1] - 5
    g = [3 + 0.1 * (u1 - u2) ** 2 - (u1 + u2) / np.sqrt(2), 3 + 0.1 * (u1 - u2) ** 2 + (u1 + u2) / np.sqrt(2),
         (u1 - u2) + k / np.sqrt(2), (u2 - u1) + k / np.sqrt(2)]
    return np.min(np.vstack(g), axis=0)


CAR = dict(d0=(5.0, 60.0), dv=(0.0, 20.0), tr=(0.5, 2.0), a_brake=6.0)


def car_following(U):
    """Minimum gap [m]: d0 - dv * tr - dv^2 / (2 a). d0 = initial gap, dv = closing speed (lead car stopped),
    tr = reaction time (third input, else 1.0 s). Zero contour: d0 = dv tr + dv^2 / (2 a)."""
    U = np.atleast_2d(U)
    d0 = CAR["d0"][0] + np.ptp(CAR["d0"]) * U[:, 0]
    dv = CAR["dv"][0] + np.ptp(CAR["dv"]) * U[:, 1]
    tr = CAR["tr"][0] + np.ptp(CAR["tr"]) * U[:, 2] if U.shape[1] > 2 else np.ones(len(U))
    return d0 - dv * tr - dv ** 2 / (2 * CAR["a_brake"])


def car_zero_contour(n=400):
    """The exact failure boundary of car_following (2-D, tr = 1 s) in unit coordinates: for each dv, the d0 with gap 0."""
    v = np.linspace(0, 1, n)
    dv = CAR["dv"][0] + np.ptp(CAR["dv"]) * v
    d0 = dv * 1.0 + dv ** 2 / (2 * CAR["a_brake"])
    u0 = (d0 - CAR["d0"][0]) / np.ptp(CAR["d0"])
    ok = (u0 >= 0) & (u0 <= 1)
    return np.column_stack([u0[ok], v[ok]])


def car_noise_sd(U):
    """Noise sd [m] of the noisy variant: 0.5 m at zero closing speed, rising to 6.5 m at 20 m/s."""
    U = np.atleast_2d(U)
    return 0.5 + 6.0 * U[:, 1]


@dataclass
class Problem:
    name: str
    d: int
    f: Callable
    tau: float = 0.0
    sd: Optional[Callable] = None          # x -> noise sd; None = deterministic
    alpha: float = 0.5
    labels: tuple = ()
    grid_n: int = 101
    n_regions: Optional[int] = None        # built-in disconnected failure regions (distinct mechanisms)
    calls: int = field(default=0, repr=False)

    @property
    def noisy(self):
        return self.sd is not None

    def noise_sd(self, U):
        return self.sd(U) if self.noisy else np.zeros(len(np.atleast_2d(U)))

    def run(self, U, rng):
        """One run per row of U. rng: numpy Generator, the replicate stream (independent of the search)."""
        U = np.atleast_2d(U)
        self.calls += len(U)
        y = self.f(U)
        if self.noisy:
            y = y + rng.standard_normal(len(U)) * self.sd(U)
        return y

    def p_fail(self, U):
        U = np.atleast_2d(U)
        if not self.noisy:
            return (self.f(U) < self.tau).astype(float)
        return norm.cdf((self.tau - self.f(U)) / self.sd(U))

    def fails(self, U):
        """Answer key: is x in the target region?"""
        return self.p_fail(U) >= self.alpha if self.noisy else self.f(np.atleast_2d(U)) < self.tau

    def h(self, U):
        """Threshold on the mean margin that the target region corresponds to: {f(x) < h(x)}.
        h = tau - s(x) Phi^-1(alpha); it moves to the safe side for alpha < 0.5 (course Module 14, section 2)."""
        return self.tau - self.noise_sd(U) * norm.ppf(self.alpha) if self.noisy else np.full(len(np.atleast_2d(U)), self.tau)

    def grid(self, n=None):
        n = n or self.grid_n
        g = np.linspace(0, 1, n)
        return np.stack(np.meshgrid(*[g] * self.d, indexing="ij"), -1).reshape(-1, self.d)

    @property
    def test(self):
        """Dense test grid, its answer key, the grid shape and a mask of labelled points (None = all); cached."""
        if not hasattr(self, "_test"):
            G = self.grid()
            self._test = (G, self.fails(G), (self.grid_n,) * self.d, None)
        return self._test


def get(name):
    if name == "branin":
        return Problem("branin", 2, branin, tau=10.0, labels=("x1", "x2"), n_regions=3)
    if name == "four_branch":
        return Problem("four_branch", 2, four_branch, tau=0.0, labels=("u1", "u2"), n_regions=4)
    if name == "car":
        return Problem("car", 2, car_following, tau=0.0, labels=("initial gap", "closing speed"), n_regions=1)
    if name == "car3":
        return Problem("car3", 3, car_following, tau=0.0, labels=("initial gap", "closing speed", "reaction time"), grid_n=41, n_regions=1)
    if name == "noisy_car":
        return Problem("noisy_car", 2, car_following, tau=0.0, sd=car_noise_sd, alpha=0.10, labels=("initial gap", "closing speed"), n_regions=1)
    raise KeyError(name)


ALL = ("branin", "four_branch", "car", "noisy_car")
