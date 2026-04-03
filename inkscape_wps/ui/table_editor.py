"""
专业表格编辑区（与「文字」分离，类似 WPS 表格组件）。
使用 QTableWidget 网格；单元格可存 HTML（加粗/倾斜/对齐参与排版），按 QTextLayout 生成 LayoutLine。
"""

from __future__ import annotations

import html as html_module
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextCharFormat, QTextCursor, QTextDocument
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
from inkscape_wps.ui.document_bridge import html_fragment_to_layout_lines

# 单元格内富文本（与 document_bridge.LayoutLine 兼容的元组形式）
LayoutLineUnion = Union[
    Tuple[str, float, float, float],
    Tuple[str, float, float, float, float],
    Tuple[str, float, float, float, float, Tuple[float, ...]],
]


class WpsTableEditor(QWidget):
    """类 WPS「表格」：独立网格编辑器，输出 LayoutLine 列表供 Hershey 映射。"""

    ROLE_HTML = Qt.ItemDataRole.UserRole + 42

    contentChanged = pyqtSignal()

    def __init__(self, cfg: MachineConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._font_pt_resolver: Callable[[], float] = lambda: 12.0
        self._suspend_item_sync = False

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
        self._table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self._table, stretch=1)

        hint = QLabel(
            "选中单元格后可用「开始」页加粗/倾斜/段落对齐；"
            "原地编辑单元格会按纯文本刷新格式（与 WPS 类似限制）。"
            "预览与 G-code 随当前组件切换。"
        )
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

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suspend_item_sync:
            return
        self._suspend_item_sync = True
        try:
            t = item.text()
            wrapped = (
                f'<p style="margin-top:0;margin-bottom:0;">{html_module.escape(t)}</p>'
            )
            item.setData(self.ROLE_HTML, wrapped)
        finally:
            self._suspend_item_sync = False
        self._emit_changed()

    def _cell_html(self, item: Optional[QTableWidgetItem]) -> str:
        if item is None:
            return ""
        raw = item.data(self.ROLE_HTML)
        if isinstance(raw, str) and raw.strip():
            return raw
        t = item.text()
        if not t.strip():
            return ""
        return f'<p style="margin-top:0;margin-bottom:0;">{html_module.escape(t)}</p>'

    def _commit_doc_to_item(self, item: QTableWidgetItem, doc: QTextDocument) -> None:
        self._suspend_item_sync = True
        try:
            item.setData(self.ROLE_HTML, doc.toHtml())
            item.setText(doc.toPlainText().replace("\n", " "))
        finally:
            self._suspend_item_sync = False
        self._emit_changed()

    def _current_cell_item(self) -> Optional[QTableWidgetItem]:
        return self._table.currentItem()

    def apply_bold_current_cell(self) -> None:
        item = self._current_cell_item()
        if item is None:
            return
        doc = QTextDocument()
        doc.setHtml(self._cell_html(item))
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        bold_on = cur.charFormat().fontWeight() >= QFont.Weight.DemiBold
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Normal if bold_on else QFont.Weight.Bold)
        cur.mergeCharFormat(fmt)
        self._commit_doc_to_item(item, doc)

    def apply_italic_current_cell(self) -> None:
        item = self._current_cell_item()
        if item is None:
            return
        doc = QTextDocument()
        doc.setHtml(self._cell_html(item))
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setFontItalic(not cur.charFormat().fontItalic())
        cur.mergeCharFormat(fmt)
        self._commit_doc_to_item(item, doc)

    def apply_underline_current_cell(self) -> None:
        item = self._current_cell_item()
        if item is None:
            return
        doc = QTextDocument()
        doc.setHtml(self._cell_html(item))
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        u = cur.charFormat().underlineStyle()
        fmt = QTextCharFormat()
        if u != QTextCharFormat.UnderlineStyle.NoUnderline:
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.NoUnderline)
        else:
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
        cur.mergeCharFormat(fmt)
        self._commit_doc_to_item(item, doc)

    def set_alignment_current_cell(self, al: Qt.AlignmentFlag) -> None:
        item = self._current_cell_item()
        if item is None:
            return
        doc = QTextDocument()
        doc.setHtml(self._cell_html(item))
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        bfmt = cur.blockFormat()
        bfmt.setAlignment(al)
        cur.mergeBlockFormat(bfmt)
        self._commit_doc_to_item(item, doc)

    def merge_font_family_current_cell(self, family: str) -> None:
        item = self._current_cell_item()
        if item is None:
            return
        doc = QTextDocument()
        doc.setHtml(self._cell_html(item))
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setFontFamily(family)
        cur.mergeCharFormat(fmt)
        self._commit_doc_to_item(item, doc)

    def merge_font_point_size_current_cell(self, pt: float) -> None:
        item = self._current_cell_item()
        if item is None:
            return
        doc = QTextDocument()
        doc.setHtml(self._cell_html(item))
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setFontPointSize(float(pt))
        cur.mergeCharFormat(fmt)
        self._commit_doc_to_item(item, doc)

    def to_layout_lines(self, mm_per_px: float) -> List[LayoutLineUnion]:
        """按格生成布局行；mm_per_px 与文字页一致（纸宽/视口）。"""
        m = float(self._cfg.document_margin_mm)
        cw = float(self._spin_cw.value())
        ch = float(self._spin_ch.value())
        pt = float(self._font_pt_resolver())
        if pt <= 0:
            pt = 12.0

        rows = self._table.rowCount()
        cols = self._table.columnCount()
        out: List[LayoutLineUnion] = []

        for r in range(rows):
            for c in range(cols):
                it = self._table.item(r, c)
                raw = (it.text() if it is not None else "").strip()
                if not raw:
                    continue
                html = self._cell_html(it)
                cell_left = m + c * cw + 0.5
                cell_top = m + r * ch
                lines = html_fragment_to_layout_lines(
                    html,
                    self._cfg,
                    cell_left_mm=cell_left,
                    cell_top_from_page_top_mm=cell_top,
                    cell_width_mm=max(cw - 1.0, 2.0),
                    cell_height_mm=ch * 0.95,
                    mm_per_px_x=mm_per_px,
                    default_pt=pt,
                )
                out.extend(lines)

        return out

    def to_project_blob(self) -> Dict[str, Any]:
        rows, cols = self.row_column_count()
        cells: List[List[Dict[str, Any]]] = []
        for r in range(rows):
            row: List[Dict[str, Any]] = []
            for c in range(cols):
                it = self._table.item(r, c)
                row.append(
                    {
                        "text": it.text() if it else "",
                        "html": it.data(self.ROLE_HTML) if it else None,
                    }
                )
            cells.append(row)
        return {
            "cell_w_mm": self._spin_cw.value(),
            "cell_h_mm": self._spin_ch.value(),
            "rows": rows,
            "cols": cols,
            "cells": cells,
        }

    def from_project_blob(self, blob: Dict[str, Any]) -> None:
        self._suspend_item_sync = True
        try:
            self._spin_cw.setValue(float(blob.get("cell_w_mm", 28.0)))
            self._spin_ch.setValue(float(blob.get("cell_h_mm", 12.0)))
            rows = int(blob.get("rows", 4))
            cols = int(blob.get("cols", 4))
            rows = max(1, rows)
            cols = max(1, cols)
            self._table.clear()
            self._table.setRowCount(rows)
            self._table.setColumnCount(cols)
            cells = blob.get("cells") or []
            for r in range(rows):
                row_data = cells[r] if r < len(cells) else []
                for c in range(cols):
                    cell: Dict[str, Any] = row_data[c] if c < len(row_data) else {}
                    text = str(cell.get("text", ""))
                    h = cell.get("html")
                    item = QTableWidgetItem(text)
                    if isinstance(h, str) and h.strip():
                        item.setData(self.ROLE_HTML, h)
                    self._table.setItem(r, c, item)
        finally:
            self._suspend_item_sync = False
        self._emit_changed()
