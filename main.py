"""TactileGear 入口 — 组装所有模块、启动线程、异常处理。"""

from __future__ import annotations

import atexit
import logging
import traceback

from src.core.config_manager import (
    get_active_profile_name,
    get_default_parameters,
    load_layouts,
    load_profiles,
    parse_profile,
)
from src.core.events import EventBus
from src.core.types import GearMode, LayoutID
from src.engine.loop import PhysicsLoop
from src.hardware.sdl_device import SDLDevice
from src.hardware.simhub_receiver import SimHubReceiver
from src.hardware.vjoy_device import VJoyDevice
from src.physics.force_engine import ForceEngine
from src.gui.app import TactileGearApp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("TactileGear")


class TactileGearRuntime:
    """管理 TactileGear 运行时生命周期。"""

    def __init__(self) -> None:
        self.event_bus = EventBus()
        self.physics_loop: PhysicsLoop | None = None
        self._force_engine: ForceEngine | None = None
        self._started = False

    def start_physics(self, sdl: SDLDevice) -> None:
        """设备连接后调用：创建并启动物理循环。"""
        if self._started:
            return
        self._started = True

        # 加载配置
        layouts = load_layouts()
        default_params = get_default_parameters()

        profiles = load_profiles()
        active_name = get_active_profile_name()
        if active_name in profiles:
            parsed = parse_profile(profiles[active_name])
            initial_mode = parsed["mode"]
            initial_layout = None
            if parsed["layout_id"] and parsed["layout_id"] in layouts:
                initial_layout = layouts[parsed["layout_id"]]
            params = parsed["parameters"]
        else:
            initial_mode = GearMode.HPATTERN
            initial_layout = list(layouts.values())[0] if layouts else None
            params = default_params

        # 创建 vJoy
        logger.info("初始化 vJoy...")
        vjoy = VJoyDevice(device_id=1)
        vjoy_connected = vjoy.connect()

        # SimHub
        logger.info("初始化 SimHub 接收器...")
        simhub = SimHubReceiver(port=20777)
        simhub_connected = simhub.start()

        # 更新 GUI 状态
        self.app.update_connection_status("vjoy", vjoy_connected)
        self.app.update_connection_status("simhub", simhub_connected)

        # 力反馈引擎
        self._force_engine = ForceEngine(sdl)

        # 物理循环
        self.physics_loop = PhysicsLoop(
            sdl_device=sdl,
            vjoy_device=vjoy,
            simhub_receiver=simhub,
            force_engine=self._force_engine,
            event_bus=self.event_bus,
            layouts=layouts,
            initial_mode=initial_mode,
            initial_layout=initial_layout,
            initial_params=params,
        )

        self.physics_loop.start()
        gui_queue = self.event_bus.subscribe()
        self.app.start_polling(gui_queue)

        logger.info("物理循环已启动")


def main() -> None:
    logger.info("=" * 50)
    logger.info("TactileGear 主动式力反馈控制器 v1.0")
    logger.info("=" * 50)

    runtime = TactileGearRuntime()

    # 1. 初始化 SDL（仅子系统）
    logger.info("初始化 SDL2...")
    sdl = SDLDevice()
    sdl_connected = sdl.init_sdl()

    # 2. 创建 GUI（传入 SDL 设备引用和连接回调）
    app = TactileGearApp(
        event_bus=runtime.event_bus,
        initial_params=get_default_parameters(),
        sdl_device=sdl if sdl_connected else None,
        on_device_connected=lambda idx: runtime.start_physics(sdl),
    )
    runtime.app = app

    # vJoy/SimHub 状态在物理循环启动时更新
    app.update_connection_status("moza", False)

    # 紧急安全退出
    def emergency_stop():
        logger.info("紧急停止: 释放所有力反馈效果")
        if runtime.physics_loop:
            try:
                runtime.physics_loop.stop()
            except Exception:
                pass
        try:
            sdl.stop_all()
        except Exception:
            pass

    atexit.register(emergency_stop)

    # 3. GUI 主循环
    try:
        logger.info("GUI 已启动 — 请在界面中选择并连接力反馈设备")
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C，正在停止...")
    except Exception as e:
        logger.error("未捕获的异常: %s", e)
        traceback.print_exc()
    finally:
        emergency_stop()
        sdl.disconnect()
        logger.info("TactileGear 已安全退出")


if __name__ == "__main__":
    main()
