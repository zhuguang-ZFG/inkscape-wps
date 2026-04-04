"""实时预览服务。"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.core.services.gcode_service import GCodeService
from inkscape_wps.core.services.serial_service import SerialService
from inkscape_wps.core.types import Point, VectorPath


class PreviewService:
    """实时预览服务"""

    def __init__(self, config: MachineConfig):
        self.config = config
        self.gcode_service = GCodeService(config)
        self.serial_service = SerialService(config)
        self._logger = logging.getLogger(__name__)

        # 预览状态
        self._current_paths: List[VectorPath] = []
        self._current_gcode: str = ""
        self._preview_callbacks = []

    def add_preview_callback(self, callback):
        """添加预览更新回调"""
        self._preview_callbacks.append(callback)

    def remove_preview_callback(self, callback):
        """移除预览更新回调"""
        if callback in self._preview_callbacks:
            self._preview_callbacks.remove(callback)

    def update_paths(self, paths: List[VectorPath]) -> None:
        """更新预览路径"""
        self._current_paths = paths
        self._generate_preview()

    def _generate_preview(self) -> None:
        """生成预览"""
        try:
            # 生成G-code
            self._current_gcode = self.gcode_service.generate_from_paths(
                self._current_paths, optimize=True
            )

            # 估算执行时间
            estimated_time = self.gcode_service.estimate_execution_time(
                self._current_gcode
            )

            # 验证G-code
            is_valid, errors = self.gcode_service.validate_gcode(
                self._current_gcode
            )

            # 准备预览数据
            preview_data = {
                'paths': self._current_paths,
                'gcode': self._current_gcode,
                'estimated_time': estimated_time,
                'is_valid': is_valid,
                'errors': errors,
                'path_count': len(self._current_paths),
                'gcode_lines': len(self._current_gcode.split('\n'))
            }

            # 通知回调
            for callback in self._preview_callbacks:
                try:
                    callback(preview_data)
                except Exception as e:
                    self._logger.error(f"预览回调执行失败: {e}")

        except Exception as e:
            self._logger.error(f"生成预览失败: {e}")

    async def simulate_execution(self, speed_multiplier: float = 1.0) -> None:
        """模拟执行"""
        if not self._current_gcode:
            return

        try:
            lines = self._current_gcode.strip().split('\n')
            current_position = Point(0, 0)
            is_drawing = False

            total_lines = max(1, len(lines))
            for index, line in enumerate(lines, start=1):
                line = line.strip()
                if not line or line.startswith(('(', ';')):
                    continue

                # 解析移动命令
                if 'G0' in line or 'G1' in line:
                    new_position, drawing = self._parse_move_command(
                        line, current_position
                    )

                    if new_position:
                        current_position = new_position
                        is_drawing = drawing

                        # 发送模拟更新
                        simulation_data = {
                            'position': current_position,
                            'is_drawing': is_drawing,
                            'command': line,
                            'progress': index / total_lines
                        }

                        for callback in self._preview_callbacks:
                            try:
                                callback(simulation_data)
                            except Exception as e:
                                self._logger.error(f"模拟回调执行失败: {e}")

                        # 根据速度倍率调整延迟
                        if speed_multiplier > 0:
                            import asyncio

                            delay = 0.1 / speed_multiplier
                            await asyncio.sleep(delay)

        except Exception as e:
            self._logger.error(f"模拟执行失败: {e}")

    def _parse_move_command(self, line: str, current_pos: Point) -> Tuple[Optional[Point], bool]:
        """解析移动命令"""
        import re

        # 确定移动类型
        is_drawing = 'G1' in line  # G1为绘制，G0为快速移动

        # 提取坐标
        x_match = re.search(r'X([-+]?\d*\.?\d+)', line)
        y_match = re.search(r'Y([-+]?\d*\.?\d+)', line)

        new_x = float(x_match.group(1)) if x_match else current_pos.x
        new_y = float(y_match.group(1)) if y_match else current_pos.y

        if x_match or y_match:
            return Point(new_x, new_y), is_drawing

        return None, is_drawing

    def get_preview_summary(self) -> dict:
        """获取预览摘要"""
        return {
            'path_count': len(self._current_paths),
            'gcode_lines': len(self._current_gcode.split('\n')) if self._current_gcode else 0,
            'estimated_time': (
                self.gcode_service.estimate_execution_time(self._current_gcode)
                if self._current_gcode
                else 0
            ),
            'has_errors': False  # 简化处理
        }
