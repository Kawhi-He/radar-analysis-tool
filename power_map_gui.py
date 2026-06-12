#!/usr/bin/env python3
"""
Author: Kawhi.He
Overview:
Windows GUI tool for generating radar detection power maps
from imported folders. After selecting a folder, the tool
automatically detects dataset roots and saves an output
power-map image into the selected folder.

Input Parameters:
- None directly. User selects input folder via GUI.

Return Values:
- None. The GUI generates a PNG file in the selected folder.
"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from plot_radar_detection_power import (
    build_runtime_args,
    collect_series,
    draw_plot,
)


def is_dataset_root(folder: Path) -> bool:
    """
    Overview:
    Check whether a folder looks like one effect-range dataset root.

    Input Parameters:
    - folder (Path): Folder to verify.

    Return Values:
    - bool: True if it has numeric scene subfolders with frame.txt files.
    """

    if not folder.is_dir():
        return False

    numeric_subdirs = [
        p for p in folder.iterdir() if p.is_dir() and _is_integer_text(p.name)
    ]
    if not numeric_subdirs:
        return False

    return any((sub / "frame.txt").exists() for sub in numeric_subdirs)


def _is_integer_text(text: str) -> bool:
    """
    Overview:
    Check whether text is an integer string.

    Input Parameters:
    - text (str): Input text.

    Return Values:
    - bool: True when input is integer-like.
    """

    if not text:
        return False

    if text.startswith("-"):
        return text[1:].isdigit()
    return text.isdigit()


def find_dataset_roots(selected_folder: Path) -> list[Path]:
    """
    Overview:
    Find dataset roots from the selected folder.

    Input Parameters:
    - selected_folder (Path): User-selected directory.

    Return Values:
    - list[Path]: Detected dataset root folders.
    """

    if is_dataset_root(selected_folder):
        return [selected_folder]

    roots = [p for p in selected_folder.iterdir() if is_dataset_root(p)]
    roots.sort(key=lambda item: item.name)
    return roots


class PowerMapGui:
    """
    Overview:
    Main GUI application for generating radar power-map images.

    Input Parameters:
    - root (tk.Tk): Tk root window.

    Return Values:
    - PowerMapGui: Application instance.
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("威力图辅助生成工具")
        self.root.geometry("760x430")
        self.root.minsize(720, 380)

        self.folder_var = tk.StringVar()
        self.target_dbm_var = tk.StringVar(value="10")
        self.target_speed_var = tk.StringVar(value="10")
        self.speed_tol_var = tk.StringVar(value="+-0.3")
        self.status_var = tk.StringVar(
            value="请选择要导入的文件夹 / Please select an input folder"
        )

        self._build_ui()

    def _build_ui(self) -> None:
        """
        Overview:
        Build GUI widgets and layout.

        Input Parameters:
        - None.

        Return Values:
        - None.
        """

        container = ttk.Frame(self.root, padding=18)
        container.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(
            container,
            text="威力图辅助生成工具 / Power-Map Assistant",
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        title.pack(anchor=tk.W, pady=(0, 12))

        folder_card = ttk.LabelFrame(
            container,
            text="文件夹配置 / Folder Configuration",
            padding=12,
        )
        folder_card.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(folder_card, text="导入文件夹 / Imported folder:").grid(
            row=0,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
            pady=6,
        )
        ttk.Entry(folder_card, textvariable=self.folder_var, width=78).grid(
            row=1,
            column=0,
            sticky=tk.EW,
            pady=2,
        )
        ttk.Button(
            folder_card,
            text="选择文件夹 / Browse",
            command=self.select_folder,
        ).grid(
            row=1,
            column=1,
            padx=(8, 0),
            pady=2,
        )

        ttk.Label(folder_card, text="目标功率 / Target power (dBm):").grid(
            row=2,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
            pady=(10, 4),
        )
        ttk.Combobox(
            folder_card,
            textvariable=self.target_dbm_var,
            values=["0", "5", "10"],
            state="readonly",
            width=18,
        ).grid(
            row=3,
            column=0,
            sticky=tk.W,
            pady=2,
        )

        ttk.Label(folder_card, text="目标速度 / Target speed (m/s):").grid(
            row=2,
            column=1,
            sticky=tk.W,
            padx=(8, 0),
            pady=(10, 4),
        )
        ttk.Combobox(
            folder_card,
            textvariable=self.target_speed_var,
            values=["1", "5", "10", "20"],
            state="readonly",
            width=18,
        ).grid(
            row=3,
            column=1,
            sticky=tk.W,
            padx=(8, 0),
            pady=2,
        )

        ttk.Label(folder_card, text="速度容差 / Speed tolerance (m/s):").grid(
            row=4,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
            pady=(10, 4),
        )
        ttk.Combobox(
            folder_card,
            textvariable=self.speed_tol_var,
            values=["+-0.1", "+-0.2", "+-0.3", "+-0.4"],
            state="readonly",
            width=18,
        ).grid(
            row=5,
            column=0,
            sticky=tk.W,
            pady=2,
        )

        folder_card.columnconfigure(0, weight=1)

        action_bar = ttk.Frame(container)
        action_bar.pack(fill=tk.X, pady=(4, 10))

        self.generate_btn = ttk.Button(
            action_bar,
            text="生成威力图 / Generate Power Map",
            command=self.generate_power_map,
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

    def select_folder(self) -> None:
        """
        Overview:
        Select imported folder from dialog.

        Input Parameters:
        - None.

        Return Values:
        - None.
        """

        selected = filedialog.askdirectory(
            title="选择导入文件夹 / Select input folder"
        )
        if not selected:
            return

        folder = Path(selected)
        self.folder_var.set(str(folder))
        self.status_var.set("已选择文件夹 / Folder selected")

    def generate_power_map(self) -> None:
        """
        Overview:
        Detect datasets and generate one combined power-map image.

        Input Parameters:
        - None.

        Return Values:
        - None.
        """

        folder_text = self.folder_var.get().strip()
        if not folder_text:
            messagebox.showwarning(
                "提示 / Notice",
                "请先选择导入文件夹\nPlease select an input folder first.",
            )
            return

        selected_folder = Path(folder_text)
        if not selected_folder.exists() or not selected_folder.is_dir():
            messagebox.showerror(
                "错误 / Error",
                f"文件夹不存在 / Folder does not exist:\n{selected_folder}",
            )
            return

        try:
            target_dbm = int(self.target_dbm_var.get().strip())
            target_speed = float(self.target_speed_var.get().strip())
            speed_tol_text = self.speed_tol_var.get().strip()
            speed_tol = float(speed_tol_text.replace("+-", ""))
        except ValueError:
            messagebox.showerror(
                "错误 / Error",
                "目标功率、目标速度或速度容差格式无效。",
            )
            return

        dataset_roots = find_dataset_roots(selected_folder)
        if not dataset_roots:
            messagebox.showerror(
                "错误 / Error",
                "未识别到可用数据集目录。\n"
                "请导入包含角度子目录（-40~40 等）和 frame.txt 的目录。",
            )
            return

        self.generate_btn.configure(state=tk.DISABLED)
        self.status_var.set("正在生成威力图，请稍候... / Generating power map...")
        self.root.update_idletasks()

        try:
            runtime_args = build_runtime_args(
                speed_target_mps=target_speed,
                speed_tol_mps=speed_tol,
                target_dbm=target_dbm,
            )
            series_map = {}

            for root in dataset_roots:
                x, y = collect_series(root, runtime_args)
                if x.size > 0:
                    series_map[root.name] = (x, y)

            if not series_map:
                messagebox.showerror(
                    "错误 / Error",
                    (
                        "识别到数据集目录，但未提取到"
                        f"{target_speed:.1f}m/s±{speed_tol:.1f}m/s附近的有效点云。"
                    ),
                )
                self.status_var.set(
                    "未生成图像：未提取到有效数据 / No valid data extracted"
                )
                return

            output_path = selected_folder / "radar_detection_power_map.png"
            plot_kwargs = {
                "speed_target_mps": target_speed,
                "speed_tol_mps": speed_tol,
                "target_dbm": target_dbm,
            }
            draw_plot(
                series_map,
                output_path=output_path,
                dpi=220,
                **plot_kwargs,
            )

            done_msg = (
                "威力图生成成功 / Power map generated successfully\n"
                f"输出路径 / Output path:\n{output_path}"
            )
            self.status_var.set(done_msg)
            messagebox.showinfo("完成 / Done", done_msg)
        except (OSError, ValueError, RuntimeError, tk.TclError) as exc:
            detail = f"{type(exc).__name__}: {exc}"
            fail_msg = f"生成失败 / Failed to generate\n{detail}"
            self.status_var.set(fail_msg)
            messagebox.showerror("错误 / Error", fail_msg)
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

    app = PowerMapGui(root)
    _ = app
    root.mainloop()


if __name__ == "__main__":
    main()
