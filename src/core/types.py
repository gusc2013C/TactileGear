"""共享枚举、数据类和常量定义。所有模块均依赖此文件。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Optional


# =============================================================================
# 枚举
# =============================================================================

class GearMode(Enum):
    HPATTERN = "HPATTERN"
    SEQUENTIAL = "SEQUENTIAL"
    HANDBRAKE = "HANDBRAKE"
    AUTO_PRND = "AUTO_PRND"


class LayoutID(Enum):
    CIVILIAN_6R_LEFT = "CIVILIAN_6R_LEFT"
    CIVILIAN_6R_RIGHT = "CIVILIAN_6R_RIGHT"
    PORSCHE_7R = "PORSCHE_7R"
    TRUCK_18 = "TRUCK_18"


class Gear(Enum):
    NEUTRAL = "NEUTRAL"
    R = "R"
    G1 = "G1"
    G2 = "G2"
    G3 = "G3"
    G4 = "G4"
    G5 = "G5"
    G6 = "G6"
    G7 = "G7"
    G8 = "G8"
    # PRND 专用
    P = "P"
    DRV = "DRV"
    S = "S"


class ReverseUnlockMethod(Enum):
    MODIFIER_KEY = "MODIFIER_KEY"
    GRAVITY_BREAKTHROUGH = "GRAVITY_BREAKTHROUGH"


class ConnectionStatus(Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"


class ForceType(Enum):
    CONSTANT = "CONSTANT"
    SPRING = "SPRING"
    DAMPER = "DAMPER"
    PERIODIC_SQUARE = "PERIODIC_SQUARE"
    PERIODIC_SINE = "PERIODIC_SINE"


# =============================================================================
# vJoy 按钮映射常量
# =============================================================================

# H 档模式
BTN_GEAR_1 = 1
BTN_GEAR_2 = 2
BTN_GEAR_3 = 3
BTN_GEAR_4 = 4
BTN_GEAR_5 = 5
BTN_GEAR_6 = 6
BTN_GEAR_7 = 7
BTN_GEAR_8 = 8
BTN_REVERSE = 9
BTN_NEUTRAL = 10

# 序列档模式
BTN_SEQ_UP = 11
BTN_SEQ_DOWN = 12

# 自动挡 PRND 模式
BTN_P = 13
BTN_R_PRND = 14
BTN_N_PRND = 15
BTN_D = 16
BTN_S = 17

# 卡车/特殊功能
BTN_RANGE = 18
BTN_SPLITTER = 19

# 按钮总数
TOTAL_BUTTONS = 32

# 档位到按钮的映射
GEAR_TO_BUTTON: dict[Gear, int] = {
    Gear.G1: BTN_GEAR_1,
    Gear.G2: BTN_GEAR_2,
    Gear.G3: BTN_GEAR_3,
    Gear.G4: BTN_GEAR_4,
    Gear.G5: BTN_GEAR_5,
    Gear.G6: BTN_GEAR_6,
    Gear.G7: BTN_GEAR_7,
    Gear.G8: BTN_GEAR_8,
    Gear.R: BTN_REVERSE,
    Gear.NEUTRAL: BTN_NEUTRAL,
    Gear.P: BTN_P,
    Gear.DRV: BTN_D,
    Gear.S: BTN_S,
}

# =============================================================================
# 轴常量
# =============================================================================

VJOY_AXIS_MIN = 1
VJOY_AXIS_MAX = 0x8000  # 32768
VJOY_AXIS_CENTER = 0x4000  # 16384

# 物理循环
PHYSICS_HZ = 100
PHYSICS_DT = 1.0 / PHYSICS_HZ

# SDL 力反馈
SDL_HAPTIC_INFINITY = 0xFFFFFFFF


# =============================================================================
# 数据类
# =============================================================================

@dataclass(frozen=True)
class GatePosition:
    """归一化的物理摇杆位置 (0.0 - 1.0)。"""
    x: float
    y: float


@dataclass
class GearGate:
    """单个档位闸口的定义。"""
    gear: Gear
    x: float  # 闸口中心 X (归一化)
    y: float  # 闸口中心 Y (归一化)
    width: float = 0.08  # 闸口宽度 (归一化半径)
    lockout_rule: Optional[str] = None  # None, "modifier_or_gravity", "anti_miss_from_5"


@dataclass
class LayoutDefinition:
    """H 档排布定义。"""
    layout_id: LayoutID
    display_name: str
    x_range: tuple[float, float] = (0.0, 1.0)
    y_range: tuple[float, float] = (0.0, 1.0)
    neutral_zone_y: tuple[float, float] = (0.4, 0.6)
    neutral_center_x: float = 0.5
    gates: list[GearGate] = field(default_factory=list)


@dataclass
class ProfileParameters:
    """可调参数集合。"""
    max_torque_pct: float = 80.0
    pull_in_force: float = 60.0
    neutral_spring_force: float = 70.0
    miss_penalty_force: float = 90.0
    reverse_breakthrough_threshold: float = 0.75
    clutch_grinding_enabled: bool = True
    clutch_grinding_force: float = 95.0
    notch_vibration_magnitude: float = 50.0
    notch_vibration_duration_ms: int = 80
    seq_spring_force: float = 85.0
    seq_bump_force: float = 75.0
    seq_bump_vibration_hz: int = 150
    seq_shift_debounce_ms: int = 200
    handbrake_exponential_factor: float = 3.5
    handbrake_max_resistance: float = 80.0
    prnd_spring_force: float = 50.0
    prnd_p_pullout_resistance: float = 90.0


@dataclass
class TelemetryData:
    """来自 SimHub 的遥测数据。"""
    clutch_position: float = 1.0  # 0.0=松开, 1.0=踩到底 (安全默认为踩下)
    speed_kph: float = 0.0
    rpm: float = 0.0
    game_gear: int = 0
    timestamp: float = 0.0

    @property
    def clutch_pressed(self) -> bool:
        return self.clutch_position > 0.1

    @property
    def is_stale(self) -> bool:
        """子类或外部可通过 timestamp 判断数据是否过期。"""
        return False


@dataclass
class ModeUpdateResult:
    """模式控制器每次 update 的输出。"""
    vjoy_actions: list = field(default_factory=list)  # list[VJoyAction]
    force_requests: list = field(default_factory=list)  # list[ForceRequest]
    gear_changed: bool = False
    new_gear: Optional[Gear] = None
    status_message: Optional[str] = None
