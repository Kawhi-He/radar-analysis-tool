#!/usr/bin/env python3
"""
Author: Kawhi.He
Overview:
Generate point-cloud analysis HTML report for static or dynamic target scenes.

Input Parameters:
- input_path (str): Path to frame.txt.
- output_path (str): Path to output html.
- mode (str): static or dynamic.
- config (dict): Analysis configuration selected by user.

Return Values:
- None. Writes report html file.
"""

from __future__ import annotations

import argparse
import html
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import List

HEAD_RE = re.compile(r"^\s*([A-Za-z]+)=([\-\d\.nan]+)\s*$")
POINT_RE = re.compile(
    r"^\s*\d+:Range=([\-\d\.]+)\s+Velocity=([\-\d\.]+)\s+"
    r"AngleAZ=([\-\d\.]+)\s+AngleEL=([\-\d\.]+)\s+RCS=([\-\d\.]+)\s*$"
)
OBJECT_RE = re.compile(
    r"^\s*\d+:DistLat=([\-\d\.]+)\s+DistLong=([\-\d\.]+)\s+"
    r"VreLat=([\-\d\.]+)\s+VreLong=([\-\d\.]+)\s+Power=([\-\d\.]+)\s+"
    r"DynamicPro=([\-\d\.]+)\s*$"
)


@dataclass
class Point:
    """
    Overview:
    Hold one point-cloud point in a frame.

    Input Parameters:
    - range_m (float): Point range in meters.
    - velocity_mps (float): Point velocity in m/s.
    - angle_az_rad (float): Azimuth angle in radians.
    - rcs_db (float): RCS value in dB.

    Return Values:
    - Point: Dataclass instance.

    Author: Kawhi.He
    """

    range_m: float
    velocity_mps: float
    angle_az_rad: float
    rcs_db: float


@dataclass
class DetectedObject:
    """
    Overview:
    Hold one parsed object line from [Object].

    Input Parameters:
    - dist_lat_m (float): Longitudinal distance.
    - dist_long_m (float): Lateral distance.
    - vre_lat_mps (float): Longitudinal velocity.
    - vre_long_mps (float): Lateral velocity.

    Return Values:
    - DetectedObject: Dataclass instance.

    Author: Kawhi.He
    """

    dist_lat_m: float
    dist_long_m: float
    vre_lat_mps: float
    vre_long_mps: float


@dataclass
class Frame:
    """
    Overview:
    Hold one frame parsed from frame.txt.

    Input Parameters:
    - frame_id (int): Frame index.
    - timestamp_ms (float): Timestamp in ms.
    - alarm_type (int): AlarmType from HEAD section.
    - points (list[Point]): Point list in this frame.
    - objects (list[DetectedObject]): Object list in this frame.

    Return Values:
    - Frame: Dataclass instance.

    Author: Kawhi.He
    """

    frame_id: int
    timestamp_ms: float
    alarm_type: int = 0
    points: List[Point] = field(default_factory=list)
    objects: List[DetectedObject] = field(default_factory=list)


@dataclass
class MatchResult:
    """
    Overview:
    Describe point matching result in one frame.

    Input Parameters:
    - matched (bool): Whether a point is matched.
    - point (Point | None): Matched point object.

    Return Values:
    - MatchResult: Dataclass instance.

    Author: Kawhi.He
    """

    matched: bool
    point: Point | None = None


def parse_float(value: str) -> float:
    """
    Overview:
    Parse float text and handle nan token.

    Input Parameters:
    - value (str): Numeric string.

    Return Values:
    - float: Parsed value.

    Author: Kawhi.He
    """

    if value.lower() == "nan":
        return math.nan
    return float(value)


def parse_frames(text: str) -> List[Frame]:
    """
    Overview:
    Parse frame.txt content to structured frame list.

    Input Parameters:
    - text (str): Whole frame text content.

    Return Values:
    - list[Frame]: Parsed frames.

    Author: Kawhi.He
    """

    frames: List[Frame] = []
    current_head: dict[str, float] = {}
    current_points: List[Point] = []
    current_objects: List[DetectedObject] = []
    section = ""

    def flush_frame() -> None:
        if "FrameID" not in current_head:
            return
        frames.append(
            Frame(
                frame_id=int(current_head.get("FrameID", -1)),
                timestamp_ms=float(current_head.get("TimeStamp", math.nan)),
                alarm_type=int(current_head.get("AlarmType", 0)),
                points=list(current_points),
                objects=list(current_objects),
            )
        )

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")

        if line.strip() == "[HEAD]":
            flush_frame()
            current_head = {}
            current_points = []
            current_objects = []
            section = "HEAD"
            continue
        if line.strip() == "[Point]":
            section = "POINT"
            continue
        if line.strip() == "[Object]":
            section = "OBJECT"
            continue

        if section == "HEAD":
            m = HEAD_RE.match(line)
            if m:
                current_head[m.group(1)] = parse_float(m.group(2))
        elif section == "POINT":
            m = POINT_RE.match(line)
            if m:
                current_points.append(
                    Point(
                        range_m=float(m.group(1)),
                        velocity_mps=float(m.group(2)),
                        angle_az_rad=float(m.group(3)),
                        rcs_db=float(m.group(5)),
                    )
                )
        elif section == "OBJECT":
            m = OBJECT_RE.match(line)
            if m:
                current_objects.append(
                    DetectedObject(
                        dist_lat_m=float(m.group(1)),
                        dist_long_m=float(m.group(2)),
                        vre_lat_mps=float(m.group(3)),
                        vre_long_mps=float(m.group(4)),
                    )
                )

    flush_frame()
    return frames


