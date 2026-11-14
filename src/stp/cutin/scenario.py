"""Logical cut-in scenario: a straight two-lane road (OpenDRIVE) and an OpenSCENARIO file with an ACC ego and a
scripted cutting car.

Parameters (frozen in docs/GP_BOUNDARY_PLAN.md):
  ego_speed  20-35 m/s   ego speed, also the ACC set speed
  gap         5-40 m     bumper-to-bumper longitudinal gap at the cut-in moment: when the cutting car's body first
                         crosses the lane line into the ego lane
  rel_speed -10-0  m/s   cutting car speed minus ego speed, held constant by the cutting car

The cutting car starts in the right lane (-2) and starts a sinusoidal lane change into the ego lane (-1) at T_LC, taking
LC_TIME seconds. Its body crosses the lane line TAU_X seconds later (TRIGGER_LEAD = 0.01   # s: esmini starts a triggered action one 0.02 s step after the step where the condition first
                      # holds, so the trigger is set half a step early for the lane change to start at T_LC exactly
T_CUT = T_LC + TAU_X). Its start position is placed
so that, with both cars at their set speeds, the gap at T_CUT equals `gap`.

`Defects` lets a test build a deliberately broken file while the realisation check still compares against the
intended parameters. A default Defects() writes the correct scenario.
"""
from dataclasses import dataclass, asdict, field
from pathlib import Path
import math
import numpy as np

LANE_WIDTH = 3.5
ROAD_LENGTH = 1500.0
CAR_LENGTH, CAR_WIDTH, BB_X = 4.5, 2.0, 1.3       # bounding box centre 1.3 m ahead of the reference point
FRONT, REAR = BB_X + CAR_LENGTH / 2, CAR_LENGTH / 2 - BB_X   # 3.55 m ahead, 0.95 m behind the reference point
EGO_S0 = 20.0
EGO_LANE, CUT_LANE = -1, -2
T_LC = 2.0           # s, lane change start
LC_TIME = 3.0        # s, lane change duration (sinusoidal)
LINE_SHIFT = LANE_WIDTH / 2 - CAR_WIDTH / 2      # lateral move at which the car body reaches the lane line: 0.75 m
# esmini's sinusoidal shape: shift(tau) = LANE_WIDTH * (1 - cos(pi * tau / LC_TIME)) / 2
TAU_X = LC_TIME / math.pi * math.acos(1 - 2 * LINE_SHIFT / LANE_WIDTH)
TRIGGER_LEAD = 0.01   # s: esmini starts a triggered action one 0.02 s step after the step where the condition first
                      # holds, so the trigger is set half a step early for the lane change to start at T_LC exactly
T_CUT = T_LC + TAU_X  # s, cut-in moment (body crosses the lane line)
T_END = 15.0         # s
ACC_TIME_GAP = 1.5   # s, ACC set time gap (esmini property timeGap)
MAX_DECEL = 6.0      # m/s^2, ego Performance maxDeceleration, used by the ACC

VARS = ("ego_speed", "gap", "rel_speed")
XL = [20.0, 5.0, -10.0]
XU = [35.0, 40.0, 0.0]


@dataclass(frozen=True)
class Params:
    ego_speed: float
    gap: float
    rel_speed: float

    def dict(self):
        return asdict(self)

    @property
    def cut_speed(self):
        return self.ego_speed + self.rel_speed

    @property
    def cut_s0(self):
        """Cutting car reference-point s at t = 0 so the bumper gap at T_CUT is `gap` at constant speeds."""
        return EGO_S0 + FRONT + REAR + self.gap - self.rel_speed * T_CUT + x_loss(self.cut_speed, TAU_X)


def x_loss(v, tau, n=2000):
    """Longitudinal distance the cutting car loses in the first tau seconds of the lane change, because its path speed v
    is partly lateral: integral of v * (1 - cos h) with sin h = (d shift / dt) / v. About 0.02 m at 20 m/s."""
    dt = tau / n
    tt = (np.arange(n) + 0.5) * dt
    lat = LANE_WIDTH * math.pi / (2 * LC_TIME) * np.sin(math.pi * tt / LC_TIME)
    return float(np.sum(v * (1 - np.sqrt(1 - (lat / v) ** 2))) * dt)


@dataclass(frozen=True)
class Defects:
    ego_controller: str = "ACCController"   # e.g. "DefaultController": ego ignores the cutting car
    cut_lane: int = CUT_LANE                # e.g. -1: cutting car already starts in the ego lane
    target_lane: int = EGO_LANE             # e.g. -2: "lane change" stays in its own lane
    lane_change: bool = True                # False: no lane change at all
    t_lc: float = T_LC                      # trigger time of the lane change
    cut_s_shift: float = 0.0                # m added to the cutting car start position
    cut_speed_shift: float = 0.0            # m/s added to the cutting car speed
    ego_speed_shift: float = 0.0            # m/s added to the ego initial speed and ACC set speed
    t_end: float = T_END


def xodr() -> str:
    lane = lambda i, t, w: f'<lane id="{i}" type="{t}" level="false"><link/><width sOffset="0" a="{w}" b="0" c="0" d="0"/><roadMark sOffset="0" type="{"broken" if i == -1 else "solid"}" weight="standard" color="standard" width="0.12"/></lane>'
    return f'''<?xml version="1.0" standalone="yes"?>
<OpenDRIVE>
  <header revMajor="1" revMinor="5" name="cutin" version="1" date="2026-11-14" north="0" south="0" east="0" west="0"/>
  <road name="r" length="{ROAD_LENGTH:.6f}" id="1" junction="-1">
    <link/>
    <planView>
      <geometry s="0" x="0" y="0" hdg="0" length="{ROAD_LENGTH:.6f}"><line/></geometry>
    </planView>
    <lanes>
      <laneSection s="0">
        <center><lane id="0" type="none" level="false"><link/></lane></center>
        <right>{lane(-1, "driving", LANE_WIDTH)}{lane(-2, "driving", LANE_WIDTH)}{lane(-3, "shoulder", 3.0)}</right>
      </laneSection>
    </lanes>
  </road>
</OpenDRIVE>
'''


