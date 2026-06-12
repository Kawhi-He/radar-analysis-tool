#!/usr/bin/env python3
"""
Author: Kawhi.He
Overview:
Draw a smooth and visually pleasing radar detection power map.
The x-axis is azimuth degree, and the y-axis is farthest detection distance.
Points are filtered by near-target speed (10 m/s by default).

Input Parameters:
- roots (list[str]): Dataset root folders, such as Effect_range_test-01-002.
- output (str): Output image path for the rendered plot.
- dpi (int): Output image DPI.
- show (bool): Whether to show interactive window after saving.

Return Values:
- None. The script saves the generated figure to the output path.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np

from compute_effect_range_loss import RunResult, run_dataset


def build_runtime_args(
    speed_target_mps: float = 10.0,
    speed_tol_mps: float = 0.35,
    target_dbm: int = 10,
) -> SimpleNamespace:
    """
    Overview:
    Build fixed analysis parameters shared by all datasets.

    Input Parameters:
    - None.

    Return Values:
    - SimpleNamespace: Runtime config fields for run_dataset().
    """

    return SimpleNamespace(
        angle_window_deg=8.0,
        angle_tol_deg=2.2,
        range_min_m=8.0,
        range_max_m=120.0,
        speed_target_mps=speed_target_mps,
        speed_tol_mps=speed_tol_mps,
        use_abs_speed=True,
        target_dbm=target_dbm,
    )


def collect_series(
    root: Path,
    runtime_args: SimpleNamespace,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Overview:
    Compute (angle, farthest_loss) arrays for one dataset root.

    Input Parameters:
    - root (Path): Dataset root path.
    - runtime_args (SimpleNamespace): Analysis config for run_dataset().

    Return Values:
    - tuple[np.ndarray, np.ndarray]: Sorted x/y arrays for plotting.
    """

    results: List[RunResult] = run_dataset(root, runtime_args)
    pairs = [
        (r.scene_angle_deg, r.farthest_loss_m)
        for r in results
        if r.farthest_loss_m is not None
    ]

    if not pairs:
        return np.array([], dtype=float), np.array([], dtype=float)

    pairs.sort(key=lambda item: item[0])
    x = np.array([p[0] for p in pairs], dtype=float)
    y = np.array([p[1] for p in pairs], dtype=float)
    return x, y


