"""100Hz 物理主循环 — 系统心跳。"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from src.core.events import (
    EventBus,
    LayoutChangeRequested,
    ModeChangeRequested,
    ParametersUpdated,
    ShutdownRequested,
    StatusUpdate,
)
from src.core.types import (
    PHYSICS_DT,
    GearMode,
    LayoutDefinition,
    LayoutID,
    ProfileParameters,
    ReverseUnlockMethod,
)
from src.hardware.sdl_device import SDLDevice
from src.hardware.simhub_receiver import SimHubReceiver
from src.hardware.vjoy_device import VJoyDevice
from src.physics.force_engine import ForceEngine
from src.physics.force_types import VJoyAction
from src.state.mode_base import ModeController
from src.state.mode_handbrake import HandbrakeController
from src.state.mode_hpattern import HPatternController
from src.state.mode_sequential import SequentialController

logger = logging.getLogger(__name__)


class PhysicsLoop:
    """100Hz 物理主循环。

    读硬件 → 模式更新 → 写 vJoy + FFB → 发布状态。
    """

    def __init__(
        self,
        sdl_device: SDLDevice,
        vjoy_device: VJoyDevice,
        simhub_receiver: SimHubReceiver,
        force_engine: ForceEngine,
        event_bus: EventBus,
        layouts: dict[LayoutID, LayoutDefinition],
        initial_mode: GearMode = GearMode.HPATTERN,
        initial_layout: Optional[LayoutDefinition] = None,
        initial_params: Optional[ProfileParameters] = None,
    ) -> None:
        self._sdl = sdl_device
        self._vjoy = vjoy_device
        self._simhub = simhub_receiver
        self._force_engine = force_engine
        self._event_bus = event_bus
        self._params = initial_params or ProfileParameters()
        self._layouts = layouts

        # 创建事件队列
        self._event_queue = event_bus.subscribe()

        # 初始化模式控制器
        self._current_mode = initial_mode
        self._mode_controller: Optional[ModeController] = None
        self._current_layout = initial_layout
        self._reverse_unlock_method = ReverseUnlockMethod.GRAVITY_BREAKTHROUGH

        # 线程控制
        self._thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._fps = 0.0
        self._frame_count = 0
        self._fps_timer = time.perf_counter()

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def current_mode(self) -> GearMode:
        return self._current_mode

    def start(self) -> None:
        """启动物理循环线程。"""
        # 初始化当前模式控制器
        self._create_mode_controller(self._current_mode)

        # 进入模式
        if self._mode_controller:
            enter_actions = self._mode_controller.enter()
            self._execute_vjoy_actions(enter_actions)

        self._shutdown_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("物理循环已启动 @ %d Hz", int(1.0 / PHYSICS_DT))

    def stop(self) -> None:
        """停止物理循环线程。"""
        self._shutdown_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        # 清理
        if self._mode_controller:
            exit_actions = self._mode_controller.exit()
            self._execute_vjoy_actions(exit_actions)
        self._force_engine.stop_and_clear()
        logger.info("物理循环已停止")

    # =========================================================================
    # 主循环
    # =========================================================================

    def _run_loop(self) -> None:
        """物理循环主函数。"""
        while not self._shutdown_event.is_set():
            tick_start = time.perf_counter()

            # 1. 处理 GUI 事件
            self._process_events()

            # 2. 读取硬件输入
            position = self._sdl.read_normalized_position()
            modifier = self._sdl.read_modifier_button()
            clutch = self._simhub.get_clutch_position()

            # 3. 更新模式控制器
            if self._mode_controller:
                result = self._mode_controller.update(
                    position, modifier, clutch, PHYSICS_DT,
                )

                # 4. 应用 vJoy 输出
                self._execute_vjoy_actions(result.vjoy_actions)

                # 5. 应用 FFB 力
                self._force_engine.apply_forces(result.force_requests)

            # 6. 更新 FPS 统计
            self._update_fps()

            # 7. 发布状态到 GUI (每 5 帧一次，降低 GUI 负载)
            if self._frame_count % 5 == 0:
                self._publish_status(position)

            # 8. 精确计时维持 100Hz
            elapsed = time.perf_counter() - tick_start
            sleep_time = PHYSICS_DT - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    # =========================================================================
    # 事件处理
    # =========================================================================

    def _process_events(self) -> None:
        """处理来自 GUI 的事件。"""
        while True:
            try:
                event = self._event_queue.get_nowait()
            except Exception:
                break

            if isinstance(event, ModeChangeRequested):
                self._switch_mode(event.new_mode)

            elif isinstance(event, LayoutChangeRequested):
                self._switch_layout(event.layout_id)

            elif isinstance(event, ParametersUpdated):
                self._params = event.params
                if self._mode_controller:
                    self._mode_controller.update_params(event.params)

            elif isinstance(event, ShutdownRequested):
                self._shutdown_event.set()

    def _switch_mode(self, new_mode: GearMode) -> None:
        """原子模式切换。"""
        logger.info("切换模式: %s -> %s", self._current_mode.value, new_mode.value)

        # 1. 退出旧模式
        if self._mode_controller:
            exit_actions = self._mode_controller.exit()
            self._execute_vjoy_actions(exit_actions)
        self._force_engine.stop_and_clear()

        # 2. 重置 vJoy
        self._vjoy.release_all_buttons()

        # 3. 切换
        self._current_mode = new_mode
        self._create_mode_controller(new_mode)

        # 4. 进入新模式
        if self._mode_controller:
            enter_actions = self._mode_controller.enter()
            self._execute_vjoy_actions(enter_actions)

    def _switch_layout(self, layout_id) -> None:
        """切换 H 档排布。"""
        if isinstance(self._mode_controller, HPatternController):
            if layout_id in self._layouts:
                self._current_layout = self._layouts[layout_id]
                self._mode_controller.set_layout(self._layouts[layout_id])

    # =========================================================================
    # 模式控制器创建
    # =========================================================================

    def _create_mode_controller(self, mode: GearMode) -> None:
        """根据模式创建对应的控制器。"""
        if mode == GearMode.HPATTERN:
            layout = self._current_layout
            if layout is None and self._layouts:
                layout = list(self._layouts.values())[0]
            if layout is None:
                layout = LayoutDefinition(
                    layout_id=LayoutID.CIVILIAN_6R_LEFT,
                    display_name="Default",
                )
            self._mode_controller = HPatternController(
                params=self._params,
                layout=layout,
                reverse_unlock_method=self._reverse_unlock_method,
            )
        elif mode == GearMode.SEQUENTIAL:
            self._mode_controller = SequentialController(self._params)
        elif mode == GearMode.HANDBRAKE:
            self._mode_controller = HandbrakeController(self._params)
        elif mode == GearMode.AUTO_PRND:
            self._mode_controller = AutoPRNDController(self._params)

    # =========================================================================
    # 辅助方法
    # =========================================================================

    def _execute_vjoy_actions(self, actions: list) -> None:
        """执行 vJoy 动作列表。"""
        for action in actions:
            if isinstance(action, VJoyAction):
                if action.action_type == "press_button" and action.button:
                    self._vjoy.press_button(action.button)
                elif action.action_type == "release_button" and action.button:
                    self._vjoy.release_button(action.button)
                elif action.action_type == "set_axis" and action.axis and action.value is not None:
                    self._vjoy.set_axis(action.axis, action.value)

    def _update_fps(self) -> None:
        """更新 FPS 统计。"""
        self._frame_count += 1
        now = time.perf_counter()
        elapsed = now - self._fps_timer
        if elapsed >= 1.0:
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_timer = now

    def _publish_status(self, position) -> None:
        """发布状态到 GUI。"""
        gear_name = "N"
        if self._mode_controller and self._mode_controller.current_gear:
            gear_name = self._mode_controller.current_gear.value

        self._event_bus.publish(StatusUpdate(
            current_mode=self._current_mode,
            current_gear=gear_name,
            position_x=position.x,
            position_y=position.y,
            fps=self._fps,
        ))
