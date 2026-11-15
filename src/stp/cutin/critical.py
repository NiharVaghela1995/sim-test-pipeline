"""Critical concrete scenarios and the 30 m/s read-off table (report).

Writes results/gp_boundary/critical/: for ego speed 30 m/s and relative speed 0, -2.5, -5, -7.5, -10 m/s, the last failing
and first passing reference grid gaps (.xosc + shared .xodr), plus the 10 GP-AL seed-0 runs with the smallest |margin|.
index.csv lists every file with its parameters, margin and verdict. readoff_30.csv gives, per relative speed, the reference
critical gap and the GP-AL (seed 0, 300 runs) estimate with its band.

  python -m stp.cutin.critical
"""
import csv
import numpy as np
from . import gp as GP, reference as REF, campaign as C, runner as R, scenario as S

OUT = C.OUT / "critical"


def main(v=30.0, dvs=(0.0, -2.5, -5.0, -7.5, -10.0), seed=0, n=300):
    OUT.mkdir(parents=True, exist_ok=True)
    ref = REF.load(); iv = int(np.argmin(np.abs(ref["V"] - v))); Gs = ref["G"]
    rows_al = C.run_campaign("gp_al", seed)[:n]; g = C.model_at(rows_al, seed, n)
    index, readoff = [], []
    for dv in dvs:
        idv = int(np.argmin(np.abs(ref["DV"] - dv))); line = ref["margin"][iv, idv]
        gstar = float(REF.boundary_gap(line[None])[0])
        U = GP.to_unit(np.stack([np.full(len(Gs), v), Gs, np.full(len(Gs), dv)], 1)); mu, sd = GP.predict(g, U)
        est = float(REF.boundary_gap(mu[None])[0])
        lo, hi = float(REF.boundary_gap((mu + 1.96 * sd)[None])[0]), float(REF.boundary_gap((mu - 1.96 * sd)[None])[0])
        readoff.append(dict(ego_speed=v, rel_speed=dv, reference_gap=round(gstar, 2), gp_al_gap=round(est, 2), band_low=round(lo, 2), band_high=round(hi, 2),
                            reference_inside_band=lo <= gstar <= hi))
        fails = np.nonzero(line < 0)[0]
        if len(fails) and fails[-1] < len(Gs) - 1:
            for k, tag in ((fails[-1], "last_fail"), (fails[-1] + 1, "first_pass")):
                index.append((f"ref_v30_dv{dv:+.1f}_{tag}", [v, float(Gs[k]), dv]))
    for r in sorted([r for r in rows_al if r["realised"]], key=lambda r: abs(r["margin"]))[:10]:
        index.append((f"gpal_s{seed}_v{r['x'][0]:.2f}_g{r['x'][1]:.2f}_dv{r['x'][2]:+.2f}", r["x"]))
    with open(OUT / "index.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["file", "ego_speed", "gap", "rel_speed", "realised", "min_ttc", "margin", "verdict"])
        for name, x in index:
            r = R.run(S.Params(*map(float, x)), 0, keep_file=OUT / f"{name}.xosc")
            w.writerow([f"{name}.xosc", *x, r["realised"], round(r["min_ttc"], 4), round(r["margin"], 4), "fail" if r["failed"] else "pass"])
    (OUT / "cutin.xodr").write_text(S.xodr())
    with open(C.OUT / "readoff_30.csv", "w", newline="") as f:
        w = csv.DictWriter(f, list(readoff[0])); w.writeheader(); w.writerows(readoff)
    for r in readoff: print(r)


if __name__ == "__main__":
    main()
