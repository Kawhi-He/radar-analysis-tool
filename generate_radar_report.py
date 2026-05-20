#!/usr/bin/env python3
"""
Author: Kawhi.He
Overview:
Parse millimeter-wave radar frames from frame.txt and generate an HTML report
covering object cycles, frame gaps, point-cloud matching status, and launch frames.

Input Parameters:
- input_path (str): Path to radar frame log text file.
- output_path (str): Path to generated HTML report file.

Return Values:
- None. The script writes report content into output_path.
"""

from __future__ import annotations

import argparse
import html
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


HEAD_RE = re.compile(r"^\s*([A-Za-z]+)=([\-\d\.nan]+)\s*$")

# ---------------------------------------------------------------------------
# E-bike target filter thresholds
# E-bike speed: 25–50 km/h  =>  6.94–13.89 m/s
# Target must have first appeared at least this far away (meters).
# ---------------------------------------------------------------------------
EBIKE_MIN_SPEED_MPS: float = 25.0 / 3.6   # ~6.94 m/s
EBIKE_MAX_SPEED_MPS: float = 50.0 / 3.6   # ~13.89 m/s
EBIKE_MIN_APPEAR_DIST_M: float = 10.0     # first object distance threshold
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
    Hold a single point-cloud point in one frame.

    Input Parameters:
    - range_m (float): Radial range in meters.
    - velocity_mps (float): Longitudinal velocity in m/s.
    - angle_az_rad (float): Azimuth angle in radians.

    Return Values:
    - Point: Dataclass instance.
    """

    range_m: float
    velocity_mps: float
    angle_az_rad: float


@dataclass
class DetectedObject:
    """
    Overview:
    Hold one object line parsed from [Object] section.

    Input Parameters:
    - dist_lat_m (float): Longitudinal distance.
    - dist_long_m (float): Lateral distance.
    - vre_lat_mps (float): Longitudinal relative velocity.
    - vre_long_mps (float): Lateral relative velocity.

    Return Values:
    - DetectedObject: Dataclass instance.
    """

    dist_lat_m: float
    dist_long_m: float
    vre_lat_mps: float
    vre_long_mps: float


@dataclass
class Frame:
    """
    Overview:
    Hold one full radar frame.

    Input Parameters:
    - frame_id (int): Frame ID from [HEAD].
    - timestamp_ms (float): Timestamp in ms.
    - alarm_type (int): AlarmType from [HEAD].
    - points (list[Point]): Point cloud lines.
    - objects (list[DetectedObject]): Object lines.

    Return Values:
    - Frame: Dataclass instance.
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
    Point-cloud matching result for one object in one frame.

    Input Parameters:
    - matched (bool): Whether a matching point is found.
    - angle_deg (float | None): Matched point azimuth in degree.

    Return Values:
    - MatchResult: Dataclass instance.
    """

    matched: bool
    angle_deg: float | None = None


def parse_float(value: str) -> float:
    """
    Overview:
    Parse numeric text and handle nan literals.

    Input Parameters:
    - value (str): Raw numeric string.

    Return Values:
    - float: Parsed numeric value.
    """

    if value.lower() == "nan":
        return math.nan
    return float(value)


def parse_frames(text: str) -> List[Frame]:
    """
    Overview:
    Parse raw frame text into structured frame objects.

    Input Parameters:
    - text (str): Full content of frame.txt.

    Return Values:
    - list[Frame]: Parsed frames in original order.
    """

    frames: List[Frame] = []
    current_head: dict[str, float] = {}
    current_points: List[Point] = []
    current_objects: List[DetectedObject] = []
    section = ""

    def flush_frame() -> None:
        if "FrameID" not in current_head:
            return
        frame_id = int(current_head.get("FrameID", -1))
        timestamp = current_head.get("TimeStamp", math.nan)
        alarm_type = int(current_head.get("AlarmType", 0))
        frames.append(
            Frame(
                frame_id=frame_id,
                timestamp_ms=float(timestamp),
                alarm_type=alarm_type,
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
                key, val = m.group(1), m.group(2)
                current_head[key] = parse_float(val)
        elif section == "POINT":
            m = POINT_RE.match(line)
            if m:
                current_points.append(
                    Point(
                        range_m=float(m.group(1)),
                        velocity_mps=float(m.group(2)),
                        angle_az_rad=float(m.group(3)),
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
    Split object-present frames into independent appearance/disappearance cycles.

    Input Parameters:
    - frames (list[Frame]): All parsed frames.

    Return Values:
    - list[list[Frame]]: Frame groups for each cycle.
    """

    object_frames = [f for f in frames if f.objects]
    if not object_frames:
        return []

    def is_same_cycle(prev: Frame, cur: Frame) -> bool:
        """
        Merge sparse object tracks by distance continuity.

        We allow short tracking gaps when current object position is still
        consistent with longitudinal distance/velocity progression.
        """

        frame_gap = cur.frame_id - prev.frame_id
        if frame_gap <= 1:
            return True

        # Large gaps are unlikely to belong to one continuous target track.
        if frame_gap > 30:
            return False

        prev_obj = prev.objects[0]
        cur_obj = cur.objects[0]

        dt = (cur.timestamp_ms - prev.timestamp_ms) / 1000.0
        if math.isnan(dt) or dt <= 0:
            dt = frame_gap * 0.1

        predicted_dist_lat = prev_obj.dist_lat_m + prev_obj.vre_lat_mps * dt
        dist_err = abs(cur_obj.dist_lat_m - predicted_dist_lat)
        vel_err = abs(cur_obj.vre_lat_mps - prev_obj.vre_lat_mps)

        dist_tol = max(3.5, abs(prev_obj.vre_lat_mps) * dt * 0.8 + 1.5)
        if dist_err <= dist_tol and vel_err <= 4.5:
            return True

        # Fallback: absolute longitudinal distance changes smoothly.
        prev_abs = abs(prev_obj.dist_lat_m)
        cur_abs = abs(cur_obj.dist_lat_m)
        per_frame_change = abs(cur_abs - prev_abs) / max(frame_gap, 1)
        return per_frame_change <= 1.2 and vel_err <= 6.0

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


