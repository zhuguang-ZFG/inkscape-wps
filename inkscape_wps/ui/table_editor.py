"""
专业表格编辑区（与「文字」分离，类似 WPS 表格组件）。
使用 QTableWidget 网格；按单元格生成单线字路径，不参与 QTextDocument 富文本表格。
"""

from __future__ import annotations

from typing import Callable, List, Tuple, Union

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from inkscape_wps.core.config import MachineConfig

# 与 document_bridge.LayoutLine 兼容的元组形式
LayoutLine = Union[
    Tuple[str, float, float, float],
    Tuple[str, float, float, float, float],
    Tuple[str, float, float, float, float, Tuple[float, ...]],
]


class WpsTableEditor(QWidget):
    """类 WPS「表格」：独立网格编辑器，输出 LayoutLine 列表供 Hershey 映射。"""

    contentChanged = pyqtSignal()

    def __init__(self, cfg: MachineConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._font_pt_resolver: Callable[[], float] = lambda: 12.0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("单元格宽 (mm)"))
        self._spin_cw = QDoubleSpinBox()
        self._spin_cw.setRange(5.0, 500.0)
        self._spin_cw.setValue(28.0)
        self._spin_cw.setDecimals(1)
        self._spin_cw.valueChanged.connect(self._emit_changed)
        bar.addWidget(self._spin_cw)
        bar.addWidget(QLabel("单元格高 (mm)"))
        self._spin_ch = QDoubleSpinBox()
        self._spin_ch.setRange(4.0, 200.0)
        self._spin_ch.setValue(12.0)
        self._spin_ch.setDecimals(1)
        self._spin_ch.valueChanged.connect(self._emit_changed)
        bar.addWidget(self._spin_ch)
        bar.addStretch(1)

        self._btn_add_row = QPushButton("+ 行")
        self._btn_add_row.clicked.connect(self._add_row)
        bar.addWidget(self._btn_add_row)
        self._btn_del_row = QPushButton("− 行")
        self._btn_del_row.clicked.connect(self._del_row)
        bar.addWidget(self._btn_del_row)
        self._btn_add_col = QPushButton("+ 列")
        self._btn_add_col.clicked.connect(self._add_col)
        bar.addWidget(self._btn_add_col)
        self._btn_del_col = QPushButton("− 列")
        self._btn_del_col.clicked.connect(self._del_col)
        bar.addWidget(self._btn_del_col)
        root.addLayout(bar)

        self._table = QTableWidget(4, 4)
        self._table.setAlternatingRowColors(True)
        self._table.itemChanged.connect(lambda _: self._emit_changed())
        root.addWidget(self._table, stretch=1)

        hint = QLabel("表格与「文字」文档相互独立；预览与 G-code 随当前选中的组件（文字 / 表格 / 演示）切换。")
        hint.setObjectName("StatusHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

    def set_font_point_size_resolver(self, fn: Callable[[], float]) -> None:
        self._font_pt_resolver = fn

    def _emit_changed(self) -> None:
        self.contentChanged.emit()

    def _add_row(self) -> None:
        self._table.insertRow(self._table.rowCount())
        self._emit_changed()

    def _del_row(self) -> None:
        if self._table.rowCount() > 1:
            self._table.removeRow(self._table.rowCount() - 1)
            self._emit_changed()

    def _add_col(self) -> None:
        self._table.insertColumn(self._table.columnCount())
        self._emit_changed()

    def _del_col(self) -> None:
        if self._table.columnCount() > 1:
            self._table.removeColumn(self._table.columnCount() - 1)
            self._emit_changed()

    def apply_document_font(self, font: QFont) -> None:
        self._table.setFont(font)

    def select_all(self) -> None:
        self._table.selectAll()

    def row_column_count(self) -> Tuple[int, int]:
        return self._table.rowCount(), self._table.columnCount()

    def clear_all(self) -> None:
        self._table.clear()
        self._table.setRowCount(4)
        self._table.setColumnCount(4)
        self._emit_changed()

    def to_layout_lines(self) -> List[LayoutLine]:
        """按格左上角 + 字号生成布局行（每格单行文本；换行取首行）。"""
        m = float(self._cfg.document_margin_mm)
        cw = float(self._spin_cw.value())
        ch = float(self._spin_ch.value())
        pt = float(self._font_pt_resolver())
        if pt <= 0:
            pt = 12.0
        fm = self._table.fontMetrics()
        ref_ascent_pt = pt * (fm.ascent() / max(float(fm.height()), 1e-6))

        rows = self._table.rowCount()
        cols = self._table.columnCount()
        out: List[LayoutLine] = []

        for r in range(rows):
            for c in range(cols):
                it = self._table.item(r, c)
                raw = (it.text() if it is not None else "").strip()
                if not raw:
                    continue
                text = raw.split("\n")[0].split("\r")[0]
                if not text:
                    continue
                ox_mm = m + c * cw + 0.5
                # 单元格内基线：自下往上约为一行高（pt→mm 粗近似）
                line_h_mm = max(ch * 0.72, pt * float(self._cfg.mm_per_pt) * 0.85)
                cell_top_down_mm = m + r * ch
                baseline_from_bottom_mm = (
                    float(self._cfg.page_height_mm) - cell_top_down_mm - line_h_mm * 0.15
                )
                default_adv = (6.5 / 10.0) * pt * float(self._cfg.mm_per_pt)
                advs = tuple(default_adv for _ in text)
                out.append((text, ox_mm, baseline_from_bottom_mm, pt, ref_ascent_pt, advs))

        return out
