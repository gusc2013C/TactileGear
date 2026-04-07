"""参数精调面板。"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from src.core.types import ProfileParameters


class ParamTuner(ctk.CTkFrame):
    """参数调节滑块面板。"""

    # (参数名, 显示标签, 最小值, 最大值, 步长)
    _SLIDERS = [
        ("max_torque_pct", "全局最大扭矩 (%)", 0, 100, 1),
        ("pull_in_force", "吸入力度 (%)", 0, 100, 1),
        ("neutral_spring_force", "空挡弹簧力度 (%)", 0, 100, 1),
        ("miss_penalty_force", "错挡惩罚力度 (%)", 0, 100, 1),
        ("notch_vibration_magnitude", "段落震动强度 (%)", 0, 100, 1),
        ("handbrake_exponential_factor", "手刹指数因子", 1.0, 10.0, 0.1),
        ("prnd_spring_force", "PRND 弹簧力度 (%)", 0, 100, 1),
        ("prnd_p_pullout_resistance", "P档脱出阻力 (%)", 0, 100, 1),
        ("seq_spring_force", "序列档弹簧力度 (%)", 0, 100, 1),
        ("seq_bump_force", "序列档反弹力 (%)", 0, 100, 1),
        ("seq_shift_debounce_ms", "换挡防抖 (ms)", 50, 500, 10),
    ]

    def __init__(
        self,
        parent,
        params: ProfileParameters,
        on_params_change: Callable[[ProfileParameters], None],
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._params = params
        self._on_params_change = on_params_change
        self._updating = False

        # 标题
        title = ctk.CTkLabel(self, text="参数精调", font=ctk.CTkFont(weight="bold"))
        title.pack(anchor="w", padx=10, pady=(10, 5))

        # 滑块容器（带滚动）
        scroll_frame = ctk.CTkScrollableFrame(self)
        scroll_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self._sliders: dict[str, ctk.CTkSlider] = {}
        self._value_labels: dict[str, ctk.CTkLabel] = {}

        for attr, label, min_val, max_val, step in self._SLIDERS:
            row = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(row, text=label, width=180, anchor="w").pack(side="left", padx=5)

            current_val = getattr(params, attr, 0)

            slider = ctk.CTkSlider(
                row,
                from_=min_val,
                to=max_val,
                number_of_steps=int((max_val - min_val) / step),
                width=200,
                command=lambda val, a=attr: self._on_slider_change(a, val),
            )
            slider.set(current_val)
            slider.pack(side="left", padx=5)

            val_label = ctk.CTkLabel(row, text=f"{current_val:.1f}", width=50)
            val_label.pack(side="left", padx=5)

            self._sliders[attr] = slider
            self._value_labels[attr] = val_label

    def _on_slider_change(self, attr: str, value: float) -> None:
        """滑块值变化回调。"""
        if self._updating:
            return

        # 更新标签
        self._value_labels[attr].configure(text=f"{value:.1f}")

        # 更新参数
        setattr(self._params, attr, value)
        self._on_params_change(self._params)

    def set_params(self, params: ProfileParameters) -> None:
        """外部设置参数（加载配置时）。"""
        self._updating = True
        self._params = params
        for attr, _, _, _, _ in self._SLIDERS:
            if attr in self._sliders:
                val = getattr(params, attr, 0)
                self._sliders[attr].set(val)
                self._value_labels[attr].configure(text=f"{val:.1f}")
        self._updating = False
