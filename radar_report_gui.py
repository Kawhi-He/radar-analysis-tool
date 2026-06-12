#!/usr/bin/env python3
"""
Author: Kawhi.He
Overview:
Desktop GUI for generating radar HTML test report from a selected frame.txt file.

Input Parameters:
- None directly. User selects the input file and output path via GUI controls.

Return Values:
- None. The GUI generates the report file and shows status messages.
"""

from __future__ import annotations

import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from generate_radar_report import analyze_cycles, parse_frames, render_html


class RadarReportApp:
    """
    Overview:
    Main GUI application for report generation.

    Input Parameters:
    - root (tk.Tk): Root tkinter window.

    Return Values:
    - RadarReportApp: Application instance.
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("毫米波雷达测试报告工具 / Radar Report Tool")
        self.root.geometry("760x360")
        self.root.minsize(720, 320)

        self.input_var = tk.StringVar()
        self.status_var = tk.StringVar(value="请先选择 frame.txt 文件 / Please select frame.txt first")

        self._build_ui()

    def _build_ui(self) -> None:
        """
        Overview:
        Build and layout all UI widgets.

        Input Parameters:
        - None.

        Return Values:
        - None.
        """

        container = ttk.Frame(self.root, padding=18)
        container.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(
            container,
            text="毫米波雷达测试报告生成器 / Millimeter-Wave Radar Report Generator",
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        title.pack(anchor=tk.W, pady=(0, 12))

        file_card = ttk.LabelFrame(
            container,
            text="文件配置 / File Configuration",
            padding=12,
        )
        file_card.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(file_card, text="输入数据文件 / Input frame file:").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 8), pady=6
        )
        ttk.Entry(file_card, textvariable=self.input_var, width=78).grid(
            row=1, column=0, sticky=tk.EW, pady=2
        )
        ttk.Button(file_card, text="选择文件 / Browse", command=self.select_input).grid(
            row=1, column=1, padx=(8, 0), pady=2
        )

        file_card.columnconfigure(0, weight=1)

        action_bar = ttk.Frame(container)
        action_bar.pack(fill=tk.X, pady=(4, 10))

        self.generate_btn = ttk.Button(
            action_bar,
            text="生成测试报告 / Generate Test Report",
            command=self.generate_report,
        )
        self.generate_btn.pack(anchor=tk.W)

        status_card = ttk.LabelFrame(
            container,
            text="执行状态 / Status",
            padding=12,
        )
        status_card.pack(fill=tk.BOTH, expand=True)

        status_label = ttk.Label(
            status_card,
            textvariable=self.status_var,
            justify=tk.LEFT,
            wraplength=690,
        )
        status_label.pack(anchor=tk.W)

    def select_input(self) -> None:
        """
        Overview:
        Select input frame text file.

        Input Parameters:
        - None.

        Return Values:
        - None.
        """

        path = filedialog.askopenfilename(
            title="选择 frame.txt / Select frame file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return

        in_path = Path(path)
        self.input_var.set(str(in_path))
        self.status_var.set("已选择输入文件 / Input file selected")

    def generate_report(self) -> None:
        """
        Overview:
        Generate report by calling analysis functions.

        Input Parameters:
        - None.

        Return Values:
        - None.
        """

        input_text = self.input_var.get().strip()

        if not input_text:
            messagebox.showwarning(
                "提示 / Notice",
                "请先选择 frame.txt 文件\nPlease select frame.txt first.",
            )
            return

        input_path = Path(input_text)
        output_path = input_path.with_name("report.html")

        if not input_path.exists():
            messagebox.showerror(
                "错误 / Error",
                f"输入文件不存在 / Input file does not exist:\n{input_path}",
            )
            return

        self.generate_btn.configure(state=tk.DISABLED)
        self.status_var.set("正在生成报告，请稍候... / Generating report, please wait...")
        self.root.update_idletasks()

        try:
            text = input_path.read_text(encoding="utf-8")
            frames = parse_frames(text)
            result = analyze_cycles(frames)
            result["_frame_lookup"] = frames
            html_text = render_html(result, input_path.name)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(html_text, encoding="utf-8")

            done_msg = (
                "报告生成成功 / Report generated successfully\n"
                f"报告路径 / Report path:\n{output_path}"
            )
            self.status_var.set(done_msg)
            messagebox.showinfo("完成 / Done", done_msg)
        except Exception as exc:
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            self.status_var.set(
                "生成失败 / Failed to generate report\n"
                f"{detail}"
            )
            messagebox.showerror(
                "错误 / Error",
                "报告生成失败 / Failed to generate report\n"
                f"{detail}",
            )
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
    """

    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass

    app = RadarReportApp(root)
    _ = app
    root.mainloop()


if __name__ == "__main__":
    main()
