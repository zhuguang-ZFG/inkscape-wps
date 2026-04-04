"""G-code实时预览组件"""

from __future__ import annotations

from typing import List, Optional

from inkscape_wps.core.types import Point, VectorPath
from inkscape_wps.ui.qt_compat import (
    QColor,
    QPainter,
    QPen,
    QPointF,
    Qt,
    QTimer,
    QWidget,
)


class GCodePreviewWidget(QWidget):
    """G-code实时预览组件"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)

        # 预览状态
        self.paths: List[VectorPath] = []
        self.current_position = Point(0, 0)
        self.is_drawing = False
        self.scale = 1.0
        self.offset = QPointF(0, 0)

        # 绘制设置
        self.drawing_color = QColor(0, 0, 255)  # 蓝色绘制线
        self.moving_color = QColor(255, 0, 0, 128)  # 半透明红色移动线
        self.position_color = QColor(255, 0, 0)  # 红色当前位置
        self.grid_color = QColor(200, 200, 200, 100)  # 浅灰色网格

        # 动画定时器
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._update_animation)
        self.animation_speed = 1.0
        self.animation_progress = 0.0

        # 启用鼠标交互
        self.setMouseTracking(True)
        self._last_mouse_pos = None
        self._dragging = False

    def set_paths(self, paths: List[VectorPath]) -> None:
        """设置要预览的路径"""
        self.paths = paths
        self.animation_progress = 0.0
        self._calculate_view()
        self.update()

    def start_animation(self, speed: float = 1.0) -> None:
        """开始动画"""
        self.animation_speed = speed
        self.animation_progress = 0.0
        self.animation_timer.start(50)  # 20 FPS

    def stop_animation(self) -> None:
        """停止动画"""
        self.animation_timer.stop()

    def reset_view(self) -> None:
        """重置视图"""
        self.scale = 1.0
        self.offset = QPointF(0, 0)
        self._calculate_view()
        self.update()

    def fit_to_view(self) -> None:
        """适应视图"""
        if not self.paths:
            return

        self._calculate_view(fit_to_content=True)
        self.update()

    def paintEvent(self, event) -> None:
        """绘制事件"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 清空背景
        painter.fillRect(self.rect(), Qt.GlobalColor.white)

        # 绘制网格
        self._draw_grid(painter)

        # 绘制路径
        self._draw_paths(painter)

        # 绘制当前位置
        self._draw_current_position(painter)

        # 绘制边框
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def wheelEvent(self, event) -> None:
        """鼠标滚轮事件 - 缩放"""
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 0.9

        # 以鼠标位置为中心的缩放
        mouse_pos = event.position()
        self._zoom_at_position(mouse_pos, factor)

    def mousePressEvent(self, event) -> None:
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._dragging = True
            self._last_mouse_pos = event.position()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        """鼠标移动事件"""
        if self._dragging and self._last_mouse_pos:
            current_pos = event.position()
            delta = current_pos - self._last_mouse_pos

            # 移动视图
            self.offset += delta
            self._last_mouse_pos = current_pos
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        """鼠标释放事件"""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._dragging = False
            self._last_mouse_pos = None

    def _calculate_view(self, fit_to_content: bool = False) -> None:
        """计算视图参数"""
        if not self.paths:
            return

        if fit_to_content:
            # 计算内容边界
            min_x = min_y = float('inf')
            max_x = max_y = float('-inf')

            for path in self.paths:
                for point in path:
                    min_x = min(min_x, point.x)
                    min_y = min(min_y, point.y)
                    max_x = max(max_x, point.x)
                    max_y = max(max_y, point.y)

            if min_x != float('inf'):
                # 计算适应视图的缩放和偏移
                content_width = max_x - min_x
                content_height = max_y - min_y
                widget_width = self.width() - 40  # 留边距
                widget_height = self.height() - 40

                scale_x = widget_width / content_width if content_width > 0 else 1
                scale_y = widget_height / content_height if content_height > 0 else 1
                self.scale = min(scale_x, scale_y, 10.0)  # 限制最大缩放

                # 居中显示
                center_x = (min_x + max_x) / 2
                center_y = (min_y + max_y) / 2
                self.offset = QPointF(
                    self.width() / 2 - center_x * self.scale,
                    self.height() / 2 + center_y * self.scale  # Y轴翻转
                )
        else:
            # 确保视图居中
            if self.scale == 1.0 and self.offset == QPointF(0, 0):
                self.offset = QPointF(
                    self.width() / 2,
                    self.height() / 2
                )

    def _draw_grid(self, painter: QPainter) -> None:
        """绘制网格"""
        painter.setPen(QPen(self.grid_color, 1))

        # 计算网格范围和间距
        grid_spacing = 10 * self.scale
        if grid_spacing < 5:
            grid_spacing = 10 * self.scale
        elif grid_spacing > 50:
            grid_spacing = 5 * self.scale

        # 绘制垂直线
        x = self.offset.x() % grid_spacing
        while x < self.width():
            painter.drawLine(int(x), 0, int(x), self.height())
            x += grid_spacing

        # 绘制水平线
        y = self.offset.y() % grid_spacing
        while y < self.height():
            painter.drawLine(0, int(y), self.width(), int(y))
            y += grid_spacing

    def _draw_paths(self, painter: QPainter) -> None:
        """绘制路径"""
        if not self.paths:
            return

        # 计算动画要显示的路径数量
        total_points = sum(len(path) for path in self.paths)
        animated_points = int(total_points * self.animation_progress)

        current_points = 0
        for path in self.paths:
            if current_points >= animated_points:
                break

            if len(path) < 2:
                continue

            # 绘制路径段
            for i in range(1, len(path)):
                if current_points >= animated_points:
                    break

                p1 = self._world_to_screen(path[i-1])
                p2 = self._world_to_screen(path[i])

                # 设置画笔颜色
                if self.is_drawing:
                    painter.setPen(QPen(self.drawing_color, 2))
                else:
                    painter.setPen(QPen(self.moving_color, 1, Qt.PenStyle.DashLine))

                painter.drawLine(p1, p2)
                current_points += 1

    def _draw_current_position(self, painter: QPainter) -> None:
        """绘制当前位置"""
        if not self.paths:
            return

        pos = self._world_to_screen(self.current_position)

        # 绘制位置指示器
        painter.setPen(QPen(self.position_color, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # 十字准线
        size = 10
        painter.drawLine(pos.x() - size, pos.y(), pos.x() + size, pos.y())
        painter.drawLine(pos.x(), pos.y() - size, pos.x(), pos.y() + size)

        # 小圆点
        painter.setBrush(self.position_color)
        painter.drawEllipse(pos, 3, 3)

    def _world_to_screen(self, point: Point) -> QPointF:
        """世界坐标转屏幕坐标"""
        return QPointF(
            self.offset.x() + point.x * self.scale,
            self.offset.y() - point.y * self.scale  # Y轴翻转
        )

    def _zoom_at_position(self, pos: QPointF, factor: float) -> None:
        """在指定位置缩放"""
        # 计算缩放前的世界坐标
        world_pos = QPointF(
            (pos.x() - self.offset.x()) / self.scale,
            (self.offset.y() - pos.y()) / self.scale
        )

        # 应用缩放
        self.scale *= factor

        # 计算缩放后的偏移，保持鼠标位置不变
        self.offset = QPointF(
            pos.x() - world_pos.x() * self.scale,
            pos.y() + world_pos.y() * self.scale
        )

        self.update()

    def _update_animation(self) -> None:
        """更新动画"""
        self.animation_progress += 0.01 * self.animation_speed
        if self.animation_progress >= 1.0:
            self.animation_progress = 1.0
            self.animation_timer.stop()

        self.update()