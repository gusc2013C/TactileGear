"""SDL2 摇杆和力反馈设备封装。"""

from __future__ import annotations

import atexit
import ctypes
import logging
from typing import Optional

from src.core.types import GatePosition

logger = logging.getLogger(__name__)


class SDLDevice:
    """SDL2 摇杆 + 力反馈设备封装。

    隔离所有 SDL ctypes 操作，对外只暴露高级 API。
    """

    def __init__(self) -> None:
        self._sdl = None
        self._joystick = None
        self._haptic = None
        self._connected = False
        self._joystick_id: Optional[int] = None
        self._joystick_name: str = ""
        self._num_axes = 0
        self._num_buttons = 0
        self._haptic_capabilities = 0
        self._sdl_initialized = False

    # =========================================================================
    # SDL 初始化 & 设备枚举
    # =========================================================================

    def init_sdl(self) -> bool:
        """仅初始化 SDL 子系统（不打开任何设备）。"""
        try:
            import sdl2
            self._sdl = sdl2
        except ImportError:
            logger.error("PySDL2 未安装，请运行: pip install pysdl2")
            return False

        ret = self._sdl.SDL_Init(
            self._sdl.SDL_INIT_JOYSTICK | self._sdl.SDL_INIT_HAPTIC
        )
        if ret < 0:
            err = self._sdl.SDL_GetError()
            logger.error("SDL 初始化失败: %s", err)
            return False

        self._sdl_initialized = True
        atexit.register(self._cleanup)
        logger.info("SDL 子系统初始化完成")
        return True

    def enumerate_joysticks(self) -> list[dict]:
        """枚举所有可用摇杆设备。

        Returns:
            [{"index": 0, "name": "MOZA AB6", "guid": "..."}, ...]
        """
        if not self._sdl_initialized:
            if not self.init_sdl():
                return []

        devices = []
        n = self._sdl.SDL_NumJoysticks()
        for i in range(n):
            raw_name = self._sdl.SDL_JoystickNameForIndex(i)
            name = raw_name.decode("utf-8", errors="replace") if raw_name else f"Joystick {i}"
            guid_buf = ctypes.create_string_buffer(33)
            self._sdl.SDL_JoystickGetDeviceGUIDString(i, guid_buf, 33)
            guid = guid_buf.value.decode("ascii", errors="replace")
            devices.append({"index": i, "name": name, "guid": guid})
        return devices

    def open_joystick(self, index: int) -> bool:
        """打开指定索引的摇杆并初始化力反馈。

        Args:
            index: 摇杆索引（来自 enumerate_joysticks）
        """
        if not self._sdl_initialized:
            if not self.init_sdl():
                return False

        sdl2 = self._sdl

        # 如果已经打开了一个设备，先关闭
        if self._joystick:
            self.close_joystick()

        raw_name = sdl2.SDL_JoystickNameForIndex(index)
        self._joystick_name = raw_name.decode("utf-8", errors="replace") if raw_name else f"Joystick {index}"

        self._joystick = sdl2.SDL_JoystickOpen(index)
        if not self._joystick:
            err = sdl2.SDL_GetError()
            logger.error("打开摇杆 %d (%s) 失败: %s", index, self._joystick_name, err)
            return False

        self._joystick_id = index
        self._num_axes = sdl2.SDL_JoystickNumAxes(self._joystick)
        self._num_buttons = sdl2.SDL_JoystickNumButtons(self._joystick)

        # 打开力反馈
        self._haptic = sdl2.SDL_HapticOpenFromJoystick(self._joystick)
        if self._haptic:
            self._haptic_capabilities = sdl2.SDL_HapticQuery(self._haptic)
            logger.info(
                "力反馈已打开，支持: constant=%s spring=%s periodic=%s",
                bool(self._haptic_capabilities & sdl2.SDL_HAPTIC_CONSTANT),
                bool(self._haptic_capabilities & sdl2.SDL_HAPTIC_SPRING),
                bool(self._haptic_capabilities & sdl2.SDL_HAPTIC_SQUARE),
            )
        else:
            logger.warning("该设备不支持力反馈")

        self._connected = True
        logger.info(
            "摇杆已连接: %s (轴=%d, 按钮=%d, haptic=%s)",
            self._joystick_name, self._num_axes, self._num_buttons,
            "YES" if self._haptic else "NO",
        )
        return True

    def close_joystick(self) -> None:
        """关闭当前摇杆（不退出 SDL）。"""
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
        self._connected = False
        self._haptic_capabilities = 0
        logger.info("摇杆已关闭")

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def has_haptic(self) -> bool:
        return self._haptic is not None

    @property
    def joystick_name(self) -> str:
        return self._joystick_name

    # =========================================================================
    # 输入读取
    # =========================================================================

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
        ctypes.memset(ctypes.byref(effect), 0, ctypes.sizeof(sdl2.SDL_HapticEffect))

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

        effect_id = sdl2.SDL_HapticNewEffect(self._haptic, ctypes.byref(effect))
        if effect_id < 0:
            logger.error("创建恒定力效果失败")
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
        ctypes.memset(ctypes.byref(effect), 0, ctypes.sizeof(sdl2.SDL_HapticEffect))

        effect.type = sdl2.SDL_HAPTIC_SPRING
        s = effect.condition
        for axis_idx in (0, 1):
            s.right_sat[axis_idx] = saturation
            s.left_sat[axis_idx] = saturation
            s.right_coeff[axis_idx] = coefficient
            s.left_coeff[axis_idx] = coefficient
            s.deadband[axis_idx] = deadband
            s.center[axis_idx] = center
        s.length = duration

        effect_id = sdl2.SDL_HapticNewEffect(self._haptic, ctypes.byref(effect))
        if effect_id < 0:
            logger.error("创建弹簧效果失败")
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
        ctypes.memset(ctypes.byref(effect), 0, ctypes.sizeof(sdl2.SDL_HapticEffect))

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

        effect_id = sdl2.SDL_HapticNewEffect(self._haptic, ctypes.byref(effect))
        if effect_id < 0:
            logger.error("创建方波效果失败")
            return None
        return effect_id

    def run_effect(self, effect_id: int, iterations: int = 1) -> bool:
        """运行指定效果。"""
        if not self._haptic or effect_id < 0:
            return False
        return self._sdl.SDL_HapticRunEffect(self._haptic, effect_id, iterations) >= 0

    def stop_effect(self, effect_id: int) -> bool:
        """停止指定效果。"""
        if not self._haptic or effect_id < 0:
            return False
        return self._sdl.SDL_HapticStopEffect(self._haptic, effect_id) >= 0

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

    # =========================================================================
    # 生命周期
    # =========================================================================

    def _cleanup(self) -> None:
        """atexit 清理。"""
        self.close_joystick()
        if self._sdl_initialized:
            try:
                self._sdl.SDL_Quit()
            except Exception:
                pass
            self._sdl_initialized = False

    def disconnect(self) -> None:
        """断开连接并清理所有资源。"""
        self._cleanup()
        logger.info("SDL 设备已断开")
