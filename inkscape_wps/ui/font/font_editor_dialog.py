"""自定义字库编辑器"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from inkscape_wps.core.types import Point, VectorPath
from inkscape_wps.ui.qt_compat import (
    QColor,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPainter,
    QPen,
    QPointF,
    QPushButton,
    QSplitter,
    Qt,
    QVBoxLayout,
    QWidget,
)


class StrokeCanvas(QWidget):
    """笔画绘制画布"""

    stroke_completed = None  # 将在子类中定义为pyqtSignal

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: white;")

        # 绘制状态
        self.current_stroke: List[Point] = []
        self.all_strokes: List[List[Point]] = []
        self.is_drawing = False

        # 视图参数
        self.scale = 1.0
        self.offset = QPointF(0, 0)

        # 绘制设置
        self.grid_color = QColor(200, 200, 200, 100)
        self.stroke_color = QColor(0, 0, 255)
        self.current_color = QColor(255, 0, 0)

        # 启用鼠标跟踪
        self.setMouseTracking(True)

    def start_new_stroke(self) -> None:
        """开始新笔画"""
        self.current_stroke = []
        self.is_drawing = True
        self.update()

    def add_point(self, point: Point) -> None:
        """添加点到当前笔画"""
        if self.is_drawing:
            self.current_stroke.append(point)
            self.update()

    def finish_stroke(self) -> None:
        """完成当前笔画"""
        if self.is_drawing and self.current_stroke:
            self.all_strokes.append(self.current_stroke.copy())
            self.current_stroke = []
            self.is_drawing = False
            self.update()

            # 发射信号
            if hasattr(self, 'stroke_completed'):
                self.stroke_completed.emit()

    def clear_all(self) -> None:
        """清除所有笔画"""
        self.current_stroke = []
        self.all_strokes = []
        self.is_drawing = False
        self.update()

    def undo_last_stroke(self) -> None:
        """撤销最后一笔"""
        if self.all_strokes:
            self.all_strokes.pop()
            self.update()

    def get_all_paths(self) -> List[VectorPath]:
        """获取所有路径"""
        paths = []
        for stroke in self.all_strokes:
            if len(stroke) > 1:
                paths.append(stroke)
        return paths

    def set_paths(self, paths: List[VectorPath]) -> None:
        """设置路径"""
        self.all_strokes = paths.copy()
        self.current_stroke = []
        self.is_drawing = False
        self.fit_to_paths()
        self.update()

    def fit_to_paths(self, padding: float = 24.0) -> None:
        """根据当前路径自动缩放并居中。"""
        points = [point for stroke in self.all_strokes for point in stroke]
        if len(points) < 2:
            self.scale = 1.0
            self.offset = QPointF(self.width() / 2.0, self.height() / 2.0)
            return
        min_x = min(point.x for point in points)
        max_x = max(point.x for point in points)
        min_y = min(point.y for point in points)
        max_y = max(point.y for point in points)
        span_x = max(1.0, max_x - min_x)
        span_y = max(1.0, max_y - min_y)
        avail_w = max(40.0, self.width() - padding * 2.0)
        avail_h = max(40.0, self.height() - padding * 2.0)
        self.scale = min(avail_w / span_x, avail_h / span_y)
        self.offset = QPointF(
            (self.width() - span_x * self.scale) / 2.0 - min_x * self.scale,
            (self.height() - span_y * self.scale) / 2.0 - min_y * self.scale,
        )

    def paintEvent(self, event) -> None:
        """绘制事件"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制网格
        self._draw_grid(painter)

        # 绘制已完成的笔画
        for stroke in self.all_strokes:
            self._draw_stroke(painter, stroke, self.stroke_color)

        # 绘制当前笔画
        if self.current_stroke:
            self._draw_stroke(painter, self.current_stroke, self.current_color)

    def mousePressEvent(self, event) -> None:
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_new_stroke()
            point = self._screen_to_world(event.position())
            self.add_point(point)

    def mouseMoveEvent(self, event) -> None:
        """鼠标移动事件"""
        if self.is_drawing and event.buttons() & Qt.MouseButton.LeftButton:
            point = self._screen_to_world(event.position())
            self.add_point(point)

    def mouseReleaseEvent(self, event) -> None:
        """鼠标释放事件"""
        if event.button() == Qt.MouseButton.LeftButton and self.is_drawing:
            self.finish_stroke()

    def resizeEvent(self, event) -> None:
        """尺寸变化后重新适配路径。"""
        super().resizeEvent(event)
        if self.all_strokes:
            self.fit_to_paths()

    def _draw_grid(self, painter: QPainter) -> None:
        """绘制网格"""
        painter.setPen(QPen(self.grid_color, 1))

        # 计算网格范围和间距
        grid_spacing = 20 * self.scale

        # 绘制垂直线
        start_x = int(self.offset.x() % grid_spacing)
        for x in range(start_x, self.width(), int(grid_spacing)):
            painter.drawLine(x, 0, x, self.height())

        # 绘制水平线
        start_y = int(self.offset.y() % grid_spacing)
        for y in range(start_y, self.height(), int(grid_spacing)):
            painter.drawLine(0, y, self.width(), y)

    def _draw_stroke(self, painter: QPainter, stroke: List[Point], color: QColor) -> None:
        """绘制笔画"""
        if len(stroke) < 2:
            return

        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # 绘制路径
        for i in range(1, len(stroke)):
            p1 = self._world_to_screen(stroke[i-1])
            p2 = self._world_to_screen(stroke[i])
            painter.drawLine(p1, p2)

    def _world_to_screen(self, point: Point) -> QPointF:
        """世界坐标转屏幕坐标"""
        return QPointF(
            self.offset.x() + point.x * self.scale,
            self.offset.y() + point.y * self.scale
        )

    def _screen_to_world(self, screen_pos: QPointF) -> Point:
        """屏幕坐标转世界坐标"""
        return Point(
            (screen_pos.x() - self.offset.x()) / self.scale,
            (screen_pos.y() - self.offset.y()) / self.scale
        )