def split_object_cycles(frames: List[Frame]) -> List[List[Frame]]:
    """
    Overview:
    Split object frames into independent cycles by continuity.

    Input Parameters:
    - frames (list[Frame]): Parsed frames.

    Return Values:
    - list[list[Frame]]: Split cycles.

    Author: Kawhi.He
    """

    object_frames = [f for f in frames if f.objects]
    if not object_frames:
        return []

    def is_same_cycle(prev: Frame, cur: Frame) -> bool:
        gap = cur.frame_id - prev.frame_id
        if gap <= 1:
            return True
        if gap > 30:
            return False

        prev_obj = prev.objects[0]
        cur_obj = cur.objects[0]

        dt = (cur.timestamp_ms - prev.timestamp_ms) / 1000.0
        if math.isnan(dt) or dt <= 0:
            dt = gap * 0.1

        pred_lat = prev_obj.dist_lat_m + prev_obj.vre_lat_mps * dt
        lat_err = abs(cur_obj.dist_lat_m - pred_lat)
        vel_err = abs(cur_obj.vre_lat_mps - prev_obj.vre_lat_mps)

        dist_tol = max(3.5, abs(prev_obj.vre_lat_mps) * dt * 0.8 + 1.5)
        return lat_err <= dist_tol and vel_err <= 4.5

    cycles: List[List[Frame]] = []
    current: List[Frame] = [object_frames[0]]

    for prev, cur in zip(object_frames, object_frames[1:]):
        if is_same_cycle(prev, cur):
            current.append(cur)
        else:
            cycles.append(current)
            current = [cur]
    cycles.append(current)
    return cycles


def detect_primary_axis(cycle: List[Frame]) -> str:
    """
    Overview:
    Detect whether DistLat or DistLong is the dominant motion axis.

    Input Parameters:
    - cycle (list[Frame]): One object cycle.

    Return Values:
    - str: "lat" or "long".

    Author: Kawhi.He
    """

    lat_vals = [abs(f.objects[0].dist_lat_m) for f in cycle if f.objects]
    long_vals = [abs(f.objects[0].dist_long_m) for f in cycle if f.objects]
    if not lat_vals or not long_vals:
        return "lat"
    return "long" if safe_mean(long_vals) > safe_mean(lat_vals) * 1.8 else "lat"


def object_primary_distance(obj: DetectedObject, axis: str) -> float:
    """
    Overview:
    Return primary-axis absolute distance for one object.

    Input Parameters:
    - obj (DetectedObject): Object item.
    - axis (str): "lat" or "long".

    Return Values:
    - float: Absolute primary distance.

    Author: Kawhi.He
    """

    return abs(obj.dist_long_m) if axis == "long" else abs(obj.dist_lat_m)


def object_primary_speed(obj: DetectedObject, axis: str) -> float:
    """
    Overview:
    Return primary-axis absolute speed for one object.

    Input Parameters:
    - obj (DetectedObject): Object item.
    - axis (str): "lat" or "long".

    Return Values:
    - float: Absolute primary speed.

    Author: Kawhi.He
    """

    return abs(obj.vre_long_mps) if axis == "long" else abs(obj.vre_lat_mps)


def representative_speed(speed_values: List[float]) -> float:
    """
    Overview:
    Compute representative speed from a cycle, robust to long tails of zero speed.

    Input Parameters:
    - speed_values (list[float]): Absolute speed samples.

    Return Values:
    - float: Representative speed.

    Author: Kawhi.He
    """

    valid = sorted(v for v in speed_values if not math.isnan(v))
    if not valid:
        return 0.0

    # Use top quantile average so early fast-motion segment is preserved.
    tail_count = max(3, int(len(valid) * 0.12))
    tail = valid[-tail_count:]
    return safe_mean(tail)


def classify_motion_scene(cycle: List[Frame]) -> str:
    """
    Overview:
    Classify cycle as approaching or receding using DistLat trend.

    Input Parameters:
    - cycle (list[Frame]): One cycle.

    Return Values:
    - str: approaching, receding, or unknown.

    Author: Kawhi.He
    """

    axis = detect_primary_axis(cycle)
    dists = [object_primary_distance(f.objects[0], axis) for f in cycle if f.objects]
    if len(dists) < 2:
        return "unknown"

    overall = dists[-1] - dists[0]
    if overall > 0.05:
        return "approaching"
    if overall < -0.05:
        return "receding"
    return "unknown"


def missing_frame_ids_in_cycle(cycle: List[Frame]) -> List[int]:
    """
    Overview:
    Find missing frame IDs inside one cycle.

    Input Parameters:
    - cycle (list[Frame]): Object cycle frames.

    Return Values:
    - list[int]: Missing frame IDs.

    Author: Kawhi.He
    """

    missing: List[int] = []
    for prev, cur in zip(cycle, cycle[1:]):
        if cur.frame_id > prev.frame_id + 1:
            missing.extend(list(range(prev.frame_id + 1, cur.frame_id)))
    return missing


def alarm_label(alarm_type: int) -> str:
    """
    Overview:
    Convert alarm code to text.

    Input Parameters:
    - alarm_type (int): AlarmType code.

    Return Values:
    - str: Alarm label.

    Author: Kawhi.He
    """

    if alarm_type == 0:
        return "无报警"
    if alarm_type == 1:
        return "左侧"
    if alarm_type == 2:
        return "右侧"
    return f"未知({alarm_type})"


