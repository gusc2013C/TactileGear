"""ctypes 直接调用 vJoyInterface.dll，无第三方依赖。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import os
import platform
from pathlib import Path
from typing import Optional

from src.core.types import (
    TOTAL_BUTTONS,
    VJOY_AXIS_CENTER,
    VJOY_AXIS_MAX,
    VJOY_AXIS_MIN,
)

logger = logging.getLogger(__name__)

# =============================================================================
# HID Usage ID 常量 (vJoy 使用这些标识轴)
# =============================================================================
HID_USAGE_X = 0x30
HID_USAGE_Y = 0x31
HID_USAGE_Z = 0x32
HID_USAGE_RX = 0x33
HID_USAGE_RY = 0x34
HID_USAGE_RZ = 0x35
HID_USAGE_SL0 = 0x36
HID_USAGE_SL1 = 0x37
HID_USAGE_WHL = 0x38
HID_USAGE_POV = 0x39

# 轴名 → HID Usage 映射
AXIS_NAME_TO_HID = {
    "X": HID_USAGE_X,
    "Y": HID_USAGE_Y,
    "Z": HID_USAGE_Z,
    "RX": HID_USAGE_RX,
    "RY": HID_USAGE_RY,
    "RZ": HID_USAGE_RZ,
    "SL0": HID_USAGE_SL0,
    "SL1": HID_USAGE_SL1,
    "WHL": HID_USAGE_WHL,
    "POV": HID_USAGE_POV,
}

# vJoy 设备状态
VJD_STAT_OWN = 0  # 已拥有
VJD_STAT_FREE = 1  # 空闲
VJD_STAT_BUSY = 2  # 被其他程序占用
VJD_STAT_MISS = 3  # 不存在


class VJoyDevice:
    """通过 ctypes 直接调用 vJoyInterface.dll 的虚拟设备封装。

    不依赖 pyvjoy 第三方库，直接使用 Windows DLL。
    """

    def __init__(self, device_id: int = 1) -> None:
        self._device_id = device_id
        self._dll: Optional[ctypes.CDLL] = None
        self._connected = False

    def connect(self) -> bool:
        """加载 DLL 并获取 vJoy 设备。返回是否成功。"""
        if platform.system() != "Windows":
            logger.error("vJoy 只支持 Windows 平台")
            return False

        # 搜索 vJoyInterface.dll
        dll_path = self._find_dll()
        if dll_path is None:
            logger.error(
                "未找到 vJoyInterface.dll。请确认已安装 vJoy 驱动。"
            )
            return False

        try:
            self._dll = ctypes.CDLL(str(dll_path))
        except OSError as e:
            logger.error("加载 vJoyInterface.dll 失败: %s", e)
            return False

        self._setup_signatures()

        # 检查 vJoy 是否启用
        if not self._dll.vJoyEnabled():
            logger.error("vJoy 驱动未启用")
            return False

        # 检查驱动版本匹配
        major = ctypes.c_uint()
        minor = ctypes.c_uint()
        if not self._dll.DriverMatch(ctypes.byref(major), ctypes.byref(minor)):
            logger.warning(
                "vJoy DLL/驱动版本不匹配 (DLL %d.%d), 部分功能可能异常",
                major.value, minor.value,
            )

        # 检查目标设备状态
        status = self._dll.GetVJDStatus(self._device_id)
        if status == VJD_STAT_MISS:
            logger.error("vJoy 设备 %d 不存在，请在 vJoy 配置中启用", self._device_id)
            return False
        if status == VJD_STAT_BUSY:
            logger.error("vJoy 设备 %d 被其他程序占用", self._device_id)
            return False

        # 获取设备
        if not self._dll.AcquireVJD(self._device_id):
            logger.error("获取 vJoy 设备 %d 失败", self._device_id)
            return False

        # 重置设备
        self._dll.ResetVJD(self._device_id)

        self._connected = True
        logger.info(
            "vJoy 设备 %d 已连接 (DLL: %s)", self._device_id, dll_path,
        )
        return True

    @property
    def connected(self) -> bool:
        return self._connected

    # =========================================================================
    # 按钮操作
    # =========================================================================

    def press_button(self, btn: int) -> None:
        """按下指定按钮 (1-based)。"""
        if not self._connected:
            return
        self._dll.SetBtn(True, self._device_id, ctypes.c_ubyte(btn))

    def release_button(self, btn: int) -> None:
        """释放指定按钮 (1-based)。"""
        if not self._connected:
            return
        self._dll.SetBtn(False, self._device_id, ctypes.c_ubyte(btn))

    def release_all_buttons(self) -> None:
        """释放所有按钮。"""
        if not self._connected:
            return
        for btn in range(1, TOTAL_BUTTONS + 1):
            self._dll.SetBtn(False, self._device_id, ctypes.c_ubyte(btn))

    # =========================================================================
    # 轴操作
    # =========================================================================

    def set_axis(self, axis_name: str, value: int) -> None:
        """设置轴值。

        Args:
            axis_name: "X", "Y", "Z", "RX", "RY", "RZ", "SL0", "SL1"
            value: 轴值 (VJOY_AXIS_MIN ~ VJOY_AXIS_MAX)
        """
        if not self._connected:
            return
        hid = AXIS_NAME_TO_HID.get(axis_name.upper())
        if hid is None:
            logger.warning("未知轴名: %s", axis_name)
            return
        value = max(VJOY_AXIS_MIN, min(VJOY_AXIS_MAX, value))
        self._dll.SetAxis(ctypes.c_long(value), self._device_id, ctypes.c_uint(hid))

    def reset_device(self) -> None:
        """重置设备：释放所有按钮，居中所有轴。"""
        if not self._connected:
            return
        self._dll.ResetVJD(self._device_id)

    def disconnect(self) -> None:
        """断开连接并释放设备。"""
        if self._connected and self._dll:
            self.release_all_buttons()
            self._dll.RelinquishVJD(self._device_id)
            self._connected = False
            logger.info("vJoy 设备 %d 已断开", self._device_id)

    # =========================================================================
    # DLL 签名设置
    # =========================================================================

    def _setup_signatures(self) -> None:
        """为 DLL 导出函数设置 ctypes 参数和返回类型。"""
        dll = self._dll

        # BOOL vJoyEnabled(void)
        dll.vJoyEnabled.restype = ctypes.wintypes.BOOL
        dll.vJoyEnabled.argtypes = []

        # BOOL DriverMatch(UINT *Major, UINT *Minor)
        dll.DriverMatch.restype = ctypes.wintypes.BOOL
        dll.DriverMatch.argtypes = [
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
        ]

        # UINT GetVJDStatus(UINT rID)
        dll.GetVJDStatus.restype = ctypes.c_uint
        dll.GetVJDStatus.argtypes = [ctypes.c_uint]

        # BOOL AcquireVJD(UINT rID)
        dll.AcquireVJD.restype = ctypes.wintypes.BOOL
        dll.AcquireVJD.argtypes = [ctypes.c_uint]

        # void RelinquishVJD(UINT rID)
        dll.RelinquishVJD.restype = None
        dll.RelinquishVJD.argtypes = [ctypes.c_uint]

        # BOOL ResetVJD(UINT rID)
        dll.ResetVJD.restype = ctypes.wintypes.BOOL
        dll.ResetVJD.argtypes = [ctypes.c_uint]

        # BOOL SetBtn(BOOL value, UINT rID, UCHAR button)
        dll.SetBtn.restype = ctypes.wintypes.BOOL
        dll.SetBtn.argtypes = [
            ctypes.wintypes.BOOL,
            ctypes.c_uint,
            ctypes.c_ubyte,
        ]

        # BOOL SetAxis(LONG value, UINT rID, UINT axis)
        dll.SetAxis.restype = ctypes.wintypes.BOOL
        dll.SetAxis.argtypes = [
            ctypes.c_long,
            ctypes.c_uint,
            ctypes.c_uint,
        ]

    # =========================================================================
    # DLL 搜索
    # =========================================================================

    @staticmethod
    def _find_dll() -> Optional[Path]:
        """搜索 vJoyInterface.dll。"""
        # 常见安装路径
        search_paths = [
            # vJoy 默认安装目录
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "vJoy" / "x64" / "vJoyInterface.dll",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "vJoy" / "vJoyInterface.dll",
            # SDK 路径
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "vJoy" / "SDK" / "x64" / "vJoyInterface.dll",
            # 相对于项目
            Path(__file__).resolve().parent.parent.parent / "lib" / "vJoyInterface.dll",
            # 系统路径尝试 ( ctypes.CDLL 会自动搜索 PATH )
            Path("vJoyInterface.dll"),
        ]

        # 添加 vJoy 安装注册表常见路径
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{8E526DBE-8A6A-4E42-B0FD-4E1D2D64D6B3}_is1",
            )
            install_dir, _ = winreg.QueryValueEx(key, "InstallLocation")
            if install_dir:
                search_paths.insert(0, Path(install_dir) / "x64" / "vJoyInterface.dll")
                search_paths.insert(1, Path(install_dir) / "vJoyInterface.dll")
            winreg.CloseKey(key)
        except Exception:
            pass

        for p in search_paths:
            if isinstance(p, Path) and p.is_file():
                return p

        # 最后让 ctypes 自己搜 PATH
        return None