def _vehicle(name):
    return f'''<Vehicle name="{name}" vehicleCategory="car">
        <ParameterDeclarations/>
        <BoundingBox><Center x="{BB_X}" y="0" z="0.8"/><Dimensions width="{CAR_WIDTH}" length="{CAR_LENGTH}" height="1.5"/></BoundingBox>
        <Performance maxSpeed="70" maxDeceleration="{MAX_DECEL}" maxAcceleration="3"/>
        <Axles>
          <FrontAxle maxSteering="0.5" wheelDiameter="0.6" trackWidth="1.6" positionX="2.7" positionZ="0.3"/>
          <RearAxle maxSteering="0" wheelDiameter="0.6" trackWidth="1.6" positionX="0" positionZ="0.3"/>
        </Axles>
        <Properties/>
      </Vehicle>'''


def _speed(v):
    return f'<PrivateAction><LongitudinalAction><SpeedAction><SpeedActionDynamics dynamicsShape="step" value="0" dynamicsDimension="time"/><SpeedActionTarget><AbsoluteTargetSpeed value="{v:.10g}"/></SpeedActionTarget></SpeedAction></LongitudinalAction></PrivateAction>'


def _pos(lane, s):
    return f'<PrivateAction><TeleportAction><Position><LanePosition roadId="1" laneId="{lane}" offset="0" s="{s:.10g}"/></Position></TeleportAction></PrivateAction>'


def xosc(p: Params, xodr_name: str, d: Defects = Defects()) -> str:
    v_ego = p.ego_speed + d.ego_speed_shift
    v_cut = p.cut_speed + d.cut_speed_shift
    s_cut = p.cut_s0 + d.cut_s_shift
    lc = "" if not d.lane_change else f'''
      <ManeuverGroup maximumExecutionCount="1" name="cut"><Actors selectTriggeringEntities="false"><EntityRef entityRef="Cut"/></Actors>
        <Maneuver name="cutin"><Event name="lc" priority="override"><Action name="lc"><PrivateAction><LateralAction><LaneChangeAction>
          <LaneChangeActionDynamics dynamicsShape="sinusoidal" value="{LC_TIME}" dynamicsDimension="time"/>
          <LaneChangeTarget><AbsoluteTargetLane value="{d.target_lane}"/></LaneChangeTarget>
        </LaneChangeAction></LateralAction></PrivateAction></Action>
        <StartTrigger><ConditionGroup><Condition name="t" delay="0" conditionEdge="rising"><ByValueCondition><SimulationTimeCondition value="{d.t_lc - TRIGGER_LEAD:.10g}" rule="greaterThan"/></ByValueCondition></Condition></ConditionGroup></StartTrigger>
        </Event></Maneuver>
      </ManeuverGroup>'''
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<OpenSCENARIO>
  <FileHeader revMajor="1" revMinor="1" date="2026-11-14T00:00:00" description="cut-in ego_speed={p.ego_speed:.10g} gap={p.gap:.10g} rel_speed={p.rel_speed:.10g}" author="stp"/>
  <ParameterDeclarations/>
  <CatalogLocations/>
  <RoadNetwork><LogicFile filepath="{xodr_name}"/></RoadNetwork>
  <Entities>
    <ScenarioObject name="Ego">
      {_vehicle("ego")}
      <ObjectController><Controller name="sut"><ParameterDeclarations/><Properties>
        <Property name="esminiController" value="{d.ego_controller}"/>
        <Property name="timeGap" value="{ACC_TIME_GAP}"/>
        <Property name="setSpeed" value="{v_ego:.10g}"/>
        <Property name="mode" value="override"/>
      </Properties></Controller></ObjectController>
    </ScenarioObject>
    <ScenarioObject name="Cut">
      {_vehicle("cut")}
    </ScenarioObject>
  </Entities>
  <Storyboard>
    <Init><Actions>
      <Private entityRef="Ego">{_pos(EGO_LANE, EGO_S0)}{_speed(v_ego)}
        <PrivateAction><ControllerAction><ActivateControllerAction longitudinal="true" lateral="false"/></ControllerAction></PrivateAction>
      </Private>
      <Private entityRef="Cut">{_pos(d.cut_lane, s_cut)}{_speed(v_cut)}</Private>
    </Actions></Init>
    <Story name="s"><Act name="a">{lc}
      <StartTrigger><ConditionGroup><Condition name="c" delay="0" conditionEdge="none"><ByValueCondition><SimulationTimeCondition value="0" rule="greaterThan"/></ByValueCondition></Condition></ConditionGroup></StartTrigger>
    </Act></Story>
    <StopTrigger><ConditionGroup><Condition name="end" delay="0" conditionEdge="rising"><ByValueCondition><SimulationTimeCondition value="{d.t_end:.10g}" rule="greaterThan"/></ByValueCondition></Condition></ConditionGroup></StopTrigger>
  </Storyboard>
</OpenSCENARIO>
'''


def write(p: Params, d_out: Path, defects: Defects = Defects(), name="cutin"):
    d_out.mkdir(parents=True, exist_ok=True)
    (d_out / "cutin.xodr").write_text(xodr())
    f = d_out / f"{name}.xosc"
    f.write_text(xosc(p, "cutin.xodr", defects))
    return f