def analyze_alarm_in_cycle(cycle: List[Frame]) -> dict:
    """
    Overview:
    Analyze alarm continuity and switching in one cycle.

    Input Parameters:
    - cycle (list[Frame]): One object cycle.

    Return Values:
    - dict: Alarm statistics.

    Author: Kawhi.He
    """

    first_alarm_idx = None
    for i, frame in enumerate(cycle):
        if frame.alarm_type in (1, 2):
            first_alarm_idx = i
            break

    if first_alarm_idx is None:
        return {
            "has_alarm": False,
            "alarm_start_frame": None,
            "alarm_start_type": 0,
            "farthest_alarm_distance_m": None,
            "missing_alarm_frames": [],
            "alarm_switches": [],
        }

    active_frames = cycle[first_alarm_idx:]
    prev_type = cycle[first_alarm_idx - 1].alarm_type if first_alarm_idx > 0 else 0

    valid_alarm_distances: List[float] = []
    missing_alarm_frames: List[int] = []
    alarm_switches: List[dict] = []

    for frame in active_frames:
        dist_m = abs(frame.objects[0].dist_lat_m)
        if frame.alarm_type in (1, 2):
            valid_alarm_distances.append(dist_m)
        else:
            missing_alarm_frames.append(frame.frame_id)

        if frame.alarm_type != prev_type:
            alarm_switches.append(
                {
                    "frame_id": frame.frame_id,
                    "from": prev_type,
                    "to": frame.alarm_type,
                    "distance_m": dist_m,
                }
            )
        prev_type = frame.alarm_type

    return {
        "has_alarm": True,
        "alarm_start_frame": active_frames[0].frame_id,
        "alarm_start_type": active_frames[0].alarm_type,
        "farthest_alarm_distance_m": max(valid_alarm_distances) if valid_alarm_distances else None,
        "missing_alarm_frames": missing_alarm_frames,
        "alarm_switches": alarm_switches,
    }


def find_best_point(
    frame: Frame,
    expected_distance_m: float,
    expected_rcs_db: float,
    expected_speed_mps: float | None = None,
) -> MatchResult:
    """
    Overview:
    Find best point in frame based on configured distance/RCS/speed target.

    Input Parameters:
    - frame (Frame): Current frame.
    - expected_distance_m (float): Configured target distance.
    - expected_rcs_db (float): Configured target RCS.
    - expected_speed_mps (float | None): Configured target speed if needed.

    Return Values:
    - MatchResult: Match status and selected point.

    Author: Kawhi.He
    """

    dist_tol = max(2.0, expected_distance_m * 0.25)
    rcs_tol = 12.0
    speed_tol = None
    if expected_speed_mps is not None:
        speed_tol = max(1.0, abs(expected_speed_mps) * 0.5)

    best_score = None
    best_point = None

    for point in frame.points:
        d_dist = abs(point.range_m - expected_distance_m)
        d_rcs = abs(point.rcs_db - expected_rcs_db)
        if d_dist > dist_tol or d_rcs > rcs_tol:
            continue

        d_speed = 0.0
        if expected_speed_mps is not None and speed_tol is not None:
            d_speed = min(
                abs(point.velocity_mps - expected_speed_mps),
                abs(point.velocity_mps + expected_speed_mps),
            )
            if d_speed > speed_tol:
                continue

        score = d_dist / max(dist_tol, 1e-6) + d_rcs / max(rcs_tol, 1e-6)
        if expected_speed_mps is not None and speed_tol is not None:
            score += d_speed / max(speed_tol, 1e-6)

        if best_score is None or score < best_score:
            best_score = score
            best_point = point

    if best_point is None:
        return MatchResult(matched=False)
    return MatchResult(matched=True, point=best_point)


