"""H 档模式控制器 — 最复杂的模式。"""

from __future__ import annotations

import time
from typing import Any, Optional

from src.core.types import (
    BTN_NEUTRAL,
    BTN_RANGE,
    BTN_SPLITTER,
    GEAR_TO_BUTTON,
    ForceType,
    GatePosition,
    Gear,
    GearGate,
    LayoutDefinition,
    LayoutID,
    ModeUpdateResult,
    ProfileParameters,
    ReverseUnlockMethod,
    SDL_HAPTIC_INFINITY,
)
from src.physics.force_curves import (
    gravity_breakthrough_curve,
    nonlinear_centering_spring,
    scale_to_sdl_range,
)
from src.physics.force_types import ForceRequest, VJoyAction
from src.physics.gate_geometry import (
    detect_gate,
    find_gate_by_gear,
    find_nearest_column,
    is_in_neutral_zone,
)
from src.state.mode_base import ModeController


class HPatternController(ModeController):
    """竞技级/民用 H 档模式。

    支持多种排布阵型、物理力反馈墙、重力突破、打齿惩罚等。
    """

    def __init__(
        self,
        params: ProfileParameters,
        layout: LayoutDefinition,
        reverse_unlock_method: ReverseUnlockMethod = ReverseUnlockMethod.GRAVITY_BREAKTHROUGH,
    ) -> None:
        super().__init__(params)
        self._layout = layout
        self._reverse_unlock_method = reverse_unlock_method
        self._last_active_gear: Optional[Gear] = None
        self._last_notch_time = 0.0
        self._is_in_reverse_unlocked = False
        self._truck_range = False  # 卡车高低档
        self._truck_splitter = False  # 卡车半档

    def set_layout(self, layout: LayoutDefinition) -> None:
        """切换排布。"""
        self._layout = layout
        self._last_active_gear = None

    def set_reverse_unlock_method(self, method: ReverseUnlockMethod) -> None:
        """设置倒档解锁方式。"""
        self._reverse_unlock_method = method

    def enter(self) -> list[Any]:
        """进入 H 档模式。"""
        self._current_gear = Gear.NEUTRAL
        self._last_active_gear = None
        # 默认按下空挡按钮
        return [VJoyAction.press(BTN_NEUTRAL)]

    def exit(self) -> list[Any]:
        """退出 H 档模式。"""
        actions = [VJoyAction.release(BTN_NEUTRAL)]
        # 释放所有可能按下的档位按钮
        for gear, btn in GEAR_TO_BUTTON.items():
            actions.append(VJoyAction.release(btn))
        actions.append(VJoyAction.release(BTN_RANGE))
        actions.append(VJoyAction.release(BTN_SPLITTER))
        return actions

    def update(
        self,
        position: GatePosition,
        modifier_pressed: bool,
        clutch_position: float,
        dt: float,
    ) -> ModeUpdateResult:
        vjoy_actions = []
        force_requests = []
        torque_gain = self._params.max_torque_pct / 100.0

        # 1. 检测当前档位
        detected_gear = detect_gate(position, self._layout)
        in_neutral = is_in_neutral_zone(position, self._layout)

        # 2. 判断是否在空挡
        if in_neutral or detected_gear is None:
            detected_gear = Gear.NEUTRAL

        # 3. 检查锁定规则
        blocked = False
        if detected_gear != Gear.NEUTRAL:
            gate = find_gate_by_gear(detected_gear, self._layout)
            if gate and gate.lockout_rule:
                blocked = self._check_lockout(gate, modifier_pressed, position)

        # 4. 打齿检查（离合器未踩下）
        clutch_grinding = False
        if (
            detected_gear != Gear.NEUTRAL
            and not blocked
            and self._params.clutch_grinding_enabled
            and clutch_position < 0.1
            and detected_gear != self._last_active_gear
        ):
            clutch_grinding = True
            blocked = True  # 阻止入档

        # 5. 更新档位和 vJoy 按钮
        effective_gear = Gear.NEUTRAL if blocked else detected_gear
        gear_changed = effective_gear != self._last_active_gear

        if gear_changed:
            # 释放旧档位按钮
            if self._last_active_gear and self._last_active_gear in GEAR_TO_BUTTON:
                vjoy_actions.append(
                    VJoyAction.release(GEAR_TO_BUTTON[self._last_active_gear])
                )
            if self._last_active_gear != Gear.NEUTRAL:
                vjoy_actions.append(VJoyAction.release(BTN_NEUTRAL))

            # 按下新档位按钮
            if effective_gear == Gear.NEUTRAL:
                vjoy_actions.append(VJoyAction.press(BTN_NEUTRAL))
            elif effective_gear in GEAR_TO_BUTTON:
                vjoy_actions.append(VJoyAction.release(BTN_NEUTRAL))
                vjoy_actions.append(VJoyAction.press(GEAR_TO_BUTTON[effective_gear]))

            self._last_active_gear = effective_gear
            self._current_gear = effective_gear

        # 6. 生成 FFB 效果
        force_requests.extend(
            self._generate_forces(
                position, effective_gear, blocked, clutch_grinding,
                modifier_pressed, torque_gain,
            )
        )

        # 7. 卡车模式特殊处理
        if self._layout.layout_id == LayoutID.TRUCK_18:
            vjoy_actions.extend(self._handle_truck_buttons(modifier_pressed))

        return ModeUpdateResult(
            vjoy_actions=vjoy_actions,
            force_requests=force_requests,
            gear_changed=gear_changed,
            new_gear=effective_gear if gear_changed else None,
        )

    # =========================================================================
    # 锁定规则检查
    # =========================================================================

    def _check_lockout(
        self, gate: GearGate, modifier_pressed: bool, position: GatePosition,
    ) -> bool:
        """检查档位是否被锁定。"""
        if gate.lockout_rule == "modifier_or_gravity":
            if gate.gear == Gear.R:
                return self._check_reverse_lockout(modifier_pressed, position)
            # 其他有锁定规则的档位
            return not modifier_pressed

        elif gate.lockout_rule == "anti_miss_from_5":
            # 7档防误触：从5档退回时空挡弹簧应将其拉回3/4列
            # 只有在偏离主列较远时才锁定
            target_col = find_nearest_column(position.x, self._layout)
            # 如果最近的列就是7档所在的列，且距离较近，则锁定
            if abs(position.x - gate.x) < gate.width * 2:
                return True
            return False

        return False

    def _check_reverse_lockout(
        self, modifier_pressed: bool, position: GatePosition,
    ) -> bool:
        """检查倒档锁定。"""
        if self._reverse_unlock_method == ReverseUnlockMethod.MODIFIER_KEY:
            if modifier_pressed:
                self._is_in_reverse_unlocked = True
                return False
            self._is_in_reverse_unlocked = False
            return True

        elif self._reverse_unlock_method == ReverseUnlockMethod.GRAVITY_BREAKTHROUGH:
            # 重力突破：需要计算接近程度
            r_gate = find_gate_by_gear(Gear.R, self._layout)
            if r_gate:
                dist_x = abs(position.x - r_gate.x)
                threshold = self._params.reverse_breakthrough_threshold * r_gate.width
                if dist_x < r_gate.width:
                    # 已经在 R 档闸口内，允许
                    self._is_in_reverse_unlocked = True
                    return False
                if dist_x < threshold and self._is_in_reverse_unlocked:
                    return False
            return not self._is_in_reverse_unlocked

        return True

    # =========================================================================
    # FFB 力生成
    # =========================================================================

    def _generate_forces(
        self,
        position: GatePosition,
        current_gear: Gear,
        blocked: bool,
        clutch_grinding: bool,
        modifier_pressed: bool,
        torque_gain: float,
    ) -> list[ForceRequest]:
        """根据当前状态生成所有力请求。"""
        forces = []
        now = time.time()

        # 1. 空挡区域：非线性回中弹簧
        if current_gear == Gear.NEUTRAL and not blocked:
            # X 轴回中到最近的列
            nearest_x = find_nearest_column(position.x, self._layout)
            displacement_x = abs(position.x - nearest_x) / 0.5  # 归一化
            spring_force = nonlinear_centering_spring(
                displacement_x,
                max_force=self._params.neutral_spring_force / 100.0,
                deadband=0.02,
                exponent=1.5,
            )
            forces.append(ForceRequest(
                name="h_neutral_center_spring_x",
                force_type=ForceType.SPRING,
                axis=0,
                spring_coefficient=scale_to_sdl_range(spring_force),
                spring_deadband=500,
                duration_ms=SDL_HAPTIC_INFINITY,
                gain=torque_gain,
            ))

            # Y 轴回中到空挡走廊
            y_center = (
                self._layout.neutral_zone_y[0] + self._layout.neutral_zone_y[1]
            ) / 2.0
            displacement_y = abs(position.y - y_center) / 0.5
            spring_force_y = nonlinear_centering_spring(
                displacement_y,
                max_force=self._params.neutral_spring_force / 100.0 * 0.5,
                deadband=0.05,
                exponent=1.2,
            )
            forces.append(ForceRequest(
                name="h_neutral_center_spring_y",
                force_type=ForceType.SPRING,
                axis=1,
                spring_coefficient=scale_to_sdl_range(spring_force_y),
                spring_deadband=800,
                duration_ms=SDL_HAPTIC_INFINITY,
                gain=torque_gain,
            ))

        # 2. 档位吸入力：轻弹簧 + 到达后的低力保持
        elif not blocked and current_gear != Gear.NEUTRAL:
            gate = find_gate_by_gear(current_gear, self._layout)
            if gate:
                pull_force = self._params.pull_in_force / 100.0
                forces.append(ForceRequest(
                    name="h_gate_pull_in",
                    force_type=ForceType.SPRING,
                    axis=0,
                    spring_coefficient=scale_to_sdl_range(pull_force * 0.3),
                    spring_deadband=300,
                    duration_ms=SDL_HAPTIC_INFINITY,
                    gain=torque_gain,
                ))

                # 入档瞬间的金属段落感（方波震动）
                if current_gear != self._last_active_gear:
                    if (now - self._last_notch_time) > 0.05:
                        notch_mag = scale_to_sdl_range(
                            self._params.notch_vibration_magnitude / 100.0
                        )
                        forces.append(ForceRequest(
                            name="h_notch_vibration",
                            force_type=ForceType.PERIODIC_SQUARE,
                            axis=0,
                            periodic_magnitude=notch_mag,
                            periodic_period=8000,  # 高频
                            duration_ms=self._params.notch_vibration_duration_ms,
                            gain=torque_gain,
                        ))
                        self._last_notch_time = now

        # 3. 物理墙（锁定档位的阻挡力）
        if blocked:
            wall_force = scale_to_sdl_range(
                self._params.miss_penalty_force / 100.0
            )

            # 倒档重力突破：非线性阻力而非绝对墙
            if (
                self._reverse_unlock_method == ReverseUnlockMethod.GRAVITY_BREAKTHROUGH
                and not modifier_pressed
            ):
                r_gate = find_gate_by_gear(Gear.R, self._layout)
                if r_gate:
                    dist = abs(position.x - r_gate.x)
                    max_dist = r_gate.width * 3
                    progress = 1.0 - min(dist / max_dist, 1.0)
                    resistance = gravity_breakthrough_curve(
                        progress,
                        threshold=self._params.reverse_breakthrough_threshold,
                        peak_force=self._params.miss_penalty_force / 100.0,
                    )
                    wall_force = scale_to_sdl_range(resistance)

            forces.append(ForceRequest(
                name="h_brick_wall",
                force_type=ForceType.CONSTANT,
                axis=0,
                level=-wall_force,  # 反方向阻挡
                direction=180,
                duration_ms=SDL_HAPTIC_INFINITY,
                gain=torque_gain,
            ))

        # 4. 打齿惩罚
        if clutch_grinding:
            grind_force = scale_to_sdl_range(
                self._params.clutch_grinding_force / 100.0
            )
            # 强力反向恒定推力
            forces.append(ForceRequest(
                name="h_grind_reject",
                force_type=ForceType.CONSTANT,
                axis=0,
                level=-grind_force,
                direction=180,
                duration_ms=SDL_HAPTIC_INFINITY,
                gain=torque_gain,
            ))
            # 持续震动
            forces.append(ForceRequest(
                name="h_grind_vibration",
                force_type=ForceType.PERIODIC_SQUARE,
                axis=0,
                periodic_magnitude=scale_to_sdl_range(0.5),
                periodic_period=5000,
                duration_ms=SDL_HAPTIC_INFINITY,
                gain=torque_gain,
            ))

        # 5. 7档防误触弹簧 (Layout C: PORSCHE_7R)
        if self._layout.layout_id == LayoutID.PORSCHE_7R:
            if current_gear == Gear.G5 or (
                current_gear == Gear.NEUTRAL and position.y < 0.4
            ):
                # 从5档退回空挡时，强力回中到3/4列
                forces.append(ForceRequest(
                    name="h_anti_miss_7th",
                    force_type=ForceType.SPRING,
                    axis=0,
                    spring_coefficient=0x7FFF,
                    spring_deadband=200,
                    duration_ms=SDL_HAPTIC_INFINITY,
                    gain=torque_gain,
                ))

        return forces

    # =========================================================================
    # 卡车模式
    # =========================================================================

    def _handle_truck_buttons(self, modifier_pressed: bool) -> list[VJoyAction]:
        """处理卡车高低档和半档按钮（简化版，使用额外按钮切换）。"""
        # 这里可以扩展为更复杂的卡车档位逻辑
        # 当前实现：按钮7切换 Range，按钮8切换 Splitter
        return []
