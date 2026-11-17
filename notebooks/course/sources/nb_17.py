CELLS = [
("md", r"""
# 17 · Explore or replicate (fixed replicates, OCBA, stochastic kriging, threshold allocation, APT, IMSPE)

**Theory:** Chen & Lee 2011; Gramacy 2020; Binois et al. 2019; Locatelli et al. 2016 (full references at the end). On a noisy system one run at a point says little; repeats show how often it fails, which
is what the target {p(x) ≥ α} is about. But each repeat is a run not spent on a new point. This notebook implements the
allocation rules, shows where a rule built for the best point goes wrong on a boundary, measures fixed replication with
and without a noise model, and ends with the esmini cut-in, deterministic and noisy. Harness: `failreg/replication.py`,
`failreg/models.py` (notebook 32). CPU only, about two minutes.

| Rule | Source |
|---|---|
| fixed r per site | baseline |
| OCBA, N_i/N_j = ((σ_i/δ_b,i)/(σ_j/δ_b,j))², N_b = σ_b √(Σ N_i²/σ_i²) | Chen & Lee 2011, Theorem 3.2 |
| stochastic kriging: GP on site means with per-site noise | Gramacy 2020; Binois et al. 2018 (`HetGP`) |
| threshold allocation N_i ∝ σ_i²/(\|μ_i − τ\| + ε)², or ∝ 1/KL(α‖p_i) for pass/fail | the author's own derivation, large budgets only |
| APT: pull argmin √T_k (\|μ̂_k − τ\| + ε), each arm once first | Locatelli et al. 2016 |
| replicate or explore by IMSPE, one step | Binois et al. 2019 (their h = 0 case) |
"""),
("md", r"""
## 1. OCBA selects the best, not the boundary

Three sites with means 0, 0.48 and 0.9, sd 1, threshold 0.5, 300 runs. Then the consequence, as the
expected number of sites put on the wrong side, Σ Φ(−|μ_i − τ|√N_i/σ_i), against the exact optimum found by trying every
integer split. The threshold rule is asymptotic: at a small budget it over-concentrates on the site nearest the threshold.
"""),
("code", r"""
from scipy.stats import norm
m, sd, tau, T = np.array([0.0, 0.48, 0.9]), np.ones(3), 0.5, 300
wrong = lambda n: float(np.sum(norm.cdf(-np.abs(m - tau) * np.sqrt(np.maximum(n, 1e-9)) / sd)))
ALLOC = {"fixed": R.fixed(3, T).astype(float), "OCBA (best = lowest)": R.ocba(m, sd, T),
         "threshold rule, eps 0.01": R.threshold_alloc(m, sd, tau, T, eps=0.01), "threshold rule, eps 0.1": R.threshold_alloc(m, sd, tau, T, eps=0.1)}
grid = [(a, b, T - a - b) for a in range(1, T) for b in range(1, T - a)]
opt = min(grid, key=lambda n: wrong(np.array(n)))
for k, a in ALLOC.items():
    n = R.integerise(a, T); print(f"{k:26s} runs per site {n}  expected wrong sites {wrong(n):.3f}")
print(f"{'exact optimum':26s} runs per site {np.array(opt)}  expected wrong sites {wrong(np.array(opt)):.3f}")
"""),
("md", r"""
The exact optimum, like the threshold rule, puts most runs on the site nearest the threshold; OCBA does not, because it
measures gaps to the best site. At 300 runs the asymptotic rule overshoots; a larger ε tempers it.
"""),
("md", r"""
## 2. APT on pass/fail arms

12 sites with failure probabilities on both sides of α = 0.10, 1200 runs, ε = 0.01. Error = some site with |p − α| > ε put on the wrong
side (Locatelli et al.'s loss). With one initial pull and a small α, a site whose first run fails gets p̂ = 1, looks far from α
and can be starved; about 1/α initial pulls avoid it. 200 seeds.
"""),
("code", r"""
p_arm = np.array([0.01, 0.02, 0.04, 0.05, 0.06, 0.15, 0.16, 0.2, 0.25, 0.3, 0.4, 0.5]); a, eps, B = 0.10, 0.01, 1200
far = np.abs(p_arm - a) > eps
def err(est): return bool(np.any((est[far] >= a) != (p_arm[far] >= a)))
out = {"uniform": [], "APT, 1 initial pull": [], "APT, 10 initial pulls": [], "KL allocation after 10 pulls": []}
starved = []
for s in range(200):
    rng = np.random.default_rng(s); pull = lambda k: float(rng.random() < p_arm[k])
    n = R.fixed(12, B); out["uniform"].append(err(np.array([rng.binomial(n[k], p_arm[k]) / n[k] for k in range(12)])))
    est, cnt = R.apt(pull, 12, a, B, eps, n_init=1); out["APT, 1 initial pull"].append(err(est)); starved.append(cnt.min())
    est, cnt = R.apt(pull, 12, a, B, eps, n_init=10); out["APT, 10 initial pulls"].append(err(est))
    k0 = np.array([rng.binomial(10, q) for q in p_arm]); ph = (k0 + 0.5) / 11
    n2 = R.integerise(R.threshold_alloc(ph, None, a, B - 120, eps=eps, rate="kl"), B - 120)
    out["KL allocation after 10 pulls"].append(err((k0 + np.array([rng.binomial(n2[k], p_arm[k]) for k in range(12)])) / (10 + n2)))
for k, v in out.items(): print(f"{k:30s} error rate {np.mean(v):.3f}")
print("APT with 1 initial pull: fewest pulls any site got, median over seeds:", np.median(starved))
"""),
("md", r"""
APT with about 1/α initial pulls has the lowest error. With a single initial pull, in the median seed some site gets only
that one run: it was starved.
"""),
("md", r"""
## 3. Fixed replicates, with and without a noise model

`noisy_car`, target {p(x) ≥ 0.10}, 240 runs on Sobol' sites: r = 1 (240 sites), 2, 4 and 8 replicates. A homoskedastic GP
fits one noise level; the heteroskedastic GP needs replicates to learn the noise. 5 seeds, misclassified share of the grid.
"""),
("code", r"""
pn = P.get("noisy_car")
def rep_arm(problem, r, n, seed, mk):
    X = np.repeat(D.sobol(n // r, 2, L.seed_of("design", seed)), r, axis=0)
    y = problem.run(X, np.random.default_rng(L.seed_of("rep", problem.name, seed)))
    return L.evaluate(problem, L.fit(problem, mk, X, y))
ARMS = [("r = 1, hom GP", 1, MD.GPR), ("r = 2, hom GP", 2, MD.GPR), ("r = 2, het GP", 2, MD.HetGP), ("r = 4, het GP", 4, MD.HetGP), ("r = 8, het GP", 8, MD.HetGP)]
t = time.time()
for name, r, mk in ARMS:
    v = [rep_arm(pn, r, 240, s, mk) for s in range(5)]
    print(f"{name:15s} misclassified % median {100*np.median([x['misclassified'] for x in v]):.2f}  false-safe {np.median([x['false_safe'] for x in v]):.3f}")
print(f"{time.time() - t:.0f} s")
"""),
("md", r"""
The same in a search: active learning on the α-threshold h(x) = τ − ŝ(x)Φ⁻¹(α) with the straddle, single runs with a hom GP
against r = 2 with the het GP (the shape of the repo's noise study, `docs/NOISE_REPORT.md`). 200 runs, 3 seeds.
"""),
("code", r"""
t = time.time(); NA = [100, 200]
H = {"single runs, hom GP": [L.active(pn, MD.GPR, L.by_score(A.straddle), 200, s, n0=20, batch=10, checkpoints=NA)[0] for s in range(3)],
     "r = 2, het GP": [L.active(pn, MD.HetGP, L.by_score(A.straddle), 200, s, n0=20, batch=10, replicate=2, checkpoints=NA)[0] for s in range(3)]}
for k, hs in H.items():
    print(f"{k:20s} misclassified % at {NA}:", [round(100 * np.median(L.table(hs, 'misclassified', n)), 2) for n in NA])
print(f"{time.time() - t:.0f} s")
"""),
("md", r"""
## 4. Replicate or explore: one-step IMSPE

With a homoskedastic GP, compare the integrated predictive variance after one run at the best new site with that after one
more replicate at the best existing site (Binois et al. 2019, Prop. 3.1 at horizon 0). Sequentially for 40 runs after 10
Sobol' points, at three noise scales. Gramacy (2020) notes that IMSPE prefers replication only when the predictive
variance is everywhere large enough, and in practice asks for it not often enough.
"""),
("code", r"""
ref = D.sobol(256, 2, 5)
for c in (0.1, 1.0, 3.0):
    pc = P.Problem("noisy_car_x", 2, P.car_following, sd=lambda U, c=c: c * P.car_noise_sd(U), alpha=0.1)
    rng = np.random.default_rng(0); X = D.sobol(10, 2, 0); y = pc.run(X, rng); reps = 0
    for step in range(40):
        m = MD.GPR(restarts=0).fit(X, y)
        what, x, _ = R.imspe_choice(m, X, D.sobol(256, 2, 100 + step), ref)
        reps += what == "replicate"; X = np.vstack([X, x]); y = np.append(y, pc.run(x[None], rng))
    print(f"noise x {c:3.1f}: {reps} of 40 runs were replicates")
"""),
("md", r"""
Replicates stay rare at every noise scale here, in line with Gramacy's remark; a lookahead horizon h > 0 is what Binois et
al. add to make replication more attractive.
"""),
("md", r"""
## 5. esmini: deterministic, so replication is wasted

The esmini cut-in with the ACC controller is deterministic: five reruns of the same point with different seeds give the
same margin.
"""),
("code", r"""
from failreg import esmini_case as E
ec = E.cutin(); pts = np.array([[0.2, 0.3], [0.5, 0.5], [0.8, 0.9]])
for u in pts:
    ys = [ec.run(u[None], np.random.default_rng(s))[0] for s in range(5)]
    print(f"point {u}: margins {np.round(ys, 6)}, spread {np.ptp(ys):.1e}")
"""),
("md", r"""
## 6. esmini: the noisy R157 cut-in

The repo's noisy SUT (`src/stp/noise`): perception noise on the cutter and actuation delay, level `mid`; a 2-D slice at
ego speed 13.3 m/s over v_rel and TTC at lane intrusion; fail = minimum gap below 1 m; target {p(x) ≥ 0.10}. The answer key
is the committed reference (`results/noise/reference_mid.npz`, isotonic p on the applicable grid points). 100 runs on Sobol'
sites: single runs with a hom GP, r = 2 with a hom GP, r = 2 with the het GP; 3 seeds, so read it as a description.
"""),
("code", r"""
en = E.noisy_cutin("mid"); t = time.time()
for name, r, mk in (("r = 1, hom GP", 1, MD.GPR), ("r = 2, hom GP", 2, MD.GPR), ("r = 2, het GP", 2, MD.HetGP)):
    v = [rep_arm(en, r, 100, s, mk) for s in range(3)]
    print(f"{name:15s} misclassified % {np.round([100 * x['misclassified'] for x in v], 2)}  false-safe {np.round([x['false_safe'] for x in v], 3)}")
lost = np.mean([not rec["realised"] for rec in en.records])
print(f"{en.calls} noisy esmini runs in {time.time() - t:.0f} s; {lost:.1%} failed their realisation check (no data, still counted against the budget)")
"""),
("md", r"""
## References

- C.-H. Chen, L. H. Lee, *Stochastic Simulation Optimization: An Optimal Computing Budget Allocation*, World Scientific, 2011 (OCBA, Theorem 3.2).
- R. B. Gramacy, *Surrogates: Gaussian Process Modeling, Design, and Optimization for the Applied Sciences*, CRC Press, 2020 (replication, stochastic kriging, IMSPE).
- M. Binois, J. Huang, R. B. Gramacy, M. Ludkovski, "Replication or Exploration? Sequential Design for Stochastic Simulation Experiments," Technometrics 61(1), 2019 (IMSPE replicate-or-explore).
- A. Locatelli, M. Gutzeit, A. Carpentier, "An optimal algorithm for the Thresholding Bandit Problem," ICML 2016, arXiv:1605.08671 (APT).
- M. Binois, R. B. Gramacy, M. Ludkovski, "Practical heteroscedastic Gaussian process modeling for large simulation experiments," J. Comput. Graph. Stat. 27(4), 2018, arXiv:1611.05902 (no minimum replication needed).
"""),
]
