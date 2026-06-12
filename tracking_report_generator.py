#!/usr/bin/env python3
"""
Author: Kawhi.He
Overview:
Generate a TXT tracking report for a selected target speed from frame.txt logs.

Input Parameters:
- input_path (Path): Path to the source frame.txt file.
- target_speed_mps (float): Speed filter selected from the GUI.

Return Values:
- str: Formatted TXT report content.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Iterable

HEAD_RE = re.compile(r"^\s*([A-Za-z]+)=([\-\d\.nan]+)\s*$")
POINT_RE = re.compile(
    r"^\s*\d+:Range=([\-\d\.]+)\s+Velocity=([\-\d\.]+)\s+"
    r"AngleAZ=([\-\d\.]+)\s+AngleEL=([\-\d\.]+)\s+RCS=([\-\d\.]+)\s*$"
)
OBJECT_RE = re.compile(
    r"^\s*(\d+):DistLat=([\-\d\.]+)\s+DistLong=([\-\d\.]+)\s+"
    r"VreLat=([\-\d\.]+)\s+VreLong=([\-\d\.]+)\s+Power=([\-\d\.]+)\s+"
    r"DynamicPro=([\-\d\.]+)\s*$"
)


@dataclass
class Point:
    """
    Overview:
    Hold one point-cloud point parsed from [Point].

    Input Parameters:
    - range_m (float): Radial range in meters.
    - velocity_mps (float): Doppler velocity in m/s.
    - angle_az_rad (float): Azimuth angle in radians.
    - rcs_db (float): RCS value.

    Return Values:
    - Point: Dataclass instance.

    Author: Kawhi.He
    """

    range_m: float
    velocity_mps: float
    angle_az_rad: float
    rcs_db: float


@dataclass
class RadarObject:
    """
    Overview:
    Hold one object entry parsed from [Object].

    Input Parameters:
    - object_id (int): Object ID shown before the colon.
    - dist_lat_m (float): Longitudinal distance.
    - dist_long_m (float): Lateral distance.
    - vre_lat_mps (float): Longitudinal relative speed.
    - vre_long_mps (float): Lateral relative speed.
    - power (float): Power field.
    - dynamic_pro (float): Dynamic probability field.

    Return Values:
    - RadarObject: Dataclass instance.

    Author: Kawhi.He
    """

    object_id: int
    dist_lat_m: float
    dist_long_m: float
    vre_lat_mps: float
    vre_long_mps: float
    power: float
    dynamic_pro: float


@dataclass
class Frame:
    """
    Overview:
    Hold one parsed radar frame.

    Input Parameters:
    - frame_id (int): Frame ID from [HEAD].
    - timestamp_ms (float): Timestamp in milliseconds.
    - alarm_type (int): Alarm type from [HEAD].
    - points (list[Point]): Point cloud entries.
    - objects (list[RadarObject]): Object entries.

    Return Values:
    - Frame: Dataclass instance.

    Author: Kawhi.He
    """

    frame_id: int
    timestamp_ms: float
    alarm_type: int = 0
    points: list[Point] = field(default_factory=list)
    objects: list[RadarObject] = field(default_factory=list)


@dataclass
class TrackSample:
    """
    Overview:
    Hold one selected object sample in the final target track.

    Input Parameters:
    - frame_id (int): Frame ID.
    - timestamp_ms (float): Frame timestamp.
    - object_id (int): Object ID.
    - primary_distance_m (float): Distance along the dominant axis.
    - primary_speed_mps (float): Speed along the dominant axis.
    - angle_deg (float): Expected object azimuth in degree.
    - candidate_count (int): Matching candidate count in the frame.
    - point_matched (bool): Whether a point-cloud point was matched.
    - point_angle_deg (float | None): Matched point azimuth in degree.

    Return Values:
    - TrackSample: Dataclass instance.

    Author: Kawhi.He
    """

    frame_id: int
    timestamp_ms: float
    object_id: int
    primary_distance_m: float
    primary_speed_mps: float
    angle_deg: float
    candidate_count: int
    point_matched: bool
    point_angle_deg: float | None = None


def parse_float(value: str) -> float:
    """
    Overview:
    Parse a numeric string and handle nan.

    Input Parameters:
    - value (str): Numeric text.

    Return Values:
    - float: Parsed value.

    Author: Kawhi.He
    """

    if value.lower() == "nan":
        return math.nan
    return float(value)


def safe_mean(values: Iterable[float]) -> float:
    """
    Overview:
    Compute a mean value with empty-input protection.

    Input Parameters:
    - values (Iterable[float]): Numeric values.

    Return Values:
    - float: Mean value or 0.0.

    Author: Kawhi.He
    """

    values_list = list(values)
    return mean(values_list) if values_list else 0.0


def safe_round(value: float | None, digits: int = 1) -> str:
    """
    Overview:
    Format a numeric value for report output.

    Input Parameters:
    - value (float | None): Numeric value.
    - digits (int): Decimal digits.

    Return Values:
    - str: Formatted text.

    Author: Kawhi.He
    """

    if value is None or math.isnan(value):
        return "无"
    return f"{value:.{digits}f}"


def parse_frames(text: str) -> list[Frame]:
    """
    Overview:
    Parse raw frame text into structured frames.

    Input Parameters:
    - text (str): Full frame.txt content.

    Return Values:
    - list[Frame]: Parsed frames in original order.

    Author: Kawhi.He
    """

    frames: list[Frame] = []
    current_head: dict[str, float] = {}
    current_points: list[Point] = []
    current_objects: list[RadarObject] = []
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
            match = HEAD_RE.match(line)
            if match:
                current_head[match.group(1)] = parse_float(match.group(2))
        elif section == "POINT":
            match = POINT_RE.match(line)
            if match:
                current_points.append(
                    Point(
                        range_m=float(match.group(1)),
                        velocity_mps=float(match.group(2)),
                        angle_az_rad=float(match.group(3)),
                        rcs_db=float(match.group(5)),
                    )
                )
        elif section == "OBJECT":
            match = OBJECT_RE.match(line)
            if match:
                current_objects.append(
                    RadarObject(
                        object_id=int(match.group(1)),
                        dist_lat_m=float(match.group(2)),
                        dist_long_m=float(match.group(3)),
                        vre_lat_mps=float(match.group(4)),
                        vre_long_mps=float(match.group(5)),
                        power=float(match.group(6)),
                        dynamic_pro=float(match.group(7)),
                    )
                )

    flush_frame()
    return frames


def detect_axis_from_objects(objects: Iterable[RadarObject]) -> str:
    """
    Overview:
    Detect whether the target should be interpreted on the lat or long axis.

    Input Parameters:
    - objects (Iterable[RadarObject]): Candidate objects.

    Return Values:
    - str: "lat" or "long".

    Author: Kawhi.He
    """

    lat_values = []
    long_values = []

    for obj in objects:
        if not math.isnan(obj.dist_lat_m):
            lat_values.append(abs(obj.dist_lat_m))
        if not math.isnan(obj.dist_long_m):
            long_values.append(abs(obj.dist_long_m))

    if not lat_values or not long_values:
        return "lat"
    if safe_mean(long_values) > safe_mean(lat_values) * 1.8:
        return "long"
    return "lat"


def object_primary_distance(obj: RadarObject, axis: str) -> float:
    """
    Overview:
    Get the distance used for report output.

    Input Parameters:
    - obj (RadarObject): Radar object.
    - axis (str): Dominant axis.

    Return Values:
    - float: Absolute primary distance.

    Author: Kawhi.He
    """

    return abs(obj.dist_long_m) if axis == "long" else abs(obj.dist_lat_m)


def object_primary_speed(obj: RadarObject, axis: str) -> float:
    """
    Overview:
    Get the speed used for speed filtering.

    Input Parameters:
    - obj (RadarObject): Radar object.
    - axis (str): Dominant axis.

    Return Values:
    - float: Absolute primary speed.

    Author: Kawhi.He
    """

    return abs(obj.vre_long_mps) if axis == "long" else abs(obj.vre_lat_mps)


def expected_angle_deg(obj: RadarObject, axis: str) -> float:
    """
    Overview:
    Compute the expected azimuth angle for matching.

    Input Parameters:
    - obj (RadarObject): Radar object.
    - axis (str): Dominant axis.

    Return Values:
    - float: Expected azimuth angle in degree.

    Author: Kawhi.He
    """

    if axis == "long":
        return math.degrees(
            math.atan2(
                obj.dist_lat_m,
                max(abs(obj.dist_long_m), 1e-6),
            )
        )
    return math.degrees(
        math.atan2(
            obj.dist_long_m,
            max(abs(obj.dist_lat_m), 1e-6),
        )
    )


def speed_tolerance(speed_mps: float) -> float:
    """
    Overview:
    Compute the configurable tolerance used to filter objects.

    Input Parameters:
    - speed_mps (float): Selected speed.

    Return Values:
    - float: Speed tolerance in m/s.

    Author: Kawhi.He
    """

    return 0.5


def match_point_for_object(
    frame: Frame,
    obj: RadarObject,
    axis: str,
) -> tuple[bool, float | None]:
    """
    Overview:
    Match the target object to one point-cloud point in the same frame.

    Input Parameters:
    - frame (Frame): Current frame.
    - obj (RadarObject): Selected object.
    - axis (str): Dominant axis.

    Return Values:
    - tuple[bool, float | None]: Match status and point azimuth in degree.

    Author: Kawhi.He
    """

    expected_range = math.hypot(abs(obj.dist_lat_m), abs(obj.dist_long_m))
    expected_speed = object_primary_speed(obj, axis)
    expected_angle = expected_angle_deg(obj, axis)

    range_tol = max(1.6, expected_range * 0.22)
    speed_tol = 0.3
    angle_tol = 14.0

    best_score = None
    best_angle = None

    for point in frame.points:
        d_range = abs(point.range_m - expected_range)
        point_speed = abs(point.velocity_mps)
        d_speed = min(
            abs(point_speed - expected_speed),
            abs(point_speed + expected_speed),
        )
        point_angle = math.degrees(point.angle_az_rad)
        d_angle = min(
            abs(point_angle - expected_angle),
            abs(point_angle + expected_angle),
            abs(abs(point_angle) - abs(expected_angle)),
        )

        if d_range > range_tol or d_speed > speed_tol or d_angle > angle_tol:
            continue

        score = (
            d_range / max(range_tol, 1e-6)
            + d_speed / max(speed_tol, 1e-6)
            + d_angle / max(angle_tol, 1e-6)
        )
        if best_score is None or score < best_score:
            best_score = score
            best_angle = point_angle

    if best_score is None:
        return False, None
    return True, best_angle


def choose_track(
    frames: list[Frame],
    target_speed_mps: float,
    speed_tolerance_mps: float | None = None,
) -> tuple[str, list[TrackSample]]:
    """
    Overview:
    Select the most likely object track for the chosen speed.

    Input Parameters:
    - frames (list[Frame]): Parsed frames.
    - target_speed_mps (float): User-selected speed.
        - speed_tolerance_mps (float | None): Optional speed tolerance.
            If None, use the default tolerance rule.

    Return Values:
    - tuple[str, list[TrackSample]]: Dominant axis and selected track samples.

    Author: Kawhi.He
    """

    tol = (
        speed_tolerance(target_speed_mps)
        if speed_tolerance_mps is None
        else max(0.0, speed_tolerance_mps)
    )
    candidate_objects: list[RadarObject] = []
    for frame in frames:
        for obj in frame.objects:
            axis_guess = detect_axis_from_objects([obj])
            current_speed = object_primary_speed(obj, axis_guess)
            if abs(current_speed - target_speed_mps) <= tol:
                candidate_objects.append(obj)

    if not candidate_objects:
        raise ValueError(f"未找到与 {target_speed_mps:g} m/s 匹配的目标对象")

    axis = detect_axis_from_objects(candidate_objects)

    selected: list[TrackSample] = []
    prev_sample: TrackSample | None = None

    for frame in frames:
        frame_candidates: list[RadarObject] = []
        for obj in frame.objects:
            if detect_axis_from_objects([obj]) != axis:
                continue
            current_speed = object_primary_speed(obj, axis)
            if abs(current_speed - target_speed_mps) <= tol:
                frame_candidates.append(obj)

        if not frame_candidates:
            continue

        if prev_sample is None:
            chosen = max(
                frame_candidates,
                key=lambda obj: (
                    object_primary_distance(obj, axis),
                    obj.dynamic_pro,
                    -obj.object_id,
                ),
            )
        else:
            dt = (frame.timestamp_ms - prev_sample.timestamp_ms) / 1000.0
            if math.isnan(dt) or dt <= 0:
                dt = 0.1
            predicted_distance = max(
                prev_sample.primary_distance_m - target_speed_mps * dt,
                0.0,
            )
            best_score = None
            chosen = None
            prev_object_id = prev_sample.object_id
            prev_distance = prev_sample.primary_distance_m

            for obj in frame_candidates:
                current_distance = object_primary_distance(obj, axis)
                current_speed = object_primary_speed(obj, axis)
                distance_delta = abs(current_distance - predicted_distance)
                speed_delta = abs(current_speed - target_speed_mps)
                same_id_penalty = 0.0
                if obj.object_id != prev_object_id:
                    same_id_penalty = 0.8
                trend_penalty = 0.0
                if current_distance > prev_distance + 4.0:
                    trend_penalty = 1.4
                score = (
                    distance_delta,
                    speed_delta,
                    same_id_penalty + trend_penalty,
                    obj.object_id,
                )
                if best_score is None or score < best_score:
                    best_score = score
                    chosen = obj

            assert chosen is not None

        point_matched, point_angle_deg = match_point_for_object(
            frame,
            chosen,
            axis,
        )
        selected.append(
            TrackSample(
                frame_id=frame.frame_id,
                timestamp_ms=frame.timestamp_ms,
                object_id=chosen.object_id,
                primary_distance_m=object_primary_distance(chosen, axis),
                primary_speed_mps=object_primary_speed(chosen, axis),
                angle_deg=expected_angle_deg(chosen, axis),
                candidate_count=len(frame_candidates),
                point_matched=point_matched,
                point_angle_deg=point_angle_deg,
            )
        )
        prev_sample = selected[-1]

    if not selected:
        raise ValueError(f"未能根据 {target_speed_mps:g} m/s 构建目标跟踪轨迹")

    return axis, selected


def infer_launch_frames(
    first_sample: TrackSample,
    selected_index: int,
    frames: list[Frame],
    start_frame_index: int = 0,
) -> tuple[int, float]:
    """
    Overview:
    Estimate how many frames of point cloud exist before object launch.

    Input Parameters:
    - first_sample (TrackSample): First selected sample.
    - selected_index (int): Index of the first selected frame.
    - frames (list[Frame]): All parsed frames.

        Return Values:
        - tuple[int, float]: Estimated launch frame count and earliest
            pre-launch point distance.

    Author: Kawhi.He
    """

    if selected_index <= 0:
        return 0, first_sample.primary_distance_m
    if start_frame_index >= selected_index:
        return 0, first_sample.primary_distance_m

    expected_range = first_sample.primary_distance_m
    speed_mag = max(abs(first_sample.primary_speed_mps), 1e-6)
    expected_angle = first_sample.angle_deg

    launch_count = 0
    cumulative_time = 0.0
    prev_selected_range = expected_range
    earliest_range = expected_range
    miss_count = 0
    max_consecutive_misses = 12

    for idx in range(selected_index - 1, start_frame_index - 1, -1):
        prev_frame = frames[idx]
        next_frame = frames[idx + 1]

        dt = (next_frame.timestamp_ms - prev_frame.timestamp_ms) / 1000.0
        if math.isnan(dt) or dt <= 0:
            dt = 0.1
        cumulative_time += dt

        predicted_range = prev_selected_range + speed_mag * dt * 0.45
        range_tol = max(3.0, predicted_range * 0.08)
        speed_tol = max(1.0, speed_mag * 0.12)
        angle_tol = 12.0

        best_point = None
        best_score = None

        for point in prev_frame.points:
            d_range = abs(point.range_m - predicted_range)
            d_speed = abs(abs(point.velocity_mps) - speed_mag)
            p_angle = math.degrees(point.angle_az_rad)
            d_angle = min(
                abs(p_angle - expected_angle),
                abs(p_angle + expected_angle),
                abs(abs(p_angle) - abs(expected_angle)),
            )

            if d_range > range_tol or d_speed > speed_tol:
                continue
            if d_angle > angle_tol:
                continue
            if point.range_m + 0.3 < prev_selected_range:
                continue

            score = d_range + d_speed + d_angle * 0.08
            if best_score is None or score < best_score:
                best_score = score
                best_point = point

        if best_point is None:
            # Fallback for noisy range trend: prefer speed/angle-consistent
            # points that are still farther than the current launch point.
            for point in prev_frame.points:
                d_speed = abs(abs(point.velocity_mps) - speed_mag)
                p_angle = math.degrees(point.angle_az_rad)
                d_angle = min(
                    abs(p_angle - expected_angle),
                    abs(p_angle + expected_angle),
                    abs(abs(p_angle) - abs(expected_angle)),
                )

                if d_speed > max(2.0, speed_mag * 0.08):
                    continue
                if d_angle > 5.0:
                    continue
                if point.range_m + 1.0 < prev_selected_range:
                    continue

                score = d_speed + d_angle * 0.15
                if best_score is None or score < best_score:
                    best_score = score
                    best_point = point

        if best_point is None:
            miss_count += 1
            if miss_count >= max_consecutive_misses:
                break
            continue

        miss_count = 0

        if best_point.range_m + 0.4 < prev_selected_range:
            break

        launch_count += 1
        prev_selected_range = best_point.range_m
        earliest_range = best_point.range_m

    return launch_count, earliest_range


def split_track_cycles(selected: list[TrackSample]) -> list[list[TrackSample]]:
    """
    Overview:
    Split the selected track samples into multiple cycles.

    Input Parameters:
    - selected (list[TrackSample]): Selected track samples.

    Return Values:
    - list[list[TrackSample]]: Cycles ordered by appearance time.

    Author: Kawhi.He
    """

    if not selected:
        return []

    cycles: list[list[TrackSample]] = [[selected[0]]]

    for prev, cur in zip(selected, selected[1:]):
        distance_reset = (
            cur.primary_distance_m - prev.primary_distance_m > 20.0
        )
        if distance_reset:
            cycles.append([cur])
            continue
        cycles[-1].append(cur)

    return cycles


def build_event_ranges(
    selected: list[TrackSample],
    frames: list[Frame],
    frame_index_by_id: dict[int, int],
) -> tuple[list[str], list[str], list[str]]:
    """
    Overview:
    Derive gap, split, and ID-jump summaries from the selected track.

    Input Parameters:
    - selected (list[TrackSample]): Selected track samples.
    - frames (list[Frame]): All parsed frames.
    - frame_index_by_id (dict[int, int]): Frame index lookup table.

    Return Values:
    - tuple[list[str], list[str], list[str]]: Gap, split, and ID jump text.

    Author: Kawhi.He
    """

    frame_by_id: dict[int, Frame] = {f.frame_id: f for f in frames}

    gaps: list[str] = []
    splits: list[str] = []
    id_jumps: list[str] = []

    for prev, cur in zip(selected, selected[1:]):
        if cur.frame_id - prev.frame_id > 1:
            # Check if the same object ID exists in every skipped frame.
            # If it does, the object was never truly absent -> no gap.
            skipped_ids = range(prev.frame_id + 1, cur.frame_id)
            object_absent = any(
                not any(
                    obj.object_id == prev.object_id
                    for obj in frame_by_id[fid].objects
                )
                for fid in skipped_ids
                if fid in frame_by_id
            )
            if object_absent:
                gaps.append(
                    f"{safe_round(prev.primary_distance_m)}m到"
                    f"{safe_round(cur.primary_distance_m)}m之间断航"
                )

        if cur.candidate_count > 1 and (
            prev.candidate_count <= 1 or cur.object_id != prev.object_id
        ):
            splits.append(
                f"{safe_round(cur.primary_distance_m)}m时目标分裂，"
                f"分裂成{cur.candidate_count}个目标"
            )

        if cur.object_id != prev.object_id:
            id_jumps.append(
                f"{safe_round(cur.primary_distance_m)}m时出现ID跳变"
            )

    return gaps, splits, id_jumps


def build_angle_bins(selected: list[TrackSample]) -> list[str]:
    """
    Overview:
    Build 5m azimuth-mean segments after launch.

    Input Parameters:
    - selected (list[TrackSample]): Selected track samples.

    Return Values:
    - list[str]: Segment descriptions.

    Author: Kawhi.He
    """

    bins: dict[tuple[float, float], list[float]] = defaultdict(list)

    for sample in selected:
        if not sample.point_matched or sample.point_angle_deg is None:
            continue
        bucket_high = math.ceil(sample.primary_distance_m / 5.0) * 5.0
        bucket_low = max(bucket_high - 5.0, 0.0)
        bins[(bucket_low, bucket_high)].append(sample.point_angle_deg)

    segments: list[str] = []
    for (bucket_low, bucket_high), angles in sorted(
        bins.items(),
        key=lambda item: item[0][1],
        reverse=True,
    ):
        segments.append(
            f"{safe_round(bucket_high, 0)}-{safe_round(bucket_low, 0)}m，"
            f"水平角平均偏移{safe_round(safe_mean(angles), 2)}度"
        )
    return segments


def cycle_label(cycle_index: int) -> str:
    """
    Overview:
    Format the display label for a cycle section.

    Input Parameters:
    - cycle_index (int): Zero-based cycle index.

    Return Values:
    - str: Human-readable cycle label.

    Author: Kawhi.He
    """

    labels = [
        "第一次",
        "第二次",
        "第三次",
        "第四次",
        "第五次",
        "第六次",
        "第七次",
        "第八次",
        "第九次",
        "第十次",
    ]
    if cycle_index < len(labels):
        return f"{labels[cycle_index]}循环："
    return f"第{cycle_index + 1}次循环："


def build_cycle_report_text(
    cycle_samples: list[TrackSample],
    frames: list[Frame],
    frame_index_by_id: dict[int, int],
    start_frame_index: int,
) -> str:
    """
    Overview:
    Build the report text for a single cycle.

    Input Parameters:
    - cycle_samples (list[TrackSample]): Samples that belong to one cycle.
    - frames (list[Frame]): All parsed frames.
    - frame_index_by_id (dict[int, int]): Frame index lookup table.

    Return Values:
    - str: Six-line report block for one cycle.

    Author: Kawhi.He
    """

    first_point_sample = next(
        (sample for sample in cycle_samples if sample.point_matched),
        cycle_samples[0],
    )
    selected_index = frame_index_by_id.get(cycle_samples[0].frame_id, 0)
    launch_frames, inferred_first_distance = infer_launch_frames(
        cycle_samples[0],
        selected_index,
        frames,
        start_frame_index=start_frame_index,
    )

    gaps, splits, id_jumps = build_event_ranges(
        cycle_samples, frames, frame_index_by_id
    )
    angle_bins = build_angle_bins(cycle_samples)

    if launch_frames > 0:
        first_distance = safe_round(inferred_first_distance)
    else:
        first_distance = safe_round(first_point_sample.primary_distance_m)
    launch_distance = safe_round(cycle_samples[0].primary_distance_m)

    line1 = f"1.目标点云首次出现在 {first_distance}m"
    line2 = f"2.{launch_distance}m时建航，建航帧数 {launch_frames} 帧"
    line3 = f"3.断航情况： {'，'.join(gaps) if gaps else '无'}"
    line4 = f"4.分裂情况： {'，'.join(splits) if splits else '无'}"
    line5 = f"5.建航后，{'，'.join(angle_bins) if angle_bins else '无'}"
    line6 = f"6.ID跳变： {'，'.join(id_jumps) if id_jumps else '无'}"

    return "\n".join([line1, line2, line3, line4, line5, line6])


def build_report_text(input_path: Path, target_speed_mps: float) -> str:
    """
    Overview:
    Parse the source log and generate the final TXT report text.

    Input Parameters:
    - input_path (Path): Source frame.txt path.
    - target_speed_mps (float): Selected speed in m/s.

    Return Values:
    - str: Final report text.

    Author: Kawhi.He
    """

    frames = parse_frames(input_path.read_text(encoding="utf-8"))
    axis, selected = choose_track(frames, target_speed_mps)
    _ = axis

    cycles = split_track_cycles(selected)
    frame_index_by_id = {
        frame.frame_id: index for index, frame in enumerate(frames)
    }

    report_blocks = []
    for cycle_index, cycle_samples in enumerate(cycles):
        if cycle_index == 0:
            cycle_start_frame_index = 0
        else:
            previous_last_frame = cycles[cycle_index - 1][-1].frame_id
            cycle_start_frame_index = (
                frame_index_by_id.get(previous_last_frame, 0) + 1
            )

        report_blocks.append(
            cycle_label(cycle_index)
            + "\n"
            + build_cycle_report_text(
                cycle_samples,
                frames,
                frame_index_by_id,
                cycle_start_frame_index,
            )
        )

    return "\n\n".join(report_blocks)


def generate_tracking_report(
    input_path: Path,
    output_path: Path,
    target_speed_mps: float,
) -> str:
    """
    Overview:
    Generate a TXT tracking report file.

    Input Parameters:
    - input_path (Path): Source frame.txt path.
    - output_path (Path): Output txt path.
    - target_speed_mps (float): Selected speed.

    Return Values:
    - str: Generated report text.

    Author: Kawhi.He
    """

    report_text = build_report_text(input_path, target_speed_mps)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding="utf-8")
    return report_text