def match_point_for_object(frame: Frame, obj: DetectedObject) -> MatchResult:
    """
    Overview:
    Find best matching point for one object by distance and velocity consistency.

    Input Parameters:
    - frame (Frame): Current frame.
    - obj (DetectedObject): Current object.

    Return Values:
    - MatchResult: Matched status and angle in degree if found.
    """

    expected_range = math.hypot(abs(obj.dist_lat_m), obj.dist_long_m)
    expected_v = obj.vre_lat_mps
    expected_angle_deg = math.degrees(
        math.atan2(obj.dist_long_m, max(abs(obj.dist_lat_m), 1e-6))
    )

    range_tol = max(1.4, expected_range * 0.2)
    vel_tol = max(2.5, abs(expected_v) * 0.8)
    angle_tol = 14.0

    best_score = None
    best_angle_deg = None

    for p in frame.points:
        dr = abs(p.range_m - expected_range)
        p_angle_deg = math.degrees(p.angle_az_rad)

        # Device conventions can invert angle and velocity signs.
        dv = min(
            abs(p.velocity_mps - expected_v),
            abs(p.velocity_mps + expected_v),
            abs(p.velocity_mps),
        )
        da = min(
            abs(p_angle_deg - expected_angle_deg),
            abs(p_angle_deg + expected_angle_deg),
            abs(abs(p_angle_deg) - abs(expected_angle_deg)),
        )

        if dr > range_tol or dv > vel_tol or da > angle_tol:
            continue

        score = (
            dr / max(range_tol, 1e-6)
            + dv / max(vel_tol, 1e-6)
            + da / max(angle_tol, 1e-6)
        )
        if best_score is None or score < best_score:
            best_score = score
            best_angle_deg = p_angle_deg

    if best_score is None:
        return MatchResult(matched=False)
    return MatchResult(matched=True, angle_deg=best_angle_deg)


def infer_launch_frames(cycle: List[Frame], all_frames: List[Frame]) -> int:
    """
    Overview:
    Estimate how many frames point cloud appears before object track is created.

    Input Parameters:
    - cycle (list[Frame]): One object cycle.
    - all_frames (list[Frame]): All frames in timeline order.

    Return Values:
    - int: Launch frame count (point-only frames before first object frame).
    """

    first = cycle[0]
    obj0 = first.objects[0]
    idx = next(
        (i for i, f in enumerate(all_frames) if f.frame_id == first.frame_id),
        None,
    )
    if idx is None or idx == 0:
        return 0

    expected_range0 = math.hypot(abs(obj0.dist_lat_m), obj0.dist_long_m)
    expected_angle = math.degrees(
        math.atan2(obj0.dist_long_m, max(abs(obj0.dist_lat_m), 1e-6))
    )
    speed_mag = max(abs(obj0.vre_lat_mps), 1e-6)

    # Range/velocity are used as hard constraints; angle is used as a soft
    # penalty only to avoid rejecting valid launch points with noisy azimuth.
    wr = 0.45
    wv = 0.45
    wa = 0.10

    launch_count = 0
    cumulative_time = 0.0
    prev_selected_range = expected_range0

    for i in range(idx - 1, -1, -1):
        prev = all_frames[i]
        nxt = all_frames[i + 1]

        dt = (nxt.timestamp_ms - prev.timestamp_ms) / 1000.0
        if math.isnan(dt) or dt <= 0:
            dt = 0.1
        cumulative_time += dt

        predicted_range = expected_range0 + speed_mag * cumulative_time
        range_tol = max(2.0, predicted_range * 0.18 + 1.5)
        vel_tol = max(1.5, speed_mag * 0.18)
        min_speed = speed_mag * 0.55

        best_score = None
        best_point = None

        for p in prev.points:
            dr = abs(p.range_m - predicted_range)
            point_speed = abs(p.velocity_mps)
            dv = abs(point_speed - speed_mag)
            p_angle = math.degrees(p.angle_az_rad)
            da = min(
                abs(p_angle - expected_angle),
                abs(p_angle + expected_angle),
                abs(abs(p_angle) - abs(expected_angle)),
            )

            if dr > range_tol or dv > vel_tol or point_speed < min_speed:
                continue

            score = (
                wr * (dr / max(range_tol, 1e-6))
                + wv * (dv / max(vel_tol, 1e-6))
                + wa * (min(da, 45.0) / 45.0)
            )
            if best_score is None or score < best_score:
                best_score = score
                best_point = p

        if best_point is None:
            break

        # Backward tracing for approaching targets should be non-decreasing in
        # range with limited step jitter.
        if best_point.range_m + 0.4 < prev_selected_range:
            break
        max_step = speed_mag * dt + 2.0
        if abs(best_point.range_m - prev_selected_range) > max_step:
            break

        launch_count += 1
        prev_selected_range = best_point.range_m

    return launch_count


