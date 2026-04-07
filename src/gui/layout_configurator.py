"""排布配置面板。"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from src.core.types import LayoutID


class LayoutConfigurator(ctk.CTkFrame):
    """H 档排布选择器和倒档解锁方式配置。"""

    _LAYOUTS = {
        LayoutID.CIVILIAN_6R_LEFT: "民用 6+R (左上倒档)",
        LayoutID.CIVILIAN_6R_RIGHT: "民用 6+R (右下倒档)",
        LayoutID.PORSCHE_7R: "保时捷 7+R",
        LayoutID.TRUCK_18: "卡车 18速",
    }

    _UNLOCK_METHODS = {
        "modifier_key": "提环/按键解锁",
        "gravity_breakthrough": "重力突破",
    }

    def __init__(
        self,
        parent,
        on_layout_change: Callable[[str], None],
        on_unlock_method_change: Callable[[str], None],
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_layout_change = on_layout_change
        self._on_unlock_method_change = on_unlock_method_change

        # 标题
        title = ctk.CTkLabel(self, text="排布配置", font=ctk.CTkFont(weight="bold"))
        title.pack(anchor="w", padx=10, pady=(10, 5))

        # 排布选择
        layout_frame = ctk.CTkFrame(self, fg_color="transparent")
        layout_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(layout_frame, text="排布阵型:").pack(side="left", padx=(0, 10))

        self._layout_var = ctk.StringVar(value=LayoutID.CIVILIAN_6R_LEFT.value)
        layout_names = {v: lid.value for lid, v in self._LAYOUTS.items()}
        # 用 display name 显示
        display_values = [f"{lid.value}" for lid in self._LAYOUTS.keys()]

        self._layout_combo = ctk.CTkComboBox(
            layout_frame,
            values=[lid.value for lid in self._LAYOUTS.keys()],
            variable=self._layout_var,
            command=self._on_layout_selected,
            width=250,
        )
        self._layout_combo.pack(side="left")

        # 倒档解锁方式
        unlock_frame = ctk.CTkFrame(self, fg_color="transparent")
        unlock_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(unlock_frame, text="倒档解锁:").pack(side="left", padx=(0, 10))

        self._unlock_var = ctk.StringVar(value="gravity_breakthrough")
        self._unlock_combo = ctk.CTkComboBox(
            unlock_frame,
            values=list(self._UNLOCK_METHODS.keys()),
            variable=self._unlock_var,
            command=self._on_unlock_selected,
            width=200,
        )
        self._unlock_combo.pack(side="left")

        # 排布预览 (简单文本)
        self._preview_label = ctk.CTkLabel(
            self,
            text=self._get_layout_preview(LayoutID.CIVILIAN_6R_LEFT),
            font=ctk.CTkFont(family="Courier", size=11),
            justify="left",
        )
        self._preview_label.pack(anchor="w", padx=10, pady=10)

    def _on_layout_selected(self, value: str) -> None:
        self._on_layout_change(value)
        try:
            lid = LayoutID(value)
            self._preview_label.configure(text=self._get_layout_preview(lid))
        except ValueError:
            pass

    def _on_unlock_selected(self, value: str) -> None:
        self._on_unlock_method_change(value)

    def set_visible(self, visible: bool) -> None:
        """设置面板可见性。"""
        if visible:
            self.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        else:
            self.pack_forget()

    @staticmethod
    def _get_layout_preview(layout_id: LayoutID) -> str:
        """返回排布的 ASCII 预览。"""
        previews = {
            LayoutID.CIVILIAN_6R_LEFT:
                "  R - 1 - 3 - 5\n"
                "  |   |   |   |\n"
                "  N - 2 - 4 - 6",
            LayoutID.CIVILIAN_6R_RIGHT:
                "  1 - 3 - 5\n"
                "  |   |   |\n"
                "  2 - 4 - 6 - R",
            LayoutID.PORSCHE_7R:
                "  R - 1 - 3 - 5 - 7\n"
                "  |   |   |   |   |\n"
                "  N - 2 - 4 - 6 - N",
            LayoutID.TRUCK_18:
                "  1 - 3 - 5\n"
                "  |   |   |\n"
                "  2 - 4 - 6\n"
                "  [Range] [Splitter]",
        }
        return previews.get(layout_id, "")
