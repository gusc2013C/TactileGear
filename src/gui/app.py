"""CustomTkinter 主窗口。"""

from __future__ import annotations

import queue
import logging
from typing import Optional

import customtkinter as ctk

from src.core.events import (
    EventBus,
    ModeChangeRequested,
    ParametersUpdated,
    ShutdownRequested,
    StatusUpdate,
)
from src.core.types import GearMode, ProfileParameters
from src.gui.status_bar import StatusBar
from src.gui.mode_selector import ModeSelector
from src.gui.layout_configurator import LayoutConfigurator
from src.gui.param_tuner import ParamTuner
from src.gui.profile_manager import ProfileManager

logger = logging.getLogger(__name__)


class TactileGearApp(ctk.CTk):
    """TactileGear 主 GUI 窗口。"""

    def __init__(self, event_bus: EventBus, initial_params: ProfileParameters) -> None:
        super().__init__()

        self._event_bus = event_bus
        self._params = initial_params
        self._gui_queue: Optional[queue.Queue] = None

        # 窗口设置
        self.title("TactileGear - 主动式力反馈控制器")
        self.geometry("900x700")
        self.minsize(800, 600)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # 构建 UI
        self._build_ui()

        # 关闭窗口处理
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def start_polling(self, gui_queue: queue.Queue) -> None:
        """开始轮询物理线程的状态更新。"""
        self._gui_queue = gui_queue
        self._poll_queue()

    def _build_ui(self) -> None:
        """构建所有 UI 组件。"""
        # 顶部状态栏
        self._status_bar = StatusBar(self)
        self._status_bar.pack(fill="x", padx=10, pady=(10, 5))

        # 模式选择器
        self._mode_selector = ModeSelector(self, on_mode_change=self._on_mode_change)
        self._mode_selector.pack(fill="x", padx=10, pady=5)

        # 中间区域：左=排布配置，右=参数调节
        middle_frame = ctk.CTkFrame(self)
        middle_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 排布配置器
        self._layout_configurator = LayoutConfigurator(
            middle_frame,
            on_layout_change=self._on_layout_change,
            on_unlock_method_change=self._on_unlock_method_change,
        )
        self._layout_configurator.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        # 参数调节
        self._param_tuner = ParamTuner(
            middle_frame,
            params=self._params,
            on_params_change=self._on_params_change,
        )
        self._param_tuner.pack(side="right", fill="both", expand=True, padx=5, pady=5)

        # 底部：配置管理
        self._profile_manager = ProfileManager(self)
        self._profile_manager.pack(fill="x", padx=10, pady=(5, 10))

        # 底部状态标签
        self._status_label = ctk.CTkLabel(
            self, text="就绪", text_color="gray",
        )
        self._status_label.pack(fill="x", padx=10, pady=(0, 5))

    # =========================================================================
    # 事件处理
    # =========================================================================

    def _on_mode_change(self, mode: GearMode) -> None:
        """模式切换回调。"""
        self._event_bus.publish(ModeChangeRequested(new_mode=mode))
        self._status_label.configure(text=f"切换模式: {mode.value}")

        # 根据模式显示/隐藏排布配置
        self._layout_configurator.set_visible(mode == GearMode.HPATTERN)

    def _on_layout_change(self, layout_id: str) -> None:
        """排布切换回调。"""
        from src.core.types import LayoutID
        try:
            lid = LayoutID(layout_id)
            from src.core.events import LayoutChangeRequested
            self._event_bus.publish(LayoutChangeRequested(layout_id=lid))
            self._status_label.configure(text=f"切换排布: {layout_id}")
        except ValueError:
            logger.error("无效的排布 ID: %s", layout_id)

    def _on_unlock_method_change(self, method: str) -> None:
        """倒档解锁方式切换回调。"""
        from src.core.events import ReverseUnlockMethodChanged
        self._event_bus.publish(ReverseUnlockMethodChanged(method=method))

    def _on_params_change(self, params: ProfileParameters) -> None:
        """参数变化回调。"""
        self._params = params
        self._event_bus.publish(ParametersUpdated(params=params))

    # =========================================================================
    # 队列轮询
    # =========================================================================

    def _poll_queue(self) -> None:
        """从物理线程接收状态更新。"""
        if not self._gui_queue:
            return

        while True:
            try:
                event = self._gui_queue.get_nowait()
            except queue.Empty:
                break

            if isinstance(event, StatusUpdate):
                self._update_status(event)
            elif isinstance(event, ShutdownRequested):
                self.destroy()
                return

        self.after(50, self._poll_queue)  # 20Hz 轮询

    def _update_status(self, status: StatusUpdate) -> None:
        """更新 GUI 状态显示。"""
        self._status_label.configure(
            text=(
                f"模式: {status.current_mode.value} | "
                f"档位: {status.current_gear} | "
                f"位置: ({status.position_x:.2f}, {status.position_y:.2f}) | "
                f"FPS: {status.fps:.0f}"
            )
        )

    # =========================================================================
    # 公共方法
    # =========================================================================

    def update_connection_status(self, device: str, connected: bool) -> None:
        """更新连接状态指示灯。"""
        self._status_bar.set_status(device, connected)

    def _on_closing(self) -> None:
        """窗口关闭处理。"""
        self._event_bus.publish(ShutdownRequested())
        self.destroy()