def match_point_for_object(
    frame: Frame,
    obj: DetectedObject,
    expected_rcs_db: float | None = None,
    expected_speed_mps: float | None = None,
    primary_axis: str = "lat",
) -> MatchResult:
    """
    Overview:
    Match one object with one point based on distance and velocity consistency.

    Input Parameters:
        - frame (Frame): Current frame.
        - obj (DetectedObject): Current object.
        - expected_rcs_db (float | None): Optional configured RCS used to constrain
            the matched point.
        - expected_speed_mps (float | None): Optional configured speed used to
            constrain the matched point.
        - primary_axis (str): Dominant object axis, "lat" or "long".

    Return Values:
    - MatchResult: Match status and selected point.

    Author: Kawhi.He
    """

    expected_range = math.hypot(abs(obj.dist_lat_m), obj.dist_long_m)
    if primary_axis == "long":
        expected_v = obj.vre_long_mps
        expected_angle_deg = math.degrees(
            math.atan2(obj.dist_lat_m, max(abs(obj.dist_long_m), 1e-6))
        )
    else:
        expected_v = obj.vre_lat_mps
        expected_angle_deg = math.degrees(
            math.atan2(obj.dist_long_m, max(abs(obj.dist_lat_m), 1e-6))
        )

    range_tol = max(1.4, expected_range * 0.2)
    vel_tol = max(2.5, abs(expected_v) * 0.8)
    angle_tol = 14.0
    rcs_tol = 12.0 if expected_rcs_db is not None else None
    cfg_speed_tol = (
        max(1.0, abs(expected_speed_mps) * 0.45)
        if expected_speed_mps is not None
        else None
    )

    best_score = None
    best_point = None

    for point in frame.points:
        d_range = abs(point.range_m - expected_range)
        p_angle_deg = math.degrees(point.angle_az_rad)
        d_v = min(
            abs(point.velocity_mps - expected_v),
            abs(point.velocity_mps + expected_v),
            abs(point.velocity_mps),
        )
        d_angle = min(
            abs(p_angle_deg - expected_angle_deg),
            abs(p_angle_deg + expected_angle_deg),
            abs(abs(p_angle_deg) - abs(expected_angle_deg)),
        )

        d_rcs = 0.0
        if expected_rcs_db is not None and rcs_tol is not None:
            d_rcs = abs(point.rcs_db - expected_rcs_db)
            if d_rcs > rcs_tol:
                continue

        d_cfg_speed = 0.0
        if expected_speed_mps is not None and cfg_speed_tol is not None:
            d_cfg_speed = abs(abs(point.velocity_mps) - abs(expected_speed_mps))
            if d_cfg_speed > cfg_speed_tol:
                continue

        if d_range > range_tol or d_v > vel_tol or d_angle > angle_tol:
            continue

        score = (
            d_range / max(range_tol, 1e-6)
            + d_v / max(vel_tol, 1e-6)
            + d_angle / max(angle_tol, 1e-6)
        )
        if expected_rcs_db is not None and rcs_tol is not None:
            score += d_rcs / max(rcs_tol, 1e-6)
        if expected_speed_mps is not None and cfg_speed_tol is not None:
            score += d_cfg_speed / max(cfg_speed_tol, 1e-6)
        if best_score is None or score < best_score:
            best_score = score
            best_point = point

    if best_point is None:
        return MatchResult(matched=False)
    return MatchResult(matched=True, point=best_point)


def infer_launch_frames(cycle: List[Frame], all_frames: List[Frame]) -> int:
    """
    Overview:
    Infer how many frames point cloud appears before first object frame.

    Input Parameters:
    - cycle (list[Frame]): One approaching cycle.
    - all_frames (list[Frame]): Full frame timeline.

    Return Values:
    - int: Launch frame count.

    Author: Kawhi.He
    """

    first = cycle[0]
    obj0 = first.objects[0]
    idx = next((i for i, f in enumerate(all_frames) if f.frame_id == first.frame_id), None)
    if idx is None or idx == 0:
        return 0

    expected_range = math.hypot(abs(obj0.dist_lat_m), obj0.dist_long_m)
    speed_mag = max(abs(obj0.vre_lat_mps), 1e-6)

    launch = 0
    elapsed = 0.0
    prev_selected_range = expected_range

    for i in range(idx - 1, -1, -1):
        prev = all_frames[i]
        nxt = all_frames[i + 1]
        dt = (nxt.timestamp_ms - prev.timestamp_ms) / 1000.0
        if math.isnan(dt) or dt <= 0:
            dt = 0.1
        elapsed += dt

        pred_range = expected_range + speed_mag * elapsed
        range_tol = max(2.0, pred_range * 0.2 + 1.2)

        best_point = None
        best_score = None
        for point in prev.points:
            d_range = abs(point.range_m - pred_range)
            d_speed = abs(abs(point.velocity_mps) - speed_mag)
            if d_range > range_tol or d_speed > max(1.5, speed_mag * 0.2):
                continue
            score = d_range + d_speed
            if best_score is None or score < best_score:
                best_score = score
                best_point = point

        if best_point is None:
            break
        if best_point.range_m + 0.4 < prev_selected_range:
            break

        launch += 1
        prev_selected_range = best_point.range_m

    return launch


def format_ids(ids: List[int]) -> str:
    """
    Overview:
    Format integer ID list to display string.

    Input Parameters:
    - ids (list[int]): IDs to display.

    Return Values:
    - str: Formatted text.

    Author: Kawhi.He
    """

    return "无" if not ids else ", ".join(str(i) for i in ids)


def to_mps(speed_value: float, speed_unit: str) -> float:
    """
    Overview:
    Convert configured speed to m/s.

    Input Parameters:
    - speed_value (float): User input speed value.
    - speed_unit (str): m/s or km/h.

    Return Values:
    - float: Speed in m/s.

    Author: Kawhi.He
    """

    if speed_unit == "km/h":
        return speed_value / 3.6
    return speed_value


def safe_mean(values: List[float]) -> float:
    """
    Overview:
    Return average and fallback to 0 for empty input.

    Input Parameters:
    - values (list[float]): Numeric list.

    Return Values:
    - float: Average value.

    Author: Kawhi.He
    """

    return mean(values) if values else 0.0


def safe_std(values: List[float]) -> float:
    """
    Overview:
    Compute standard deviation with empty/single safeguards.

    Input Parameters:
    - values (list[float]): Numeric list.

    Return Values:
    - float: Standard deviation.

    Author: Kawhi.He
    """

    if len(values) <= 1:
        return 0.0
    avg = mean(values)
    variance = sum((x - avg) ** 2 for x in values) / len(values)
    return variance ** 0.5


