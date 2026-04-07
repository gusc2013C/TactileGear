"""设备选择对话框。启动时弹出，让用户选择 FFB 摇杆设备。"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk


class DeviceSelectDialog(ctk.CTkToplevel):
    """设备选择对话框，列出所有 SDL 摇杆供用户选择。"""

    def __init__(self, parent, devices: list[dict]) -> None:
        super().__init__(parent)
        self.title("选择力反馈设备")
        self.geometry("420x320")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._selected_index: Optional[int] = None
        self._devices = devices

        # 标题
        ctk.CTkLabel(
            self,
            text="检测到以下摇杆设备",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            self,
            text="请选择你的力反馈底座（如 MOZA AB6）",
            text_color="gray",
        ).pack(pady=(0, 10))

        # 设备列表
        if not devices:
            ctk.CTkLabel(
                self,
                text="未检测到任何摇杆设备！\n请确认设备已连接并安装驱动。",
                text_color="red",
            ).pack(pady=20)
            ctk.CTkButton(
                self, text="退出", command=self._on_skip,
            ).pack(pady=10)
            return

        self._list_frame = ctk.CTkScrollableFrame(self, height=180)
        self._list_frame.pack(fill="both", expand=True, padx=20, pady=5)

        for dev in devices:
            btn_text = f"[{dev['index']}] {dev['name']}"
            btn = ctk.CTkButton(
                self._list_frame,
                text=btn_text,
                anchor="w",
                command=lambda idx=dev["index"]: self._on_select(idx),
            )
            btn.pack(fill="x", pady=2)

        # 跳过按钮
        ctk.CTkButton(
            self,
            text="跳过（不使用力反馈设备）",
            fg_color="gray",
            command=self._on_skip,
        ).pack(pady=(5, 15))

        # 居中显示
        self.after(50, self._center_on_parent, parent)

    def _center_on_parent(self, parent) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _on_select(self, index: int) -> None:
        self._selected_index = index
        self.grab_release()
        self.destroy()

    def _on_skip(self) -> None:
        self._selected_index = None
        self.grab_release()
        self.destroy()

    @property
    def selected_index(self) -> Optional[int]:
        return self._selected_index
