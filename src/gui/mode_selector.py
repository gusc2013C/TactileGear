"""模式选择面板。"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from src.core.types import GearMode


class ModeSelector(ctk.CTkFrame):
    """四大工作模式选择器。"""

    _MODES = [
        (GearMode.HPATTERN, "H 档"),
        (GearMode.SEQUENTIAL, "序列档"),
        (GearMode.HANDBRAKE, "手刹"),
        (GearMode.AUTO_PRND, "自动挡"),
    ]

    def __init__(
        self,
        parent,
        on_mode_change: Callable[[GearMode], None],
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_mode_change = on_mode_change
        self._current_mode = GearMode.HPATTERN

        # 标题
        title = ctk.CTkLabel(self, text="工作模式", font=ctk.CTkFont(weight="bold"))
        title.pack(side="left", padx=(10, 20))

        # 模式按钮
        self._buttons: dict[GearMode, ctk.CTkButton] = {}
        for mode, label in self._MODES:
            btn = ctk.CTkButton(
                self,
                text=label,
                width=100,
                command=lambda m=mode: self._select_mode(m),
                fg_color=("#3a7ebf" if mode == self._current_mode else "gray"),
            )
            btn.pack(side="left", padx=5, pady=5)
            self._buttons[mode] = btn

    def _select_mode(self, mode: GearMode) -> None:
        """选择模式。"""
        self._current_mode = mode

        # 更新按钮颜色
        for m, btn in self._buttons.items():
            if m == mode:
                btn.configure(fg_color="#3a7ebf")
            else:
                btn.configure(fg_color="gray")

        self._on_mode_change(mode)

    def set_mode(self, mode: GearMode) -> None:
        """外部设置当前模式。"""
        self._select_mode(mode)