def analyze_static(frames: List[Frame], config: dict) -> dict:
    """
    Overview:
    Analyze static-target point cloud stability and errors.

    Input Parameters:
    - frames (list[Frame]): Parsed frames.
    - config (dict): Static analysis config.

    Return Values:
    - dict: Static analysis result.

    Author: Kawhi.He
    """

    expected_speed_mps = to_mps(config["speed_value"], config["speed_unit"])
    expected_rcs_db = config["rcs_db"]
    expected_distance_m = config["distance_m"]

    matched_ids: List[int] = []
    drop_ids: List[int] = []
    distance_errors: List[float] = []
    speed_errors: List[float] = []
    angle_errors: List[float] = []
    ranges: List[float] = []

    for frame in frames:
        if not frame.points:
            drop_ids.append(frame.frame_id)
            continue

        match = find_best_point(
            frame,
            expected_distance_m=expected_distance_m,
            expected_rcs_db=expected_rcs_db,
            expected_speed_mps=expected_speed_mps,
        )
        if not match.matched or match.point is None:
            drop_ids.append(frame.frame_id)
            continue

        point = match.point
        matched_ids.append(frame.frame_id)
        distance_errors.append(point.range_m - expected_distance_m)
        speed_errors.append(point.velocity_mps - expected_speed_mps)
        # Static frontal target is assumed to have expected azimuth around 0 deg.
        angle_errors.append(math.degrees(point.angle_az_rad) - 0.0)
        ranges.append(point.range_m)

    total_frames = len(frames)
    matched_count = len(matched_ids)
    drop_ratio = (len(drop_ids) / total_frames) if total_frames else 0.0

    distance_abs = [abs(x) for x in distance_errors]
    speed_abs = [abs(x) for x in speed_errors]
    angle_abs = [abs(x) for x in angle_errors]

    std_range = safe_std(ranges)
    std_speed = safe_std(speed_errors)
    std_angle = safe_std(angle_errors)

    stable = (
        std_range <= 0.50
        and std_speed <= 0.50
        and std_angle <= 2.0
        and drop_ratio <= 0.10
    )

    return {
        "mode": "static",
        "expected_speed_mps": expected_speed_mps,
        "expected_speed_display": f"{config['speed_value']:.2f} {config['speed_unit']}",
        "expected_rcs_db": expected_rcs_db,
        "expected_distance_m": expected_distance_m,
        "total_frames": total_frames,
        "matched_count": matched_count,
        "drop_ids": drop_ids,
        "distance_mean_abs_err": safe_mean(distance_abs),
        "distance_max_abs_err": max(distance_abs) if distance_abs else 0.0,
        "speed_mean_abs_err": safe_mean(speed_abs),
        "speed_max_abs_err": max(speed_abs) if speed_abs else 0.0,
        "angle_mean_abs_err": safe_mean(angle_abs),
        "angle_max_abs_err": max(angle_abs) if angle_abs else 0.0,
        "std_range": std_range,
        "std_speed": std_speed,
        "std_angle": std_angle,
        "stable": stable,
    }


def analyze_dynamic(frames: List[Frame], config: dict) -> dict:
    """
    Overview:
    Analyze dynamic-target point cloud result by selected mode.

    Input Parameters:
    - frames (list[Frame]): Parsed frames.
    - config (dict): Dynamic analysis config.

    Return Values:
    - dict: Dynamic analysis result.

    Author: Kawhi.He
    """

    selected_mode = config["scene_mode"]
    expected_rcs_db = config["rcs_db"]
    expected_speed_mps = config["speed_mps"]
    cycles = split_object_cycles(frames)

    if selected_mode == "接近":
        desired = "approaching"
    else:
        desired = "receding"

    speed_tol = max(1.2, abs(expected_speed_mps) * 0.45)

    cycle_meta = []
    for cycle in cycles:
        axis = detect_primary_axis(cycle)
        rep_speed = representative_speed(
            [object_primary_speed(f.objects[0], axis) for f in cycle if f.objects]
        )
        scene = classify_motion_scene(cycle)
        cycle_meta.append({
            "cycle": cycle,
            "axis": axis,
            "scene": scene,
            "rep_speed": rep_speed,
        })

    speed_matched = [m for m in cycle_meta if abs(m["rep_speed"] - abs(expected_speed_mps)) <= speed_tol]
    selected_meta = [m for m in speed_matched if m["scene"] == desired]

    scene_filter_fallback = False
    if not selected_meta:
        # Some logs contain long static sections that make scene trend ambiguous.
        selected_meta = [m for m in speed_matched if m["scene"] == "unknown"]
        if selected_meta:
            scene_filter_fallback = True

    speed_filter_fallback = False
    if not selected_meta and cycle_meta:
        selected_meta = cycle_meta
        speed_filter_fallback = True

    cycle_rows = []
    all_drop_ids: List[int] = []
    lost_distances: List[float] = []
    launch_frames_list: List[int] = []
    all_object_drop_ids: List[int] = []

    for index, meta in enumerate(selected_meta, start=1):
        cycle = meta["cycle"]
        axis = meta["axis"]
        point_drop_ids: List[int] = []
        point_drop_distances: List[float] = []

        for frame in cycle:
            obj = frame.objects[0]
            obj_speed = object_primary_speed(obj, axis)
            if abs(obj_speed - abs(expected_speed_mps)) > speed_tol:
                continue

            match = match_point_for_object(
                frame,
                obj,
                expected_rcs_db=expected_rcs_db,
                expected_speed_mps=expected_speed_mps,
                primary_axis=axis,
            )
            if not match.matched:
                point_drop_ids.append(frame.frame_id)
                point_drop_distances.append(object_primary_distance(obj, axis))

        object_drop_ids = missing_frame_ids_in_cycle(cycle)
        all_drop_ids.extend(point_drop_ids)
        all_object_drop_ids.extend(object_drop_ids)

        alarm = analyze_alarm_in_cycle(cycle)
        if point_drop_distances:
            if selected_mode == "远离":
                peak_distance = max(
                    object_primary_distance(f.objects[0], axis)
                    for f in cycle
                    if f.objects and abs(object_primary_speed(f.objects[0], axis) - abs(expected_speed_mps)) <= speed_tol
                )
                high_band = peak_distance * 0.8
                candidates = [d for d in point_drop_distances if d >= high_band]
                lost_distance = candidates[0] if candidates else point_drop_distances[0]
            else:
                lost_distance = point_drop_distances[0]
        else:
            lost_distance = object_primary_distance(cycle[-1].objects[0], axis)

        lost_distances.append(lost_distance)

        launch_frames = infer_launch_frames(cycle, frames) if selected_mode == "接近" else 0
        if selected_mode == "接近":
            launch_frames_list.append(launch_frames)

        cycle_rows.append(
            {
                "index": index,
                "start": cycle[0].frame_id,
                "end": cycle[-1].frame_id,
                "duration": len(cycle),
                "primary_axis": axis,
                "lost_distance": lost_distance,
                "point_drop_ids": point_drop_ids,
                "object_drop_ids": object_drop_ids,
                "launch_frames": launch_frames,
                "object_always_exists": len(object_drop_ids) == 0,
                "alarm": alarm,
            }
        )

    return {
        "mode": "dynamic",
        "scene_mode": selected_mode,
        "expected_rcs_db": config["rcs_db"],
        "expected_speed_mps": expected_speed_mps,
        "expected_speed_display": f"{config['speed_value']:.2f} {config['speed_unit']}",
        "cycle_count": len(selected_meta),
        "scene_filter_fallback": scene_filter_fallback,
        "speed_filter_fallback": speed_filter_fallback,
        "farthest_lost_distance": max(lost_distances) if lost_distances else None,
        "all_point_drop_ids": sorted(set(all_drop_ids)),
        "all_object_drop_ids": sorted(set(all_object_drop_ids)),
        "avg_launch_frames": safe_mean(launch_frames_list) if launch_frames_list else None,
        "cycle_rows": cycle_rows,
    }


