#!/usr/bin/env python3
"""
Author: Kawhi.He
Overview:
Compute farthest loss distance per scene angle from simulator point-cloud logs.
This version focuses on points whose velocity is near the target speed
(10 m/s by default), and directly reports the farthest detected distance
across multi-cycle frames for each angle folder.

Input Parameters:
- roots (list[str]): One or more dataset root folders (for example,
  Effect_range_test-01-004).
- angle_window_deg (float): Candidate center search window around scene angle.
- angle_tol_deg (float): Point azimuth tolerance around candidate center.
- range_min_m (float): Minimum range to treat as target candidate.
- range_max_m (float): Maximum range to treat as target candidate.
- speed_target_mps (float): Target speed center for filtering.
- speed_tol_mps (float): Allowed speed deviation around target speed.
- signed_speed (bool): Whether to use signed speed instead of absolute speed.

Return Values:
- None. Prints a CSV-like report to stdout.
"""

from __future__ import annotations

import argparse
import math
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

POINT_RE = re.compile(
    r"^\s*\d+:Range=([\-\d\.]+)\s+Velocity=([\-\d\.]+)\s+"
    r"AngleAZ=([\-\d\.]+)\s+AngleEL=([\-\d\.]+)\s+RCS=([\-\d\.]+)\s*$"
)


@dataclass
class RunResult:
    """
    Overview:
    Hold one scene analysis result.

    Input Parameters:
    - scene_angle_deg (int): Folder angle value.
        - selected_track_angle_deg (float | None):
            Best fitted tracking angle center.
    - run_count (int): Number of valid filtered points.
    - farthest_loss_m (float | None): Maximum filtered range value.
    - median_loss_m (float | None): Median filtered range value.

    Return Values:
    - RunResult: Dataclass instance for output.
    """

    scene_angle_deg: int
    selected_track_angle_deg: float | None
    run_count: int
    farthest_loss_m: float | None
    median_loss_m: float | None


def parse_frame_points(
    file_path: Path,
) -> List[List[tuple[float, float, float]]]:
    """
    Overview:
    Parse frame.txt into frame-wise point lists
    (range, azimuth_deg, velocity_mps).

    Input Parameters:
    - file_path (Path): Path to one frame.txt file.

    Return Values:
    - list[list[tuple[float, float, float]]]: Per-frame point arrays.
    """

    text = file_path.read_text(encoding="utf-8")
    frames: List[List[tuple[float, float, float]]] = []
    current_points: List[tuple[float, float, float]] = []
    in_point_section = False
    started = False

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if line == "[HEAD]":
            if started:
                frames.append(current_points)
            started = True
            current_points = []
            in_point_section = False
            continue

        if line == "[Point]":
            in_point_section = True
            continue

        if line == "[Object]":
            in_point_section = False
            continue

        if not in_point_section:
            continue

        match = POINT_RE.match(raw_line)
        if not match:
            continue

        range_m = float(match.group(1))
        velocity_mps = float(match.group(2))
        angle_az_deg = math.degrees(float(match.group(3)))
        current_points.append((range_m, angle_az_deg, velocity_mps))

    if started:
        frames.append(current_points)

    return frames


def collect_speed_filtered_ranges(
    frames: Iterable[List[tuple[float, float, float]]],
    center_angle_deg: float,
    angle_tol_deg: float,
    range_min_m: float,
    range_max_m: float,
    speed_target_mps: float,
    speed_tol_mps: float,
    use_abs_speed: bool,
) -> List[float]:
    """
    Overview:
    Collect all point ranges that pass angle, distance, and speed filters.

    Input Parameters:
    - frames (Iterable[list[tuple[float, float, float]]]): Parsed frame points.
    - center_angle_deg (float): Candidate track center azimuth in degrees.
    - angle_tol_deg (float): Allowed azimuth deviation.
    - range_min_m (float): Minimum valid range.
    - range_max_m (float): Maximum valid range.
    - speed_target_mps (float): Target speed center.
    - speed_tol_mps (float): Allowed speed deviation.
    - use_abs_speed (bool): Whether speed comparison uses absolute value.

    Return Values:
    - list[float]: All candidate ranges from all frames.
    """

    selected_ranges: List[float] = []

    for points in frames:
        for range_m, angle_az_deg, velocity_mps in points:
            speed_value = abs(velocity_mps) if use_abs_speed else velocity_mps
            if not (
                range_min_m <= range_m <= range_max_m
                and abs(angle_az_deg - center_angle_deg) <= angle_tol_deg
                and abs(speed_value - speed_target_mps) <= speed_tol_mps
            ):
                continue
            selected_ranges.append(range_m)

    return selected_ranges