class StrokeCanvasWithSignal(StrokeCanvas):
    """带信号的笔画画布"""

    stroke_completed = None  # 将在运行时设置

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        # 注意：这里不能直接定义pyqtSignal，需要在兼容层处理


class FontEditorDialog(QDialog):
    """自定义字库编辑器对话框"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("自定义字库编辑器")
        self.resize(1000, 700)

        # 当前编辑状态
        self.current_character = ""
        self.current_font_name = ""
        self.characters: dict = {}  # 字符 -> 笔画数据

        self._setup_ui()

    def _setup_ui(self) -> None:
        """设置界面"""
        layout = QVBoxLayout(self)

        # 顶部工具栏
        toolbar = QHBoxLayout()

        # 字符输入
        char_layout = QHBoxLayout()
        char_layout.addWidget(QLabel("字符:"))
        self.char_input = QComboBox()
        self.char_input.setEditable(True)
        self.char_input.setMaximumWidth(100)
        self.char_input.editTextChanged.connect(self._on_character_changed)
        char_layout.addWidget(self.char_input)

        # 字体名称
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("字体名称:"))
        self.font_name_input = QComboBox()
        self.font_name_input.setEditable(True)
        font_layout.addWidget(self.font_name_input)

        toolbar.addLayout(char_layout)
        toolbar.addLayout(font_layout)
        toolbar.addStretch()

        # 操作按钮
        self.new_btn = QPushButton("新建字体")
        self.save_btn = QPushButton("保存字体")
        self.load_btn = QPushButton("加载字体")

        self.new_btn.clicked.connect(self._new_font)
        self.save_btn.clicked.connect(self._save_font)
        self.load_btn.clicked.connect(self._load_font)

        toolbar.addWidget(self.new_btn)
        toolbar.addWidget(self.save_btn)
        toolbar.addWidget(self.load_btn)

        layout.addLayout(toolbar)

        # 主要内容区域
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：字符列表
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("字符列表:"))
        self.char_list = QListWidget()
        self.char_list.itemSelectionChanged.connect(self._on_list_selection_changed)
        left_layout.addWidget(self.char_list)

        # 字符操作按钮
        char_buttons = QHBoxLayout()
        self.add_char_btn = QPushButton("添加")
        self.delete_char_btn = QPushButton("删除")
        self.duplicate_btn = QPushButton("复制")

        self.add_char_btn.clicked.connect(self._add_character)
        self.delete_char_btn.clicked.connect(self._delete_character)
        self.duplicate_btn.clicked.connect(self._duplicate_character)

        char_buttons.addWidget(self.add_char_btn)
        char_buttons.addWidget(self.delete_char_btn)
        char_buttons.addWidget(self.duplicate_btn)
        left_layout.addLayout(char_buttons)

        splitter.addWidget(left_panel)

        # 右侧：笔画编辑区
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # 笔画画布
        canvas_layout = QVBoxLayout()
        canvas_layout.addWidget(QLabel("笔画编辑区:"))

        self.canvas = StrokeCanvas()
        canvas_layout.addWidget(self.canvas)

        # 笔画操作按钮
        stroke_buttons = QHBoxLayout()
        self.undo_btn = QPushButton("撤销")
        self.clear_btn = QPushButton("清除")
        self.preview_btn = QPushButton("预览")

        self.undo_btn.clicked.connect(self.canvas.undo_last_stroke)
        self.clear_btn.clicked.connect(self.canvas.clear_all)
        self.preview_btn.clicked.connect(self._preview_character)

        stroke_buttons.addWidget(self.undo_btn)
        stroke_buttons.addWidget(self.clear_btn)
        stroke_buttons.addWidget(self.preview_btn)
        canvas_layout.addLayout(stroke_buttons)

        right_layout.addLayout(canvas_layout)
        splitter.addWidget(right_panel)

        # 设置分割器比例
        splitter.setSizes([200, 600])

        layout.addWidget(splitter)

        # 底部按钮
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        bottom_layout.addWidget(self.close_btn)

        layout.addLayout(bottom_layout)

    def _canvas_strokes_payload(self) -> list[list[list[float]]]:
        strokes: list[list[list[float]]] = []
        for path in self.canvas.get_all_paths():
            stroke = [[float(point.x), float(point.y)] for point in path]
            if len(stroke) > 1:
                strokes.append(stroke)
        return strokes

    def _store_current_character_strokes(self) -> None:
        char = (self.current_character or "").strip()
        if len(char) != 1:
            return
        strokes = self._canvas_strokes_payload()
        if strokes:
            self.characters[char] = strokes
        elif char in self.characters:
            self.characters[char] = []

    def _on_character_changed(self, char: str) -> None:
        """字符改变事件"""
        if len(char) == 1:
            if self.current_character and self.current_character != char:
                self._store_current_character_strokes()
            self.current_character = char
            self._load_character_strokes(char)

    def _on_list_selection_changed(self) -> None:
        """列表选择改变事件"""
        selected_items = self.char_list.selectedItems()
        if selected_items:
            char = selected_items[0].text()
            self.char_input.setCurrentText(char)
            self.current_character = char
            self._load_character_strokes(char)

    def _load_character_strokes(self, char: str) -> None:
        """加载字符笔画"""
        if char in self.characters:
            strokes = self.characters[char]
            # 转换为VectorPath格式
            paths = []
            for stroke in strokes:
                if isinstance(stroke, list) and len(stroke) > 1:
                    path = []
                    for point in stroke:
                        if isinstance(point, (list, tuple)) and len(point) >= 2:
                            path.append(Point(point[0], point[1]))
                    if path:
                        paths.append(path)
            self.canvas.set_paths(paths)
        else:
            self.canvas.clear_all()

    def _add_character(self) -> None:
        """添加字符"""
        char = self.char_input.currentText()
        if len(char) != 1:
            QMessageBox.warning(self, "错误", "请输入单个字符")
            return

        self._store_current_character_strokes()
        if char not in self.characters:
            self.characters[char] = []

        # 添加到列表
        existing = [self.char_list.item(i).text() for i in range(self.char_list.count())]
        if char not in existing:
            self.char_list.addItem(char)
        self.current_character = char
        self.char_input.setCurrentText(char)

    def _delete_character(self) -> None:
        """删除字符"""
        selected_items = self.char_list.selectedItems()
        if not selected_items:
            return

        char = selected_items[0].text()
        if char in self.characters:
            del self.characters[char]

        # 从列表中删除
        row = self.char_list.currentRow()
        self.char_list.takeItem(row)

    def _duplicate_character(self) -> None:
        """复制字符"""
        selected_items = self.char_list.selectedItems()
        if not selected_items:
            return

        source_char = selected_items[0].text()
        target_char = self.char_input.currentText()

        if len(target_char) != 1:
            QMessageBox.warning(self, "错误", "请输入目标字符")
            return

        self._store_current_character_strokes()
        if source_char in self.characters:
            self.characters[target_char] = [
                [list(point) for point in stroke]
                for stroke in self.characters[source_char]
            ]

            # 添加到列表
            if target_char not in [self.char_list.item(i).text()
                                 for i in range(self.char_list.count())]:
                self.char_list.addItem(target_char)

    def _preview_character(self) -> None:
        """预览字符"""
        if not self.current_character:
            return

        self._store_current_character_strokes()
        strokes = self.characters.get(self.current_character) or []
        if not strokes:
            QMessageBox.information(self, "预览", "当前字符还没有可预览的笔画。")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"字符预览 - {self.current_character}")
        dialog.resize(520, 420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                f"字符：{self.current_character}    笔画数：{len(strokes)}"
            )
        )
        preview = StrokeCanvas(dialog)
        preview.setMinimumSize(420, 320)
        preview.setEnabled(False)
        paths: list[list[Point]] = []
        for stroke in strokes:
            pts = [Point(point[0], point[1]) for point in stroke if len(point) >= 2]
            if len(pts) > 1:
                paths.append(pts)
        preview.set_paths(paths)
        layout.addWidget(preview)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec()

    def _new_font(self) -> None:
        """新建字体"""
        font_name = self.font_name_input.currentText()
        if not font_name:
            QMessageBox.warning(self, "错误", "请输入字体名称")
            return

        self._store_current_character_strokes()
        self.current_font_name = font_name
        self.characters = {}
        self.char_list.clear()
        self.canvas.clear_all()
        self.current_character = ""

    def _save_font(self) -> None:
        """保存字体"""
        self._store_current_character_strokes()
        if not self.current_font_name:
            QMessageBox.warning(self, "错误", "请先设置字体名称")
            return

        if not self.characters:
            QMessageBox.warning(self, "错误", "字体为空")
            return

        file_dialog = QFileDialog(self)
        file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        file_dialog.setNameFilter("JSON字体 (*.json)")
        file_dialog.setDefaultSuffix("json")

        if file_dialog.exec() == QDialog.DialogCode.Accepted:
            file_path = Path(file_dialog.selectedFiles()[0])
            self._save_to_file(file_path)

    def _load_font(self) -> None:
        """加载字体"""
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setNameFilter("JSON字体 (*.json)")

        if file_dialog.exec() == QDialog.DialogCode.Accepted:
            file_path = Path(file_dialog.selectedFiles()[0])
            self._load_from_file(file_path)

    def _save_to_file(self, file_path: Path) -> None:
        """保存到文件"""
        try:
            self._store_current_character_strokes()
            font_data = {
                'metadata': {
                    'name': self.current_font_name,
                    'version': '1.0',
                    'description': f'自定义字体 {self.current_font_name}',
                    'created': '2024-01-01'
                },
                'characters': self.characters
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(font_data, f, ensure_ascii=False, indent=2)

            QMessageBox.information(self, "成功", f"字体已保存到 {file_path}")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败: {e}")

    def _load_from_file(self, file_path: Path) -> None:
        """从文件加载"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                font_data = json.load(f)

            self.current_font_name = font_data.get('metadata', {}).get('name', file_path.stem)
            self.font_name_input.setCurrentText(self.current_font_name)

            self.characters = font_data.get('characters', {})
            self.current_character = ""
            self.canvas.clear_all()

            # 更新字符列表
            self.char_list.clear()
            for char in sorted(self.characters.keys()):
                self.char_list.addItem(char)

            QMessageBox.information(self, "成功", f"字体已从 {file_path} 加载")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载失败: {e}")
