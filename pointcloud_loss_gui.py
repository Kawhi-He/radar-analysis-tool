#!/usr/bin/env python3
"""
Author: Kawhi.He
Overview:
Desktop GUI for analyzing the farthest distance where point cloud is lost
for at least three consecutive frames.

Input Parameters:
- None directly. The user selects frame.txt, target speed, and speed tolerance.

Return Values:
- None. The GUI prints analysis text in a preview box.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import traceback

from tracking_report_generator import parse_frames

SPEED_OPTIONS = ["1 m/s", "5 m/s", "10 m/s", "20 m/s", "30 m/s"]
TOLERANCE_OPTIONS = ["±0.1 m/s", "±0.2 m/s", "±0.3 m/s", "±0.4 m/s"]


@dataclass
class LossRun:
    """
    Overview:
    Hold one consecutive point-cloud loss run.

    Input Parameters:
    - start_frame_id (int): Start frame ID of the run.
    - end_frame_id (int): End frame ID of the run.
    - run_length (int): Number of consecutive loss samples.
    - farthest_distance_m (float): Estimated farthest lost distance.
    - farthest_frame_id (int): Frame ID of the farthest lost frame.

    Return Values:
    - LossRun: Dataclass instance.

    Author: Kawhi.He
    """

    start_frame_id: int
    end_frame_id: int
    run_length: int
    farthest_distance_m: float
    farthest_frame_id: int


@dataclass
class FrameSpeedSample:
    """
    Overview:
    Hold one frame-level speed filter result based on [Point] only.

    Input Parameters:
    - frame_id (int): Frame ID.
    - has_match (bool): Whether any point matches speed filter.
    - matched_distance_m (float | None): Representative matched distance.

    Return Values:
    - FrameSpeedSample: Dataclass instance.

    Author: Kawhi.He
    """

    frame_id: int
    has_match: bool
    matched_distance_m: float | None


def parse_speed_label(speed_text: str) -> float:
    """
    Overview:
    Parse speed combobox label to numeric m/s value.

    Input Parameters:
    - speed_text (str): Speed text such as "10 m/s".

    Return Values:
    - float: Parsed speed in m/s.

    Author: Kawhi.He
    """

    return float(speed_text.split()[0])


def parse_tolerance_label(tol_text: str) -> float:
    """
    Overview:
    Parse tolerance combobox label to numeric m/s value.

    Input Parameters:
    - tol_text (str): Tolerance text such as "±0.2 m/s".

    Return Values:
    - float: Parsed tolerance in m/s.

    Author: Kawhi.He
    """

    normalized = tol_text.replace("±", "").strip()
    return float(normalized.split()[0])


def build_frame_speed_samples(
    frames: list,
    target_speed_mps: float,
    speed_tolerance_mps: float,
) -> list[FrameSpeedSample]:
    """
    Overview:
    Build frame-level speed match samples from point cloud only.

    Input Parameters:
    - frames (list): Parsed frame list.
    - target_speed_mps (float): Selected speed in m/s.
    - speed_tolerance_mps (float): Allowed speed deviation in m/s.

    Return Values:
    - list[FrameSpeedSample]: Frame-level speed matching results.

    Author: Kawhi.He
    """

    samples: list[FrameSpeedSample] = []

    for frame in frames:
        matched_ranges = [
            point.range_m
            for point in frame.points
            if abs(abs(point.velocity_mps) - target_speed_mps)
            <= speed_tolerance_mps
        ]
        if matched_ranges:
            matched_ranges.sort()
            rep_index = int(0.75 * (len(matched_ranges) - 1))
            # Use upper quartile distance to suppress extreme outliers while
            # keeping long-range trend.
            representative_distance = matched_ranges[rep_index]
            samples.append(
                FrameSpeedSample(
                    frame_id=frame.frame_id,
                    has_match=True,
                    matched_distance_m=representative_distance,
                )
            )
        else:
            samples.append(
                FrameSpeedSample(
                    frame_id=frame.frame_id,
                    has_match=False,
                    matched_distance_m=None,
                )
            )

    return samples


def estimate_loss_distance(
    samples: list[FrameSpeedSample],
    index: int,
) -> float | None:
    """
    Overview:
    Estimate loss distance for a frame without speed-matched points.

    Input Parameters:
    - samples (list[FrameSpeedSample]): Frame-level speed samples.
    - index (int): Index of the missing frame in samples.

    Return Values:
    - float | None: Estimated distance.

    Author: Kawhi.He
    """

    prev_index = index - 1
    next_index = index + 1

    while prev_index >= 0 and not samples[prev_index].has_match:
        prev_index -= 1
    while next_index < len(samples) and not samples[next_index].has_match:
        next_index += 1

    prev_dist = None
    next_dist = None

    if prev_index >= 0:
        prev_dist = samples[prev_index].matched_distance_m
    if next_index < len(samples):
        next_dist = samples[next_index].matched_distance_m

    if prev_dist is not None and next_dist is not None:
        span = max(1, next_index - prev_index)
        weight = (index - prev_index) / span
        return prev_dist + (next_dist - prev_dist) * weight
    if prev_dist is not None:
        return prev_dist
    if next_dist is not None:
        return next_dist
    return None


def find_loss_runs(
    samples: list[FrameSpeedSample],
    min_run_length: int = 3,
) -> list[LossRun]:
    """
    Overview:
    Find consecutive loss runs where speed-matched points are missing.

    Input Parameters:
    - samples (list[FrameSpeedSample]): Frame-level speed samples.
    - min_run_length (int): Minimum consecutive loss frame count.

    Return Values:
    - list[LossRun]: All qualified loss runs.

    Author: Kawhi.He
    """

    runs: list[LossRun] = []
    current_indexes: list[int] = []

    def flush_current() -> None:
        if len(current_indexes) < min_run_length:
            return

        estimated_points: list[tuple[int, float]] = []
        for idx in current_indexes:
            estimated = estimate_loss_distance(samples, idx)
            if estimated is not None:
                estimated_points.append((samples[idx].frame_id, estimated))

        if estimated_points:
            farthest_frame_id, farthest_distance_m = max(
                estimated_points,
                key=lambda item: item[1],
            )
        else:
            farthest_frame_id = samples[current_indexes[0]].frame_id
            farthest_distance_m = 0.0

        runs.append(
            LossRun(
                start_frame_id=samples[current_indexes[0]].frame_id,
                end_frame_id=samples[current_indexes[-1]].frame_id,
                run_length=len(current_indexes),
                farthest_distance_m=farthest_distance_m,
                farthest_frame_id=farthest_frame_id,
            )
        )

    for index, sample in enumerate(samples):
        if not sample.has_match:
            if (
                current_indexes
                and sample.frame_id
                != samples[current_indexes[-1]].frame_id + 1
            ):
                flush_current()
                current_indexes = []
            current_indexes.append(index)
            continue

        flush_current()
        current_indexes = []

    flush_current()
    return runs


def split_samples_into_rounds(
    samples: list[FrameSpeedSample],
    distance_reset_threshold_m: float = 40.0,
) -> list[list[FrameSpeedSample]]:
    """
    Overview:
    Split samples into test rounds by distance reset behavior.

    Input Parameters:
    - samples (list[FrameSpeedSample]): Frame-level speed samples.
        - distance_reset_threshold_m (float): Threshold for round reset.
            A new round is started only when distance drops significantly.

    Return Values:
    - list[list[FrameSpeedSample]]: Split rounds in time order.

    Author: Kawhi.He
    """

    if not samples:
        return []

    rounds: list[list[FrameSpeedSample]] = [[samples[0]]]
    prev_matched_distance: float | None = samples[0].matched_distance_m

    for sample in samples[1:]:
        if (
            sample.has_match
            and sample.matched_distance_m is not None
            and prev_matched_distance is not None
            and (
                prev_matched_distance - sample.matched_distance_m
                > distance_reset_threshold_m
            )
        ):
            rounds.append([sample])
        else:
            rounds[-1].append(sample)

        if sample.has_match and sample.matched_distance_m is not None:
            prev_matched_distance = sample.matched_distance_m

    return rounds


def merge_small_rounds(
    rounds: list[list[FrameSpeedSample]],
    min_matched_frames: int = 15,
) -> list[list[FrameSpeedSample]]:
    """
    Overview:
    Merge tiny fragmented rounds into neighbor rounds.

    Input Parameters:
    - rounds (list[list[FrameSpeedSample]]): Preliminary split rounds.
    - min_matched_frames (int): Minimum matched frame count for valid round.

    Return Values:
    - list[list[FrameSpeedSample]]: Merged valid rounds.

    Author: Kawhi.He
    """

    if not rounds:
        return []

    merged: list[list[FrameSpeedSample]] = []
    pending_prefix: list[FrameSpeedSample] = []

    for current in rounds:
        current_matched = sum(1 for sample in current if sample.has_match)

        if current_matched < min_matched_frames:
            if merged:
                merged[-1].extend(current)
            else:
                pending_prefix.extend(current)
            continue

        valid_round = list(current)
        if pending_prefix:
            valid_round = pending_prefix + valid_round
            pending_prefix = []
        merged.append(valid_round)

    if pending_prefix:
        if merged:
            merged[-1].extend(pending_prefix)
        else:
            merged.append(pending_prefix)

    return merged


def round_label(index: int) -> str:
    """
    Overview:
    Build Chinese round label text.

    Input Parameters:
    - index (int): 1-based round index.

    Return Values:
    - str: Round label text.

    Author: Kawhi.He
    """

    labels = [
        "第一轮",
        "第二轮",
        "第三轮",
        "第四轮",
        "第五轮",
        "第六轮",
        "第七轮",
        "第八轮",
        "第九轮",
        "第十轮",
    ]
    if 1 <= index <= len(labels):
        return labels[index - 1]
    return f"第{index}轮"


def build_analysis_text(
    input_path: Path,
    target_speed_mps: float,
    speed_tolerance_mps: float,
) -> str:
    """
    Overview:
    Build analysis text for farthest three-frame point-cloud loss distance.

    Input Parameters:
    - input_path (Path): Path to frame.txt.
    - target_speed_mps (float): Selected target speed in m/s.
    - speed_tolerance_mps (float): Selected speed tolerance in m/s.

    Return Values:
    - str: Analysis result text.

    Author: Kawhi.He
    """

    text = input_path.read_text(encoding="utf-8")
    frames = parse_frames(text)
    if not frames:
        raise ValueError("未解析到任何帧数据")

    samples = build_frame_speed_samples(
        frames,
        target_speed_mps,
        speed_tolerance_mps,
    )
    runs = find_loss_runs(samples, min_run_length=3)
    rounds = split_samples_into_rounds(samples)
    rounds = merge_small_rounds(rounds)

    matched_count = sum(1 for sample in samples if sample.has_match)

    header = [
        f"文件: {input_path}",
        f"速度筛选: {target_speed_mps:.1f} m/s",
        f"速度范围: ±{speed_tolerance_mps:.1f} m/s",
        f"总帧数: {len(samples)}",
        f"有匹配点的帧数: {matched_count}",
        f"识别轮次: {len(rounds)}",
        "判定规则: 连续3帧及以上无速度匹配点=点云丢失",
    ]

    if not runs:
        header.append("结论: 未发现连续三帧点云丢失")
        return "\n".join(header)

    farthest_run = max(runs, key=lambda run: run.farthest_distance_m)
    header.extend(
        [
            (
                "结论: 连续三帧及以上点云丢失的最远距离 = "
                f"{farthest_run.farthest_distance_m:.2f} m"
            ),
            f"最远丢失帧: FrameID {farthest_run.farthest_frame_id}",
            (
                "对应区间: "
                f"FrameID {farthest_run.start_frame_id} ~ "
                f"{farthest_run.end_frame_id}"
            ),
            f"连续丢失帧数: {farthest_run.run_length}",
            "",
            "全部连续丢失区间:",
        ]
    )

    for index, run in enumerate(runs, start=1):
        header.append(
            (
                f"{index}. FrameID {run.start_frame_id}~{run.end_frame_id}, "
                f"连续{run.run_length}帧, 最远丢失帧{run.farthest_frame_id}, "
                f"最远距离{run.farthest_distance_m:.2f}m"
            )
        )

    round_farthest_values: list[float] = []

    lines = ["分轮结果:"]

    for round_index, round_samples in enumerate(rounds, start=1):
        round_runs = find_loss_runs(round_samples, min_run_length=3)
        label = round_label(round_index)
        if round_runs:
            round_farthest = max(
                round_runs,
                key=lambda run: run.farthest_distance_m,
            )
            round_farthest_values.append(round_farthest.farthest_distance_m)
            lines.append(
                f"{label} {round_farthest.farthest_distance_m:.2f}m"
            )
        else:
            lines.append(f"{label} 无")

    if round_farthest_values:
        avg_farthest = sum(round_farthest_values) / len(round_farthest_values)
        lines.append(f"平均 {avg_farthest:.2f}m")
    else:
        lines.append("平均 无")

    header.extend(["", *lines])

    return "\n".join(header)


class PointCloudLossApp:
    """
    Overview:
    Main GUI application for point-cloud loss distance analysis.

    Input Parameters:
    - root (tk.Tk): Root tkinter window.

    Return Values:
    - PointCloudLossApp: Application instance.

    Author: Kawhi.He
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("点云连续丢帧最远距离分析工具")
        self.root.geometry("920x680")
        self.root.minsize(860, 620)

        self.input_var = tk.StringVar()
        self.speed_var = tk.StringVar(value="10 m/s")
        self.tolerance_var = tk.StringVar(value="±0.1 m/s")
        self.status_var = tk.StringVar(
            value="请先选择 frame.txt 文件 / Please select frame.txt first"
        )

        self.preview_text: tk.Text | None = None
        self.analyze_btn: ttk.Button | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        """
        Overview:
        Build and layout the GUI widgets.

        Input Parameters:
        - None.

        Return Values:
        - None.

        Author: Kawhi.He
        """

        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(
            container,
            text="点云连续三帧丢失最远距离分析",
            font=("Microsoft YaHei UI", 14, "bold"),
        )
        title.pack(anchor=tk.W, pady=(0, 10))

        file_card = ttk.LabelFrame(
            container,
            text="文件配置 / File Configuration",
            padding=12,
        )
        file_card.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(file_card, text="输入 frame.txt 文件:").grid(
            row=0,
            column=0,
            sticky=tk.W,
        )
        ttk.Entry(file_card, textvariable=self.input_var, width=92).grid(
            row=1,
            column=0,
            sticky=tk.EW,
            pady=(6, 0),
        )
        ttk.Button(
            file_card,
            text="选择文件 / Browse",
            command=self.select_input,
        ).grid(row=1, column=1, padx=(8, 0), pady=(6, 0))

        file_card.columnconfigure(0, weight=1)

        param_card = ttk.LabelFrame(
            container,
            text="筛选参数 / Filter Parameters",
            padding=12,
        )
        param_card.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(param_card, text="目标速度:").grid(row=0, column=0, sticky=tk.W)
        speed_combo = ttk.Combobox(
            param_card,
            textvariable=self.speed_var,
            values=SPEED_OPTIONS,
            state="readonly",
            width=12,
        )
        speed_combo.grid(row=0, column=1, sticky=tk.W, padx=(8, 0))

        ttk.Label(param_card, text="速度范围:").grid(
            row=0,
            column=2,
            sticky=tk.W,
            padx=(20, 0),
        )
        tolerance_combo = ttk.Combobox(
            param_card,
            textvariable=self.tolerance_var,
            values=TOLERANCE_OPTIONS,
            state="readonly",
            width=12,
        )
        tolerance_combo.grid(row=0, column=3, sticky=tk.W, padx=(8, 0))

        action_bar = ttk.Frame(container)
        action_bar.pack(fill=tk.X, pady=(0, 10))

        self.analyze_btn = ttk.Button(
            action_bar,
            text="开始分析 / Analyze",
            command=self.analyze,
        )
        self.analyze_btn.pack(anchor=tk.W)

        preview_card = ttk.LabelFrame(
            container,
            text="结果预览 / Result",
            padding=12,
        )
        preview_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        preview_container = ttk.Frame(preview_card)
        preview_container.pack(fill=tk.BOTH, expand=True)

        self.preview_text = tk.Text(
            preview_container,
            wrap=tk.WORD,
            height=18,
            font=("Consolas", 10),
            padx=10,
            pady=10,
        )
        preview_scroll = ttk.Scrollbar(
            preview_container,
            orient=tk.VERTICAL,
            command=self.preview_text.yview,
        )
        self.preview_text.configure(yscrollcommand=preview_scroll.set)
        self.preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        preview_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.preview_text.insert(
            tk.END,
            "请选择 frame.txt 并点击 Analyze 按钮。\n默认速度为 10 m/s。",
        )
        self.preview_text.configure(state=tk.DISABLED)

        status_card = ttk.LabelFrame(
            container,
            text="执行状态 / Status",
            padding=12,
        )
        status_card.pack(fill=tk.X)

        ttk.Label(
            status_card,
            textvariable=self.status_var,
            justify=tk.LEFT,
            wraplength=840,
        ).pack(anchor=tk.W)

    def select_input(self) -> None:
        """
        Overview:
        Select source frame.txt file.

        Input Parameters:
        - None.

        Return Values:
        - None.

        Author: Kawhi.He
        """

        path = filedialog.askopenfilename(
            title="选择 frame.txt / Select frame.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return

        self.input_var.set(path)
        self.status_var.set("已选择输入文件 / Input file selected")

    def _write_preview(self, content: str) -> None:
        """
        Overview:
        Render analysis text in preview box.

        Input Parameters:
        - content (str): Analysis output text.

        Return Values:
        - None.

        Author: Kawhi.He
        """

        if self.preview_text is None:
            return

        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert(tk.END, content)
        self.preview_text.configure(state=tk.DISABLED)

    def analyze(self) -> None:
        """
        Overview:
        Validate input and run analysis.

        Input Parameters:
        - None.

        Return Values:
        - None.

        Author: Kawhi.He
        """

        raw_input = self.input_var.get().strip()
        if not raw_input:
            messagebox.showwarning(
                "提示 / Notice",
                "请先选择 frame.txt 文件\nPlease select a frame.txt file first.",
            )
            return

        input_path = Path(raw_input)
        if not input_path.exists():
            messagebox.showerror(
                "错误 / Error",
                f"输入文件不存在 / Input file does not exist:\n{input_path}",
            )
            return

        try:
            target_speed_mps = parse_speed_label(self.speed_var.get().strip())
            speed_tolerance_mps = parse_tolerance_label(
                self.tolerance_var.get().strip()
            )
        except (IndexError, ValueError):
            messagebox.showerror("错误 / Error", "速度或速度范围格式错误")
            return

        if self.analyze_btn is not None:
            self.analyze_btn.configure(state=tk.DISABLED)

        self.status_var.set("正在分析，请稍候... / Analyzing, please wait...")
        self.root.update_idletasks()

        try:
            result_text = build_analysis_text(
                input_path,
                target_speed_mps,
                speed_tolerance_mps,
            )
            self._write_preview(result_text)
            self.status_var.set("分析完成 / Analysis completed")
        except (OSError, ValueError, UnicodeError) as exc:
            detail = "".join(
                traceback.format_exception_only(type(exc), exc)
            ).strip()
            self.status_var.set(f"分析失败 / Analysis failed\n{detail}")
            messagebox.showerror(
                "错误 / Error",
                f"分析失败 / Analysis failed\n{detail}",
            )
        finally:
            if self.analyze_btn is not None:
                self.analyze_btn.configure(state=tk.NORMAL)


def main() -> None:
    """
    Overview:
    GUI entrypoint.

    Input Parameters:
    - None.

    Return Values:
    - None.

    Author: Kawhi.He
    """

    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass

    app = PointCloudLossApp(root)
    _ = app
    root.mainloop()


if __name__ == "__main__":
    main()
