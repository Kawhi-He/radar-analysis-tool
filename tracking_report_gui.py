#!/usr/bin/env python3
"""
Author: Kawhi.He
Overview:
Desktop GUI for generating a TXT tracking report from frame.txt.

Input Parameters:
- None directly. The user selects the input file, speed, and output file.

Return Values:
- None. The GUI writes a TXT report and shows the content in a preview box.
"""

from __future__ import annotations

import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tracking_report_generator import generate_tracking_report

SPEED_OPTIONS = ["1 m/s", "5 m/s", "10 m/s", "20 m/s", "30 m/s"]


class TrackingReportApp:
    """
    Overview:
    Main GUI application for TXT tracking report generation.

    Input Parameters:
    - root (tk.Tk): Root tkinter window.

    Return Values:
    - TrackingReportApp: Application instance.

    Author: Kawhi.He
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(
            "雷达跟踪 TXT 报告工具 / Radar Tracking TXT Report Tool"
        )
        self.root.geometry("920x680")
        self.root.minsize(860, 620)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.speed_var = tk.StringVar(value=SPEED_OPTIONS[1])
        self.status_var = tk.StringVar(
            value="请先选择 frame.txt 文件 / Please select frame.txt first"
        )

        self.preview_text: tk.Text | None = None

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
            text="雷达跟踪 TXT 报告生成器",
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
            row=1, column=0, sticky=tk.EW, pady=(6, 0)
        )
        ttk.Button(
            file_card,
            text="选择文件 / Browse",
            command=self.select_input,
        ).grid(row=1, column=1, padx=(8, 0), pady=(6, 0))

        ttk.Label(file_card, text="输出 TXT 文件:").grid(
            row=2,
            column=0,
            sticky=tk.W,
            pady=(10, 0),
        )
        ttk.Entry(file_card, textvariable=self.output_var, width=92).grid(
            row=3, column=0, sticky=tk.EW, pady=(6, 0)
        )
        ttk.Button(
            file_card,
            text="另存为 / Save As",
            command=self.select_output,
        ).grid(row=3, column=1, padx=(8, 0), pady=(6, 0))

        file_card.columnconfigure(0, weight=1)

        param_card = ttk.LabelFrame(
            container,
            text="跟踪参数 / Tracking Parameters",
            padding=12,
        )
        param_card.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(param_card, text="速度筛选:").grid(
            row=0, column=0, sticky=tk.W
        )
        speed_combo = ttk.Combobox(
            param_card,
            textvariable=self.speed_var,
            values=SPEED_OPTIONS,
            state="readonly",
            width=12,
        )
        speed_combo.grid(row=0, column=1, sticky=tk.W, padx=(8, 0))
        speed_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._refresh_default_output(),
        )

        action_bar = ttk.Frame(container)
        action_bar.pack(fill=tk.X, pady=(0, 10))

        self.generate_btn = ttk.Button(
            action_bar,
            text="生成 TXT 报告 / Generate TXT Report",
            command=self.generate_report,
        )
        self.generate_btn.pack(anchor=tk.W)

        preview_card = ttk.LabelFrame(
            container,
            text="报告预览 / Report Preview",
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
        self.preview_text.insert(tk.END, "请选择 frame.txt 并点击生成按钮。")
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

    def _refresh_default_output(self) -> None:
        """
        Overview:
        Update the default output path based on the current input file.
        The selected speed is used to build the default filename.

        Input Parameters:
        - None.

        Return Values:
        - None.

        Author: Kawhi.He
        """

        input_text = self.input_var.get().strip()
        if not input_text:
            return

        input_path = Path(input_text)

        speed_token = self.speed_var.get().split()[0]
        default_name = f"{input_path.stem}_{speed_token}mps_report.txt"
        if not self.output_var.get().strip():
            self.output_var.set(str(input_path.with_name(default_name)))

    def select_input(self) -> None:
        """
        Overview:
        Select the source frame.txt file.

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

        input_path = Path(path)
        self.input_var.set(str(input_path))
        self.status_var.set("已选择输入文件 / Input file selected")
        self._refresh_default_output()

    def select_output(self) -> None:
        """
        Overview:
        Select the output TXT file path.

        Input Parameters:
        - None.

        Return Values:
        - None.

        Author: Kawhi.He
        """

        initial = self.output_var.get().strip() or "tracking_report.txt"
        path = filedialog.asksaveasfilename(
            title="保存 TXT 报告 / Save TXT report",
            defaultextension=".txt",
            initialfile=Path(initial).name,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return

        self.output_var.set(path)
        self.status_var.set("已选择输出路径 / Output path selected")

    def _write_preview(self, report_text: str) -> None:
        """
        Overview:
        Render the generated report into the preview text box.

        Input Parameters:
        - report_text (str): Generated report text.

        Return Values:
        - None.

        Author: Kawhi.He
        """

        if self.preview_text is None:
            return

        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert(tk.END, report_text)
        self.preview_text.configure(state=tk.DISABLED)

    def generate_report(self) -> None:
        """
        Overview:
        Validate inputs and generate the TXT report.

        Input Parameters:
        - None.

        Return Values:
        - None.

        Author: Kawhi.He
        """

        raw_input = self.input_var.get().strip()
        raw_output = self.output_var.get().strip()
        speed_text = self.speed_var.get().strip()

        if not raw_input:
            messagebox.showwarning(
                "提示 / Notice",
                "请先选择 frame.txt 文件\nPlease select a frame.txt file first.",
            )
            return
        if not raw_output:
            messagebox.showwarning(
                "提示 / Notice",
                "请先选择输出 TXT 文件\nPlease select an output TXT file first.",
            )
            return

        input_path = Path(raw_input)
        output_path = Path(raw_output)

        if not input_path.exists():
            messagebox.showerror(
                "错误 / Error",
                f"输入文件不存在 / Input file does not exist:\n{input_path}",
            )
            return

        try:
            target_speed_mps = float(speed_text.split()[0])
        except (IndexError, ValueError):
            messagebox.showerror(
                "错误 / Error",
                f"速度格式错误 / Invalid speed value:\n{speed_text}",
            )
            return

        self.generate_btn.configure(state=tk.DISABLED)
        self.status_var.set(
            "正在生成报告，请稍候... / Generating report, please wait..."
        )
        self.root.update_idletasks()

        try:
            report_text = generate_tracking_report(
                input_path,
                output_path,
                target_speed_mps,
            )
            self._write_preview(report_text)
            done_msg = (
                "报告生成成功 / Report generated successfully\n"
                f"输出路径 / Output path:\n{output_path}"
            )
            self.status_var.set(done_msg)
            messagebox.showinfo("完成 / Done", done_msg)
        except (OSError, ValueError, UnicodeError) as exc:
            detail = "".join(
                traceback.format_exception_only(type(exc), exc)
            ).strip()
            self.status_var.set(
                f"生成失败 / Failed to generate report\n{detail}"
            )
            messagebox.showerror(
                "错误 / Error",
                f"报告生成失败 / Failed to generate report\n{detail}",
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

    Author: Kawhi.He
    """

    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass

    app = TrackingReportApp(root)
    _ = app
    root.mainloop()


if __name__ == "__main__":
    main()