def is_ebike_cycle(cycle: List[Frame]) -> bool:
    """
    Overview:
    Determine whether an object cycle matches an e-bike target profile.
    Filters out pedestrian interference by requiring:
    1. Target first appears at a far distance (>= EBIKE_MIN_APPEAR_DIST_M).
    2. Median longitudinal speed magnitude falls within the e-bike range
       [EBIKE_MIN_SPEED_MPS, EBIKE_MAX_SPEED_MPS].

    Input Parameters:
    - cycle (list[Frame]): One object appearance cycle.

    Return Values:
    - bool: True if the cycle looks like an e-bike target.
    """

    if not cycle:
        return False

    # Condition 1: farthest detected distance must exceed the appearance threshold
    # (target entered the detection zone from far away).
    object_dists = [abs(f.objects[0].dist_lat_m) for f in cycle if f.objects]
    if not object_dists or max(object_dists) < EBIKE_MIN_APPEAR_DIST_M:
        return False

    # Condition 2: representative speed magnitude must be in the e-bike speed
    # range. Use upper-quartile speed (P75) + peak speed instead of median to
    # reduce false filtering when some frames are slowed by radial projection
    # or temporary tracking jitter.
    speeds = [
        abs(f.objects[0].vre_lat_mps)
        for f in cycle
        if f.objects and not math.isnan(f.objects[0].vre_lat_mps)
    ]
    if not speeds:
        return False

    sorted_speeds = sorted(speeds)
    mid = len(sorted_speeds) // 2
    median_speed = (
        sorted_speeds[mid]
        if len(sorted_speeds) % 2 == 1
        else (sorted_speeds[mid - 1] + sorted_speeds[mid]) / 2.0
    )
    p75_index = int((len(sorted_speeds) - 1) * 0.75)
    p75_speed = sorted_speeds[p75_index]
    peak_speed = sorted_speeds[-1]

    return (
        EBIKE_MIN_SPEED_MPS <= p75_speed <= EBIKE_MAX_SPEED_MPS
        and peak_speed >= EBIKE_MIN_SPEED_MPS
        and median_speed >= EBIKE_MIN_SPEED_MPS * 0.75
    )


def classify_motion_scene(cycle: List[Frame]) -> tuple[str, str, int]:
    """
    Overview:
    Classify one cycle as approaching or receding by DistLat absolute trend.

    Input Parameters:
    - cycle (list[Frame]): One object appearance cycle.

    Return Values:
    - tuple[str, str, int]: (scene_key, scene_label, scene_priority).
      Lower priority value means earlier display order.
    """

    dists = [abs(f.objects[0].dist_lat_m) for f in cycle if f.objects]
    if len(dists) < 2:
        return ("unknown", "趋势不明确", 2)

    eps = 0.05
    dec = 0
    inc = 0
    for prev, cur in zip(dists, dists[1:]):
        delta = cur - prev
        if delta < -eps:
            dec += 1
        elif delta > eps:
            inc += 1

    overall = dists[-1] - dists[0]
    if dec >= inc and overall < -eps:
        return ("approaching", "接近场景", 0)
    if inc > dec and overall > eps:
        return ("receding", "远离场景", 1)

    # Fallback by start/end change direction.
    if overall < 0:
        return ("approaching", "接近场景", 0)
    if overall > 0:
        return ("receding", "远离场景", 1)
    return ("unknown", "趋势不明确", 2)


