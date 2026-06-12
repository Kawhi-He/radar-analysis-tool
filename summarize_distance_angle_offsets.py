#!/usr/bin/env python3
"""
Author: Kawhi.He
Overview:
Summarize horizontal angle offsets for simulator target distances from
frame.txt datasets. The script filters points by the configured distance band,
finds the dominant azimuth cluster, and reports max/min/average azimuth angle
in degrees for each radar folder and distance folder.

Input Parameters:
- root (str): Dataset root folder that contains radar-id subfolders.
- range_tol_m (float): Allowed absolute distance deviation from configured
  folder distance.
- cluster_window_deg (float): Sliding window width used to locate the dominant
  azimuth cluster.
- angle_tol_deg (float): Allowed azimuth deviation from the dominant cluster
  center when selecting per-frame target points.
- output (str | None): Optional CSV output path.

Return Values:
- None. Prints a table to stdout and optionally writes a CSV file.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook

POINT_RE = re.compile(
    r"^\s*\d+:Range=([\-\d\.]+)\s+Velocity=([\-\d\.]+)\s+"
    r"AngleAZ=([\-\d\.]+)\s+AngleEL=([\-\d\.]+)\s+RCS=([\-\d\.]+)\s*$"
)


@dataclass
class AngleSummaryRow:
    """
    Overview:
    Hold one summarized distance-angle result row.

    Input Parameters:
    - radar_id (str): Radar folder name.
    - distance_m (float): Configured simulator distance.
        - max_offset_deg (float): Filtered angle with the largest absolute
            horizontal offset.
        - min_offset_deg (float): Filtered angle with the smallest absolute
            horizontal offset.
        - avg_offset_deg (float): Average filtered horizontal angle.
        - matched_frame_count (int): Number of frames that contributed
            one target point after filtering.

    Return Values:
    - AngleSummaryRow: Dataclass instance for output.
    """

    radar_id: str
    distance_m: float
    max_offset_deg: float
    min_offset_deg: float
    avg_offset_deg: float
    matched_frame_count: int


def parse_frame_points(file_path: Path) -> list[list[tuple[float, float]]]:
    """
    Overview:
    Parse one frame.txt file into per-frame point arrays.

    Input Parameters:
    - file_path (Path): Path to one frame.txt file.

    Return Values:
    - list[list[tuple[float, float]]]: Per-frame point lists as
      (range_m, angle_deg).
    """

    text = file_path.read_text(encoding="utf-8")
    frames: list[list[tuple[float, float]]] = []
    current_points: list[tuple[float, float]] = []
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
        angle_deg = math.degrees(float(match.group(3)))
        current_points.append((range_m, angle_deg))

    if started:
        frames.append(current_points)

    return frames


def find_dominant_center(
    angles_deg: Iterable[float],
    window_deg: float,
) -> float | None:
    """
    Overview:
    Find the dominant azimuth cluster center with a sliding window.

    Input Parameters:
    - angles_deg (Iterable[float]): Candidate azimuth angles in degrees.
    - window_deg (float): Sliding window width.

    Return Values:
    - float | None: Mean angle of the densest window, or None if empty.
    """

    values = sorted(angles_deg)
    if not values:
        return None

    best_start = 0
    best_end = 0
    end = 0

    for start, value in enumerate(values):
        while end < len(values) and values[end] <= value + window_deg:
            end += 1
        if end - start > best_end - best_start:
            best_start = start
            best_end = end

    segment = values[best_start:best_end]
    return statistics.mean(segment)


def summarize_one_file(
    file_path: Path,
    target_distance_m: float,
    range_tol_m: float,
    cluster_window_deg: float,
    angle_tol_deg: float,
) -> AngleSummaryRow | None:
    """
    Overview:
    Summarize one frame.txt file into max/min/average horizontal angle.

    Input Parameters:
    - file_path (Path): Path to one frame.txt file.
    - target_distance_m (float): Configured simulator distance.
    - range_tol_m (float): Allowed absolute distance deviation.
    - cluster_window_deg (float): Dominant cluster search width.
    - angle_tol_deg (float): Allowed deviation around dominant cluster center.

    Return Values:
        - AngleSummaryRow | None: Summary row, or None if no stable target
            is found.
    """

    frames = parse_frame_points(file_path)
    candidate_angle_magnitudes = [
        abs(angle_deg)
        for points in frames
        for range_m, angle_deg in points
        if abs(range_m - target_distance_m) <= range_tol_m
    ]
    center_abs_deg = find_dominant_center(
        candidate_angle_magnitudes,
        cluster_window_deg,
    )
    if center_abs_deg is None:
        return None

    filtered_angles: list[float] = []

    for points in frames:
        candidates = [
            (
                abs(range_m - target_distance_m),
                abs(abs(angle_deg) - center_abs_deg),
                angle_deg,
            )
            for range_m, angle_deg in points
            if abs(range_m - target_distance_m) <= range_tol_m
            and abs(abs(angle_deg) - center_abs_deg) <= angle_tol_deg
        ]
        if not candidates:
            continue

        _, _, selected_angle_deg = min(candidates)
        filtered_angles.append(selected_angle_deg)

    if not filtered_angles:
        return None

    return AngleSummaryRow(
        radar_id=file_path.parent.parent.name,
        distance_m=target_distance_m,
        max_offset_deg=max(filtered_angles, key=abs),
        min_offset_deg=min(filtered_angles, key=abs),
        avg_offset_deg=statistics.mean(filtered_angles),
        matched_frame_count=len(filtered_angles),
    )


def collect_rows(
    root: Path,
    range_tol_m: float,
    cluster_window_deg: float,
    angle_tol_deg: float,
) -> list[AngleSummaryRow]:
    """
    Overview:
    Walk the dataset root and collect summary rows.

    Input Parameters:
    - root (Path): Dataset root folder.
    - range_tol_m (float): Allowed absolute distance deviation.
    - cluster_window_deg (float): Dominant cluster search width.
    - angle_tol_deg (float): Allowed deviation around dominant cluster center.

    Return Values:
    - list[AngleSummaryRow]: Summarized rows sorted by radar and distance.
    """

    rows: list[AngleSummaryRow] = []

    radar_dirs = sorted(
        (path for path in root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    )

    for radar_dir in radar_dirs:
        distance_dirs = sorted(
            (path for path in radar_dir.iterdir() if path.is_dir()),
            key=lambda path: float(path.name),
        )
        for distance_dir in distance_dirs:
            frame_path = distance_dir / "frame.txt"
            if not frame_path.is_file():
                continue

            row = summarize_one_file(
                file_path=frame_path,
                target_distance_m=float(distance_dir.name),
                range_tol_m=range_tol_m,
                cluster_window_deg=cluster_window_deg,
                angle_tol_deg=angle_tol_deg,
            )
            if row is not None:
                rows.append(row)

    return rows


def print_table(rows: list[AngleSummaryRow]) -> None:
    """
    Overview:
    Print a plain-text table to stdout.

    Input Parameters:
    - rows (list[AngleSummaryRow]): Summary rows to print.

    Return Values:
    - None.
    """

    headers = [
        "Radar ID",
        "Distance (m)",
        "Max Offset (deg)",
        "Min Offset (deg)",
        "Avg Offset (deg)",
        "Matched Frames",
    ]
    data_rows = [
        [
            row.radar_id,
            f"{row.distance_m:.0f}",
            f"{row.max_offset_deg:.3f}",
            f"{row.min_offset_deg:.3f}",
            f"{row.avg_offset_deg:.3f}",
            str(row.matched_frame_count),
        ]
        for row in rows
    ]
    widths = [len(header) for header in headers]
    for data_row in data_rows:
        for index, value in enumerate(data_row):
            widths[index] = max(widths[index], len(value))

    def format_row(values: list[str]) -> str:
        return " | ".join(
            value.ljust(widths[index])
            for index, value in enumerate(values)
        )

    print(format_row(headers))
    print("-+-".join("-" * width for width in widths))
    for data_row in data_rows:
        print(format_row(data_row))


def write_csv(rows: list[AngleSummaryRow], output_path: Path) -> None:
    """
    Overview:
    Write summary rows to a CSV file.

    Input Parameters:
    - rows (list[AngleSummaryRow]): Summary rows to write.
    - output_path (Path): Output CSV path.

    Return Values:
    - None.
    """

    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([
            "Radar ID",
            "Distance (m)",
            "Max Offset (deg)",
            "Min Offset (deg)",
            "Avg Offset (deg)",
            "Matched Frames",
        ])
        for row in rows:
            writer.writerow([
                row.radar_id,
                f"{row.distance_m:.0f}",
                f"{row.max_offset_deg:.3f}",
                f"{row.min_offset_deg:.3f}",
                f"{row.avg_offset_deg:.3f}",
                row.matched_frame_count,
            ])


def write_excel(rows: list[AngleSummaryRow], output_path: Path) -> None:
    """
    Overview:
    Write summary rows to an Excel workbook.

    Input Parameters:
    - rows (list[AngleSummaryRow]): Summary rows to write.
    - output_path (Path): Output Excel path.

    Return Values:
    - None.
    """

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Distance Angle Summary"
    worksheet.append([
        "Radar ID",
        "Distance (m)",
        "Max Offset (deg)",
        "Min Offset (deg)",
        "Avg Offset (deg)",
        "Matched Frames",
    ])
    for row in rows:
        worksheet.append([
            row.radar_id,
            float(f"{row.distance_m:.0f}"),
            round(row.max_offset_deg, 3),
            round(row.min_offset_deg, 3),
            round(row.avg_offset_deg, 3),
            row.matched_frame_count,
        ])

    for column_cells in worksheet.columns:
        width = max(
            len(str(cell.value)) if cell.value is not None else 0
            for cell in column_cells
        )
        column_letter = column_cells[0].column_letter
        worksheet.column_dimensions[column_letter].width = width + 2

    workbook.save(output_path)


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Overview:
    Build the command-line argument parser.

    Input Parameters:
    - None.

    Return Values:
    - argparse.ArgumentParser: Configured argument parser.
    """

    parser = argparse.ArgumentParser(
        description="Summarize simulator target horizontal angle offsets.",
    )
    parser.add_argument(
        "root",
        nargs="?",
        default="距离数据_20260603",
        help="Dataset root folder.",
    )
    parser.add_argument(
        "--range-tol",
        type=float,
        default=2.0,
        help="Allowed absolute range deviation in meters.",
    )
    parser.add_argument(
        "--cluster-window",
        type=float,
        default=3.0,
        help="Dominant angle cluster window in degrees.",
    )
    parser.add_argument(
        "--angle-tol",
        type=float,
        default=2.5,
        help="Allowed deviation from the dominant angle center in degrees.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("distance_angle_summary.csv"),
        help="Optional CSV output path.",
    )
    parser.add_argument(
        "--excel-output",
        type=Path,
        default=Path("distance_angle_summary.xlsx"),
        help="Optional Excel output path.",
    )
    return parser


def main() -> None:
    """
    Overview:
    Parse arguments, summarize the dataset, print the table, and write files.

    Input Parameters:
    - None.

    Return Values:
    - None.
    """

    parser = build_argument_parser()
    args = parser.parse_args()
    root = Path(args.root)

    rows = collect_rows(
        root=root,
        range_tol_m=args.range_tol,
        cluster_window_deg=args.cluster_window,
        angle_tol_deg=args.angle_tol,
    )
    print_table(rows)
    if args.output:
        write_csv(rows, args.output)
    if args.excel_output:
        write_excel(rows, args.excel_output)


if __name__ == "__main__":
    main()