def render_alarm_section(alarm: dict) -> str:
    """
    Overview:
    Render one cycle alarm section as html.

    Input Parameters:
    - alarm (dict): Alarm analysis result.

    Return Values:
    - str: HTML block.

    Author: Kawhi.He
    """

    if not alarm["has_alarm"]:
        return "<div class='subcard'><span>报警分析</span><strong>本周期未触发报警</strong></div>"

    switches = alarm["alarm_switches"]
    if switches:
        rows = "".join(
            (
                "<tr>"
                f"<td>{item['frame_id']}</td>"
                f"<td>{alarm_label(item['from'])}</td>"
                f"<td>{alarm_label(item['to'])}</td>"
                f"<td>{item['distance_m']:.2f} m</td>"
                "</tr>"
            )
            for item in switches
        )
        switch_table = (
            "<table class='mini-table'>"
            "<thead><tr><th>帧号</th><th>切换前</th><th>切换后</th><th>距离</th></tr></thead>"
            f"<tbody>{rows}</tbody>"
            "</table>"
        )
    else:
        switch_table = "<strong>无切换</strong>"

    farthest_alarm = (
        f"{alarm['farthest_alarm_distance_m']:.2f} m"
        if alarm["farthest_alarm_distance_m"] is not None
        else "无"
    )

    return (
        "<div class='subgrid'>"
        f"<div class='subcard'><span>报警起始帧</span><strong>{alarm['alarm_start_frame']}</strong></div>"
        f"<div class='subcard'><span>报警起始类型</span><strong>{alarm_label(alarm['alarm_start_type'])}</strong></div>"
        f"<div class='subcard'><span>最远报警距离</span><strong>{farthest_alarm}</strong></div>"
        f"<div class='subcard'><span>丢失报警帧</span><strong>{html.escape(format_ids(alarm['missing_alarm_frames']))}</strong></div>"
        "<div class='subcard full'><span>报警切换详情</span>"
        f"{switch_table}"
        "</div>"
        "</div>"
    )


