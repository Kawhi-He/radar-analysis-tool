#!/usr/bin/env python3
"""
Author: Kawhi.He
Overview:
Desktop GUI for point-cloud analysis report generation.

Input Parameters:
- None directly. User interacts with GUI controls.

Return Values:
- None. Generates HTML report and displays status.
"""

from __future__ import annotations

import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from generate_pointcloud_report import generate_report


class PointCloudAnalysisApp:
    """
    Overview:
    Main GUI app for static/dynamic point-cloud analysis report generation.

    Input Parameters:
    - root (tk.Tk): Tk root window.

    Return Values:
    - PointCloudAnalysisApp: App instance.

    Author: Kawhi.He
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("点云分析工具")
        self.root.geometry("860x560")
        self.root.minsize(840, 520)

        self.mode_var = tk.StringVar(value="static")
        self.input_var = tk.StringVar()
        self.status_var = tk.StringVar(value="请先选择 frame.txt 文件")

        self.speed_value_var = tk.StringVar(value="5.0")
        self.speed_unit_var = tk.StringVar(value="m/s")
        self.static_rcs_var = tk.StringVar(value="10.0")
        self.static_distance_var = tk.StringVar(value="30.0")

        self.dynamic_rcs_var = tk.StringVar(value="10.0")
        self.dynamic_speed_value_var = tk.StringVar(value="5.0")
        self.dynamic_speed_unit_var = tk.StringVar(value="m/s")
        self.dynamic_scene_var = tk.StringVar(value="接近")

        self._build_ui()
        self._update_mode_ui()

    def _build_ui(self) -> None:
        """
        Overview:
        Build all widgets and layout.

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
            text="点云分析报告生成器",
            font=("Microsoft YaHei UI", 13, "bold"),
        )
        title.pack(anchor=tk.W, pady=(0, 10))

        mode_card = ttk.LabelFrame(container, text="目标类型（互斥选择）", padding=12)
        mode_card.pack(fill=tk.X, pady=(0, 10))

        ttk.Radiobutton(
            mode_card,
            text="静态目标",
            value="static",
            variable=self.mode_var,
            command=self._update_mode_ui,
        ).grid(row=0, column=0, sticky=tk.W, padx=(0, 16))
        ttk.Radiobutton(
            mode_card,
            text="动态目标",
            value="dynamic",
            variable=self.mode_var,
            command=self._update_mode_ui,
        ).grid(row=0, column=1, sticky=tk.W)

        file_card = ttk.LabelFrame(container, text="输入文件", padding=12)
        file_card.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(file_card, text="frame.txt 文件:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(file_card, textvariable=self.input_var, width=94).grid(
            row=1, column=0, sticky=tk.EW, pady=(6, 0)
        )
        ttk.Button(file_card, text="选择文件", command=self.select_input).grid(
            row=1, column=1, padx=(8, 0), pady=(6, 0)
        )
        file_card.columnconfigure(0, weight=1)

        self.static_card = ttk.LabelFrame(container, text="静态目标参数", padding=12)
        self.static_card.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(self.static_card, text="速度:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(self.static_card, textvariable=self.speed_value_var, width=14).grid(
            row=0, column=1, sticky=tk.W, padx=(6, 10)
        )
        ttk.Combobox(
            self.static_card,
            textvariable=self.speed_unit_var,
            values=["m/s", "km/h"],
            state="readonly",
            width=10,
        ).grid(row=0, column=2, sticky=tk.W)

        ttk.Label(self.static_card, text="RCS(dB):").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(self.static_card, textvariable=self.static_rcs_var, width=14).grid(
            row=1, column=1, sticky=tk.W, padx=(6, 10), pady=(8, 0)
        )

        ttk.Label(self.static_card, text="距离(m):").grid(row=1, column=2, sticky=tk.W, pady=(8, 0))
        ttk.Entry(self.static_card, textvariable=self.static_distance_var, width=14).grid(
            row=1, column=3, sticky=tk.W, padx=(6, 0), pady=(8, 0)
        )

        self.dynamic_card = ttk.LabelFrame(container, text="动态目标参数", padding=12)
        self.dynamic_card.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(self.dynamic_card, text="RCS(dB):").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(self.dynamic_card, textvariable=self.dynamic_rcs_var, width=14).grid(
            row=0, column=1, sticky=tk.W, padx=(6, 16)
        )

        ttk.Label(self.dynamic_card, text="速度:").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(self.dynamic_card, textvariable=self.dynamic_speed_value_var, width=14).grid(
            row=0, column=3, sticky=tk.W, padx=(6, 16)
        )
        ttk.Combobox(
            self.dynamic_card,
            textvariable=self.dynamic_speed_unit_var,
            values=["m/s", "km/h"],
            state="readonly",
            width=10,
        ).grid(row=0, column=4, sticky=tk.W)

        ttk.Label(self.dynamic_card, text="模式:").grid(row=0, column=5, sticky=tk.W)
        ttk.Combobox(
            self.dynamic_card,
            textvariable=self.dynamic_scene_var,
            values=["接近", "远离"],
            state="readonly",
            width=10,
        ).grid(row=0, column=6, sticky=tk.W, padx=(6, 0))

        action_bar = ttk.Frame(container)
        action_bar.pack(fill=tk.X, pady=(2, 10))

        self.generate_btn = ttk.Button(action_bar, text="生成点云分析报告", command=self.generate)
        self.generate_btn.pack(anchor=tk.W)

        status_card = ttk.LabelFrame(container, text="执行状态", padding=12)
        status_card.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            status_card,
            textvariable=self.status_var,
            justify=tk.LEFT,
            wraplength=800,
        ).pack(anchor=tk.W)

    def _update_mode_ui(self) -> None:
        """
        Overview:
        Toggle static/dynamic parameter panels by selected mode.

        Input Parameters:
        - None.

        Return Values:
        - None.

        Author: Kawhi.He
        """

        mode = self.mode_var.get()
        if mode == "static":
            self.static_card.configure(style="TLabelframe")
            self.dynamic_card.state(["disabled"])
            for child in self.dynamic_card.winfo_children():
                child.state(["disabled"])
            for child in self.static_card.winfo_children():
                child.state(["!disabled"])
        else:
            self.dynamic_card.configure(style="TLabelframe")
            self.static_card.state(["disabled"])
            for child in self.static_card.winfo_children():
                child.state(["disabled"])
            for child in self.dynamic_card.winfo_children():
                child.state(["!disabled"])

    def select_input(self) -> None:
        """
        Overview:
        Open file dialog to select frame input file.

        Input Parameters:
        - None.

        Return Values:
        - None.

        Author: Kawhi.He
        """

        path = filedialog.askopenfilename(
            title="选择 frame.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return

        self.input_var.set(path)
        self.status_var.set("已选择输入文件")

    def _build_config(self) -> tuple[str, dict]:
        """
        Overview:
        Build mode and config dict from current GUI values.

        Input Parameters:
        - None.

        Return Values:
        - tuple[str, dict]: (mode, config).

        Author: Kawhi.He
        """

        mode = self.mode_var.get()
        if mode == "static":
            return (
                "static",
                {
                    "speed_value": float(self.speed_value_var.get().strip()),
                    "speed_unit": self.speed_unit_var.get().strip(),
                    "rcs_db": float(self.static_rcs_var.get().strip()),
                    "distance_m": float(self.static_distance_var.get().strip()),
                },
            )

        return (
            "dynamic",
            {
                "rcs_db": float(self.dynamic_rcs_var.get().strip()),
                "speed_value": float(self.dynamic_speed_value_var.get().strip()),
                "speed_unit": self.dynamic_speed_unit_var.get().strip(),
                "speed_mps": float(self.dynamic_speed_value_var.get().strip()) / 3.6
                if self.dynamic_speed_unit_var.get().strip() == "km/h"
                else float(self.dynamic_speed_value_var.get().strip()),
                "scene_mode": self.dynamic_scene_var.get().strip(),
            },
        )

    def generate(self) -> None:
        """
        Overview:
        Validate inputs and generate HTML report.

        Input Parameters:
        - None.

        Return Values:
        - None.

        Author: Kawhi.He
        """

        raw_input = self.input_var.get().strip()
        if not raw_input:
            messagebox.showwarning("提示", "请先选择 frame.txt 文件")
            return

        input_path = Path(raw_input)
        if not input_path.exists():
            messagebox.showerror("错误", f"输入文件不存在:\n{input_path}")
            return

        try:
            mode, config = self._build_config()
        except ValueError:
            messagebox.showerror("错误", "参数格式错误，请检查速度、RCS、距离是否为数字")
            return

        output_path = input_path.with_name("pointcloud_report.html")

        self.generate_btn.configure(state=tk.DISABLED)
        self.status_var.set("正在生成报告，请稍候...")
        self.root.update_idletasks()

        try:
            result = generate_report(input_path, output_path, mode, config)
            done_msg = (
                "报告生成成功\n"
                f"输出路径:\n{output_path}\n"
                f"分析模式: {'静态目标' if mode == 'static' else f'动态目标({result.get('scene_mode', '')})'}"
            )
            self.status_var.set(done_msg)
            messagebox.showinfo("完成", done_msg)
        except Exception as exc:
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            self.status_var.set(f"生成失败\n{detail}")
            messagebox.showerror("错误", f"生成失败\n{detail}")
        finally:
            self.generate_btn.configure(state=tk.NORMAL)


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

    app = PointCloudAnalysisApp(root)
    _ = app
    root.mainloop()


if __name__ == "__main__":
    main()