def analyze_scene(
    folder: Path,
    angle_window_deg: float,
    angle_tol_deg: float,
    range_min_m: float,
    range_max_m: float,
    speed_target_mps: float,
    speed_tol_mps: float,
    use_abs_speed: bool,
) -> RunResult:
    """
    Overview:
    Analyze one scene folder and pick the best angle-center filter result.

    Input Parameters:
    - folder (Path): Scene folder whose name is angle degree.
    - angle_window_deg (float): Candidate center search window.
    - angle_tol_deg (float): Point azimuth tolerance.
    - range_min_m (float): Minimum range threshold.
    - range_max_m (float): Maximum range threshold.
    - speed_target_mps (float): Target speed center.
    - speed_tol_mps (float): Allowed speed deviation.
    - use_abs_speed (bool): Whether speed comparison uses absolute value.

    Return Values:
    - RunResult: Scene-level output.
    """

    frame_file = folder / "frame.txt"
    scene_angle = int(folder.name)

    if not frame_file.exists():
        return RunResult(scene_angle, None, 0, None, None)

    frames = parse_frame_points(frame_file)
    if not frames:
        return RunResult(scene_angle, None, 0, None, None)

    best_score: tuple[float, int, float] | None = None
    best_center: float | None = None
    best_ranges: List[float] = []

    start_angle = int(scene_angle - angle_window_deg)
    end_angle = int(scene_angle + angle_window_deg)

    for center in range(start_angle, end_angle + 1):
        ranges = collect_speed_filtered_ranges(
            frames=frames,
            center_angle_deg=float(center),
            angle_tol_deg=angle_tol_deg,
            range_min_m=range_min_m,
            range_max_m=range_max_m,
            speed_target_mps=speed_target_mps,
            speed_tol_mps=speed_tol_mps,
            use_abs_speed=use_abs_speed,
        )
        if not ranges:
            continue

        score = (max(ranges), len(ranges), statistics.median(ranges))

        if best_score is None or score > best_score:
            best_score = score
            best_center = float(center)
            best_ranges = ranges

    if not best_ranges:
        return RunResult(scene_angle, None, 0, None, None)

    return RunResult(
        scene_angle_deg=scene_angle,
        selected_track_angle_deg=best_center,
        run_count=len(best_ranges),
        farthest_loss_m=max(best_ranges),
        median_loss_m=statistics.median(best_ranges),
    )


def iter_scene_folders(root: Path) -> List[Path]:
    """
    Overview:
    Find and sort numeric scene folders under a dataset root.

    Input Parameters:
    - root (Path): Dataset root path.

    Return Values:
    - list[Path]: Sorted angle folders.
    """

    folders = [
        p
        for p in root.iterdir()
        if p.is_dir() and re.fullmatch(r"-?\d+", p.name)
    ]
    return sorted(folders, key=lambda p: int(p.name))


def run_dataset(root: Path, args: argparse.Namespace) -> List[RunResult]:
    """
    Overview:
    Run the full analysis for one dataset root.

    Input Parameters:
    - root (Path): Dataset root folder.
    - args (argparse.Namespace): CLI configuration values.

    Return Values:
    - list[RunResult]: One record per scene folder.
    """

    results: List[RunResult] = []
    for folder in iter_scene_folders(root):
        result = analyze_scene(
            folder=folder,
            angle_window_deg=args.angle_window_deg,
            angle_tol_deg=args.angle_tol_deg,
            range_min_m=args.range_min_m,
            range_max_m=args.range_max_m,
            speed_target_mps=args.speed_target_mps,
            speed_tol_mps=args.speed_tol_mps,
            use_abs_speed=args.use_abs_speed,
        )
        results.append(result)
    return results


def print_results(dataset_name: str, results: List[RunResult]) -> None:
    """
    Overview:
    Print dataset results in CSV-like rows.

    Input Parameters:
    - dataset_name (str): Root folder name.
    - results (list[RunResult]): Computed scene results.

    Return Values:
    - None.
    """

    print(f"dataset={dataset_name}")
    print(
        "scene_deg,best_track_angle_deg,run_count,farthest_loss_m,"
        "median_loss_m"
    )
    for row in results:
        if row.selected_track_angle_deg is None:
            angle = "NA"
        else:
            angle = f"{row.selected_track_angle_deg:.1f}"
        far = (
            "NA"
            if row.farthest_loss_m is None
            else f"{row.farthest_loss_m:.1f}"
        )
        med = "NA" if row.median_loss_m is None else f"{row.median_loss_m:.1f}"
        print(f"{row.scene_angle_deg},{angle},{row.run_count},{far},{med}")
    print()


def build_parser() -> argparse.ArgumentParser:
    """
    Overview:
    Build command-line parser.

    Input Parameters:
    - None.

    Return Values:
    - argparse.ArgumentParser: Configured parser.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Compute farthest loss distance for effect-range simulator "
            "datasets."
        ),
    )
    parser.add_argument(
        "roots",
        nargs="+",
        help=(
            "Dataset root folder paths (for example "
            "Effect_range_test-01-004)."
        ),
    )
    parser.add_argument("--angle-window-deg", type=float, default=8.0)
    parser.add_argument("--angle-tol-deg", type=float, default=2.2)
    parser.add_argument("--range-min-m", type=float, default=8.0)
    parser.add_argument("--range-max-m", type=float, default=120.0)
    parser.add_argument("--speed-target-mps", type=float, default=10.0)
    parser.add_argument("--speed-tol-mps", type=float, default=0.35)
    parser.add_argument(
        "--signed-speed",
        action="store_true",
        help="Use signed speed matching instead of absolute speed.",
    )
    return parser


def main() -> None:
    """
    Overview:
    Script entrypoint.

    Input Parameters:
    - None.

    Return Values:
    - None.
    """

    parser = build_parser()
    args = parser.parse_args()
    args.use_abs_speed = not args.signed_speed

    for raw_root in args.roots:
        root = Path(raw_root)
        if not root.exists() or not root.is_dir():
            print(f"dataset={raw_root}")
            print("error=path_not_found")
            print()
            continue

        results = run_dataset(root=root, args=args)
        print_results(root.name, results)


if __name__ == "__main__":
    main()
