"""FFB 效果生命周期管理器。通过 diff 算法避免每帧重建效果。"""

from __future__ import annotations

import logging
from typing import Optional

from src.core.types import ForceType, SDL_HAPTIC_INFINITY
from src.physics.force_types import ForceRequest

logger = logging.getLogger(__name__)


class ForceEngine:
    """管理 SDL haptic 效果的创建、更新和销毁。

    核心策略：对比当前活跃效果与请求列表，只变更差异部分。
    每个效果通过语义名称 (name) 标识。
    """

    def __init__(self, sdl_device) -> None:
        """
        Args:
            sdl_device: SDLDevice 实例，用于实际的 SDL 操作
        """
        self._device = sdl_device
        # name -> (effect_id, force_type, params_dict)
        self._active: dict[str, tuple[int, ForceType, dict]] = {}

    def apply_forces(self, requests: list[ForceRequest]) -> None:
        """应用一组力请求，与当前活跃效果做 diff。

        - 新请求中存在但活跃中不存在的 → 创建并运行
        - 活跃中存在但新请求中不存在的 → 停止并销毁
        - 两者都存在但参数不同的 → 停止、销毁、重建
        - 两者都存在且参数相同的 → 不变
        """
        requested_names = {r.name for r in requests}
        active_names = set(self._active.keys())

        # 需要删除的效果
        to_remove = active_names - requested_names
        for name in to_remove:
            self._destroy_effect(name)

        # 处理请求（新建或更新）
        for req in requests:
            if req.name in self._active:
                # 检查是否需要更新
                current_id, current_type, current_params = self._active[req.name]
                new_params = self._request_to_params(req)
                if current_type == req.force_type and current_params == new_params:
                    continue  # 无变化
                # 参数变了，销毁后重建
                self._destroy_effect(req.name)
                self._create_and_run(req)
            else:
                # 新效果
                self._create_and_run(req)

    def stop_and_clear(self) -> None:
        """停止并销毁所有活跃效果。用于模式切换和关机。"""
        for name in list(self._active.keys()):
            self._destroy_effect(name)
        self._active.clear()
        # 额外安全：确保所有效果停止
        self._device.stop_all()
        logger.info("所有力反馈效果已清除")

    def get_active_count(self) -> int:
        """返回当前活跃效果数量。"""
        return len(self._active)

    # =========================================================================
    # 内部方法
    # =========================================================================

    def _create_and_run(self, req: ForceRequest) -> None:
        """根据 ForceRequest 创建并运行效果。"""
        effect_id = self._create_effect(req)
        if effect_id is not None:
            self._device.run_effect(effect_id)
            params = self._request_to_params(req)
            self._active[req.name] = (effect_id, req.force_type, params)

    def _create_effect(self, req: ForceRequest) -> Optional[int]:
        """根据力类型调用对应的 SDL 创建方法。"""
        gain = req.gain

        if req.force_type == ForceType.CONSTANT:
            level = int(req.level * gain)
            return self._device.create_constant_force(
                level=level,
                direction=req.direction,
                duration=req.duration_ms,
                attack_length=req.attack_length,
                attack_level=req.attack_level,
                fade_length=req.fade_length,
                fade_level=req.fade_level,
            )

        elif req.force_type == ForceType.SPRING:
            coeff = int(req.spring_coefficient * gain)
            return self._device.create_spring_effect(
                center=req.spring_center,
                coefficient=coeff,
                deadband=req.spring_deadband,
                saturation=req.spring_saturation,
                duration=req.duration_ms,
            )

        elif req.force_type == ForceType.PERIODIC_SQUARE:
            mag = int(req.periodic_magnitude * gain)
            return self._device.create_periodic_square(
                magnitude=mag,
                period=req.periodic_period,
                duration=req.duration_ms,
            )

        else:
            logger.warning("不支持的力类型: %s", req.force_type)
            return None

    def _destroy_effect(self, name: str) -> None:
        """停止并销毁指定名称的效果。"""
        if name not in self._active:
            return
        effect_id, _, _ = self._active[name]
        self._device.stop_effect(effect_id)
        self._device.destroy_effect(effect_id)
        del self._active[name]

    @staticmethod
    def _request_to_params(req: ForceRequest) -> dict:
        """提取请求中影响效果的关键参数，用于 diff 比较。"""
        return {
            "type": req.force_type,
            "level": req.level,
            "direction": req.direction,
            "spring_center": req.spring_center,
            "spring_coefficient": req.spring_coefficient,
            "spring_deadband": req.spring_deadband,
            "spring_saturation": req.spring_saturation,
            "periodic_magnitude": req.periodic_magnitude,
            "periodic_period": req.periodic_period,
            "duration_ms": req.duration_ms,
            "gain": req.gain,
        }
