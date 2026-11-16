# Test design: UN R157 cut-in rule on the esmini ACC cut-in (2026-11-16)

**Source.** UN Regulation No. 157, Automated Lane Keeping Systems, E/ECE/TRANS/505/Rev.3/Add.156, 4 March 2021 (the original version; the document states it is a documentation tool and that the authentic text is ECE/TRANS/WP.29/2020/81). Local copy: `~/Documents/03_Master_thesis/03_Literature/E_Scenario_Based_VnV_Foundations/UNECE_2021_R157_ALKS.pdf`; printed page = PDF page. Later amendments (for example higher speeds) were **not** checked and are not used. Code: `src/stp/r157/design.py`, `src/stp/r157/runner.py`.

## Rule → KPI → threshold → parameters

| Step | Choice | Source |
|---|---|---|
| Rule | "The activated system shall avoid a collision with a cutting in vehicle", provided (a) the cutter "maintains its longitudinal speed which is lower than the longitudinal speed of the ALKS vehicle", (b) its "lateral movement … has been visible for a time of at least 0.72 seconds before the reference point for TTC_LaneIntrusion is reached", (c) TTC_LaneIntrusion > v_rel/(2·6 m/s²) + 0.35 s | para. 5.2.5.2, p. 10 |
| Reference point | "the outside of the tyre of the intruding vehicle's front wheel closest to the lane markings crosses a line 0.3 m beyond the outside edge of the visible lane marking" | para. 5.2.5.2, p. 10 |
| TTC | longitudinal distance divided by longitudinal relative speed "at any instant in time" | Annex 5 para. 2.1, p. 59 |
| Outside (a)–(c) | not "no requirement": "For conditions not specified in paragraphs 5.2.4., 5.2.5. or its subparagraphs, this shall be ensured at least to the level at which a competent and careful human driver could minimize the risks" (with Annex 4 App. 3 as guidance); and 5.2.5.4: the system "shall not deactivate or unreasonably switch the control strategy in these other conditions". Neither is tested here | paras. 5.2.5, 5.2.5.4, p. 10 |
| Speed scope | ALKS up to 60 km/h | para. 5.2.3.1, p. 9 |
| Test conditions | vary TTC, distance and relative velocity, covering avoidable and unavoidable cut-ins; vary lateral velocity | Annex 5 para. 4.4.3, p. 61 |
| KPI | min_gap: smallest bumper gap from the reference point to the end of the 15 s run; 0 if the cars collide (gap ≤ 0 with lateral overlap) | design (below) |
| Threshold | **pass if min_gap ≥ D_SAFE = 1.0 m**. R157's criterion is no collision (min_gap > 0); the 1.0 m is a **stated safety margin, our own choice**, not from R157. Reported second: the pure R157 criterion (no collision) | para. 5.2.5.2 + own margin |
| Margin for the search | margin = min(min_gap, 10 m) − 1.0 m | design |
| What 2 s is not | The 2 s TTC in Annex 4 App. 3 (p. 44) is the driver model's danger value. It is **not** used as a threshold here | Annex 4 App. 3 §3.4.1, p. 44 |

## Parameters and ranges (the logical scenario)

| Parameter | Unit | Range | Source |
|---|---|---|---|
| ego speed (also the ACC set speed) | m/s | 10.0 – 16.667 (36 – 60 km/h) | upper: para. 5.2.3.1, p. 9; lower: ODD assumption |
| v_rel = ego speed − cutter speed, set before the lane change | m/s | 0.5 – 8.0 | > 0: para. 5.2.5.2(a); bounds: ODD assumption |
| TTC_LaneIntrusion | s | 0.2 – 3.0 | para. 5.2.5.2(c); range extends below the applicability line as Annex 5 para. 4.4.3(a) asks; bounds: design |
| cutter speed | m/s | ≥ 6.0 | ODD constraint (see condition a) |

**Fixed (hidden constants made explicit).** Straight two-lane road, lanes 3.5 m; cutter in the right lane, sinusoidal lane change of 3.0 s starting at 2.0 s; car size 4.5 × 2.0 m (both); ego ACC: esmini `ACCController`, time gap 1.5 s, maximum deceleration 6 m/s², longitudinal only; run 15 s at 0.02 s steps; esmini 3.11.0 pinned by sha256. These come from the GP demo (`docs/GP_BOUNDARY_PLAN.md`) and are not varied.

