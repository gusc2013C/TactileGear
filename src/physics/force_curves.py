"""纯数学力曲线函数。无外部依赖，无副作用。"""

from __future__ import annotations

import math


def exponential_resistance(displacement: float, factor: float) -> float:
    """指数阻力曲线，用于手刹液压模拟。

    Args:
        displacement: 位移量 (0.0 ~ 1.0)
        factor: 指数因子 (越大阻力增长越快)

    Returns:
        归一化力值 (0.0 ~ 1.0)
    """
    if displacement <= 0.0:
        return 0.0
    displacement = min(displacement, 1.0)
    # A * (e^(B * x) - 1)，归一化到 [0, 1]
    raw = math.exp(factor * displacement) - 1.0
    max_raw = math.exp(factor) - 1.0
    return raw / max_raw if max_raw > 0 else 0.0


def gravity_breakthrough_curve(
    displacement: float,
    threshold: float = 0.75,
    peak_force: float = 1.0,
) -> float:
    """重力突破曲线，模拟宝马式"硬推入 R 档"。

    在 threshold 之前力急剧上升，突破后迅速归零。

    Args:
        displacement: 朝目标方向的位移 (0.0 ~ 1.0)
        threshold: 突破阈值 (0.0 ~ 1.0)
        peak_force: 阻力峰值 (归一化)

    Returns:
        归一化阻力值
    """
    if displacement <= 0.0:
        return 0.0
    if displacement >= threshold:
        # 突破后：快速衰减到接近零
        overshoot = displacement - threshold
        decay = math.exp(-overshoot * 20.0)  # 快速衰减
        return peak_force * decay * 0.05  # 残余极小力
    # 突破前：二次方增长
    progress = displacement / threshold
    return peak_force * (progress ** 2)


def prnd_detent_curve(
    y_position: float,
    detent_positions: list[float],
    detent_force: float = 0.3,
    peak_width: float = 0.03,
) -> float:
    """PRND 多段棘爪力曲线。

    每个驻点位置有一个高斯峰值，制造"段落感"。

    Args:
        y_position: Y轴位置 (0.0 ~ 1.0)
        detent_positions: 各驻点 Y 坐标列表 (如 [0.1, 0.3, 0.5, 0.7, 0.9])
        detent_force: 每个驻点的峰值力 (归一化)
        peak_width: 高斯峰宽度

    Returns:
        总阻力值 (归一化)
    """
    total = 0.0
    for pos in detent_positions:
        diff = y_position - pos
        total += detent_force * math.exp(-(diff ** 2) / (2 * peak_width ** 2))
    return min(total, 1.0)


def nonlinear_centering_spring(
    displacement: float,
    max_force: float = 1.0,
    deadband: float = 0.02,
    exponent: float = 1.5,
) -> float:
    """非线性回中弹簧力。

    Args:
        displacement: 偏离中心的距离 (绝对值，0.0 ~ 1.0)
        max_force: 最大力 (归一化)
        deadband: 死区半径
        exponent: 非线性指数 (>1 越硬)

    Returns:
        回中力大小 (归一化)
    """
    if displacement <= deadband:
        return 0.0
    effective = displacement - deadband
    max_effective = 1.0 - deadband
    normalized = effective / max_effective if max_effective > 0 else 0.0
    return max_force * min(normalized ** exponent, 1.0)


def scale_to_sdl_range(normalized_value: float) -> int:
    """将归一化力值 (0.0~1.0) 缩放到 SDL 力度范围 (0~32767)。"""
    return max(0, min(32767, int(normalized_value * 32767)))
