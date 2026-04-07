"""SimHub 遥测数据 UDP 接收器。"""

from __future__ import annotations

import json
import logging
import socket
import struct
import threading
import time
from typing import Optional

from src.core.types import TelemetryData

logger = logging.getLogger(__name__)

# SimHub 默认端口
DEFAULT_SIMHUB_PORT = 20777
# 数据过期时间 (秒)
DATA_STALE_TIMEOUT = 2.0


class SimHubReceiver:
    """UDP 遥测数据接收器，在独立线程中运行。"""

    def __init__(self, port: int = DEFAULT_SIMHUB_PORT) -> None:
        self._port = port
        self._socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._data = TelemetryData()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> bool:
        """启动 UDP 接收线程。"""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind(("0.0.0.0", self._port))
            self._socket.settimeout(1.0)
        except Exception as e:
            logger.error("UDP 绑定端口 %d 失败: %s", self._port, e)
            return False

        self._running = True
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()
        logger.info("SimHub 接收器已启动，监听端口 %d", self._port)
        return True

    def stop(self) -> None:
        """停止接收线程。"""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._connected = False
        logger.info("SimHub 接收器已停止")

    def get_telemetry(self) -> TelemetryData:
        """获取最新遥测数据（线程安全）。"""
        with self._lock:
            data = TelemetryData(
                clutch_position=self._data.clutch_position,
                speed_kph=self._data.speed_kph,
                rpm=self._data.rpm,
                game_gear=self._data.game_gear,
                timestamp=self._data.timestamp,
            )
        # 检查数据是否过期
        if data.timestamp > 0 and (time.time() - data.timestamp) > DATA_STALE_TIMEOUT:
            # 数据过期，默认离合器踩下（安全）
            data.clutch_position = 1.0
        return data

    def get_clutch_position(self) -> float:
        """获取离合器位置 (快捷方法)。"""
        return self.get_telemetry().clutch_position

    def _receive_loop(self) -> None:
        """接收循环（在子线程中运行）。"""
        while self._running:
            try:
                data, addr = self._socket.recvfrom(4096)
                self._parse_packet(data)
                self._connected = True
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                logger.error("接收遥测数据异常: %s", e)
                self._connected = False

    def _parse_packet(self, data: bytes) -> None:
        """解析遥测数据包。

        支持两种格式:
        1. JSON 格式 (SimHub "Dash" 输出)
        2. 二进制格式 (未来扩展)
        """
        try:
            # 尝试 JSON 解析
            text = data.decode("utf-8")
            parsed = json.loads(text)

            clutch = float(parsed.get("clutch", 1.0))
            speed = float(parsed.get("speedKmh", 0.0))
            rpm = float(parsed.get("rpms", 0.0))
            gear = int(parsed.get("gear", 0))

            with self._lock:
                self._data.clutch_position = max(0.0, min(1.0, clutch))
                self._data.speed_kph = speed
                self._data.rpm = rpm
                self._data.game_gear = gear
                self._data.timestamp = time.time()

        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            # 非JSON格式，暂时忽略
            pass
        except Exception as e:
            logger.debug("解析遥测包失败: %s", e)
