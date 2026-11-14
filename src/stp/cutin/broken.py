"""Write the table of deliberately broken scenarios and the gates each one trips (report, step 1)."""
import csv
import sys
from pathlib import Path
from . import runner as R, scenario as S

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))


def main(out=Path("results/gp_boundary")):
    from test_cutin import BROKEN, P
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "broken_scenarios.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["defect", "realised", "verdict", "gates_failed", "expected_subset"])
        for name, d, exp in BROKEN:
            r = R.run(P, defects=d, keep_file=out / "broken" / (name.replace(" m/s", "_mps").replace(" ", "_") + ".xosc"))
            fg = sorted(k for k, v in r["gates"].items() if not v)
            w.writerow([name, r["realised"], ("fail" if r["failed"] else "pass") if r["realised"] else "none", " ".join(fg), " ".join(sorted(exp))])
            print(f"{name:38s} realised={r['realised']}  failed gates: {', '.join(fg)}")


if __name__ == "__main__":
    main()
