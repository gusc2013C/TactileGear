"""SDL2 摇杆和力反馈设备封装。"""

from __future__ import annotations

import atexit
import logging
from typing import Optional

from src.core.types import GatePosition, VJOY_AXIS_CENTER

logger = logging.getLogger(__name__)


class SDLDevice:
    """SDL2 摇杆 + 力反馈设备封装。

    隔离所有 SDL ctypes 操作，对外只暴露高级 API。
    """

    def __init__(self, joystick_name_pattern: str = "MOZA") -> None:
        self._joystick_name_pattern = joystick_name_pattern
        self._sdl = None
        self._joystick = None
        self._haptic = None
        self._connected = False
        self._joystick_id: Optional[int] = None
        self._num_axes = 0
        self._num_buttons = 0
        self._haptic_capabilities = 0

    def connect(self) -> bool:
        """初始化 SDL2 并连接摇杆。返回是否成功。"""
        try:
            import sdl2
            self._sdl = sdl2
        except ImportError:
            logger.error("PySDL2 未安装")
            return False

        # 初始化 SDL
        ret = self._sdl.SDL_Init(
            self._sdl.SDL_INIT_JOYSTICK | self._sdl.SDL_INIT_HAPTIC
        )
        if ret < 0:
            logger.error("SDL 初始化失败")
            return False

        # 注册退出清理
        atexit.register(self._cleanup)

        # 查找目标摇杆
        num_joysticks = self._sdl.SDL_NumJoysticks()
        for i in range(num_joysticks):
            name = self._sdl.SDL_JoystickNameForIndex(i)
            if name and self._joystick_name_pattern.upper() in name.upper():
                self._joystick = self._sdl.SDL_JoystickOpen(i)
                if self._joystick:
                    self._joystick_id = i
                    self._num_axes = self._sdl.SDL_JoystickNumAxes(self._joystick)
                    self._num_buttons = self._sdl.SDL_JoystickNumButtons(self._joystick)
                    break

        if not self._joystick:
            # 如果没找到匹配的，尝试打开第一个摇杆
            if num_joysticks > 0:
                logger.warning("未找到匹配 '%s' 的摇杆，尝试使用第一个设备",
                               self._joystick_name_pattern)
                self._joystick = self._sdl.SDL_JoystickOpen(0)
                self._joystick_id = 0
                self._num_axes = self._sdl.SDL_JoystickNumAxes(self._joystick)
                self._num_buttons = self._sdl.SDL_JoystickNumButtons(self._joystick)
            else:
                logger.error("没有找到任何摇杆设备")
                self._sdl.SDL_Quit()
                return False

        # 打开力反馈
        self._haptic = self._sdl.SDL_HapticOpenFromJoystick(self._joystick)
        if self._haptic:
            self._haptic_capabilities = self._sdl.SDL_HapticQuery(self._haptic)
            logger.info("力反馈设备已打开，支持的效果: 0x%X", self._haptic_capabilities)
        else:
            logger.warning("无法打开力反馈设备")

        self._connected = True
        logger.info("摇杆已连接，轴数=%d，按钮数=%d",
                     self._num_axes, self._num_buttons)
        return True

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def has_haptic(self) -> bool:
        return self._haptic is not None

    def read_axis_raw(self, axis_index: int) -> int:
        """读取原始轴值 (-32768 ~ 32767)。"""
        if not self._connected or not self._joystick:
            return 0
        return self._sdl.SDL_JoystickGetAxis(self._joystick, axis_index)

    def read_button(self, button_index: int) -> bool:
        """读取按钮状态。"""
        if not self._connected or not self._joystick:
            return False
        return self._sdl.SDL_JoystickGetButton(self._joystick, button_index) == 1

    def read_normalized_position(self) -> GatePosition:
        """读取归一化的摇杆位置 (0.0 ~ 1.0)。"""
        # SDL 轴值: -32768 ~ 32767，归一化到 0.0 ~ 1.0
        raw_x = self.read_axis_raw(0)
        raw_y = self.read_axis_raw(1)
        x = (raw_x + 32768) / 65535.0
        y = (raw_y + 32768) / 65535.0
        return GatePosition(
            x=max(0.0, min(1.0, x)),
            y=max(0.0, min(1.0, y)),
        )

    def read_modifier_button(self) -> bool:
        """读取修改器按钮状态（默认按钮 0）。"""
        return self.read_button(0)

    # =========================================================================
    # 力反馈 API
    # =========================================================================

    def create_constant_force(
        self,
        level: int,
        direction: int = 0,
        duration: int = 0xFFFFFFFF,
        attack_length: int = 0,
        attack_level: int = 0,
        fade_length: int = 0,
        fade_level: int = 0,
    ) -> Optional[int]:
        """创建恒定力效果。返回效果 ID 或 None。"""
        if not self._haptic or not self._sdl:
            return None

        sdl2 = self._sdl
        effect = sdl2.SDL_HapticEffect()
        sdl2.memset(sdl2.byref(effect), 0, sdl2.sizeof(sdl2.SDL_HapticEffect))

        effect.type = sdl2.SDL_HAPTIC_CONSTANT
        c = effect.constant
        c.type = sdl2.SDL_HAPTIC_CONSTANT
        c.direction.type = sdl2.SDL_HAPTIC_CARTESIAN
        c.direction.dir[0] = 1 if level >= 0 else -1
        c.direction.dir[1] = 0
        c.length = duration
        c.level = max(-32767, min(32767, level))
        c.attack_length = attack_length
        c.attack_level = attack_level
        c.fade_length = fade_length
        c.fade_level = fade_level

        effect_id = sdl2.SDL_HapticNewEffect(self._haptic, sdl2.byref(effect))
        if effect_id < 0:
            logger.error("创建恒定力效果失败: %d", effect_id)
            return None
        return effect_id

    def create_spring_effect(
        self,
        center: int = 0,
        coefficient: int = 0x7FFF,
        deadband: int = 0,
        saturation: int = 0xFFFF,
        duration: int = 0xFFFFFFFF,
    ) -> Optional[int]:
        """创建弹簧条件效果。返回效果 ID 或 None。"""
        if not self._haptic or not self._sdl:
            return None

        sdl2 = self._sdl
        effect = sdl2.SDL_HapticEffect()
        sdl2.memset(sdl2.byref(effect), 0, sdl2.sizeof(sdl2.SDL_HapticEffect))

        effect.type = sdl2.SDL_HAPTIC_SPRING
        s = effect.condition
        # X 轴参数
        s.right_sat[0] = saturation
        s.left_sat[0] = saturation
        s.right_coeff[0] = coefficient
        s.left_coeff[0] = coefficient
        s.deadband[0] = deadband
        s.center[0] = center
        # Y 轴参数
        s.right_sat[1] = saturation
        s.left_sat[1] = saturation
        s.right_coeff[1] = coefficient
        s.left_coeff[1] = coefficient
        s.deadband[1] = deadband
        s.center[1] = center
        s.length = duration

        effect_id = sdl2.SDL_HapticNewEffect(self._haptic, sdl2.byref(effect))
        if effect_id < 0:
            logger.error("创建弹簧效果失败: %d", effect_id)
            return None
        return effect_id

    def create_periodic_square(
        self,
        magnitude: int = 0x7FFF,
        period: int = 1000,
        duration: int = 80,
        attack_length: int = 0,
        fade_length: int = 0,
    ) -> Optional[int]:
        """创建方波周期效果（金属段落感）。返回效果 ID 或 None。"""
        if not self._haptic or not self._sdl:
            return None

        sdl2 = self._sdl
        effect = sdl2.SDL_HapticEffect()
        sdl2.memset(sdl2.byref(effect), 0, sdl2.sizeof(sdl2.SDL_HapticEffect))

        effect.type = sdl2.SDL_HAPTIC_SQUARE
        p = effect.periodic
        p.type = sdl2.SDL_HAPTIC_SQUARE
        p.direction.type = sdl2.SDL_HAPTIC_CARTESIAN
        p.direction.dir[0] = 1
        p.period = period
        p.magnitude = max(0, min(32767, magnitude))
        p.length = duration
        p.attack_length = attack_length
        p.fade_length = fade_length

        effect_id = sdl2.SDL_HapticNewEffect(self._haptic, sdl2.byref(effect))
        if effect_id < 0:
            logger.error("创建方波效果失败: %d", effect_id)
            return None
        return effect_id

    def run_effect(self, effect_id: int, iterations: int = 1) -> bool:
        """运行指定效果。"""
        if not self._haptic or effect_id < 0:
            return False
        ret = self._sdl.SDL_HapticRunEffect(self._haptic, effect_id, iterations)
        return ret >= 0

    def stop_effect(self, effect_id: int) -> bool:
        """停止指定效果。"""
        if not self._haptic or effect_id < 0:
            return False
        ret = self._sdl.SDL_HapticStopEffect(self._haptic, effect_id)
        return ret >= 0

    def destroy_effect(self, effect_id: int) -> None:
        """销毁指定效果。"""
        if not self._haptic or effect_id < 0:
            return
        self._sdl.SDL_HapticDestroyEffect(self._haptic, effect_id)

    def stop_all(self) -> None:
        """停止所有力反馈效果（紧急安全机制）。"""
        if self._haptic:
            try:
                self._sdl.SDL_HapticStopAll(self._haptic)
                logger.info("所有力反馈效果已停止")
            except Exception as e:
                logger.error("停止力反馈失败: %s", e)

    def _cleanup(self) -> None:
        """atexit 清理。"""
        self.stop_all()
        if self._haptic:
            try:
                self._sdl.SDL_HapticClose(self._haptic)
            except Exception:
                pass
            self._haptic = None
        if self._joystick:
            try:
                self._sdl.SDL_JoystickClose(self._joystick)
            except Exception:
                pass
            self._joystick = None
        if self._sdl:
            try:
                self._sdl.SDL_Quit()
            except Exception:
                pass
        self._connected = False

    def disconnect(self) -> None:
        """断开连接并清理所有资源。"""
        self._cleanup()
        logger.info("SDL 设备已断开")
