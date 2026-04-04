"""串口通信服务"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.core.grbl import GrblController


class SerialService:
    """串口通信服务 - 封装GRBL设备通信"""

    def __init__(self, config: MachineConfig):
        self.config = config
        self._controller: Optional[GrblController] = None
        self._is_connected = False
        self._connection_status_callbacks: List[Callable[[bool], None]] = []
        self._logger = logging.getLogger(__name__)

    @property
    def is_connected(self) -> bool:
        """连接状态"""
        return self._is_connected

    def add_status_callback(self, callback: Callable[[bool], None]) -> None:
        """添加连接状态变化回调"""
        self._connection_status_callbacks.append(callback)

    def remove_status_callback(self, callback: Callable[[bool], None]) -> None:
        """移除连接状态变化回调"""
        if callback in self._connection_status_callbacks:
            self._connection_status_callbacks.remove(callback)

    async def connect(self, port: str, baudrate: int = 115200) -> bool:
        """连接到设备"""
        try:
            self._controller = GrblController(port, baudrate)
            await self._controller.connect()
            self._is_connected = True
            self._notify_status_change(True)
            self._logger.info(f"成功连接到设备: {port}")
            return True
        except Exception as e:
            self._logger.error(f"连接设备失败: {e}")
            self._is_connected = False
            self._notify_status_change(False)
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        if self._controller:
            try:
                await self._controller.disconnect()
            except Exception as e:
                self._logger.error(f"断开连接时出错: {e}")
            finally:
                self._controller = None
                self._is_connected = False
                self._notify_status_change(False)

    async def send_gcode(
        self,
        gcode: str,
        callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """发送G-code到设备"""
        if not self._is_connected or not self._controller:
            raise RuntimeError("设备未连接")

        try:
            lines = gcode.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line and not line.startswith('(') and not line.startswith(';'):
                    response = await self._controller.send_line(line)
                    if callback:
                        callback(response)

                    # 检查错误响应
                    if 'error' in response.lower():
                        self._logger.error(f"G-code执行错误: {response}")
                        return False

            return True
        except Exception as e:
            self._logger.error(f"发送G-code失败: {e}")
            return False

    async def send_gcode_streaming(self, gcode: str,
                                 progress_callback: Optional[Callable[[float], None]] = None,
                                 response_callback: Optional[Callable[[str], None]] = None) -> bool:
        """流式发送G-code（带缓冲区管理）"""
        if not self._is_connected or not self._controller:
            raise RuntimeError("设备未连接")

        try:
            lines = [line.strip() for line in gcode.strip().split('\n')
                    if line.strip() and not line.strip().startswith(('(', ';'))]

            total_lines = len(lines)
            sent_lines = 0

            for line in lines:
                # 等待缓冲区有空间
                while self._controller.buffer_full():
                    await asyncio.sleep(0.01)

                response = await self._controller.send_line(line)

                if response_callback:
                    response_callback(response)

                # 检查错误
                if 'error' in response.lower():
                    self._logger.error(f"G-code执行错误: {response}")
                    return False

                sent_lines += 1
                if progress_callback:
                    progress_callback(sent_lines / total_lines)

            return True
        except Exception as e:
            self._logger.error(f"流式发送G-code失败: {e}")
            return False

    def get_machine_status(self) -> Dict[str, Any]:
        """获取机器状态"""
        if not self._is_connected or not self._controller:
            return {'connected': False, 'state': 'disconnected'}

        try:
            return {
                'connected': True,
                'state': self._controller.get_state(),
                'position': self._controller.get_position(),
                'buffer_usage': self._controller.get_buffer_usage()
            }
        except Exception as e:
            self._logger.error(f"获取机器状态失败: {e}")
            return {'connected': True, 'state': 'error', 'error': str(e)}

    def emergency_stop(self) -> None:
        """紧急停止"""
        if self._controller:
            try:
                self._controller.emergency_stop()
            except Exception as e:
                self._logger.error(f"紧急停止失败: {e}")

    def _notify_status_change(self, connected: bool) -> None:
        """通知连接状态变化"""
        for callback in self._connection_status_callbacks:
            try:
                callback(connected)
            except Exception as e:
                self._logger.error(f"状态回调执行失败: {e}")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.disconnect()
