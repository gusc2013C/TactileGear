"""TactileGear 入口 — 组装所有模块、启动线程、异常处理。"""

from __future__ import annotations

import atexit
import logging
import sys
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


def main() -> None:
    logger.info("=" * 50)
    logger.info("TactileGear 主动式力反馈控制器 v1.0")
    logger.info("=" * 50)

    # 1. 加载配置
    layouts = load_layouts()
    default_params = get_default_parameters()

    # 加载用户配置
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

    # 2. 创建事件总线
    event_bus = EventBus()

    # 3. 初始化硬件
    logger.info("初始化 vJoy...")
    vjoy = VJoyDevice(device_id=1)
    vjoy_connected = vjoy.connect()

    logger.info("初始化 SDL2...")
    sdl = SDLDevice(joystick_name_pattern="MOZA")
    sdl_connected = sdl.connect()

    logger.info("初始化 SimHub 接收器...")
    simhub = SimHubReceiver(port=20777)
    simhub_connected = simhub.start()

    # 4. 创建力反馈引擎
    force_engine = ForceEngine(sdl)

    # 5. 创建物理循环
    physics_loop = PhysicsLoop(
        sdl_device=sdl,
        vjoy_device=vjoy,
        simhub_receiver=simhub,
        force_engine=force_engine,
        event_bus=event_bus,
        layouts=layouts,
        initial_mode=initial_mode,
        initial_layout=initial_layout,
        initial_params=params,
    )

    # 注册安全退出
    def emergency_stop():
        logger.info("紧急停止: 释放所有力反馈效果")
        try:
            physics_loop.stop()
        except Exception:
            pass
        try:
            sdl.stop_all()
        except Exception:
            pass
        try:
            vjoy.release_all_buttons()
        except Exception:
            pass

    atexit.register(emergency_stop)

    # 6. 启动物理循环
    physics_loop.start()

    # 7. 启动 GUI (主线程)
    try:
        app = TactileGearApp(event_bus=event_bus, initial_params=params)

        # 更新连接状态
        app.update_connection_status("moza", sdl_connected)
        app.update_connection_status("vjoy", vjoy_connected)
        app.update_connection_status("simhub", simhub_connected)

        # 启动状态轮询
        gui_queue = event_bus.subscribe()
        app.start_polling(gui_queue)

        logger.info("GUI 已启动")
        app.mainloop()

    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C，正在停止...")
    except Exception as e:
        logger.error("未捕获的异常: %s", e)
        traceback.print_exc()
    finally:
        emergency_stop()
        simhub.stop()
        sdl.disconnect()
        vjoy.disconnect()
        logger.info("TactileGear 已安全退出")


if __name__ == "__main__":
    main()
