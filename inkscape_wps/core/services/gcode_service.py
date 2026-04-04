"""G-code生成服务。"""

from __future__ import annotations

import logging
from typing import List, Tuple

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.core.gcode import order_paths_nearest_neighbor, paths_to_gcode
from inkscape_wps.core.types import Point, VectorPath


class GCodeService:
    """G-code生成和优化服务"""

    def __init__(self, config: MachineConfig):
        self.config = config
        self._logger = logging.getLogger(__name__)

    def generate_from_paths(self, paths: List[VectorPath],
                          optimize: bool = True) -> str:
        """从路径生成G-code"""
        try:
            # 路径优化
            if optimize:
                paths = self.optimize_paths(paths)

            # 生成G-code
            gcode = paths_to_gcode(
                paths=paths,
                cfg=self.config,
                program_prefix=self.config.gcode_program_prefix,
                program_suffix=self.config.gcode_program_suffix,
                g92_origin=self.config.gcode_g92_origin,
                add_m30=self.config.gcode_add_m30
            )

            self._logger.info(f"生成G-code完成，共 {len(paths)} 条路径")
            return gcode

        except Exception as e:
            self._logger.error(f"G-code生成失败: {e}")
            raise

    def optimize_paths(self, paths: List[VectorPath]) -> List[VectorPath]:
        """路径优化"""
        if not paths:
            return paths

        try:
            # 最近邻排序
            optimized = order_paths_nearest_neighbor(paths)

            # 移除过短路径
            min_length = float(getattr(self.config, "min_path_length", 0.1))
            filtered = [path for path in optimized if self._path_length(path) >= min_length]

            # 合并相邻路径（可选）
            if bool(getattr(self.config, "merge_adjacent_paths", True)):
                filtered = self._merge_adjacent_paths(filtered)

            self._logger.info(f"路径优化: {len(paths)} -> {len(filtered)} 条路径")
            return filtered

        except Exception as e:
            self._logger.error(f"路径优化失败: {e}")
            return paths

    def estimate_execution_time(self, gcode: str) -> float:
        """估算G-code执行时间（秒）"""
        try:
            lines = gcode.strip().split('\n')
            total_time = 0.0
            current = Point(0.0, 0.0)
            current_feed = float(getattr(self.config, "draw_feed_rate", 1000.0))

            for line in lines:
                line = line.strip()
                if not line or line.startswith(('(', ';', 'G20', 'G21', 'G90', 'G91')):
                    continue

                # 简单的时间估算逻辑
                if 'G1' in line or 'G0' in line:
                    # 提取移动距离和速度
                    next_point, distance = self._extract_movement(line, current)
                    speed = self._extract_feedrate(line, current_feed)

                    if distance > 0 and speed > 0:
                        # 时间 = 距离 / 速度
                        time = (distance / speed) * 60  # 转换为秒
                        total_time += time
                    if next_point is not None:
                        current = next_point
                    if speed > 0:
                        current_feed = speed

            return total_time

        except Exception as e:
            self._logger.error(f"执行时间估算失败: {e}")
            return 0.0

    def validate_gcode(self, gcode: str) -> Tuple[bool, List[str]]:
        """验证G-code语法"""
        errors = []

        try:
            lines = gcode.strip().split('\n')

            for i, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith(('(', ';')):
                    continue

                # 基本语法检查
                if not self._validate_line_syntax(line):
                    errors.append(f"第{i}行: 语法错误 - {line}")

                # GRBL兼容性检查
                if not self._validate_grbl_compatibility(line):
                    errors.append(f"第{i}行: GRBL不兼容 - {line}")

            return len(errors) == 0, errors

        except Exception as e:
            self._logger.error(f"G-code验证失败: {e}")
            return False, [f"验证过程出错: {str(e)}"]

    def _path_length(self, path: VectorPath) -> float:
        """计算路径长度"""
        if len(path.points) < 2:
            return 0.0

        total_length = 0.0
        for i in range(1, len(path.points)):
            p1, p2 = path.points[i - 1], path.points[i]
            dx, dy = p2.x - p1.x, p2.y - p1.y
            total_length += (dx * dx + dy * dy) ** 0.5

        return total_length

    def _merge_adjacent_paths(self, paths: List[VectorPath]) -> List[VectorPath]:
        """合并相邻路径"""
        if len(paths) < 2:
            return paths

        merged = []
        current_path = paths[0]

        for next_path in paths[1:]:
            # 检查是否相邻（终点到起点距离小于阈值）
            if self._paths_adjacent(current_path, next_path):
                # 合并路径
                current_path = self._merge_two_paths(current_path, next_path)
            else:
                merged.append(current_path)
                current_path = next_path

        merged.append(current_path)
        return merged

    def _paths_adjacent(self, path1: VectorPath, path2: VectorPath,
                       threshold: float = 1.0) -> bool:
        """检查两条路径是否相邻"""
        if not path1.points or not path2.points:
            return False

        # 检查path1的终点到path2的起点的距离
        end_point = path1.points[-1]
        start_point = path2.points[0]

        dx = end_point.x - start_point.x
        dy = end_point.y - start_point.y
        distance = (dx*dx + dy*dy) ** 0.5

        return distance <= threshold

    def _merge_two_paths(self, path1: VectorPath, path2: VectorPath) -> VectorPath:
        """合并两条路径"""
        return VectorPath(
            tuple(path1.points + path2.points),
            pen_down=path1.pen_down or path2.pen_down,
        )

    def _extract_movement(self, line: str, current: Point) -> Tuple[Point | None, float]:
        """提取移动后的坐标和位移长度。"""
        import re

        x_match = re.search(r'X([-+]?\d*\.?\d+)', line)
        y_match = re.search(r'Y([-+]?\d*\.?\d+)', line)
        if not x_match and not y_match:
            return None, 0.0

        next_point = Point(
            float(x_match.group(1)) if x_match else current.x,
            float(y_match.group(1)) if y_match else current.y,
        )
        distance = (
            (next_point.x - current.x) ** 2 + (next_point.y - current.y) ** 2
        ) ** 0.5
        return next_point, distance

    def _extract_feedrate(self, line: str, current_feed: float) -> float:
        """提取进给速度"""
        import re

        f_match = re.search(r'F([-+]?\d*\.?\d+)', line)
        if f_match:
            return float(f_match.group(1))
        return current_feed

    def _validate_line_syntax(self, line: str) -> bool:
        """验证单行G-code语法"""
        # 简化的语法检查
        valid_commands = ['G0', 'G1', 'G2', 'G3', 'G20', 'G21', 'G90', 'G91',
                         'M0', 'M2', 'M3', 'M5', 'M30']

        # 检查是否有有效的G/M代码
        has_valid_command = any(cmd in line for cmd in valid_commands)

        # 如果没有G/M代码，检查是否是纯坐标移动
        if not has_valid_command:
            has_coordinates = any(coord in line for coord in ['X', 'Y', 'Z', 'F'])
            return has_coordinates

        return True

    def _validate_grbl_compatibility(self, line: str) -> bool:
        """验证GRBL兼容性"""
        # GRBL不支持的命令
        unsupported = ['G40', 'G41', 'G42', 'G43', 'G44', 'G49',  # 刀具补偿
                      'G61', 'G64',  # 精确停止
                      'G93', 'G94', 'G95',  # 进给模式
                      'G54', 'G55', 'G56', 'G57', 'G58', 'G59']  # 工件坐标系

        return not any(cmd in line for cmd in unsupported)