def missing_frame_ids_in_cycle(cycle: List[Frame]) -> List[int]:
    """
    Overview:
    Detect missing frame IDs inside an object cycle.

    Input Parameters:
    - cycle (list[Frame]): Frames where object exists.

    Return Values:
    - list[int]: Missing frame IDs between first and last object frame.
    """

    missing: List[int] = []
    for prev, cur in zip(cycle, cycle[1:]):
        if cur.frame_id > prev.frame_id + 1:
            missing.extend(list(range(prev.frame_id + 1, cur.frame_id)))
    return missing


def alarm_label(alarm_type: int) -> str:
    """
    Overview:
    Convert alarm type value to a bilingual display label.

    Input Parameters:
    - alarm_type (int): Alarm type value.

    Return Values:
    - str: Bilingual alarm label.
    """

    if alarm_type == 0:
        return "无报警"
    if alarm_type == 1:
        return "左侧"
    if alarm_type == 2:
        return "右侧"
    return f"未知({alarm_type})"


def format_alarm_switches(switches: List[dict]) -> str:
    """
    Overview:
    Render alarm switch records into readable text.

    Input Parameters:
    - switches (list[dict]): Alarm switch events.

    Return Values:
    - str: Readable switch summary.
    """

    if not switches:
        return "无"

    chunks: List[str] = []
    for sw in switches:
        chunks.append(
            f"帧{sw['frame_id']}: {alarm_label(sw['from'])} -> "
            f"{alarm_label(sw['to'])} @ {sw['distance_m']:.2f}m"
        )
    return " ; ".join(chunks)