def render_static_html(data: dict, input_name: str) -> str:
    """
    Overview:
    Render static analysis html report.

    Input Parameters:
    - data (dict): Static analysis result.
    - input_name (str): Input file name.

    Return Values:
    - str: HTML document string.

    Author: Kawhi.He
    """

    stable_text = "稳定" if data["stable"] else "不稳定"

    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>点云分析报告-静态目标</title>
  <style>
    :root {{
      --bg: #f4f8fb;
      --card: #ffffff;
      --line: #d7e3ef;
      --ink: #102a43;
      --sub: #486581;
      --ok: #0f766e;
      --warn: #b45309;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Microsoft YaHei UI", sans-serif; background: linear-gradient(180deg, #e8f1f8 0%, var(--bg) 100%); color: var(--ink); }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 18px; }}
    .header {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 14px; }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    p {{ margin: 4px 0; color: var(--sub); }}
    .grid {{ margin-top: 12px; display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; }}
    .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; }}
    .card span {{ display: block; color: var(--sub); font-size: 12px; }}
    .card strong {{ display: block; margin-top: 6px; font-size: 17px; }}
    .good {{ color: var(--ok); }}
    .bad {{ color: var(--warn); }}
    .block {{ margin-top: 12px; background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 12px; }}
    .mono {{ font-family: Consolas, monospace; font-size: 13px; line-height: 1.4; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"header\">
      <h1>点云分析报告（静态目标）</h1>
      <p>输入文件: {html.escape(input_name)}</p>
      <p>配置: 速度={data['expected_speed_display']}，RCS={data['expected_rcs_db']:.2f} dB，距离={data['expected_distance_m']:.2f} m</p>
      <div class=\"grid\">
        <div class=\"card\"><span>总帧数</span><strong>{data['total_frames']}</strong></div>
        <div class=\"card\"><span>有效匹配帧数</span><strong>{data['matched_count']}</strong></div>
        <div class=\"card\"><span>距离平均绝对误差</span><strong>{data['distance_mean_abs_err']:.3f} m</strong></div>
        <div class=\"card\"><span>距离最大绝对误差</span><strong>{data['distance_max_abs_err']:.3f} m</strong></div>
        <div class=\"card\"><span>速度平均绝对误差</span><strong>{data['speed_mean_abs_err']:.3f} m/s</strong></div>
        <div class=\"card\"><span>速度最大绝对误差</span><strong>{data['speed_max_abs_err']:.3f} m/s</strong></div>
        <div class=\"card\"><span>角度平均绝对误差</span><strong>{data['angle_mean_abs_err']:.3f} deg</strong></div>
        <div class=\"card\"><span>角度最大绝对误差</span><strong>{data['angle_max_abs_err']:.3f} deg</strong></div>
        <div class=\"card\"><span>点云距离标准差</span><strong>{data['std_range']:.3f} m</strong></div>
        <div class=\"card\"><span>点云速度标准差</span><strong>{data['std_speed']:.3f} m/s</strong></div>
        <div class=\"card\"><span>点云角度标准差</span><strong>{data['std_angle']:.3f} deg</strong></div>
        <div class=\"card\"><span>稳定性判定</span><strong class=\"{'good' if data['stable'] else 'bad'}\">{stable_text}</strong></div>
      </div>
    </div>

    <div class=\"block\">
      <h3>中途丢帧详情</h3>
      <p class=\"mono\">{html.escape(format_ids(data['drop_ids']))}</p>
    </div>
  </div>
</body>
</html>
"""


def render_dynamic_html(data: dict, input_name: str) -> str:
    """
    Overview:
    Render dynamic analysis html report.

    Input Parameters:
    - data (dict): Dynamic analysis result.
    - input_name (str): Input file name.

    Return Values:
    - str: HTML document string.

    Author: Kawhi.He
    """

    if data["scene_mode"] == "远离":
        core_summary = (
            f"<div class='card'><span>最远丢失距离</span><strong>{data['farthest_lost_distance']:.2f} m</strong></div>"
            if data["farthest_lost_distance"] is not None
            else "<div class='card'><span>最远丢失距离</span><strong>无</strong></div>"
        )
    else:
        launch_text = (
            f"{data['avg_launch_frames']:.2f} 帧"
            if data["avg_launch_frames"] is not None
            else "无"
        )
        core_summary = f"<div class='card'><span>平均建航时间</span><strong>{launch_text}</strong></div>"

    fallback_note = ""
    if data.get("scene_filter_fallback"):
        fallback_note += (
            "<p style='color:#b45309'>"
            "提示: 场景趋势存在长静止段，已回退使用速度匹配周期进行分析。"
            "</p>"
        )
    if data.get("speed_filter_fallback"):
        fallback_note += (
            "<p style='color:#b45309'>"
            "提示: 按设置速度未筛选到周期，已回退为使用全部周期。"
            "</p>"
        )

    cycle_blocks = []
    for row in data["cycle_rows"]:
        alarm_block = render_alarm_section(row["alarm"]) if data["scene_mode"] == "接近" else ""
        cycle_blocks.append(
            f"""
<details class='cycle' open>
  <summary>Cycle {row['index']} | 帧 {row['start']} - {row['end']}</summary>
  <div class='grid'>
    <div class='card'><span>持续帧数</span><strong>{row['duration']}</strong></div>
    <div class='card'><span>丢失距离</span><strong>{row['lost_distance']:.2f} m</strong></div>
    <div class='card'><span>点云中途丢帧</span><strong>{html.escape(format_ids(row['point_drop_ids']))}</strong></div>
    <div class='card'><span>目标中途丢帧</span><strong>{html.escape(format_ids(row['object_drop_ids']))}</strong></div>
    <div class='card'><span>建航时间</span><strong>{row['launch_frames']} 帧</strong></div>
    <div class='card'><span>建航后目标持续存在</span><strong>{'是' if row['object_always_exists'] else '否'}</strong></div>
  </div>
  {alarm_block}
</details>
"""
        )

    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>点云分析报告-动态目标</title>
  <style>
    :root {{
      --bg: #f7fbf9;
      --card: #ffffff;
      --line: #cfe8db;
      --ink: #16351f;
      --sub: #3d6351;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Microsoft YaHei UI", sans-serif; background: linear-gradient(180deg, #e9f7ef 0%, var(--bg) 100%); color: var(--ink); }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 18px; }}
    .header {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 14px; }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    p {{ margin: 4px 0; color: var(--sub); }}
    .grid {{ margin-top: 10px; display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; }}
    .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; }}
    .card span {{ display: block; color: var(--sub); font-size: 12px; }}
    .card strong {{ display: block; margin-top: 6px; font-size: 16px; }}
    .cycle {{ margin-top: 12px; background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; }}
    .cycle summary {{ cursor: pointer; font-weight: 700; }}
    .subgrid {{ margin-top: 10px; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; }}
    .subcard {{ background: #f1fcf5; border: 1px solid #b9e7cb; border-radius: 10px; padding: 8px 10px; }}
    .subcard.full {{ grid-column: 1 / -1; }}
    .subcard span {{ display: block; font-size: 12px; color: #2c5a43; }}
    .subcard strong {{ display: block; margin-top: 4px; }}
    .mini-table {{ width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 13px; }}
    .mini-table th, .mini-table td {{ border: 1px solid #b9e7cb; padding: 6px; text-align: center; }}
    .mini-table th {{ background: #dff7e7; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"header\">
      <h1>点云分析报告（动态目标 - {data['scene_mode']}）</h1>
      <p>输入文件: {html.escape(input_name)}</p>
            <p>配置: RCS={data['expected_rcs_db']:.2f} dB，速度={data['expected_speed_display']}，模式={data['scene_mode']}</p>
    {fallback_note}
      <div class=\"grid\">
        <div class=\"card\"><span>有效周期数</span><strong>{data['cycle_count']}</strong></div>
        {core_summary}
        <div class=\"card\"><span>点云中途丢帧(全局)</span><strong>{html.escape(format_ids(data['all_point_drop_ids']))}</strong></div>
        <div class=\"card\"><span>目标中途丢帧(全局)</span><strong>{html.escape(format_ids(data['all_object_drop_ids']))}</strong></div>
      </div>
    </div>
    {''.join(cycle_blocks) if cycle_blocks else "<div class='cycle'><strong>未找到匹配模式的周期数据</strong></div>"}
  </div>
</body>
</html>
"""


def generate_report(input_path: Path, output_path: Path, mode: str, config: dict) -> dict:
    """
    Overview:
    Analyze input data and generate corresponding report file.

    Input Parameters:
    - input_path (Path): frame.txt path.
    - output_path (Path): report html path.
    - mode (str): static or dynamic.
    - config (dict): User selected config.

    Return Values:
    - dict: Analysis result summary.

    Author: Kawhi.He
    """

    text = input_path.read_text(encoding="utf-8")
    frames = parse_frames(text)

    if mode == "static":
        result = analyze_static(frames, config)
        html_text = render_static_html(result, input_path.name)
    else:
        result = analyze_dynamic(frames, config)
        html_text = render_dynamic_html(result, input_path.name)

    output_path.write_text(html_text, encoding="utf-8")
    return result


def build_config_from_args(args: argparse.Namespace) -> tuple[str, dict]:
    """
    Overview:
    Build mode/config dict from command-line arguments.

    Input Parameters:
    - args (argparse.Namespace): Parsed arguments.

    Return Values:
    - tuple[str, dict]: (mode, config).

    Author: Kawhi.He
    """

    if args.mode == "static":
        if args.distance is None:
            raise ValueError("静态模式必须提供 --distance 参数")
        return (
            "static",
            {
                "speed_value": float(args.speed_value),
                "speed_unit": args.speed_unit,
                "rcs_db": float(args.rcs),
                "distance_m": float(args.distance),
            },
        )

    return (
        "dynamic",
        {
            "rcs_db": float(args.rcs),
            "speed_value": float(args.dynamic_speed_value),
            "speed_unit": args.dynamic_speed_unit,
            "speed_mps": to_mps(float(args.dynamic_speed_value), args.dynamic_speed_unit),
            "scene_mode": args.scene_mode,
        },
    )


def main() -> None:
    """
    Overview:
    Command-line entry point for point-cloud report generation.

    Input Parameters:
    - None. Uses command-line arguments.

    Return Values:
    - None.

    Author: Kawhi.He
    """

    parser = argparse.ArgumentParser(description="Generate point-cloud analysis report")
    parser.add_argument("-i", "--input", default="frame.txt", help="Input frame file")
    parser.add_argument("-o", "--output", default="pointcloud_report.html", help="Output html file")
    parser.add_argument("--mode", choices=["static", "dynamic"], required=True)
    parser.add_argument("--rcs", type=float, required=True, help="Configured RCS(dB)")
    parser.add_argument("--distance", type=float, help="Configured distance(m), required for static mode")
    parser.add_argument("--speed-value", type=float, default=0.0, help="Configured speed value")
    parser.add_argument("--speed-unit", choices=["m/s", "km/h"], default="m/s", help="Configured speed unit")
    parser.add_argument("--dynamic-speed-value", type=float, default=0.0, help="Configured dynamic speed value")
    parser.add_argument("--dynamic-speed-unit", choices=["m/s", "km/h"], default="m/s", help="Configured dynamic speed unit")
    parser.add_argument("--scene-mode", choices=["接近", "远离"], default="接近", help="Dynamic scene mode")
    args = parser.parse_args()

    mode, config = build_config_from_args(args)
    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    result = generate_report(input_path, output_path, mode, config)
    print(f"Report generated: {output_path}")
    if mode == "dynamic":
        print(f"Matched cycles: {result['cycle_count']}")


if __name__ == "__main__":
    main()
