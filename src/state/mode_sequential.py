"""序列档模式控制器。"""

from __future__ import annotations

import time
from typing import Any

from src.core.types import (
    BTN_SEQ_DOWN,
    BTN_SEQ_UP,
    ForceType,
    GatePosition,
    Gear,
    ModeUpdateResult,
    ProfileParameters,
    SDL_HAPTIC_INFINITY,
    VJOY_AXIS_CENTER,
)
from src.physics.force_types import ForceRequest, VJoyAction
from src.state.mode_base import ModeController


class SequentialController(ModeController):
    """拉力序列档模式。

    - X 轴 100% 弹簧死锁
    - Y 轴重弹簧居中，上下行程触发升/降档
    - 越过阈值时触发按钮脉冲 + 高频震动 + 触底反弹
    """

    def __init__(self, params: ProfileParameters) -> None:
        super().__init__(params)
        self._last_shift_time = 0.0
        self._current_y_zone = 0  # -1=降档区, 0=中间, 1=升档区

    def enter(self) -> list[Any]:
        """进入序列档模式。"""
        self._current_gear = Gear.NEUTRAL
        self._current_y_zone = 0
        return []

    def exit(self) -> list[Any]:
        """退出序列档模式。"""
        return [
            VJoyAction.release(BTN_SEQ_UP),
            VJoyAction.release(BTN_SEQ_DOWN),
        ]

    def update(
        self,
        position: GatePosition,
        modifier_pressed: bool,
        clutch_position: float,
        dt: float,
    ) -> ModeUpdateResult:
        vjoy_actions = []
        force_requests = []

        # Y 轴换挡检测
        y_center = 0.5
        shift_threshold = 0.3  # 上下各 30% 行程触发
        debounce_sec = self._params.seq_shift_debounce_ms / 1000.0
        now = time.time()

        # 判断 Y 轴区域
        if position.y < y_center - shift_threshold:
            new_zone = 1  # 上推 = 升档
        elif position.y > y_center + shift_threshold:
            new_zone = -1  # 下拉 = 降档
        else:
            new_zone = 0

        # 检测换挡触发（跨越阈值）
        gear_changed = False
        if new_zone != 0 and new_zone != self._current_y_zone:
            if (now - self._last_shift_time) >= debounce_sec:
                gear_changed = True
                self._last_shift_time = now

                if new_zone == 1:
                    # 升档
                    vjoy_actions.append(VJoyAction.press(BTN_SEQ_UP))
                    vjoy_actions.append(VJoyAction.release(BTN_SEQ_DOWN))
                else:
                    # 降档
                    vjoy_actions.append(VJoyAction.press(BTN_SEQ_DOWN))
                    vjoy_actions.append(VJoyAction.release(BTN_SEQ_UP))

                self._current_gear = Gear.NEUTRAL  # 序列档没有具体档位概念

        # 回到中间区域时释放按钮
        if new_zone == 0 and self._current_y_zone != 0:
            vjoy_actions.append(VJoyAction.release(BTN_SEQ_UP))
            vjoy_actions.append(VJoyAction.release(BTN_SEQ_DOWN))

        self._current_y_zone = new_zone

        # FFB 效果
        torque_gain = self._params.max_torque_pct / 100.0

        # X 轴弹簧死锁
        force_requests.append(ForceRequest(
            name="seq_x_lock",
            force_type=ForceType.SPRING,
            axis=0,
            spring_center=0,
            spring_coefficient=0x7FFF,
            spring_deadband=200,
            duration_ms=SDL_HAPTIC_INFINITY,
            gain=torque_gain,
        ))

        # Y 轴重弹簧居中
        y_spring_coeff = int(0x7FFF * (self._params.seq_spring_force / 100.0))
        force_requests.append(ForceRequest(
            name="seq_y_spring",
            force_type=ForceType.SPRING,
            axis=1,
            spring_center=0,
            spring_coefficient=y_spring_coeff,
            spring_deadband=500,
            duration_ms=SDL_HAPTIC_INFINITY,
            gain=torque_gain,
        ))

        # 换挡瞬间的震动和反弹
        if gear_changed:
            bump_force = int(0x7FFF * (self._params.seq_bump_force / 100.0))
            period_us = int(1000000 / max(self._params.seq_bump_vibration_hz, 10))

            # 高频方波震动（模拟齿轮咬合）
            force_requests.append(ForceRequest(
                name="seq_shift_vibration",
                force_type=ForceType.PERIODIC_SQUARE,
                axis=1,
                periodic_magnitude=bump_force,
                periodic_period=period_us,
                duration_ms=80,
                gain=torque_gain,
            ))

            # 反弹力
            bounce_dir = -1 if new_zone == 1 else 1
            force_requests.append(ForceRequest(
                name="seq_bump_stop",
                force_type=ForceType.CONSTANT,
                axis=1,
                level=bounce_dir * bump_force,
                direction=0 if bounce_dir > 0 else 180,
                duration_ms=100,
                gain=torque_gain,
            ))

        return ModeUpdateResult(
            vjoy_actions=vjoy_actions,
            force_requests=force_requests,
            gear_changed=gear_changed,
            new_gear=self._current_gear if gear_changed else None,
        )
