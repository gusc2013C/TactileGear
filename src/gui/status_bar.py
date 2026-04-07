"""连接状态面板 — 含设备选择下拉框、刷新/连接按钮、状态指示灯。"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import customtkinter as ctk

logger = logging.getLogger(__name__)


class StatusBar(ctk.CTkFrame):
    """设备连接面板：SDL 设备选择 + 三个服务状态指示灯。"""

    _COLORS = {
        "connected": "#00cc00",
        "disconnected": "#cc0000",
        "connecting": "#cccc00",
        "error": "#cc6600",
    }

    def __init__(
        self,
        parent,
        sdl_device=None,
        on_device_connected: Optional[Callable[[int], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)

        self._sdl = sdl_device
        self._on_device_connected = on_device_connected
        self._connected_index: Optional[int] = None

        # ── 第一行：SDL 设备选择 ──────────────────────────
        device_row = ctk.CTkFrame(self, fg_color="transparent")
        device_row.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(device_row, text="力反馈设备:", font=ctk.CTkFont(weight="bold")).pack(
            side="left", padx=(0, 8)
        )

        self._device_var = ctk.StringVar(value="未检测到设备")
        self._device_combo = ctk.CTkComboBox(
            device_row,
            values=["未检测到设备"],
            variable=self._device_var,
            width=280,
            state="disabled",
        )
        self._device_combo.pack(side="left", padx=(0, 8))

        self._btn_refresh = ctk.CTkButton(
            device_row, text="刷新", width=70, command=self._refresh_devices,
        )
        self._btn_refresh.pack(side="left", padx=(0, 5))

        self._btn_connect = ctk.CTkButton(
            device_row,
            text="连接",
            width=80,
            fg_color="#0078d4",
            command=self._toggle_connection,
        )
        self._btn_connect.pack(side="left")

        # 连接状态文字
        self._device_status = ctk.CTkLabel(
            device_row, text="", text_color="gray",
        )
        self._device_status.pack(side="left", padx=(10, 0))

        # ── 第二行：服务状态指示灯 ──────────────────────
        status_row = ctk.CTkFrame(self, fg_color="transparent")
        status_row.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(status_row, text="服务状态:", font=ctk.CTkFont(weight="bold")).pack(
            side="left", padx=(0, 20)
        )

        self._indicators: dict[str, ctk.CTkLabel] = {}
        for device in ["FFB设备", "vJoy", "SimHub"]:
            frame = ctk.CTkFrame(status_row, fg_color="transparent")
            frame.pack(side="left", padx=10)

            indicator = ctk.CTkLabel(
                frame,
                text="\u25CF",  # 圆点
                text_color=self._COLORS["disconnected"],
                font=ctk.CTkFont(size=20),
            )
            indicator.pack(side="left", padx=(0, 5))

            ctk.CTkLabel(frame, text=device).pack(side="left")

            key = device.lower().replace("设备", "").strip()
            self._indicators[key] = indicator

        # 初始化刷新设备列表
        self._devices: list[dict] = []
        if self._sdl:
            self.after(100, self._refresh_devices)

    def _refresh_devices(self) -> None:
        """刷新 SDL 设备列表。"""
        if not self._sdl:
            self._device_status.configure(text="SDL 未初始化", text_color="orange")
            return

        self._devices = self._sdl.enumerate_joysticks()
        if not self._devices:
            self._device_combo.configure(values=["未检测到设备"], state="disabled")
            self._device_var.set("未检测到设备")
            self._device_status.configure(text=f"未检测到设备", text_color="orange")
            return

        names = [f"[{i}] {d['name']}" for i, d in enumerate(self._devices)]
        self._device_combo.configure(values=names, state="normal")
        self._device_var.set(names[0])
        self._device_status.configure(text=f"检测到 {len(names)} 个设备", text_color="gray")
        logger.info("刷新设备列表: %s", names)

    def _toggle_connection(self) -> None:
        """连接/断开设备。"""
        if self._connected_index is not None:
            # 断开
            self._disconnect_device()
            return

        if not self._sdl or not self._devices:
            self._device_status.configure(text="没有可用设备", text_color="red")
            return

        # 解析选中设备 — 从列表位置获取 instance_id
        selected_text = self._device_var.get()
        try:
            idx_str = selected_text.split("]")[0].replace("[", "")
            display_idx = int(idx_str)
            instance_id = self._devices[display_idx]["instance_id"]
        except (ValueError, IndexError, KeyError):
            self._device_status.configure(text="请选择一个设备", text_color="orange")
            return

        self._device_status.configure(text="正在连接...", text_color=self._COLORS["connecting"])
        self.update_idletasks()

        success = self._sdl.open_joystick(instance_id)
        if success:
            self._connected_index = instance_id
            self._btn_connect.configure(text="断开", fg_color="#cc0000")
            self._device_combo.configure(state="disabled")
            self._btn_refresh.configure(state="disabled")
            self._device_status.configure(
                text=f"已连接: {self._sdl.joystick_name}", text_color=self._COLORS["connected"],
            )
            self.set_status("ffb", True)
            if self._on_device_connected:
                self._on_device_connected(instance_id)
        else:
            self._device_status.configure(text="连接失败", text_color="red")
            self.set_status("ffb", False)

    def _disconnect_device(self) -> None:
        """断开当前设备。"""
        if self._sdl:
            self._sdl.close_joystick()
        self._connected_index = None
        self._btn_connect.configure(text="连接", fg_color="#0078d4")
        self._device_combo.configure(state="normal")
        self._btn_refresh.configure(state="normal")
        self._device_status.configure(text="已断开", text_color="gray")
        self.set_status("ffb", False)

    def set_status(self, device: str, connected: bool) -> None:
        """设置设备连接状态指示灯。"""
        key = device.lower()
        # 兼容旧接口: "moza" -> "ffb"
        if key == "moza":
            key = "ffb"
        if key in self._indicators:
            color = self._COLORS["connected"] if connected else self._COLORS["disconnected"]
            self._indicators[key].configure(text_color=color)
