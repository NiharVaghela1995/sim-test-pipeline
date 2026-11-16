"""R157 test design: applicability, parameter mapping, KPI and one esmini known answer (docs/R157_TEST_DESIGN.md)."""
import numpy as np
import pytest
from stp.r157 import design as D, runner as RR


def test_applicability_condition_c():
    # v_rel at the reference point slightly above the set v_rel because of the cutter's sag; line at v_rel/12 + 0.35
    x_in, x_out = np.array([[15.0, 3.0, 1.0]]), np.array([[15.0, 3.0, 0.5]])
    assert D.applicable(x_in)[0] and not D.applicable(x_out)[0]
    assert abs(D.ttc_li_min(3.0) - 0.6) < 1e-12


def test_odd_cutter_speed():
    assert not D.in_odd(np.array([[10.0, 5.0, 2.0]]))[0]        # cutter 5 m/s < 6 m/s
    assert D.in_odd(np.array([[14.0, 5.0, 2.0]]))[0]


def test_reference_point_geometry():
    assert abs(D.REF_LINE - 2.11) < 1e-12
    taus = [D.tau_ref(v) for v in (6.0, 10.0, 16.0)]
    assert all(D.T_VIS_MIN <= t < 1.17 for t in taus) and taus[0] < taus[-1]   # faster cutter: smaller yaw, later reference


def test_kpi_constructed_trace():
    t_ref = 3.0
    t = np.arange(0, 6, 0.02); k0 = int(np.searchsorted(t, t_ref))
    gap = np.full(len(t), 5.0); gap[:k0] = 0.2                    # small gap before the reference point does not count
    gap[k0 + 50] = 0.7
    tr = dict(t=list(t), gap=list(gap), dy=[3.0] * len(t))
    g, coll, k = RR.kpi(tr, t_ref)
    assert g == pytest.approx(0.7) and not coll and k == k0 + 50
    tr["gap"][k0 + 60] = -0.1; tr["dy"][k0 + 60] = 0.5
    assert RR.kpi(tr, t_ref)[:2] == (0.0, True)


def test_realised_and_ttc_li_measured():
    r = RR.run([14.0, 3.0, 1.5])
    assert r["realised"] and abs(r["ttc_li_meas"] - 1.5) <= RR.TOL_TTC and r["t_vis"] >= 0.72
