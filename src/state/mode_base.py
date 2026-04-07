"""模式控制器抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.core.types import (
    GatePosition,
    Gear,
    ModeUpdateResult,
    ProfileParameters,
)


class ModeController(ABC):
    """所有工作模式的抽象基类。"""

    def __init__(self, params: ProfileParameters) -> None:
        self._params = params
        self._current_gear: Gear = Gear.NEUTRAL

    @property
    def current_gear(self) -> Gear:
        return self._current_gear

    @abstractmethod
    def enter(self) -> list[Any]:
        """进入此模式时调用。返回初始 vJoy 动作列表。"""
        ...

    @abstractmethod
    def exit(self) -> list[Any]:
        """退出此模式时调用。返回清理 vJoy 动作列表。"""
        ...

    @abstractmethod
    def update(
        self,
        position: GatePosition,
        modifier_pressed: bool,
        clutch_position: float,
        dt: float,
    ) -> ModeUpdateResult:
        """每物理帧调用。

        Args:
            position: 归一化的摇杆位置
            modifier_pressed: 修改器按键是否按下
            clutch_position: 离合器位置 (0=松开, 1=踩到底)
            dt: 帧间隔 (秒)
        """
        ...

    def update_params(self, params: ProfileParameters) -> None:
        """更新参数。"""
        self._params = params
