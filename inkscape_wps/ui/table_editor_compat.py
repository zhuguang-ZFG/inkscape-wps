"""
表格编辑区（兼容PyQt5/PyQt6，与「文字」分离，对标 WPS 表格组件）。
"""

from __future__ import annotations

import html as html_module
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.ui.document_bridge_compat import html_fragment_to_layout_lines
from inkscape_wps.ui.qt_compat import (
    QAbstractItemView,
    QApplication,
    QDoubleSpinBox,
    QFont,
    QHBoxLayout,
    QLabel,
    QPushButton,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)

LayoutLineUnion = Union[
    Tuple[str, float, float, float],
    Tuple[str, float, float, float, float],
    Tuple[str, float, float, float, float, Tuple[float, ...]],
]


class WpsTableEditor(QWidget):
    """类 WPS「表格」：独立网格编辑器，输出 LayoutLine 列表供 Hershey 映射。"""

    ROLE_HTML = Qt.UserRole + 42

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
        # 支持矩形选区（用于「合并选区单元格」）
        self._table.setSelectionMode(QAbstractItemView.ContiguousSelection)
        self._table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self._table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self._table, stretch=1)

        hint = QLabel(
            "选中单元格后可整格设置加粗/倾斜等（若主窗口已接好「编辑」菜单）；"
            "原地键盘编辑会按纯文本刷新格式。网格右键可插入/删除行列（类 WPS）。"
            "预览与 G-code 随当前组件切换。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6b7280;font-size:12px;")
        root.addWidget(hint)

    def set_font_point_size_resolver(self, fn: Callable[[], float]) -> None:
        self._font_pt_resolver = fn

    def connect_toolbar_context_refresh(self, slot: Callable[[], None]) -> None:
        self._table.currentCellChanged.connect(lambda *_: slot())

    def table_widget(self) -> QTableWidget:
        return self._table

    def clipboard_copy_cell(self) -> None:
        it = self._current_cell_item()
        if it is None:
            return
        QApplication.clipboard().setText(it.text())

    def clipboard_cut_cell(self) -> None:
        it = self._current_cell_item()
        if it is None:
            return
        QApplication.clipboard().setText(it.text())
        self._suspend_item_sync = True
        try:
            it.setText("")
            it.setData(
                self.ROLE_HTML,
                '<p style="margin-top:0;margin-bottom:0;"></p>',
            )
        finally:
            self._suspend_item_sync = False
        self._emit_changed()

    def clipboard_paste_cell(self) -> None:
        it = self._current_cell_item()
        if it is None:
            return
        t = (QApplication.clipboard().text() or "").replace("\n", " ").replace("\r", "")
        it.setText(t)
        self._on_item_changed(it)

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

    def _span_anchors(self) -> List[Tuple[int, int, int, int]]:
        """返回所有“锚点”合并单元格：(r,c,rowspan,colspan)。"""
        rows = self._table.rowCount()
        cols = self._table.columnCount()
        out: List[Tuple[int, int, int, int]] = []
        covered: set[Tuple[int, int]] = set()
        for r in range(rows):
            for c in range(cols):
                if (r, c) in covered:
                    continue
                rs = int(self._table.rowSpan(r, c) or 1)
                cs = int(self._table.columnSpan(r, c) or 1)
                if rs > 1 or cs > 1:
                    out.append((r, c, rs, cs))
                    for rr in range(r, r + rs):
                        for cc in range(c, c + cs):
                            covered.add((rr, cc))
        return out

    def _span_covered_cells(self) -> Tuple[set[Tuple[int, int]], set[Tuple[int, int]]]:
        """返回：(covered_cells, anchor_cells)。"""
        covered: set[Tuple[int, int]] = set()
        anchors: set[Tuple[int, int]] = set()
        for r, c, rs, cs in self._span_anchors():
            anchors.add((r, c))
            for rr in range(r, r + rs):
                for cc in range(c, c + cs):
                    covered.add((rr, cc))
        return covered, anchors

    def _span_anchor_of(self, r: int, c: int) -> Tuple[int, int]:
        """若 (r,c) 位于合并区内，则返回锚点坐标；否则返回自身坐标。"""
        if r < 0 or c < 0:
            return r, c
        anchors = self._span_anchors()
        for ar, ac, rs, cs in anchors:
            if ar <= r < ar + rs and ac <= c < ac + cs:
                return ar, ac
        return r, c

    def current_grid_indices(self) -> Tuple[int, int]:
        """当前单元格行列（合并区内自动归一到锚点）。"""
        r = self._table.currentRow()
        c = self._table.currentColumn()
        if r < 0:
            r = max(0, self._table.rowCount() - 1)
        if c < 0:
            c = max(0, self._table.columnCount() - 1)
        return self._span_anchor_of(r, c)

    def merge_selected_cells(self) -> None:
        """将矩形选区合并为一个单元格（保留左上角内容，其它格清空）。"""
        ranges = self._table.selectedRanges()
        if not ranges:
            # 只在矩形选区存在时合并；避免用户无意右键合并单格导致迷惑。
            return

        # 合并：只取第一个矩形范围（多范围可后续扩展）
        rng = ranges[0]
        top = int(rng.topRow())
        left = int(rng.leftColumn())
        bottom = int(rng.bottomRow())
        right = int(rng.rightColumn())
        rowspan = bottom - top + 1
        colspan = right - left + 1
        if rowspan <= 1 and colspan <= 1:
            return

        # 若选区中已有合并，先拆开避免重叠 spans
        for ar, ac, rs, cs in self._span_anchors():
            if not (ar + rs - 1 < top or ar > bottom or ac + cs - 1 < left or ac > right):
                self._table.removeSpan(ar, ac)

        anchor_item = self._table.item(top, left)
        if anchor_item is None:
            anchor_item = QTableWidgetItem("")
            self._table.setItem(top, left, anchor_item)

        self._suspend_item_sync = True
        try:
            self._table.setSpan(top, left, rowspan, colspan)
            # 清空非锚点内容（避免序列化重复；拆分后也能得到“只有锚点有字”的结果）
            for r in range(top, bottom + 1):
                for c in range(left, right + 1):
                    if r == top and c == left:
                        continue
                    it = self._table.item(r, c)
                    if it is None:
                        it = QTableWidgetItem("")
                        self._table.setItem(r, c, it)
                    it.setText("")
                    it.setData(self.ROLE_HTML, "")
        finally:
            self._suspend_item_sync = False
        self._emit_changed()

    def split_current_merged_cell(self) -> None:
        """拆分当前合并单元格（只拆锚点）。"""
        r, c = self.current_grid_indices()
        rs = int(self._table.rowSpan(r, c) or 1)
        cs = int(self._table.columnSpan(r, c) or 1)
        if rs <= 1 and cs <= 1:
            return
        self._table.removeSpan(r, c)
        self._emit_changed()

    def insert_row_above(self) -> None:
        r, _ = self.current_grid_indices()
        self._table.insertRow(r)
        self._emit_changed()

    def insert_row_below(self) -> None:
        r, _ = self.current_grid_indices()
        self._table.insertRow(r + 1)
        self._emit_changed()

    def insert_column_left(self) -> None:
        _, c = self.current_grid_indices()
        self._table.insertColumn(c)
        self._emit_changed()

    def insert_column_right(self) -> None:
        _, c = self.current_grid_indices()
        self._table.insertColumn(c + 1)
        self._emit_changed()

    def delete_current_row(self) -> None:
        if self._table.rowCount() <= 1:
            return
        r, _ = self.current_grid_indices()
        r = max(0, min(r, self._table.rowCount() - 1))
        self._table.removeRow(r)
        self._emit_changed()

    def delete_current_column(self) -> None:
        if self._table.columnCount() <= 1:
            return
        _, c = self.current_grid_indices()
        c = max(0, min(c, self._table.columnCount() - 1))
        self._table.removeColumn(c)
        self._emit_changed()

    def apply_document_font(self, font: QFont) -> None:
        self._table.setFont(font)

    def toolbar_context_font(self) -> QFont:
        """供工具栏显示：当前单元格首字符格式，无选中格或空格时用表默认字体。"""
        base = QFont(self._table.font())
        item = self._current_cell_item()
        if item is None:
            return base
        html = self._cell_html(item)
        if not html.strip():
            return base
        doc = QTextDocument()
        doc.setDefaultFont(base)
        doc.setHtml(html)
        cur = QTextCursor(doc)
        cur.movePosition(QTextCursor.Start)
        out = QFont(cur.charFormat().font())
        if not (out.family() or "").strip():
            out.setFamily(base.family())
        psz = out.pointSizeF() if out.pointSizeF() > 0 else float(out.pointSize() or 0)
        if psz <= 0:
            psz = float(base.pointSizeF() or base.pointSize() or 12)
            out.setPointSizeF(psz)
        return out

    def select_all(self) -> None:
        self._table.selectAll()

    def row_column_count(self) -> Tuple[int, int]:
        return self._table.rowCount(), self._table.columnCount()

    def clear_all(self) -> None:
        self._table.clear()
        self._table.setRowCount(4)
        self._table.setColumnCount(4)
        self._grid_gcode_mode.setCurrentIndex(0)
        self._emit_changed()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suspend_item_sync:
            return
        self._suspend_item_sync = True
        try:
            t = item.text()
            wrapped = f'<p style="margin-top:0;margin-bottom:0;">{html_module.escape(t)}</p>'
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

    def _commit_doc_to_item(
        self, item: QTableWidgetItem, doc: QTextDocument, *, emit: bool = True
    ) -> None:
        self._suspend_item_sync = True
        try:
            item.setData(self.ROLE_HTML, doc.toHtml())
            item.setText(doc.toPlainText().replace("\n", " "))
        finally:
            self._suspend_item_sync = False
        if emit:
            self._emit_changed()

    def _current_cell_item(self) -> Optional[QTableWidgetItem]:
        r, c = self.current_grid_indices()
        return self._table.item(r, c)

    def find_next_in_table(self, needle: str, *, include_current: bool = False) -> bool:
        """在整张表格中查找下一处（按行优先）。找到后切换当前单元格。"""
        needle = (needle or "").strip()
        if not needle:
            return False
        rows, cols = self.row_column_count()
        if rows <= 0 or cols <= 0:
            return False

        r0, c0 = self.current_grid_indices()
        total = rows * cols
        start_idx = r0 * cols + c0
        off0 = 0 if include_current else 1

        for off in range(off0, total):
            idx = (start_idx + off) % total
            r = idx // cols
            c = idx % cols
            it = self._table.item(r, c)
            if it is None:
                continue
            if needle in (it.text() or ""):
                self._table.setCurrentCell(r, c)
                if it is not None:
                    self._table.scrollToItem(it)
                return True
        return False

    def replace_first_in_current_cell(self, needle: str, replacement: str) -> bool:
        """仅替换当前单元格内第一个匹配；返回是否替换成功。"""
        it = self._current_cell_item()
        if it is None:
            return False
        needle = (needle or "").strip()
        if not needle:
            return False

        doc = QTextDocument()
        doc.setHtml(self._cell_html(it))
        c = doc.find(needle, 0)
        if c.isNull():
            return False
        c.beginEditBlock()
        c.insertText(replacement)
        c.endEditBlock()
        self._commit_doc_to_item(it, doc, emit=True)
        return True

    def replace_all_in_table(self, needle: str, replacement: str) -> int:
        """在整张表格中替换所有匹配；返回替换次数。"""
        needle = (needle or "").strip()
        if not needle:
            return 0

        rows, cols = self.row_column_count()
        total_n = 0
        any_changed = False

        for r in range(rows):
            for c in range(cols):
                it = self._table.item(r, c)
                if it is None:
                    continue
                if needle not in (it.text() or ""):
                    continue

                doc = QTextDocument()
                doc.setHtml(self._cell_html(it))

                pos = 0
                changed_cell = False
                while True:
                    cur = doc.find(needle, pos)
                    if cur.isNull():
                        break
                    cur.beginEditBlock()
                    cur.insertText(replacement)
                    cur.endEditBlock()
                    total_n += 1
                    changed_cell = True
                    pos = cur.selectionEnd()

                if changed_cell:
                    self._commit_doc_to_item(it, doc, emit=False)
                    any_changed = True

        if any_changed:
            self._emit_changed()
        return total_n

    def apply_bold_current_cell(self) -> None:
        item = self._current_cell_item()
        if item is None:
            return
        doc = QTextDocument()
        doc.setHtml(self._cell_html(item))
        cur = QTextCursor(doc)
        cur.select(QTextCursor.Document)
        bold_on = cur.charFormat().fontWeight() >= QFont.DemiBold
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Normal if bold_on else QFont.Bold)
        cur.mergeCharFormat(fmt)
        self._commit_doc_to_item(item, doc)

    def apply_italic_current_cell(self) -> None:
        item = self._current_cell_item()
        if item is None:
            return
        doc = QTextDocument()
        doc.setHtml(self._cell_html(item))
        cur = QTextCursor(doc)
        cur.select(QTextCursor.Document)
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
        cur.select(QTextCursor.Document)
        u = cur.charFormat().underlineStyle()
        fmt = QTextCharFormat()
        if u != QTextCharFormat.NoUnderline:
            fmt.setUnderlineStyle(QTextCharFormat.NoUnderline)
        else:
            fmt.setUnderlineStyle(QTextCharFormat.SingleUnderline)
        cur.mergeCharFormat(fmt)
        self._commit_doc_to_item(item, doc)

    def set_alignment_current_cell(self, al: Qt.Alignment) -> None:
        item = self._current_cell_item()
        if item is None:
            return
        doc = QTextDocument()
        doc.setHtml(self._cell_html(item))
        cur = QTextCursor(doc)
        cur.select(QTextCursor.Document)
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
        cur.select(QTextCursor.Document)
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
        cur.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        fmt.setFontPointSize(float(pt))
        cur.mergeCharFormat(fmt)
        self._commit_doc_to_item(item, doc)

    def to_layout_lines(self, mm_per_px: float) -> List[LayoutLineUnion]:
        m = float(self._cfg.document_margin_mm)
        cw = float(self._spin_cw.value())
        ch = float(self._spin_ch.value())
        pt = float(self._font_pt_resolver())
        if pt <= 0:
            pt = 12.0

        rows = self._table.rowCount()
        cols = self._table.columnCount()
        covered, anchor_cells = self._span_covered_cells()
        out: List[LayoutLineUnion] = []

        for r in range(rows):
            for c in range(cols):
                it = self._table.item(r, c)
                raw = (it.text() if it is not None else "").strip()
                if not raw:
                    continue
                # 合并区内非锚点单元格不参与排版（避免重复内容）
                if (r, c) in covered and (r, c) not in anchor_cells:
                    continue
                html = self._cell_html(it)
                rs = int(self._table.rowSpan(r, c) or 1)
                cs = int(self._table.columnSpan(r, c) or 1)
                cell_left = m + c * cw + 0.5
                cell_top = m + r * ch
                lines = html_fragment_to_layout_lines(
                    html,
                    self._cfg,
                    cell_left_mm=cell_left,
                    cell_top_from_page_top_mm=cell_top,
                    cell_width_mm=max(cw * cs - 1.0, 2.0),
                    cell_height_mm=ch * rs * 0.95,
                    mm_per_px_x=mm_per_px,
                    default_pt=pt,
                )
                out.extend(lines)

        return out

    def to_project_blob(self) -> Dict[str, Any]:
        rows, cols = self.row_column_count()
        anchors_info = self._span_anchors()
        covered, anchor_cells = self._span_covered_cells()
        spans = [
            {"r": int(r), "c": int(c), "rowspan": int(rs), "colspan": int(cs)}
            for r, c, rs, cs in anchors_info
            if rs > 1 or cs > 1
        ]
        cells: List[List[Dict[str, Any]]] = []
        for r in range(rows):
            row: List[Dict[str, Any]] = []
            for c in range(cols):
                it = self._table.item(r, c)
                # 非锚点合并单元格内容不序列化（由 spans + 锚点内容决定）
                if (r, c) in covered and (r, c) not in anchor_cells:
                    row.append({"text": "", "html": None})
                    continue
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
            "spans": spans,
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

            spans = blob.get("spans") or []
            # 应用 spans，并清空被覆盖的非锚点内容，确保渲染唯一性
            for sp in spans:
                try:
                    ar = int(sp.get("r", 0))
                    ac = int(sp.get("c", 0))
                    rs = int(sp.get("rowspan", 1))
                    cs = int(sp.get("colspan", 1))
                except Exception:
                    continue
                if rs <= 1 and cs <= 1:
                    continue
                if not (0 <= ar < rows and 0 <= ac < cols):
                    continue
                rs = max(1, rs)
                cs = max(1, cs)
                rs = min(rs, rows - ar)
                cs = min(cs, cols - ac)
                self._table.setSpan(ar, ac, rs, cs)
                for r in range(ar, ar + rs):
                    for c in range(ac, ac + cs):
                        if r == ar and c == ac:
                            continue
                        it = self._table.item(r, c)
                        if it is None:
                            it = QTableWidgetItem("")
                            self._table.setItem(r, c, it)
                        it.setText("")
                        it.setData(self.ROLE_HTML, "")
        finally:
            self._suspend_item_sync = False
        self._emit_changed()
