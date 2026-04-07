"""轻量级事件总线，基于 queue.Queue 的发布/订阅机制。"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any

from src.core.types import GearMode, LayoutID, ProfileParameters


# =============================================================================
# 事件定义
# =============================================================================

@dataclass
class ModeChangeRequested:
    new_mode: GearMode


@dataclass
class LayoutChangeRequested:
    layout_id: LayoutID


@dataclass
class ParametersUpdated:
    params: ProfileParameters


@dataclass
class ConnectionStatusChanged:
    device: str  # "moza", "vjoy", "simhub"
    status: str  # "connected", "disconnected", "error"


@dataclass
class GearChanged:
    old_gear: str
    new_gear: str


@dataclass
class ShutdownRequested:
    pass


@dataclass
class ProfileSaveRequested:
    name: str


@dataclass
class ProfileLoadRequested:
    name: str


@dataclass
class ReverseUnlockMethodChanged:
    method: str  # "modifier_key" or "gravity_breakthrough"


@dataclass
class StatusUpdate:
    """物理线程向 GUI 推送的状态更新。"""
    current_mode: GearMode
    current_gear: str
    position_x: float
    position_y: float
    fps: float


# =============================================================================
# 事件总线
# =============================================================================

class EventBus:
    """线程安全的发布/订阅事件总线。"""

    def __init__(self) -> None:
        self._subscribers: list[queue.Queue[Any]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[Any]:
        """订阅事件，返回一个接收事件的 Queue。"""
        q: queue.Queue[Any] = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[Any]) -> None:
        """取消订阅。"""
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def publish(self, event: Any) -> None:
        """向所有订阅者发布事件。"""
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass  # 丢弃满队列的事件，避免阻塞
