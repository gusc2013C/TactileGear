"""档位区域检测。纯数学计算，无副作用。"""

from __future__ import annotations

from typing import Optional

from src.core.types import GatePosition, Gear, GearGate, LayoutDefinition


def detect_gate(
    position: GatePosition,
    layout: LayoutDefinition,
) -> Optional[Gear]:
    """判断摇杆位置落在哪个档位闸口内。

    闸口为矩形区域，中心 (gate.x, gate.y)，半宽 gate.width。
    """
    for gate in layout.gates:
        if _is_inside_gate(position, gate):
            return gate.gear
    return None


def _is_inside_gate(position: GatePosition, gate: GearGate) -> bool:
    """判断位置是否在闸口矩形内。"""
    half_w = gate.width
    return (
        abs(position.x - gate.x) <= half_w
        and abs(position.y - gate.y) <= half_w
    )


def nearest_gate_center(
    position: GatePosition,
    layout: LayoutDefinition,
) -> tuple[float, float]:
    """返回最近闸口中心的 (x, y) 坐标。用于回中弹簧。"""
    if not layout.gates:
        return (layout.neutral_center_x, 0.5)

    best_dist = float("inf")
    best_pos = (layout.neutral_center_x, 0.5)

    for gate in layout.gates:
        dist = _euclidean_distance(position, GatePosition(gate.x, gate.y))
        if dist < best_dist:
            best_dist = dist
            best_pos = (gate.x, gate.y)

    return best_pos


def is_in_neutral_zone(
    position: GatePosition,
    layout: LayoutDefinition,
) -> bool:
    """判断摇杆是否在空挡走廊内。"""
    y_lo, y_hi = layout.neutral_zone_y
    return y_lo <= position.y <= y_hi


def find_gate_by_gear(
    gear: Gear,
    layout: LayoutDefinition,
) -> Optional[GearGate]:
    """根据档位枚举查找闸口定义。"""
    for gate in layout.gates:
        if gate.gear == gear:
            return gate
    return None


def distance_to_gate(
    position: GatePosition,
    gate: GearGate,
) -> float:
    """到闸口中心的欧氏距离。"""
    return _euclidean_distance(position, GatePosition(gate.x, gate.y))


def find_nearest_column(
    x: float,
    layout: LayoutDefinition,
) -> float:
    """找到最近的闸口列的 X 坐标。用于空挡回中对齐。"""
    if not layout.gates:
        return layout.neutral_center_x

    best_x = layout.neutral_center_x
    best_dist = abs(x - layout.neutral_center_x)

    for gate in layout.gates:
        dist = abs(x - gate.x)
        if dist < best_dist:
            best_dist = dist
            best_x = gate.x

    return best_x


def is_approaching_locked_gate(
    position: GatePosition,
    target_gate: GearGate,
    approach_threshold: float = 0.15,
) -> bool:
    """判断摇杆是否正在接近一个有锁定规则的闸口。"""
    dist = distance_to_gate(position, target_gate)
    return dist <= target_gate.width + approach_threshold


def _euclidean_distance(a: GatePosition, b: GatePosition) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5
