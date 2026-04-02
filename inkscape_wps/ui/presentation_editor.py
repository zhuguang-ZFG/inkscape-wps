"""
演示组件（与「文字」「表格」分离，类似 WPS 演示 / PPT）。
多页幻灯片，每页独立 QTextEdit；生成路径时可纵向错开各页内容。
"""

from __future__ import annotations

from typing import Callable, List

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.ui.document_bridge import LayoutLine, apply_default_tab_stops, text_edit_to_layout_lines


class WpsPresentationEditor(QWidget):
    """类 WPS「演示」：左侧幻灯片列表 + 右侧当前页编辑。"""

    contentChanged = pyqtSignal()

    def __init__(self, cfg: MachineConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._slide_height_mm = 80.0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        self._btn_new = QPushButton("新建幻灯片")
        self._btn_new.clicked.connect(self._new_slide)
        bar.addWidget(self._btn_new)
        self._btn_del = QPushButton("删除当前页")
        self._btn_del.clicked.connect(self._delete_current_slide)
        bar.addWidget(self._btn_del)
        bar.addStretch(1)
        hint = QLabel("每页独立排版；G-code 合并各页并沿 Y 错开。")
        hint.setObjectName("StatusHint")
        bar.addWidget(hint)
        root.addLayout(bar)

        split = QSplitter()
        self._list = QListWidget()
        self._list.setMaximumWidth(200)
        self._list.currentRowChanged.connect(self._on_slide_selected)
        split.addWidget(self._list)

        self._editor = QTextEdit()
        self._editor.setObjectName("PresentationSlideEditor")
        self._editor.setPlaceholderText("当前幻灯片内容…")
        self._editor.document().setDocumentMargin(8.0)
        self._editor.textChanged.connect(self._on_editor_text_changed)
        split.addWidget(self._editor)
        split.setStretchFactor(1, 1)
        root.addWidget(split, stretch=1)

        # 生成布局时用离屏编辑器，避免反复改写可见区触发闪烁与 textChanged 回写
        self._scratch = QTextEdit(self)
        self._scratch.hide()
        self._scratch.document().setDocumentMargin(8.0)

        self._slides: list[str] = [""]
        self._refresh_list(select_row=0)

    def slide_editor(self) -> QTextEdit:
        """当前可见的幻灯片正文编辑器（供主窗口对齐、快捷键与字符格式）。"""
        return self._editor

    def set_slide_document_margin_px(self, px: float) -> None:
        m = max(0.0, float(px))
        self._editor.document().setDocumentMargin(m)
        self._scratch.document().setDocumentMargin(m)

    def _on_editor_text_changed(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            row = 0
        if row < len(self._slides):
            self._slides[row] = self._editor.toPlainText()
        self.contentChanged.emit()

    def _refresh_list(self, select_row: int = 0) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for i in range(len(self._slides)):
            t = self._slides[i].strip().replace("\n", " ")[:18]
            label = f"幻灯片 {i + 1}" + (f" · {t}" if t else "")
            self._list.addItem(QListWidgetItem(label))
        self._list.blockSignals(False)
        if self._slides:
            self._list.setCurrentRow(min(select_row, len(self._slides) - 1))

    def _on_slide_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._slides):
            return
        self._editor.blockSignals(True)
        self._editor.setPlainText(self._slides[row])
        self._editor.blockSignals(False)

    def _new_slide(self) -> None:
        self._on_editor_text_changed()
        self._slides.append("")
        self._refresh_list(select_row=len(self._slides) - 1)
        self._editor.clear()
        self.contentChanged.emit()

    def _delete_current_slide(self) -> None:
        row = self._list.currentRow()
        if len(self._slides) <= 1:
            QMessageBox.information(self, "演示", "至少保留一页幻灯片。")
            return
        if row < 0:
            row = 0
        self._slides.pop(row)
        self._refresh_list(select_row=max(0, row - 1))
        self._on_slide_selected(self._list.currentRow())
        self.contentChanged.emit()

    def apply_document_font(self, font: QFont) -> None:
        self._editor.setFont(font)
        self._scratch.setFont(font)
        apply_default_tab_stops(self._editor)

    def select_all_current(self) -> None:
        self._editor.selectAll()

    def clear_all(self) -> None:
        self._slides = [""]
        self._refresh_list(0)
        self._editor.clear()
        self.contentChanged.emit()

    def current_slide_index(self) -> int:
        return max(0, self._list.currentRow())

    def slide_count(self) -> int:
        return len(self._slides)

    def status_line(self) -> str:
        return f"幻灯片 {self.current_slide_index() + 1} / {self.slide_count()}"

    def to_layout_lines_all_slides(
        self,
        *,
        mm_per_px_resolver: Callable[[QTextEdit], float],
    ) -> List[LayoutLine]:
        """各页在离屏 QTextEdit 中排版后合并，每页整体下移 slide_height_mm。"""
        scr = self._scratch
        scr.setFont(self._editor.font())
        scr.document().setDocumentMargin(self._editor.document().documentMargin())
        vw = max(1, self._editor.viewport().width())
        vh = max(1, self._editor.viewport().height())
        scr.resize(vw, vh)

        all_lines: List[LayoutLine] = []
        for i, text in enumerate(self._slides):
            scr.blockSignals(True)
            scr.setPlainText(text)
            scr.blockSignals(False)
            lines = text_edit_to_layout_lines(
                scr,
                self._cfg,
                mm_per_px=mm_per_px_resolver(scr),
            )
            dy = i * self._slide_height_mm
            for row in lines:
                if len(row) >= 4:
                    t, ox, by, fs = row[0], row[1], row[2], row[3]
                    by2 = by - dy
                    if len(row) == 6:
                        all_lines.append((t, ox, by2, fs, row[4], row[5]))
                    elif len(row) == 5:
                        all_lines.append((t, ox, by2, fs, row[4]))
                    else:
                        all_lines.append((t, ox, by2, fs))
        row = self._list.currentRow()
        if row < 0:
            row = 0
        if row < len(self._slides):
            self._editor.blockSignals(True)
            self._editor.setPlainText(self._slides[row])
            self._editor.blockSignals(False)
        return all_lines
