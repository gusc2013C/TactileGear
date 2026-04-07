"""力请求和 vJoy 动作的数据类。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from src.core.types import ForceType, SDL_HAPTIC_INFINITY


@dataclass
class ForceRequest:
    """描述一个 FFB 效果的意图，不包含 SDL 结构体。"""
    name: str  # 语义名称，用于 diff (如 "centering_spring", "brick_wall_R")
    force_type: ForceType
    axis: int  # 0=X, 1=Y
    # Constant force
    level: int = 0  # -32768 ~ 32767
    direction: int = 0  # 0° 或 180°
    # Spring / Damper
    spring_center: int = 0  # -32768 ~ 32767
    spring_coefficient: int = 0  # 正系数
    spring_deadband: int = 0
    spring_saturation: int = 0xFFFF
    # Periodic (square/sine)
    periodic_magnitude: int = 0  # 0 ~ 32767
    periodic_period: int = 1000  # 微秒
    # 通用
    duration_ms: int = SDL_HAPTIC_INFINITY
    attack_level: int = 0
    attack_length: int = 0
    fade_level: int = 0
    fade_length: int = 0
    # 乘数 (应用 max_torque_pct)
    gain: float = 1.0  # 0.0 ~ 1.0


@dataclass
class VJoyAction:
    """描述一个 vJoy 操作。"""
    action_type: str  # "press_button", "release_button", "set_axis"
    button: Optional[int] = None
    axis: Optional[Union[int, str]] = None  # 轴名 ("X","RY"...) 或 HID_USAGE
    value: Optional[int] = None  # 轴值 0~32768 或按钮状态

    @staticmethod
    def press(button: int) -> VJoyAction:
        return VJoyAction(action_type="press_button", button=button)

    @staticmethod
    def release(button: int) -> VJoyAction:
        return VJoyAction(action_type="release_button", button=button)

    @staticmethod
    def set_axis(axis: Union[int, str], value: int) -> VJoyAction:
        return VJoyAction(action_type="set_axis", axis=axis, value=value)
