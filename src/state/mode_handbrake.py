"""手刹模式控制器。"""

from __future__ import annotations

from typing import Any

from src.core.types import (
    ForceType,
    GatePosition,
    Gear,
    ModeUpdateResult,
    ProfileParameters,
    SDL_HAPTIC_INFINITY,
    VJOY_AXIS_MAX,
    VJOY_AXIS_MIN,
)
from src.physics.force_curves import exponential_resistance, scale_to_sdl_range
from src.physics.force_types import ForceRequest, VJoyAction
from src.state.mode_base import ModeController


class HandbrakeController(ModeController):
    """液压力反馈手刹模式。

    - Y轴拉向后 → vJoy RY 轴输出 0~32767
    - 施加指数级递增反向阻力
    """

    def __init__(self, params: ProfileParameters) -> None:
        super().__init__(params)
        self._last_ry_value = VJOY_AXIS_MIN

    def enter(self) -> list[Any]:
        self._current_gear = Gear.NEUTRAL
        self._last_ry_value = VJOY_AXIS_MIN
        return [
            VJoyAction.set_axis("RY", VJOY_AXIS_MIN),
        ]

    def exit(self) -> list[Any]:
        return [
            VJoyAction.set_axis("RY", VJOY_AXIS_MIN),
        ]

    def update(
        self,
        position: GatePosition,
        modifier_pressed: bool,
        clutch_position: float,
        dt: float,
    ) -> ModeUpdateResult:
        # Y 轴位移: 0.5 = 居中, 1.0 = 完全拉回
        # 只取 Y > 0.5 的部分作为手刹行程
        displacement = max(0.0, position.y - 0.5) * 2.0  # 归一化到 0~1
        displacement = min(displacement, 1.0)

        # 映射到 vJoy RY 轴
        ry_value = int(VJOY_AXIS_MIN + displacement * (VJOY_AXIS_MAX - VJOY_AXIS_MIN))

        # 计算指数阻力
        resistance = exponential_resistance(
            displacement,
            self._params.handbrake_exponential_factor,
        )
        force_level = scale_to_sdl_range(
            resistance * (self._params.handbrake_max_resistance / 100.0)
        )

        vjoy_actions = []
        if ry_value != self._last_ry_value:
            vjoy_actions.append(VJoyAction.set_axis("RY", ry_value))
            self._last_ry_value = ry_value

        # 恒定力：反方向阻力
        force_requests = []
        if force_level > 100:  # 阈值过滤噪声
            force_requests.append(ForceRequest(
                name="handbrake_resistance",
                force_type=ForceType.CONSTANT,
                axis=1,
                level=-force_level,  # 反方向
                direction=180,
                duration_ms=SDL_HAPTIC_INFINITY,
                gain=self._params.max_torque_pct / 100.0,
            ))

        return ModeUpdateResult(
            vjoy_actions=vjoy_actions,
            force_requests=force_requests,
        )
