"""Generate a logical lane-keeping scenario: an S-curve road (OpenDRIVE) and an externally driven ego (OpenSCENARIO)."""
from dataclasses import dataclass, asdict
from pathlib import Path

LANE_WIDTH = 3.5
EGO_WIDTH = 2.0
L_IN, L_ARC1, L_ARC2, L_OUT = 60.0, 80.0, 80.0, 100.0
ROAD_LENGTH = L_IN + L_ARC1 + L_ARC2 + L_OUT


@dataclass(frozen=True)
class Params:
    speed: float       # m/s
    k1: float          # curvature of the first arc, 1/m
    k2: float          # curvature of the second arc, 1/m
    gust: float        # peak lateral disturbance, m/s

    def dict(self):
        return asdict(self)


VARS = ("speed", "k1", "k2", "gust")
XL = [12.0, 0.002, -0.04, 0.0]
XU = [32.0, 0.040, 0.04, 1.0]


def _advance(x, y, h, k, L):
    import math
    if abs(k) < 1e-12:
        return x + L * math.cos(h), y + L * math.sin(h), h
    return x + (math.sin(h + k * L) - math.sin(h)) / k, y - (math.cos(h + k * L) - math.cos(h)) / k, h + k * L


def xodr(p: Params) -> str:
    segs = [(L_IN, None), (L_ARC1, p.k1), (L_ARC2, p.k2), (L_OUT, None)]
    x, y, h, s, g = 0.0, 0.0, 0.0, 0.0, []
    for i, (L, k) in enumerate(segs):
        shape = "<line/>" if k is None else f'<arc curvature="{k:.10f}"/>'
        g.append(f'      <geometry s="{s:.6f}" x="{x:.6f}" y="{y:.6f}" hdg="{h:.10f}" length="{L:.6f}">{shape}</geometry>')
        x, y, h = _advance(x, y, h, k or 0.0, L); s += L
    lane = lambda i, t: f'<lane id="{i}" type="{t}" level="false"><link/><width sOffset="0" a="{LANE_WIDTH if t == "driving" else 8.0}" b="0" c="0" d="0"/></lane>'
    return f'''<?xml version="1.0" standalone="yes"?>
<OpenDRIVE>
  <header revMajor="1" revMinor="5" name="lk" version="1" date="2026-11-10" north="0" south="0" east="0" west="0"/>
  <road name="r" length="{ROAD_LENGTH:.6f}" id="1" junction="-1">
    <link/>
    <planView>
{chr(10).join(g)}
    </planView>
    <lanes>
      <laneSection s="0">
        <center><lane id="0" type="none" level="false"><link/></lane></center>
        <right>{lane(-1, "driving")}{lane(-2, "shoulder")}</right>
      </laneSection>
    </lanes>
  </road>
</OpenDRIVE>
'''


def xosc(p: Params, xodr_name: str, external: bool = True, start_s: float = 5.0, lane: int = -1) -> str:
    ctrl = "ExternalController" if external else "DefaultController"
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<OpenSCENARIO>
  <FileHeader revMajor="1" revMinor="1" date="2026-11-10T00:00:00" description="lane keeping" author="stp"/>
  <ParameterDeclarations/>
  <CatalogLocations/>
  <RoadNetwork><LogicFile filepath="{xodr_name}"/></RoadNetwork>
  <Entities>
    <ScenarioObject name="Ego">
      <Vehicle name="car" vehicleCategory="car">
        <ParameterDeclarations/>
        <BoundingBox><Center x="1.3" y="0" z="0.8"/><Dimensions width="{EGO_WIDTH}" length="4.5" height="1.5"/></BoundingBox>
        <Performance maxSpeed="70" maxDeceleration="10" maxAcceleration="10"/>
        <Axles>
          <FrontAxle maxSteering="0.5" wheelDiameter="0.6" trackWidth="1.6" positionX="2.7" positionZ="0.3"/>
          <RearAxle maxSteering="0" wheelDiameter="0.6" trackWidth="1.6" positionX="0" positionZ="0.3"/>
        </Axles>
        <Properties/>
      </Vehicle>
      <ObjectController><Controller name="ctl"><ParameterDeclarations/><Properties><Property name="esminiController" value="{ctrl}"/></Properties></Controller></ObjectController>
    </ScenarioObject>
  </Entities>
  <Storyboard>
    <Init><Actions><Private entityRef="Ego">
      <PrivateAction><TeleportAction><Position><LanePosition roadId="1" laneId="{lane}" offset="0" s="{start_s}"/></Position></TeleportAction></PrivateAction>
      <PrivateAction><ControllerAction><ActivateControllerAction longitudinal="true" lateral="true"/></ControllerAction></PrivateAction>
      <PrivateAction><LongitudinalAction><SpeedAction><SpeedActionDynamics dynamicsShape="step" value="0" dynamicsDimension="time"/><SpeedActionTarget><AbsoluteTargetSpeed value="{p.speed}"/></SpeedActionTarget></SpeedAction></LongitudinalAction></PrivateAction>
    </Private></Actions></Init>
    <Story name="s"><Act name="a"><ManeuverGroup maximumExecutionCount="1" name="m"><Actors selectTriggeringEntities="false"><EntityRef entityRef="Ego"/></Actors></ManeuverGroup>
      <StartTrigger><ConditionGroup><Condition name="c" delay="0" conditionEdge="none"><ByValueCondition><SimulationTimeCondition value="0" rule="greaterThan"/></ByValueCondition></Condition></ConditionGroup></StartTrigger>
    </Act></Story>
    <StopTrigger/>
  </Storyboard>
</OpenSCENARIO>
'''


def write(p: Params, d: Path, **kw):
    d.mkdir(parents=True, exist_ok=True)
    (d / "r.xodr").write_text(xodr(p))
    f = d / "s.xosc"; f.write_text(xosc(p, "r.xodr", **kw))
    return f
