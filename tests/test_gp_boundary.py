"""GP boundary search, reference boundary rules, metrics and determinism (docs/GP_BOUNDARY_PLAN.md)."""
import json
import os
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np
import pytest
from stp.cutin import gp as GP, reference as REF, campaign as C, metrics as M

G = REF.G


# reference boundary rule
def test_boundary_gap_monotone_line():
    line = G - 12.3                       # fails below 12.3 m
    assert abs(REF.boundary_gap(line[None, :])[0] - 12.3) < 1e-9


def test_boundary_gap_all_pass_and_all_fail():
    assert REF.boundary_gap(np.ones((1, len(G))))[0] == 5.0
    assert REF.boundary_gap(-np.ones((1, len(G))))[0] == 40.0


def test_boundary_gap_non_monotone_takes_last_crossing():
    line = G - 20.0; line[:4] = -1.0; line[4:8] = 1.0   # small failing island at 5-6 m, then fail again until 20 m
    assert abs(REF.boundary_gap(line[None, :])[0] - 20.0) < 1e-9


def test_crossings_finds_every_sign_change():
    m = np.ones((1, 1, len(G))); m[0, 0, 10:20] = -1; m[0, 0, 50] = -1
    _, _, gc = REF.crossings(m)
    assert len(gc) == 4


# acquisition
def test_straddle_prefers_uncertain_points_near_zero():
    s = GP.straddle(np.array([0.0, 0.0, 2.0]), np.array([1.0, 0.1, 1.0]))
    assert s[0] > s[1] > s[2]


def test_select_batch_keeps_distance_and_fills():
    pool = GP.sobol_unit(256, 1); scores = -np.linalg.norm(pool - 0.5, axis=1)   # everything wants the centre
    B = GP.select_batch(pool, scores, np.full((1, 3), 0.5), 10)
    d = np.linalg.norm(B[:, None] - B[None], axis=2) + np.eye(10)
    assert len(B) == 10 and d.min() >= GP.CFG["min_dist"] and np.linalg.norm(B - 0.5, axis=1).min() >= GP.CFG["min_dist"]
    B2 = GP.select_batch(pool[:12], scores[:12], pool[:12], 10)                    # nothing far enough: backfill
    assert len(B2) == 10


def test_seeds_and_designs_are_stable():
    assert GP.seed_of("design", 0) == GP.seed_of("design", 0) != GP.seed_of("design", 1)
    assert np.array_equal(GP.sobol_unit(30, 7), GP.sobol_unit(300, 7)[:30])
    assert np.array_equal(C.fixed_design("gp_al", 3, 30), C.fixed_design("sobol", 3, 300)[:30])
    assert not np.array_equal(C.fixed_design("random", 3, 30), C.fixed_design("sobol", 3, 30))


def test_unit_scaling_round_trip():
    X = np.array([[20, 5, -10], [35, 40, 0], [27.5, 22.5, -5]], float)
    assert np.allclose(GP.from_unit(GP.to_unit(X)), X) and np.allclose(GP.to_unit(X)[2], 0.5)


def test_gp_recovers_known_plane_boundary():
    """Synthetic known answer: margin = gap - (10 + 0.8*(ego-20) - 1.0*rel) / 1 ... a plane; GP-AL beats nothing here,
    it only has to find the boundary to within a small error with 80 points."""
    f = lambda X: (X[:, 1] - (10 + 0.8 * (X[:, 0] - 20) - 1.0 * X[:, 2])) / 5.0
    U = GP.sobol_unit(80, 3); X = GP.from_unit(U)
    g = GP.fit(U, f(X), 1)
    Ut = np.random.default_rng(0).random((4000, 3)); mu, sd = GP.predict(g, Ut)
    assert np.mean((mu < 0) != (f(GP.from_unit(Ut)) < 0)) < 0.02


def test_metrics_on_perfect_and_constant_fields():
    m = np.stack(np.meshgrid(np.zeros(3), np.zeros(2), G - 15.0, indexing="ij"))[2]
    R = dict(ok=np.ones(m.size, bool), cls=m.ravel() < 0, g_star=REF.boundary_gap(m), shape=m.shape)
    perfect = M.score_field(m.ravel(), R); const = M.score_field(np.ones(m.size), R)
    assert perfect["misclass"] == 0 and perfect["berr_mean"] < 1e-9
    assert abs(const["misclass"] - np.mean(G < 15)) < 1e-12 and abs(const["berr_mean"] - 10.0) < 1e-9


# determinism and resume (runs esmini)
def test_resumed_campaign_equals_uninterrupted(tmp_path):
    a = C.run_campaign("gp_al", 0, budget=50, raw_dir=tmp_path / "a", workers=2)
    C.run_campaign("gp_al", 0, budget=40, raw_dir=tmp_path / "b", workers=2)
    f = tmp_path / "b" / "gp_al_0.jsonl"
    lines = f.read_text().splitlines(); f.write_text("\n".join(lines[:35]) + "\n" + lines[35][:20])   # crash mid-batch, torn line
    b = C.run_campaign("gp_al", 0, budget=50, raw_dir=tmp_path / "b", workers=2)
    assert [r["x"] for r in a] == [r["x"] for r in b] and [r["margin"] for r in a] == [r["margin"] for r in b]


def test_resume_refuses_foreign_rows(tmp_path):
    C.run_campaign("sobol", 0, budget=20, raw_dir=tmp_path, workers=2)
    (tmp_path / "sobol_1.jsonl").write_text((tmp_path / "sobol_0.jsonl").read_text())
    with pytest.raises(RuntimeError):
        C.run_campaign("sobol", 1, budget=20, raw_dir=tmp_path, workers=2)


def test_rerun_from_manifest_in_fresh_process_is_identical(tmp_path):
    rows = C.run_campaign("gp_al", 1, budget=40, raw_dir=tmp_path, workers=2)
    mf = tmp_path / "m.json"; mf.write_text(json.dumps(C.manifest("gp_al", 1, rows, C.grid_units(), 40)))
    env = {k: v for k, v in os.environ.items() if not k.endswith("_NUM_THREADS")}
    env["PYTHONPATH"] = str(ROOT / "src")
    p = subprocess.run([sys.executable, "-m", "stp.cutin.campaign", "rerun", str(mf)], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(p.stdout.strip().splitlines()[-1])["identical"]


def test_rerun_detects_a_changed_result(tmp_path):
    rows = C.run_campaign("random", 2, budget=20, raw_dir=tmp_path, workers=2)
    m = C.manifest("random", 2, rows, C.grid_units(), 20); m["runs"][5]["margin"] += 1e-12
    mf = tmp_path / "m.json"; mf.write_text(json.dumps(m))
    assert not C.rerun(mf, workers=2)["identical"]
