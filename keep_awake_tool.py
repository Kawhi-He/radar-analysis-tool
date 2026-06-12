"""
Keep Awake Tool
A simple UI tool to prevent Windows from sleeping or locking the screen.

Author: Kawhi.He
"""

import tkinter as tk
from tkinter import ttk
import ctypes
import sys
import threading
import time

# Windows SetThreadExecutionState flags
ES_CONTINUOUS       = 0x80000000
ES_SYSTEM_REQUIRED  = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

# Awake state combination: keep system + display awake continuously
AWAKE_FLAGS = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
# Restore state: release all previous requests
RESTORE_FLAGS = ES_CONTINUOUS


class KeepAwakeApp:
    """
    A GUI application that prevents Windows from entering sleep or locking
    the screen while active. Restores original power state on close.

    Attributes:
        root (tk.Tk): The main application window.
        is_awake (bool): Whether sleep prevention is currently active.
        pulse_thread (threading.Thread): Background thread that periodically
            re-asserts the execution state to ensure the system stays awake.
        _stop_event (threading.Event): Event used to signal the pulse thread to stop.
    """

    def __init__(self, root: tk.Tk):
        """
        Initialize the KeepAwakeApp.

        Parameters:
            root (tk.Tk): The root Tkinter window.
        """
        self.root = root
        self.is_awake = False
        self.pulse_thread = None
        self._stop_event = threading.Event()

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        """Build and configure the main UI layout."""
        self.root.title("防休眠工具")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")

        # Center the window
        win_w, win_h = 340, 220
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - win_w) // 2
        y = (screen_h - win_h) // 2
        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")

        # Title label
        title_label = tk.Label(
            self.root,
            text="防休眠 / 防锁屏工具",
            font=("Microsoft YaHei", 14, "bold"),
            fg="#cdd6f4",
            bg="#1e1e2e",
        )
        title_label.pack(pady=(22, 4))

        # Status indicator frame
        status_frame = tk.Frame(self.root, bg="#1e1e2e")
        status_frame.pack(pady=6)

        self.indicator_canvas = tk.Canvas(
            status_frame, width=16, height=16, bg="#1e1e2e", highlightthickness=0
        )
        self.indicator_canvas.pack(side=tk.LEFT, padx=(0, 8))
        self._dot = self.indicator_canvas.create_oval(2, 2, 14, 14, fill="#585b70", outline="")

        self.status_label = tk.Label(
            status_frame,
            text="当前状态：允许休眠",
            font=("Microsoft YaHei", 10),
            fg="#a6adc8",
            bg="#1e1e2e",
        )
        self.status_label.pack(side=tk.LEFT)

        # Toggle button
        self.toggle_btn = tk.Button(
            self.root,
            text="禁止休眠",
            font=("Microsoft YaHei", 11, "bold"),
            width=14,
            height=1,
            bd=0,
            relief=tk.FLAT,
            cursor="hand2",
            bg="#89b4fa",
            fg="#1e1e2e",
            activebackground="#74c7ec",
            activeforeground="#1e1e2e",
            command=self._toggle,
        )
        self.toggle_btn.pack(pady=18)

        # Hint label
        hint_label = tk.Label(
            self.root,
            text="关闭窗口后自动恢复系统默认电源设置",
            font=("Microsoft YaHei", 8),
            fg="#585b70",
            bg="#1e1e2e",
        )
        hint_label.pack(pady=(0, 12))

    def _set_execution_state(self, flags: int):
        """
        Call Windows SetThreadExecutionState to control sleep/display behavior.

        Parameters:
            flags (int): Combination of ES_* flags.

        Returns:
            int: Previous execution state, or 0 on failure.
        """
        return ctypes.windll.kernel32.SetThreadExecutionState(flags)

    def _pulse_loop(self):
        """
        Background thread: re-asserts awake execution state every 30 seconds.
        This ensures the system does not revert to sleep even after long idle periods.
        """
        while not self._stop_event.is_set():
            if self.is_awake:
                self._set_execution_state(AWAKE_FLAGS)
            self._stop_event.wait(timeout=30)

    def _toggle(self):
        """Toggle between sleep-prevented and normal state."""
        if not self.is_awake:
            result = self._set_execution_state(AWAKE_FLAGS)
            if result == 0:
                self._show_error("SetThreadExecutionState 调用失败，请以管理员权限运行。")
                return
            self.is_awake = True
            # Start pulse thread
            self._stop_event.clear()
            self.pulse_thread = threading.Thread(target=self._pulse_loop, daemon=True)
            self.pulse_thread.start()
            # Update UI
            self.indicator_canvas.itemconfig(self._dot, fill="#a6e3a1")
            self.status_label.config(text="当前状态：已禁止休眠", fg="#a6e3a1")
            self.toggle_btn.config(
                text="恢复休眠",
                bg="#f38ba8",
                fg="#1e1e2e",
                activebackground="#eba0ac",
            )
        else:
            self._restore()
            # Update UI
            self.indicator_canvas.itemconfig(self._dot, fill="#585b70")
            self.status_label.config(text="当前状态：允许休眠", fg="#a6adc8")
            self.toggle_btn.config(
                text="禁止休眠",
                bg="#89b4fa",
                fg="#1e1e2e",
                activebackground="#74c7ec",
            )

    def _restore(self):
        """
        Restore the system to its default power management state,
        allowing sleep and screen lock as configured by the OS.
        """
        self.is_awake = False
        self._stop_event.set()
        self._set_execution_state(RESTORE_FLAGS)

    def _show_error(self, message: str):
        """
        Display an error dialog.

        Parameters:
            message (str): The error message to display.
        """
        from tkinter import messagebox
        messagebox.showerror("错误", message)

    def _on_close(self):
        """Handle window close: restore power state then destroy the window."""
        if self.is_awake:
            self._restore()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = KeepAwakeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
