"""连接状态指示栏。"""

from __future__ import annotations

import customtkinter as ctk


class StatusBar(ctk.CTkFrame):
    """显示 Moza/vJoy/SimHub 连接状态的指示灯栏。"""

    # 颜色映射
    _COLORS = {
        "connected": "#00cc00",
        "disconnected": "#cc0000",
        "connecting": "#cccc00",
        "error": "#cc6600",
    }

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, **kwargs)

        self._indicators: dict[str, ctk.CTkLabel] = {}

        # 标题
        title = ctk.CTkLabel(self, text="连接状态", font=ctk.CTkFont(weight="bold"))
        title.pack(side="left", padx=(10, 20))

        # 三个设备状态
        for device in ["Moza", "vJoy", "SimHub"]:
            frame = ctk.CTkFrame(self, fg_color="transparent")
            frame.pack(side="left", padx=10)

            indicator = ctk.CTkLabel(
                frame,
                text="\u25CF",  # 圆点
                text_color=self._COLORS["disconnected"],
                font=ctk.CTkFont(size=20),
            )
            indicator.pack(side="left", padx=(0, 5))

            label = ctk.CTkLabel(frame, text=device)
            label.pack(side="left")

            self._indicators[device.lower()] = indicator

        # 初始化所有为断开
        for key in self._indicators:
            self.set_status(key, False)

    def set_status(self, device: str, connected: bool) -> None:
        """设置设备连接状态。"""
        key = device.lower()
        if key in self._indicators:
            color = self._COLORS["connected"] if connected else self._COLORS["disconnected"]
            self._indicators[key].configure(text_color=color)
