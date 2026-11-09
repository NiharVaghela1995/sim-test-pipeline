"""Thin ctypes binding to libesminiLib (pinned in env/esmini.lock)."""
import ctypes as C
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "third_party/esmini_v3.11.0/esmini/bin/libesminiLib.so"


class ObjectState(C.Structure):
    _fields_ = [("id", C.c_int), ("model_id", C.c_int), ("ctrl_type", C.c_int), ("timestamp", C.c_double), ("x", C.c_double), ("y", C.c_double), ("z", C.c_double),
                ("h", C.c_double), ("p", C.c_double), ("r", C.c_double), ("roadId", C.c_uint), ("junctionId", C.c_uint), ("t", C.c_double), ("laneId", C.c_int),
                ("laneOffset", C.c_double), ("s", C.c_double), ("speed", C.c_double), ("centerOffsetX", C.c_double), ("centerOffsetY", C.c_double), ("centerOffsetZ", C.c_double),
                ("width", C.c_double), ("length", C.c_double), ("height", C.c_double), ("objectType", C.c_int), ("objectCategory", C.c_int), ("wheel_angle", C.c_double), ("wheel_rot", C.c_double), ("visibilityMask", C.c_int)]


class RoadInfo(C.Structure):
    _fields_ = [("global_pos_x", C.c_double), ("global_pos_y", C.c_double), ("global_pos_z", C.c_double), ("local_pos_x", C.c_double), ("local_pos_y", C.c_double), ("local_pos_z", C.c_double),
                ("angle", C.c_double), ("road_heading", C.c_double), ("road_pitch", C.c_double), ("road_roll", C.c_double), ("trail_heading", C.c_double), ("curvature", C.c_double), ("speed_limit", C.c_double),
                ("roadId", C.c_uint), ("junctionId", C.c_uint), ("laneId", C.c_int), ("laneOffset", C.c_double), ("s", C.c_double), ("t", C.c_double), ("road_type", C.c_int), ("road_rule", C.c_int), ("lane_type", C.c_int), ("trail_wheel_angle", C.c_double)]


L = C.CDLL(str(LIB))
L.SE_Init.argtypes = [C.c_char_p, C.c_int, C.c_int, C.c_int, C.c_int]; L.SE_Init.restype = C.c_int
L.SE_StepDT.argtypes = [C.c_double]; L.SE_StepDT.restype = C.c_int
L.SE_GetObjectState.argtypes = [C.c_int, C.POINTER(ObjectState)]; L.SE_GetObjectState.restype = C.c_int
L.SE_GetRoadInfoAtDistance.argtypes = [C.c_int, C.c_double, C.POINTER(RoadInfo), C.c_int, C.c_bool]; L.SE_GetRoadInfoAtDistance.restype = C.c_int
L.SE_ReportObjectPosXYH.argtypes = [C.c_int, C.c_double, C.c_double, C.c_double]; L.SE_ReportObjectPosXYH.restype = C.c_int
L.SE_ReportObjectSpeed.argtypes = [C.c_int, C.c_double]; L.SE_ReportObjectSpeed.restype = C.c_int
L.SE_GetSimulationTime.restype = C.c_double
L.SE_GetId.argtypes = [C.c_int]; L.SE_GetId.restype = C.c_int
L.SE_SetLogFilePath.argtypes = [C.c_char_p]
L.SE_LogToConsole.argtypes = [C.c_bool]
L.SE_SetSeed.argtypes = [C.c_uint]
