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
    expected_v = obj0.vre_lat_mps

    launch_count = 0
    cumulative_time = 0.0

    for i in range(idx - 1, -1, -1):
        prev = all_frames[i]
        nxt = all_frames[i + 1]

        dt = (nxt.timestamp_ms - prev.timestamp_ms) / 1000.0
        if math.isnan(dt) or dt <= 0:
            dt = 0.1
        cumulative_time += dt

        predicted_range = expected_range0 + expected_v * cumulative_time
        range_tol = max(2.0, predicted_range * 0.22)
        vel_tol = max(2.8, abs(expected_v) * 0.9)
        angle_tol = 14.0

        found = False
        for p in prev.points:
            dv = min(
                abs(p.velocity_mps - expected_v),
                abs(p.velocity_mps + expected_v),
                abs(p.velocity_mps),
            )
            p_angle = math.degrees(p.angle_az_rad)
            da = min(
                abs(p_angle - expected_angle),
                abs(p_angle + expected_angle),
                abs(abs(p_angle) - abs(expected_angle)),
            )
            if (
                abs(p.range_m - predicted_range) <= range_tol
                and dv <= vel_tol
                and da <= angle_tol
            ):
                found = True
                break

        if found:
            launch_count += 1
        else:
            break

    return launch_count


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
        return "无报警 / None"
    if alarm_type == 1:
        return "左侧 / Left"
    if alarm_type == 2:
        return "右侧 / Right"
    return f"未知({alarm_type}) / Unknown({alarm_type})"


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
        return "无 / None"

    chunks: List[str] = []
    for sw in switches:
        chunks.append(
            f"帧{sw['frame_id']}: {alarm_label(sw['from'])} -> "
            f"{alarm_label(sw['to'])} @ {sw['distance_m']:.2f}m"
        )
    return " ; ".join(chunks)


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
    cycle_results = []

    for idx, cycle in enumerate(cycles, start=1):
        object_dists = [abs(f.objects[0].dist_lat_m) for f in cycle if f.objects]
        farthest = max(object_dists) if object_dists else 0.0

        frame_drop_ids = missing_frame_ids_in_cycle(cycle)

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
        alarm_data = analyze_alarm_in_cycle(cycle)

        cycle_results.append(
            {
                "cycle_index": idx,
                "start_frame": cycle[0].frame_id,
                "end_frame": cycle[-1].frame_id,
                "duration_frames": len(cycle),
                "farthest_distance_m": farthest,
                "object_frame_drops": frame_drop_ids,
                "launch_frames": launch_frames,
                "missing_point_frames": missing_point_frames,
                "lost_events": lost_events,
                "alarm": alarm_data,
                "rows": match_rows,
            }
        )

    global_farthest = 0.0
    if cycle_results:
        global_farthest = max(item["farthest_distance_m"] for item in cycle_results)

    return {
        "frame_count": len(frames),
        "cycle_count": len(cycle_results),
        "global_farthest_distance_m": global_farthest,
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
        return "无 / None"
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

    for c in data["cycles"]:
        rows_html = []
        for r in c["rows"]:
            point_angle = "-" if r["point_angle_deg"] is None else f"{r['point_angle_deg']:.2f}"
            frame_alarm_type = next(
                (f.alarm_type for f in data["_frame_lookup"] if f.frame_id == r["frame_id"]),
                0,
            )
            rows_html.append(
                "<tr>"
                f"<td>{r['frame_id']}</td>"
                f"<td>{r['obj_dist_lat']:.2f}</td>"
                f"<td>{r['obj_dist_long']:.2f}</td>"
                f"<td>{r['obj_vre_lat']:.2f}</td>"
                f"<td>{r['obj_vre_long']:.2f}</td>"
                f"<td>{r['expected_angle_deg']:.2f}</td>"
                f"<td>{alarm_label(frame_alarm_type)}</td>"
                f"<td>{'是 / Yes' if r['matched'] else '否 / No'}</td>"
                f"<td>{point_angle}</td>"
                "</tr>"
            )

        alarm = c["alarm"]
        alarm_start_frame = (
            str(alarm["alarm_start_frame"])
            if alarm["alarm_start_frame"] is not None
            else "无 / None"
        )
        farthest_alarm = (
            f"{alarm['farthest_alarm_distance_m']:.2f} m"
            if alarm["farthest_alarm_distance_m"] is not None
            else "无 / None"
        )

        cycle_blocks.append(
            f"""
<section class=\"cycle\">
    <h2>周期 / Cycle {c['cycle_index']} (帧 / Frame {c['start_frame']} - {c['end_frame']})</h2>
  <div class=\"metrics\">
        <div><span>持续帧数 / Duration</span><strong>{c['duration_frames']} 帧 / frames</strong></div>
        <div><span>最远目标距离 / Farthest Object Distance</span><strong>{c['farthest_distance_m']:.2f} m</strong></div>
        <div><span>目标中途丢帧 / Object Mid-Track Frame Drops</span><strong>{html.escape(fmt_ids(c['object_frame_drops']))}</strong></div>
        <div><span>建航帧数（点云先于目标）/ Launch Frames (Point before Object)</span><strong>{c['launch_frames']}</strong></div>
        <div><span>点云缺失帧 / Missing Point Frames</span><strong>{html.escape(fmt_ids(c['missing_point_frames']))}</strong></div>
        <div><span>点云丢失事件（连续3帧）/ Point Lost Events (3 consecutive misses)</span><strong>{html.escape(fmt_ids(c['lost_events']))}</strong></div>
                <div><span>报警起始帧 / Alarm Start Frame</span><strong>{alarm_start_frame}</strong></div>
                <div><span>报警起始类型 / Alarm Start Type</span><strong>{alarm_label(alarm['alarm_start_type'])}</strong></div>
                <div><span>最远报警距离 / Farthest Alarm Distance</span><strong>{farthest_alarm}</strong></div>
                <div><span>丢失报警帧（应持续报警）/ Missing Alarm Frames</span><strong>{html.escape(fmt_ids(alarm['missing_alarm_frames']))}</strong></div>
                <div><span>报警提示切换距离 / Alarm Switch Distance</span><strong>{html.escape(format_alarm_switches(alarm['alarm_switches']))}</strong></div>
  </div>
  <table>
    <thead>
      <tr>
                <th>帧号 / FrameID</th>
                <th>目标纵向距离 / Obj DistLat (m)</th>
                <th>目标横向距离 / Obj DistLong (m)</th>
                <th>目标纵向速度 / Obj VreLat (m/s)</th>
                <th>目标横向速度 / Obj VreLong (m/s)</th>
                <th>目标相对角度 / Obj Angle vs Radar (deg)</th>
                <th>报警提示 / Alarm Type</th>
                <th>点云匹配 / Point Matched</th>
                <th>匹配点方位角 / Matched Point AngleAZ (deg)</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
</section>
"""
        )

    # Keep a lightweight lookup for rendering row alarm type by FrameID.
    data["_frame_lookup"] = data.get("_frame_lookup", [])

    cycles_html = (
        "\n".join(cycle_blocks)
        if cycle_blocks
        else "<p>未检测到目标数据 / No object data found.</p>"
    )

    return f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>毫米波雷达分析报告 / Radar Analysis Report</title>
  <style>
    :root {{
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --line: #e5e7eb;
      --accent: #0f766e;
      --accent-soft: #ccfbf1;
      --bad: #b91c1c;
    }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: linear-gradient(160deg, #f0fdfa 0%, var(--bg) 40%, #eef2ff 100%);
      color: var(--text);
    }}
    .container {{
      max-width: 1200px;
      margin: 24px auto;
      padding: 0 16px 40px;
    }}
    .header {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 20px;
      box-shadow: 0 6px 24px rgba(15, 23, 42, 0.06);
    }}
    .header h1 {{ margin: 0 0 6px 0; font-size: 28px; }}
    .header p {{ margin: 6px 0; color: var(--muted); }}
    .overview {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 12px;
      background: #fff;
    }}
    .card span {{ display: block; color: var(--muted); font-size: 12px; }}
    .card strong {{ font-size: 20px; color: var(--accent); }}
    .cycle {{
      margin-top: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 4px 18px rgba(15, 23, 42, 0.05);
    }}
    .cycle h2 {{ margin: 0 0 12px; font-size: 20px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }}
    .metrics div {{
      background: var(--accent-soft);
      border-radius: 10px;
      padding: 10px;
      border: 1px solid #99f6e4;
    }}
    .metrics span {{ display: block; font-size: 12px; color: #115e59; }}
    .metrics strong {{ font-size: 15px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border: 1px solid var(--line); padding: 8px; text-align: center; }}
    th {{ background: #f9fafb; }}
    .warn {{ color: var(--bad); font-weight: 600; }}
  </style>
</head>
<body>
  <div class=\"container\">
    <div class=\"header\">
            <h1>毫米波雷达测试报告 / Millimeter-Wave Radar Test Report</h1>
            <p>输入文件 / Input File: {html.escape(input_name)}</p>
            <p>规则说明 / Rules Applied: 帧连续性检查、点云与目标匹配、连续3帧缺失判定丢失 / frame continuity check, point/object matching, 3-frame point-loss rule.</p>
      <div class=\"overview\">
                <div class=\"card\"><span>总帧数 / Total Frames</span><strong>{data['frame_count']}</strong></div>
                <div class=\"card\"><span>目标周期数 / Object Cycles</span><strong>{data['cycle_count']}</strong></div>
                <div class=\"card\"><span>全局最远目标距离 / Global Farthest Object Distance</span><strong>{data['global_farthest_distance_m']:.2f} m</strong></div>
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