def smooth_curve(
    x: np.ndarray,
    y: np.ndarray,
    dense_count: int = 500,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Overview:
    Generate a smooth curve using dense interpolation and Gaussian convolution.

    Input Parameters:
    - x (np.ndarray): Angle data.
    - y (np.ndarray): Distance data.
    - dense_count (int): Number of dense points for interpolation.

    Return Values:
    - tuple[np.ndarray, np.ndarray]: Smoothed x/y arrays.
    """

    if x.size <= 2:
        return x, y

    xd = np.linspace(float(x.min()), float(x.max()), dense_count)
    yi = np.interp(xd, x, y)

    # Gaussian kernel for gentle smoothing while preserving global trend.
    sigma = 4.0
    radius = 12
    kernel_x = np.arange(-radius, radius + 1, dtype=float)
    kernel = np.exp(-0.5 * (kernel_x / sigma) ** 2)
    kernel /= kernel.sum()

    ys = np.convolve(yi, kernel, mode="same")
    return xd, ys


def draw_plot(
    series_map: Dict[str, Tuple[np.ndarray, np.ndarray]],
    output_path: Path,
    dpi: int,
    speed_target_mps: float = 10.0,
    speed_tol_mps: float = 0.35,
    target_dbm: int = 10,
) -> None:
    """
    Overview:
    Render and save the radar detection power map.

    Input Parameters:
    - series_map (dict[str, tuple[np.ndarray, np.ndarray]]): Dataset plot data.
    - output_path (Path): Image output path.
    - dpi (int): Figure DPI.

    Return Values:
    - None.
    """

    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "DejaVu Sans",
    ]

    fig = plt.figure(figsize=(14, 7), constrained_layout=True)
    grid = fig.add_gridspec(nrows=1, ncols=2, width_ratios=[3.9, 1.25])
    ax = fig.add_subplot(grid[0, 0])
    ax_table = fig.add_subplot(grid[0, 1])

    # Soft gradient background for a cleaner and more modern look.
    gradient = np.linspace(0.96, 0.86, 256)
    gradient = np.vstack([gradient] * 256)
    ax.imshow(
        gradient,
        extent=[-42, 42, 0, 50],
        cmap="Blues",
        alpha=0.12,
        aspect="auto",
        zorder=0,
    )

    colors = ["#0a7a6a", "#d04c2e", "#1f4e8c", "#ad8b00"]

    for index, (name, (x, y)) in enumerate(series_map.items()):
        if x.size == 0:
            continue

        xd, ys = smooth_curve(x, y)
        color = colors[index % len(colors)]

        ax.plot(
            xd,
            ys,
            color=color,
            linewidth=2.8,
            label=f"{name} (smooth)",
            zorder=3,
        )
        ax.scatter(
            x,
            y,
            color=color,
            s=28,
            alpha=0.85,
            edgecolors="white",
            linewidths=0.6,
            zorder=4,
        )
        ax.fill_between(xd, ys, alpha=0.10, color=color, zorder=2)

    ax.set_title(
        (
            "Radar Detection Power Map "
            f"(Near {speed_target_mps:.1f} m/s "
            f"+-{speed_tol_mps:.1f} m/s, {target_dbm} dBm)"
        ),
        fontsize=18,
        pad=14,
    )
    ax.set_xlabel("Azimuth Degree (deg)", fontsize=13)
    ax.set_ylabel("Farthest Detection Distance (m)", fontsize=13)
    ax.set_xlim(-42, 42)

    y_max = 0.0
    for _, (_, y) in series_map.items():
        if y.size:
            y_max = max(y_max, float(np.max(y)))
    ax.set_ylim(0, max(20.0, y_max + 4.0))

    ax.grid(True, linestyle="--", linewidth=0.8, alpha=0.35)
    ax.legend(loc="upper center", ncol=2, frameon=True, framealpha=0.92)
    ax.text(
        0.985,
        0.03,
        (
            f"Target Power: {target_dbm} dBm | "
            f"Target Speed: {speed_target_mps:.1f} m/s | "
            f"Speed Tol: +- {speed_tol_mps:.1f} m/s"
        ),
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=10,
        color="#2a334d",
        bbox={
            "boxstyle": "round,pad=0.22",
            "fc": "#f4f7ff",
            "ec": "#cfd7ea",
            "alpha": 0.90,
        },
    )

    # Build right-side detailed table from the first available dataset.
    table_name = ""
    table_x = np.array([], dtype=float)
    table_y = np.array([], dtype=float)
    for name, (x, y) in series_map.items():
        if x.size > 0:
            table_name = name
            table_x = x
            table_y = y
            break

    ax_table.set_axis_off()
    ax_table.set_facecolor("#1f2026")

    if table_x.size > 0:
        cell_text = [
            [f"{int(angle)}", f"{distance:.1f}"]
            for angle, distance in zip(table_x, table_y)
        ]
        headers = ["角度(°)", "最远丢失距离(m)"]

        table = ax_table.table(
            cellText=cell_text,
            colLabels=headers,
            colWidths=[0.34, 0.66],
            cellLoc="center",
            loc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(10.5)
        table.scale(1.0, 1.55)

        for (row, _), cell in table.get_celld().items():
            cell.set_edgecolor("#404452")
            cell.set_linewidth(0.8)
            if row == 0:
                cell.set_facecolor("#202531")
                cell.set_text_props(color="#f6f8ff", weight="bold")
            else:
                cell.set_facecolor("#232733")
                cell.set_text_props(color="#e6ecff")

        if len(series_map) > 1:
            ax_table.set_title(
                f"详细数据: {table_name}",
                fontsize=11,
                color="#d9deec",
                pad=10,
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    """
    Overview:
    Create CLI parser.

    Input Parameters:
    - None.

    Return Values:
    - argparse.ArgumentParser: Configured parser instance.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Plot smooth radar detection power curves from dataset folders."
        ),
    )
    parser.add_argument(
        "roots",
        nargs="*",
        default=[
            "Effect_range_test-01-002",
            "Effect_range_test-01-004",
            "Effect_range_test-01-006",
        ],
        help="Dataset root folders.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="radar_detection_power_map.png",
        help="Output image path.",
    )
    parser.add_argument("--dpi", type=int, default=220)
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

    runtime_args = build_runtime_args()
    series_map: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}

    for raw_root in args.roots:
        root = Path(raw_root)
        if not root.exists() or not root.is_dir():
            print(f"skip={raw_root} reason=path_not_found")
            continue

        x, y = collect_series(root, runtime_args)
        series_map[root.name] = (x, y)

    if not series_map:
        print("No valid dataset found. Nothing to plot.")
        return

    output_path = Path(args.output)
    draw_plot(
        series_map,
        output_path=output_path,
        dpi=args.dpi,
        speed_target_mps=runtime_args.speed_target_mps,
        speed_tol_mps=runtime_args.speed_tol_mps,
        target_dbm=runtime_args.target_dbm,
    )
    print(f"saved_plot={output_path}")


if __name__ == "__main__":
    main()