def format_alarm_switches_html(switches: List[dict]) -> str:
    """
    Overview:
    Render alarm switch records as an HTML mini-table for display in the report.

    Input Parameters:
    - switches (list[dict]): Alarm switch events, each with keys
      'frame_id', 'from', 'to', 'distance_m'.

    Return Values:
    - str: HTML string containing a compact table of switch events,
      or a plain "无 / None" string when there are no events.

    Author: Kawhi.He
    """
    if not switches:
        return "<strong>无</strong>"

    rows = []
    for sw in switches:
        from_label = html.escape(alarm_label(sw['from']))
        to_label   = html.escape(alarm_label(sw['to']))
        rows.append(
            f"<tr>"
            f"<td>{sw['frame_id']}</td>"
            f"<td>{from_label}</td>"
            f"<td>{to_label}</td>"
            f"<td>{sw['distance_m']:.2f} m</td>"
            f"</tr>"
        )
    header = (
        "<table class='switch-table'>"
        "<thead><tr>"
        "<th>帧号</th>"
        "<th>切换前</th>"
        "<th>切换后</th>"
        "<th>距离</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )
    return header


def analyze_alarm_in_cycle(cycle: List[Frame]) -> dict:
    """
    Overview:
    Analyze alarm continuity after first alarm until target disappears.

    Input Parameters:
    - cycle (list[Frame]): One object cycle.

    Return Values:
    - dict: Alarm analysis for report.
    """

    first_alarm_idx = None
    for i, f in enumerate(cycle):
        if f.alarm_type in (1, 2):
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

    for f in active_frames:
        dist_m = abs(f.objects[0].dist_lat_m)

        if f.alarm_type in (1, 2):
            valid_alarm_distances.append(dist_m)
        else:
            missing_alarm_frames.append(f.frame_id)

        if f.alarm_type != prev_type:
            alarm_switches.append(
                {
                    "frame_id": f.frame_id,
                    "from": prev_type,
                    "to": f.alarm_type,
                    "distance_m": dist_m,
                }
            )
        prev_type = f.alarm_type

    farthest_alarm = max(valid_alarm_distances) if valid_alarm_distances else None

    return {
        "has_alarm": True,
        "alarm_start_frame": active_frames[0].frame_id,
        "alarm_start_type": active_frames[0].alarm_type,
        "farthest_alarm_distance_m": farthest_alarm,
        "missing_alarm_frames": missing_alarm_frames,
        "alarm_switches": alarm_switches,
    }


def analyze_cycles(frames: List[Frame]) -> dict:
    """
    Overview:
    Run all required statistics for each object appearance cycle.

    Input Parameters:
    - frames (list[Frame]): Parsed frames.

    Return Values:
    - dict: Structured analysis result for report rendering.
    """

    cycles = split_object_cycles(frames)
    frame_lookup = {f.frame_id: f for f in frames}

    # Keep only e-bike cycles; skip pedestrian or other slow/close targets.
    ebike_cycles = [c for c in cycles if is_ebike_cycle(c)]
    filtered_count = len(cycles) - len(ebike_cycles)

    sorted_cycles = sorted(
        ebike_cycles,
        key=lambda c: (
            classify_motion_scene(c)[2],
            c[0].frame_id,
        ),
    )

    cycle_results = []

    for idx, cycle in enumerate(sorted_cycles, start=1):
        scene_key, scene_label, _ = classify_motion_scene(cycle)
        object_dists = [abs(f.objects[0].dist_lat_m) for f in cycle if f.objects]
        farthest = max(object_dists) if object_dists else 0.0

        frame_drop_ids = missing_frame_ids_in_cycle(cycle)
        frame_drop_set = set(frame_drop_ids)
        match_rows = []
        missing_point_frames: List[int] = []
        consecutive_missing_streak = 0
        lost_events: List[int] = []

        for f in cycle:
            obj = f.objects[0]
            match = match_point_for_object(f, obj)
            if match.matched:
                consecutive_missing_streak = 0
            else:
                missing_point_frames.append(f.frame_id)
                consecutive_missing_streak += 1
                if consecutive_missing_streak == 3:
                    lost_events.append(f.frame_id)

            expected_angle_deg = math.degrees(
                math.atan2(obj.dist_long_m, max(abs(obj.dist_lat_m), 1e-6))
            )

            match_rows.append(
                {
                    "frame_id": f.frame_id,
                    "obj_dist_lat": obj.dist_lat_m,
                    "obj_dist_long": obj.dist_long_m,
                    "obj_vre_lat": obj.vre_lat_mps,
                    "obj_vre_long": obj.vre_long_mps,
                    "expected_angle_deg": expected_angle_deg,
                    "matched": match.matched,
                    "point_angle_deg": match.angle_deg,
                }
            )

        launch_frames = infer_launch_frames(cycle, frames)
        launch_start_frame = max(cycle[0].frame_id - launch_frames, 0)
        display_start_frame = max(launch_start_frame - 2, 0)
        alarm_data = analyze_alarm_in_cycle(cycle)

        row_by_frame = {r["frame_id"]: r for r in match_rows}
        timeline_rows = []
        for frame_id in range(display_start_frame, cycle[-1].frame_id + 1):
            row = row_by_frame.get(frame_id)

            if row is None:
                row = {
                    "frame_id": frame_id,
                    "obj_dist_lat": None,
                    "obj_dist_long": None,
                    "obj_vre_lat": None,
                    "obj_vre_long": None,
                    "expected_angle_deg": None,
                    "matched": False,
                    "point_angle_deg": None,
                }

            status_tags: List[str] = []
            frame_data = frame_lookup.get(frame_id)

            if frame_id < launch_start_frame:
                status_tags.append("建航前参考帧")
            elif frame_id < cycle[0].frame_id:
                if frame_data and frame_data.points:
                    status_tags.append("建航阶段")
                else:
                    status_tags.append("建航前无点云")
            else:
                if frame_id in frame_drop_set:
                    status_tags.append("目标丢失")
                else:
                    status_tags.append("目标存在")

            if frame_id == cycle[0].frame_id:
                status_tags.append("目标首次出现")

            if frame_id in missing_point_frames:
                status_tags.append("点云丢失")

            if (
                frame_id >= cycle[0].frame_id
                and frame_id not in frame_drop_set
                and row.get("matched")
            ):
                status_tags.append("点云匹配")

            row["target_status"] = " | ".join(status_tags)
            timeline_rows.append(row)

        cycle_results.append(
            {
                "cycle_index": idx,
                "start_frame": cycle[0].frame_id,
                "end_frame": cycle[-1].frame_id,
                "duration_frames": len(cycle),
                "scene_key": scene_key,
                "scene_label": scene_label,
                "farthest_distance_m": farthest,
                "launch_start_frame": launch_start_frame,
                "object_frame_drops": frame_drop_ids,
                "launch_frames": launch_frames,
                "missing_point_frames": missing_point_frames,
                "lost_events": lost_events,
                "alarm": alarm_data,
                "rows": timeline_rows,
            }
        )

    global_farthest = 0.0
    if cycle_results:
        global_farthest = max(item["farthest_distance_m"] for item in cycle_results)

    approaching = [c["farthest_distance_m"] for c in cycle_results if c["scene_key"] == "approaching"]
    receding    = [c["farthest_distance_m"] for c in cycle_results if c["scene_key"] == "receding"]
    global_farthest_approaching = max(approaching) if approaching else None
    global_farthest_receding    = max(receding)    if receding    else None

    return {
        "frame_count": len(frames),
        "total_cycle_count": len(cycles),
        "filtered_cycle_count": filtered_count,
        "cycle_count": len(cycle_results),
        "global_farthest_distance_m": global_farthest,
        "global_farthest_approaching_m": global_farthest_approaching,
        "global_farthest_receding_m": global_farthest_receding,
        "cycles": cycle_results,
    }


def fmt_ids(ids: List[int]) -> str:
    """
    Overview:
    Render frame IDs as readable text.

    Input Parameters:
    - ids (list[int]): Frame IDs.

    Return Values:
    - str: Rendered text.
    """

    if not ids:
        return "无"
    return ", ".join(str(x) for x in ids)


def render_html(data: dict, input_name: str) -> str:
    """
    Overview:
    Build final HTML report from analysis result.

    Input Parameters:
    - data (dict): Analysis output.
    - input_name (str): Input file name for display.

    Return Values:
    - str: Full HTML text.
    """

    cycle_blocks = []
    frame_lookup = {f.frame_id: f for f in data.get("_frame_lookup", [])}

    def fmt_num(value: float | None) -> str:
        if value is None:
            return "-"
        return f"{value:.2f}"

    def build_frame_detail_text(frame_id: int) -> str:
        frame = frame_lookup.get(frame_id)
        if frame is None:
            return f"FrameID={frame_id}\nFrame not found in source data."

        lines = [
            f"FrameID={frame.frame_id}",
            f"TimeStamp={frame.timestamp_ms:.0f}",
            f"AlarmType={frame.alarm_type} ({alarm_label(frame.alarm_type)})",
            f"PointNum={len(frame.points)}",
            f"ObjectNum={len(frame.objects)}",
            "[Point]",
        ]

        if frame.points:
            for i, p in enumerate(frame.points, start=1):
                lines.append(
                    f"{i}:Range={p.range_m:.1f} Velocity={p.velocity_mps:.1f} "
                    f"AngleAZ={p.angle_az_rad:.6f}"
                )
        else:
            lines.append("None")

        lines.append("[Object]")
        if frame.objects:
            for i, obj in enumerate(frame.objects, start=1):
                lines.append(
                    f"{i}:DistLat={obj.dist_lat_m:.1f} DistLong={obj.dist_long_m:.1f} "
                    f"VreLat={obj.vre_lat_mps:.1f} VreLong={obj.vre_long_mps:.1f}"
                )
        else:
            lines.append("None")

        return "\n".join(lines)

    for c in data["cycles"]:
        rows_html = []
        for r in c["rows"]:
            point_angle = "-" if r["point_angle_deg"] is None else f"{r['point_angle_deg']:.2f}"
            frame_data = frame_lookup.get(r["frame_id"])
            frame_alarm_type = frame_data.alarm_type if frame_data else 0
            detail_text = html.escape(build_frame_detail_text(r["frame_id"]))
            rows_html.append(
                "<tr>"
                "<td>"
                "<details class='frame-detail-inline'>"
                f"<summary>{r['frame_id']}</summary>"
                f"<pre>{detail_text}</pre>"
                "</details>"
                "</td>"
                f"<td>{fmt_num(r['obj_dist_lat'])}</td>"
                f"<td>{fmt_num(r['obj_dist_long'])}</td>"
                f"<td>{fmt_num(r['obj_vre_lat'])}</td>"
                f"<td>{fmt_num(r['obj_vre_long'])}</td>"
                f"<td>{fmt_num(r['expected_angle_deg'])}</td>"
                f"<td>{alarm_label(frame_alarm_type)}</td>"
                f"<td>{'是' if r['matched'] else '否'}</td>"
                f"<td>{point_angle}</td>"
                f"<td>{html.escape(r['target_status'])}</td>"
                "</tr>"
            )

        alarm = c["alarm"]
        alarm_start_frame = (
            str(alarm["alarm_start_frame"])
            if alarm["alarm_start_frame"] is not None
            else "无"
        )
        farthest_alarm = (
            f"{alarm['farthest_alarm_distance_m']:.2f} m"
            if alarm["farthest_alarm_distance_m"] is not None
            else "无"
        )

        cycle_blocks.append(
            f"""
<details class=\"cycle\">
    <summary>
        <span class=\"summary-title\">Cycle {c['cycle_index']}</span>
        <span class=\"summary-meta\">{c['scene_label']} | 帧 {c['start_frame']} - {c['end_frame']}</span>
    </summary>
    <h2>Cycle {c['cycle_index']} (帧 {c['start_frame']} - {c['end_frame']})</h2>
  <div class=\"metrics\">
        <div><span>持续帧数</span><strong>{c['duration_frames']} 帧</strong></div>
        <div><span>运动场景</span><strong>{c['scene_label']}</strong></div>
        <div><span>建航起始帧</span><strong>{c['launch_start_frame']}</strong></div>
        <div><span>最远目标距离</span><strong>{c['farthest_distance_m']:.2f} m</strong></div>
        <div><span>目标中途丢帧</span><strong>{html.escape(fmt_ids(c['object_frame_drops']))}</strong></div>
        <div><span>建航帧数（点云先于目标）</span><strong>{c['launch_frames']}</strong></div>
        <div><span>点云缺失帧</span><strong>{html.escape(fmt_ids(c['missing_point_frames']))}</strong></div>
        <div><span>点云丢失事件（连续3帧）</span><strong>{html.escape(fmt_ids(c['lost_events']))}</strong></div>
                <div><span>报警起始帧</span><strong>{alarm_start_frame}</strong></div>
                <div><span>报警起始类型</span><strong>{alarm_label(alarm['alarm_start_type'])}</strong></div>
                <div><span>最远报警距离</span><strong>{farthest_alarm}</strong></div>
                <div><span>丢失报警帧（应持续报警）</span><strong>{html.escape(fmt_ids(alarm['missing_alarm_frames']))}</strong></div>
                <div class="metrics-full"><span>报警提示切换距离</span>{format_alarm_switches_html(alarm['alarm_switches'])}</div>
  </div>
    <div class="table-wrap">
    <table>
    <thead>
      <tr>
                <th>帧号</th>
                <th>目标纵向距离 (m)</th>
                <th>目标横向距离 (m)</th>
                <th>目标纵向速度 (m/s)</th>
                <th>目标横向速度 (m/s)</th>
                <th>目标相对角度 (deg)</th>
                <th>报警提示</th>
                <th>点云匹配</th>
                <th>匹配点方位角 (deg)</th>
                <th>目标状态</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
    </table>
    </div>
</details>
"""
        )

    # Keep a lightweight lookup for rendering row alarm type by FrameID.
    data["_frame_lookup"] = data.get("_frame_lookup", [])

    cycles_html = (
        "\n".join(cycle_blocks)
        if cycle_blocks
        else "<p>未检测到目标数据</p>"
    )

    return f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>毫米波雷达分析报告</title>
  <style>
    :root {{
            --bg-1: #f6f8ef;
            --bg-2: #e6eef6;
            --bg-3: #f6efe7;
            --panel: #ffffff;
            --text: #15222c;
            --muted: #5c6772;
            --line: #d8dee6;
            --accent: #0a7a6a;
            --accent-2: #d04c2e;
            --accent-soft: #daf6ee;
            --bad: #b42318;
            --shadow-lg: 0 20px 40px rgba(11, 31, 52, 0.10);
            --shadow-md: 0 8px 22px rgba(11, 31, 52, 0.08);
    }}
    body {{
      margin: 0;
            font-family: "Source Han Sans SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
            background:
                radial-gradient(circle at 5% 12%, rgba(10, 122, 106, 0.14), transparent 35%),
                radial-gradient(circle at 92% 22%, rgba(208, 76, 46, 0.12), transparent 30%),
                linear-gradient(140deg, var(--bg-1) 0%, var(--bg-2) 48%, var(--bg-3) 100%);
      color: var(--text);
            min-height: 100vh;
    }}
    .container {{
            max-width: 1320px;
            margin: 20px auto;
            padding: 0 18px 44px;
    }}
    .header {{
            background: linear-gradient(145deg, rgba(255, 255, 255, 0.90), rgba(255, 255, 255, 0.72));
            backdrop-filter: blur(8px);
      border: 1px solid var(--line);
            border-radius: 18px;
            padding: 22px;
            box-shadow: var(--shadow-lg);
    }}
        .header h1 {{
            margin: 0 0 6px 0;
            font-size: 31px;
            letter-spacing: 0.4px;
        }}
        .header p {{ margin: 6px 0; color: var(--muted); }}
    .overview {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 14px;
            margin-top: 16px;
    }}
    .card {{
      border: 1px solid var(--line);
            border-radius: 14px;
            padding: 13px;
            background: linear-gradient(160deg, #ffffff 0%, #f8fbff 100%);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8), var(--shadow-md);
    }}
    .card span {{ display: block; color: var(--muted); font-size: 12px; }}
        .card strong {{ font-size: 22px; color: var(--accent); }}
    .cycle {{
            margin-top: 20px;
            background: linear-gradient(165deg, #ffffff 0%, #fbfcfe 100%);
      border: 1px solid var(--line);
            border-radius: 18px;
            padding: 16px;
            box-shadow: var(--shadow-md);
            overflow: hidden;
            animation: fadeSlide 0.42s ease both;
    }}
        .cycle summary {{
            cursor: pointer;
            list-style: none;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
                        padding: 8px 4px 12px;
                        border-bottom: 1px dashed #c8d2dc;
                        margin-bottom: 12px;
        }}
        .cycle summary::-webkit-details-marker {{
            display: none;
        }}
        .summary-title {{
                        font-size: 20px;
            font-weight: 700;
            color: var(--accent);
        }}
        .summary-meta {{
                        font-size: 13px;
            color: var(--muted);
                        padding: 4px 10px;
                        border: 1px solid #dbe4ec;
                        border-radius: 999px;
                        background: rgba(255, 255, 255, 0.7);
        }}
        .cycle h2 {{ margin: 0 0 12px; font-size: 21px; }}
    .metrics {{
      display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 12px;
            margin-bottom: 14px;
    }}
    .metrics div {{
            background: linear-gradient(145deg, var(--accent-soft) 0%, #f2fcf8 100%);
            border-radius: 12px;
            padding: 10px 12px;
            border: 1px solid #b7e9d8;
    }}
    .metrics-full {{
            grid-column: 1 / -1;
    }}
    .metrics span {{ display: block; font-size: 12px; color: #115e59; }}
        .metrics strong {{ font-size: 15px; line-height: 1.35; }}
    .switch-table {{
            width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 13px;
    }}
    .switch-table th {{
            background: #d1fae5; color: #065f46; font-weight: 600;
            padding: 4px 10px; border: 1px solid #a7f3d0; text-align: center;
    }}
    .switch-table td {{
            padding: 4px 10px; border: 1px solid #a7f3d0; text-align: center; color: #1e293b;
    }}
    .switch-table tr:nth-child(even) td {{ background: #f0fdf8; }}
        .table-wrap {{
            overflow-x: auto;
            border: 1px solid var(--line);
            border-radius: 12px;
            background: #fff;
        }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; min-width: 1080px; }}
        th, td {{ border: 1px solid var(--line); padding: 9px; text-align: center; }}
        th {{
            background: linear-gradient(180deg, #f8fafd 0%, #eef3f8 100%);
            position: sticky;
            top: 0;
            z-index: 2;
        }}
        tbody tr:nth-child(even) {{ background: #fbfdff; }}
        tbody tr:hover {{ background: #f1f8ff; }}
    .warn {{ color: var(--bad); font-weight: 600; }}
        .frame-detail-inline {{ text-align: left; }}
        .frame-detail-inline summary {{
            cursor: pointer;
                        color: var(--accent);
            font-weight: 600;
            list-style: none;
                        display: inline-flex;
                        align-items: center;
                        gap: 6px;
                        padding: 3px 8px;
                        border-radius: 999px;
                        border: 1px solid #c8dbd5;
                        background: #f4fcf9;
                        text-decoration: none;
        }}
        .frame-detail-inline pre {{
            margin-top: 8px;
            background: #f8fafc;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 8px;
            max-height: 280px;
            overflow: auto;
            white-space: pre;
            font-size: 12px;
        }}
        @keyframes fadeSlide {{
            from {{ opacity: 0; transform: translateY(8px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        @media (max-width: 768px) {{
            .container {{ margin-top: 12px; padding: 0 10px 24px; }}
            .header {{ padding: 16px; border-radius: 14px; }}
            .header h1 {{ font-size: 22px; }}
            .summary-title {{ font-size: 17px; }}
            .summary-meta {{ font-size: 12px; }}
            .cycle {{ padding: 12px; border-radius: 14px; }}
            .metrics {{ grid-template-columns: 1fr; gap: 8px; }}
        }}
  </style>
</head>
<body>
  <div class=\"container\">
    <div class=\"header\">
            <h1>毫米波雷达测试报告</h1>
            <p>输入文件: {html.escape(input_name)}</p>
            <p>规则说明: 帧连续性检查、点云与目标匹配、连续3帧缺失判定丢失。</p>
      <div class=\"overview\">
                <div class=\"card\"><span>总帧数</span><strong>{data['frame_count']}</strong></div>
                <div class="card"><span>检测到目标周期总数</span><strong>{data['total_cycle_count']}</strong></div>
                <div class="card"><span>电瓶车目标周期数（25–50 km/h）</span><strong>{data['cycle_count']}</strong></div>
                <div class="card"><span>被过滤周期数（行人等）</span><strong>{data['filtered_cycle_count']}</strong></div>
                <div class=\"card\"><span>接近场景最远目标距离</span><strong>{ f"{data['global_farthest_approaching_m']:.2f} m" if data['global_farthest_approaching_m'] is not None else '无' }</strong></div>
                <div class=\"card\"><span>远离场景最远目标距离</span><strong>{ f"{data['global_farthest_receding_m']:.2f} m" if data['global_farthest_receding_m'] is not None else '无' }</strong></div>
      </div>
    </div>
    {cycles_html}
  </div>
</body>
</html>
"""


def main() -> None:
    """
    Overview:
    Entrypoint for command-line usage.

    Input Parameters:
    - None. Arguments come from command line.

    Return Values:
    - None.
    """

    parser = argparse.ArgumentParser(description="Generate radar HTML report from frame log")
    parser.add_argument("-i", "--input", default="frame.txt", help="Input frame text path")
    parser.add_argument("-o", "--output", default="report.html", help="Output HTML path")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    text = input_path.read_text(encoding="utf-8")
    frames = parse_frames(text)
    result = analyze_cycles(frames)
    result["_frame_lookup"] = frames
    html_text = render_html(result, input_path.name)

    output_path.write_text(html_text, encoding="utf-8")
    print(f"Report generated: {output_path}")
    print(f"Frames: {result['frame_count']}, Cycles: {result['cycle_count']}")


if __name__ == "__main__":
    main()
