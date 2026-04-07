"""SDL3 摇杆和力反馈设备封装。"""

from __future__ import annotations

import atexit
import ctypes
import logging
from typing import Optional

from src.core.types import GatePosition

logger = logging.getLogger(__name__)


class SDLDevice:
    """SDL3 摇杆 + 力反馈设备封装。

    隔离所有 SDL3 ctypes 操作，对外只暴露高级 API。
    使用 PySDL3 (pip install PySDL3) 包装层。
    """

    def __init__(self) -> None:
        self._sdl = None
        self._joystick = None
        self._haptic = None
        self._connected = False
        self._joystick_id: Optional[int] = None  # SDL_JoystickID (uint32)
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
            import sdl3
            self._sdl = sdl3
        except ImportError:
            logger.error("PySDL3 未安装，请运行: pip install PySDL3")
            return False

        # SDL3: SDL_Init 返回 bool (True=成功)
        ret = self._sdl.SDL_Init(
            self._sdl.SDL_INIT_JOYSTICK | self._sdl.SDL_INIT_HAPTIC
        )
        if not ret:
            err = self._sdl.SDL_GetError()
            err_str = err.decode("utf-8", errors="replace") if isinstance(err, bytes) else str(err)
            logger.error("SDL 初始化失败: %s", err_str)
            return False

        self._sdl_initialized = True
        atexit.register(self._cleanup)
        logger.info("SDL3 子系统初始化完成")
        return True

    def enumerate_joysticks(self) -> list[dict]:
        """枚举所有可用摇杆设备。

        Returns:
            [{"instance_id": 123, "name": "MOZA AB6", "guid": "..."}, ...]
        """
        if not self._sdl_initialized:
            if not self.init_sdl():
                return []

        sdl3 = self._sdl
        devices = []

        # SDL3: SDL_GetJoysticks(count) 返回 SDL_JoystickID 数组
        count = ctypes.c_int(0)
        ids_ptr = sdl3.SDL_GetJoysticks(ctypes.byref(count))

        if not ids_ptr or count.value <= 0:
            return devices

        for i in range(count.value):
            try:
                instance_id = int(ids_ptr[i])
            except (TypeError, IndexError):
                continue
            if instance_id == 0:
                break  # NULL 终止符

            # 名称
            name_raw = sdl3.SDL_GetJoystickNameForID(instance_id)
            if isinstance(name_raw, bytes):
                name = name_raw.decode("utf-8", errors="replace")
            elif name_raw:
                name = str(name_raw)
            else:
                name = f"Joystick {instance_id}"

            # GUID
            guid_str = ""
            try:
                guid = sdl3.SDL_GetJoystickGUIDForID(instance_id)
                guid_buf = ctypes.create_string_buffer(33)
                sdl3.SDL_GUIDToString(guid, guid_buf, 33)
                guid_str = guid_buf.value.decode("ascii", errors="replace")
            except Exception:
                guid_str = "unknown"

            devices.append({
                "instance_id": instance_id,
                "name": name,
                "guid": guid_str,
            })

        # 释放 SDL 分配的数组
        try:
            sdl3.SDL_free(ids_ptr)
        except Exception:
            pass

        return devices

    def open_joystick(self, instance_id: int) -> bool:
        """打开指定 SDL_JoystickID 的摇杆并初始化力反馈。

        Args:
            instance_id: 摇杆实例 ID（来自 enumerate_joysticks）
        """
        if not self._sdl_initialized:
            if not self.init_sdl():
                return False

        sdl3 = self._sdl

        # 如果已经打开了一个设备，先关闭
        if self._joystick:
            self.close_joystick()

        name_raw = sdl3.SDL_GetJoystickNameForID(instance_id)
        if isinstance(name_raw, bytes):
            self._joystick_name = name_raw.decode("utf-8", errors="replace")
        elif name_raw:
            self._joystick_name = str(name_raw)
        else:
            self._joystick_name = f"Joystick {instance_id}"

        # SDL3: SDL_OpenJoystick(instance_id)
        self._joystick = sdl3.SDL_OpenJoystick(instance_id)
        if not self._joystick:
            err = sdl3.SDL_GetError()
            err_str = err.decode("utf-8", errors="replace") if isinstance(err, bytes) else str(err)
            logger.error("打开摇杆 %s (ID=%d) 失败: %s", self._joystick_name, instance_id, err_str)
            return False

        self._joystick_id = instance_id
        self._num_axes = sdl3.SDL_GetNumJoystickAxes(self._joystick)
        self._num_buttons = sdl3.SDL_GetNumJoystickButtons(self._joystick)

        # 打开力反馈 — SDL3: SDL_OpenHapticFromJoystick
        self._haptic = sdl3.SDL_OpenHapticFromJoystick(self._joystick)
        if self._haptic:
            self._haptic_capabilities = sdl3.SDL_GetHapticFeatures(self._haptic)
            logger.info(
                "力反馈已打开，支持: constant=%s spring=%s periodic=%s",
                bool(self._haptic_capabilities & sdl3.SDL_HAPTIC_CONSTANT),
                bool(self._haptic_capabilities & sdl3.SDL_HAPTIC_SPRING),
                bool(self._haptic_capabilities & sdl3.SDL_HAPTIC_SQUARE),
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
                self._sdl.SDL_CloseHaptic(self._haptic)
            except Exception:
                pass
            self._haptic = None
        if self._joystick:
            try:
                self._sdl.SDL_CloseJoystick(self._joystick)
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
        val = self._sdl.SDL_GetJoystickAxis(self._joystick, axis_index)
        return int(val)

    def read_button(self, button_index: int) -> bool:
        """读取按钮状态。"""
        if not self._connected or not self._joystick:
            return False
        val = self._sdl.SDL_GetJoystickButton(self._joystick, button_index)
        return bool(val)

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
    # 力反馈 API — SDL3 重命名版本
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

        sdl3 = self._sdl
        effect = sdl3.SDL_HapticEffect()
        ctypes.memset(ctypes.byref(effect), 0, ctypes.sizeof(sdl3.SDL_HapticEffect))

        effect.type = sdl3.SDL_HAPTIC_CONSTANT
        c = effect.constant
        c.type = sdl3.SDL_HAPTIC_CONSTANT
        c.direction.type = sdl3.SDL_HAPTIC_CARTESIAN
        c.direction.dir[0] = 1 if level >= 0 else -1
        c.direction.dir[1] = 0
        c.length = duration
        c.level = max(-32767, min(32767, level))
        c.attack_length = attack_length
        c.attack_level = attack_level
        c.fade_length = fade_length
        c.fade_level = fade_level

        # SDL3: SDL_CreateHapticEffect
        effect_id = sdl3.SDL_CreateHapticEffect(self._haptic, ctypes.byref(effect))
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

        sdl3 = self._sdl
        effect = sdl3.SDL_HapticEffect()
        ctypes.memset(ctypes.byref(effect), 0, ctypes.sizeof(sdl3.SDL_HapticEffect))

        effect.type = sdl3.SDL_HAPTIC_SPRING
        s = effect.condition
        for axis_idx in (0, 1):
            s.right_sat[axis_idx] = saturation
            s.left_sat[axis_idx] = saturation
            s.right_coeff[axis_idx] = coefficient
            s.left_coeff[axis_idx] = coefficient
            s.deadband[axis_idx] = deadband
            s.center[axis_idx] = center
        s.length = duration

        effect_id = sdl3.SDL_CreateHapticEffect(self._haptic, ctypes.byref(effect))
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

        sdl3 = self._sdl
        effect = sdl3.SDL_HapticEffect()
        ctypes.memset(ctypes.byref(effect), 0, ctypes.sizeof(sdl3.SDL_HapticEffect))

        effect.type = sdl3.SDL_HAPTIC_SQUARE
        p = effect.periodic
        p.type = sdl3.SDL_HAPTIC_SQUARE
        p.direction.type = sdl3.SDL_HAPTIC_CARTESIAN
        p.direction.dir[0] = 1
        p.period = period
        p.magnitude = max(0, min(32767, magnitude))
        p.length = duration
        p.attack_length = attack_length
        p.fade_length = fade_length

        effect_id = sdl3.SDL_CreateHapticEffect(self._haptic, ctypes.byref(effect))
        if effect_id < 0:
            logger.error("创建方波效果失败")
            return None
        return effect_id

    def run_effect(self, effect_id: int, iterations: int = 1) -> bool:
        """运行指定效果。"""
        if not self._haptic or effect_id < 0:
            return False
        return bool(self._sdl.SDL_RunHapticEffect(self._haptic, effect_id, iterations))

    def stop_effect(self, effect_id: int) -> bool:
        """停止指定效果。"""
        if not self._haptic or effect_id < 0:
            return False
        return bool(self._sdl.SDL_StopHapticEffect(self._haptic, effect_id))

    def destroy_effect(self, effect_id: int) -> None:
        """销毁指定效果。"""
        if not self._haptic or effect_id < 0:
            return
        self._sdl.SDL_DestroyHapticEffect(self._haptic, effect_id)

    def stop_all(self) -> None:
        """停止所有力反馈效果（紧急安全机制）。"""
        if self._haptic:
            try:
                self._sdl.SDL_StopHapticEffects(self._haptic)
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
