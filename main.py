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


def main() -> None:
    logger.info("=" * 50)
    logger.info("TactileGear 主动式力反馈控制器 v1.0")
    logger.info("=" * 50)

    # 1. 加载配置
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

    # 2. 创建事件总线
    event_bus = EventBus()

    # 3. 初始化 vJoy
    logger.info("初始化 vJoy...")
    vjoy = VJoyDevice(device_id=1)
    vjoy_connected = vjoy.connect()

    # 4. 初始化 SDL（仅子系统，不打开设备）
    logger.info("初始化 SDL2...")
    sdl = SDLDevice()
    sdl_connected = sdl.init_sdl()

    # 5. 枚举设备
    devices = sdl.enumerate_joysticks() if sdl_connected else []
    logger.info("检测到 %d 个摇杆设备", len(devices))
    for d in devices:
        logger.info("  [%d] %s  (GUID: %s)", d["index"], d["name"], d["guid"])

    # 6. SimHub
    logger.info("初始化 SimHub 接收器...")
    simhub = SimHubReceiver(port=20777)
    simhub_connected = simhub.start()

    # 7. 创建 GUI — 先显示主窗口，然后弹出设备选择
    app = TactileGearApp(event_bus=event_bus, initial_params=params)
    app.update_connection_status("vjoy", vjoy_connected)
    app.update_connection_status("simhub", simhub_connected)
    app.update_connection_status("moza", False)

    # 显示设备选择对话框
    if devices:
        from src.gui.device_select import DeviceSelectDialog
        dialog = DeviceSelectDialog(app, devices)
        app.wait_window(dialog)
        selected = dialog.selected_index

        if selected is not None:
            logger.info("用户选择了设备 [%d]", selected)
            if sdl.open_joystick(selected):
                app.update_connection_status("moza", True)
            else:
                logger.error("打开摇杆失败")
        else:
            logger.warning("用户跳过了设备选择")
    else:
        logger.warning("未检测到任何摇杆设备")

    # 8. 创建力反馈引擎 + 物理循环
    force_engine = ForceEngine(sdl)
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

    # 紧急安全退出
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

    # 9. 启动物理循环
    physics_loop.start()

    # 10. 启动 GUI 主循环
    gui_queue = event_bus.subscribe()
    app.start_polling(gui_queue)

    try:
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