## Applicability: where the rule requires avoidance

Runs are drawn **only** where §5.2.5.2 applies. Elsewhere this paragraph's collision-avoidance requirement does not apply, but the weaker "competent and careful human driver" level of para. 5.2.5 and the no-deactivation clause of 5.2.5.4 do; this test does not check them.

- **(a) Constant lower longitudinal speed.** The cutter is scripted at a constant path speed below the ego's. esmini's lane change keeps the *path* speed, so the cutter's longitudinal speed sags while it turns (first pilot: up to 0.56 m/s at the lowest cutter speeds drawn; about 1 m/s for a 2 m/s cutter by the geometry). Read here as: sag up to the reference point ≤ 0.30 m/s, which holds for cutter speeds ≥ 6 m/s (ODD constraint). Checked per run (gate `cut_speed_lc`).
- **(b) Visibility ≥ 0.72 s.** Lateral motion starts at the lane-change start; the reference point is reached about 0.8–1.0 s later for the fixed 3.0 s lane change (depending on the cutter's speed, through its yaw). Checked per run (gate `visibility`).
- **(c) TTC_LaneIntrusion > v_rel,ref/12 + 0.35 s**, with v_rel,ref the *longitudinal* relative speed at the reference point (ego at set speed, cutter's sagged longitudinal speed). R157 says only "relative velocity between both vehicles"; taking the longitudinal component is **our reading** (effect ≤ 0.025 s).
- **Reference point geometry.** The road marking is 0.12 m wide (`scenario.xodr()`), so its outside edge is 0.06 m past the lane line and the reference line is 2.11 m from the cutter's lane centre. The intruding front tyre is 2.7 m ahead of the reference point (vehicle file) and its outside edge 0.9 m from the centre line (half track 0.8 m plus an assumed half tyre width 0.1 m); its lateral position is computed with the cutter's heading (yaw). The reference time therefore depends on the cutter's speed (2.80–3.02 s after start in this box). Found again in every trace (gate `ttc_li_realised`).
- **TTC_LaneIntrusion is nominal.** It is the TTC at the reference point with the ego still at its set speed: the criticality of the cutter's manoeuvre as the test sets it up. esmini's ACC often brakes before that point (it reacts while the cutter is 2.7–3.1 m to the side), so the **actual** TTC at the reference point is larger, for example 1.57 s for a nominal 1.0 s. Every run records the actual value; the report shows both. A compliant verdict at a nominal TTC_LaneIntrusion therefore includes the system's early reaction, which the rule allows.

## Realisation

All 13 gates of the demo (`src/stp/cutin/gates.py`), including `dynamics_valid_to_kpi` (no over-braking beyond the deceleration limit before the KPI minimum), plus three R157 gates: `ttc_li_realised` (TTC_LaneIntrusion measured in the trace within 0.02 s of the design), `visibility` (≥ 0.72 s), `cut_speed_lc` (longitudinal sag ≤ 0.30 m/s). A run failing any gate gets no verdict.

## What this design cannot say

It tests esmini's ACC, not an ALKS; there are no sensors, so "visible" is geometric. Not covered: different lateral velocities and lateral accelerations (Annex 5 4.4.3(c); 4.4.2 makes lateral velocity part of criticality, here it is fixed by the 3 s lane change); accelerating or decelerating cutters (4.4.3(b)); powered two-wheelers (4.4.3(d)); the competent-driver level outside (a)–(c) and the no-deactivation clause (5.2.5, 5.2.5.4); re-establishing the following distance "without any harsh braking" (5.2.3.3, p. 9), and the fact that any deceleration over 5 m/s² counts as an Emergency Manoeuvre (5.3.1.1, p. 10): esmini's ACC brakes up to 6 m/s² and over-brakes in a few runs, which the realisation gate excludes but does not judge. The 1.0 m margin is a choice. Collision is judged with axis-aligned boxes (yaw ignored).

## Independent review before the plan

An independent read-only review of this design against the regulation text (16 Nov 2026) found: a reference point that ignored yaw and the 0.12 m marking (fixed: now yaw-aware, per cutter speed), an unstated nominal TTC (now stated, actual TTC recorded), a misstatement of what applies outside (a)–(c) (fixed), missing limits (added), the v_rel reading (labelled), and a sag figure (corrected). Quotes, pages, units and the code's gap placement were confirmed.
