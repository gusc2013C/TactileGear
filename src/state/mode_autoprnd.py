"""自动挡 PRND 模式控制器。"""

from __future__ import annotations

import time
from typing import Any, Optional

from src.core.types import (
    BTN_D,
    BTN_N_PRND,
    BTN_P,
    BTN_R_PRND,
    BTN_S,
    ForceType,
    GatePosition,
    Gear,
    ModeUpdateResult,
    ProfileParameters,
    SDL_HAPTIC_INFINITY,
)
from src.physics.force_curves import prnd_detent_curve, scale_to_sdl_range
from src.physics.force_types import ForceRequest, VJoyAction
from src.state.mode_base import ModeController


# PRND 档位驻点位置 (Y 轴，从上到下)
_PRND_POSITIONS = {
    Gear.P: 0.1,
    Gear.R: 0.3,
    Gear.NEUTRAL: 0.5,
    Gear.DRV: 0.7,
    Gear.S: 0.9,
}

# 档位到按钮映射
_PRND_BUTTONS = {
    Gear.P: BTN_P,
    Gear.R: BTN_R_PRND,
    Gear.NEUTRAL: BTN_N_PRND,
    Gear.DRV: BTN_D,
    Gear.S: BTN_S,
}


class AutoPRNDController(ModeController):
    """民用自动挡 PRND 模式。

    - X 轴锁死居中
    - Y 轴分配 P/R/N/D/S 驻点
    - 多段限位器制造段落感
    - P 档最高脱出阻力
    """

    def __init__(self, params: ProfileParameters) -> None:
        super().__init__(params)
        self._last_active_gear: Optional[Gear] = None

    def enter(self) -> list[Any]:
        """进入自动挡模式。"""
        self._current_gear = Gear.P
        self._last_active_gear = None
        return []

    def exit(self) -> list[Any]:
        """退出自动挡模式，释放所有 PRND 按钮。"""
        actions = []
        for gear, btn in _PRND_BUTTONS.items():
            actions.append(VJoyAction.release(btn))
        return actions

    def update(
        self,
        position: GatePosition,
        modifier_pressed: bool,
        clutch_position: float,
        dt: float,
    ) -> ModeUpdateResult:
        # 检测当前驻点
        detected_gear = self._detect_gear(position.y)

        vjoy_actions = []
        force_requests = []

        if detected_gear != self._last_active_gear:
            # 释放旧按钮
            if self._last_active_gear and self._last_active_gear in _PRND_BUTTONS:
                vjoy_actions.append(
                    VJoyAction.release(_PRND_BUTTONS[self._last_active_gear])
                )

            # 检查 P 档脱出是否需要额外力
            if self._last_active_gear == Gear.P and detected_gear != Gear.P:
                # P 档脱出逻辑：通过棘爪模拟，由 FFB 力来实现
                pass

            # 按下新按钮
            if detected_gear and detected_gear in _PRND_BUTTONS:
                vjoy_actions.append(
                    VJoyAction.press(_PRND_BUTTONS[detected_gear])
                )

            self._last_active_gear = detected_gear
            if detected_gear:
                self._current_gear = detected_gear

        # PRND 棘爪力
        detent_positions = list(_PRND_POSITIONS.values())
        resistance = prnd_detent_curve(
            position.y,
            detent_positions,
            detent_force=self._params.prnd_spring_force / 100.0,
        )
        force_level = scale_to_sdl_range(resistance)

        # P 档额外驻车棘爪力
        if detected_gear == Gear.P or (
            self._last_active_gear == Gear.P and position.y < 0.2
        ):
            p_extra = scale_to_sdl_range(
                self._params.prnd_p_pullout_resistance / 100.0
            )
            force_level = max(force_level, p_extra)

        if force_level > 100:
            force_requests.append(ForceRequest(
                name="prnd_detent_spring",
                force_type=ForceType.SPRING,
                axis=1,
                spring_center=0,
                spring_coefficient=force_level,
                spring_deadband=500,  # 小死区
                duration_ms=SDL_HAPTIC_INFINITY,
                gain=self._params.max_torque_pct / 100.0,
            ))

        # X 轴锁定弹簧
        force_requests.append(ForceRequest(
            name="prnd_x_lock",
            force_type=ForceType.SPRING,
            axis=0,
            spring_center=0,
            spring_coefficient=0x7FFF,
            spring_deadband=500,
            duration_ms=SDL_HAPTIC_INFINITY,
            gain=self._params.max_torque_pct / 100.0,
        ))

        gear_changed = detected_gear != self._last_active_gear
        return ModeUpdateResult(
            vjoy_actions=vjoy_actions,
            force_requests=force_requests,
            gear_changed=gear_changed,
            new_gear=detected_gear,
        )

    def _detect_gear(self, y: float) -> Optional[Gear]:
        """根据 Y 轴位置判断当前档位。"""
        best_gear = None
        best_dist = float("inf")

        for gear, pos_y in _PRND_POSITIONS.items():
            dist = abs(y - pos_y)
            if dist < 0.08 and dist < best_dist:  # 驻点容差
                best_dist = dist
                best_gear = gear

        return best_gear
