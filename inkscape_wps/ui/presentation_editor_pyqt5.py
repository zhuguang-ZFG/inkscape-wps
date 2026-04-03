"""
PyQt5 版演示组件（对标 WPS 演示 / PPT）：左侧幻灯片列表 + 右侧每页富文本。
"""

from __future__ import annotations

from typing import Callable, List

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QKeyEvent, QTextDocument
from PyQt5.QtWidgets import (
    QAbstractItemView,
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
from inkscape_wps.ui.document_bridge_pyqt5 import LayoutLine, apply_default_tab_stops, text_edit_to_layout_lines


def _slide_plain_preview(stored: str, max_len: int = 18) -> str:
    if not stored or not stored.strip():
        return ""
    s = stored.lstrip()
    if s.startswith("<"):
        doc = QTextDocument()
        doc.setHtml(stored)
        t = doc.toPlainText().strip().replace("\n", " ")
    else:
        t = stored.strip().replace("\n", " ")
    if len(t) <= max_len:
        return t
    return t[:max_len] + "…"


class _SlideListWidget(QListWidget):
    """左侧列表：内部拖拽排序；聚焦时 Alt+↑/↓ 与菜单「上移/下移」一致。"""

    _host: "WpsPresentationEditorPyQt5 | None" = None

    def dropEvent(self, event) -> None:  # noqa: ANN001
        h = self._host
        if h is not None:
            h._on_editor_text_changed()
        super().dropEvent(event)
        if h is not None:
            h._sync_slide_order_after_list_drag()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        h = self._host
        if (
            h is not None
            and event.modifiers() == Qt.AltModifier
            and event.key() in (Qt.Key_Up, Qt.Key_Down)
        ):
            if event.key() == Qt.Key_Up:
                h.move_current_slide_up()
            else:
                h.move_current_slide_down()
            event.accept()
            return
        super().keyPressEvent(event)


class WpsPresentationEditorPyQt5(QWidget):
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
        hint = QLabel(
            "每页独立富文本；G-code 合并各页并沿 Y 错开。"
            " 左侧列表可拖拽排序；列表聚焦时 Alt+↑ / Alt+↓ 上移/下移。"
        )
        hint.setStyleSheet("color:#6b7280;font-size:12px;")
        hint.setWordWrap(True)
        bar.addWidget(hint)
        root.addLayout(bar)

        split = QSplitter()
        self._list = _SlideListWidget()
        self._list._host = self
        self._list.setMaximumWidth(220)
        self._list.setDragDropMode(QAbstractItemView.InternalMove)
        self._list.setDefaultDropAction(Qt.MoveAction)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setToolTip("拖拽条目可调整顺序；Alt+↑ / Alt+↓ 上移或下移当前页")
        self._list.currentRowChanged.connect(self._on_slide_selected)
        split.addWidget(self._list)

        self._editor = QTextEdit()
        self._editor.setPlaceholderText("当前幻灯片内容…")
        self._editor.document().setDocumentMargin(8.0)
        self._editor.textChanged.connect(self._on_editor_text_changed)
        split.addWidget(self._editor)
        split.setStretchFactor(1, 1)
        root.addWidget(split, stretch=1)

        self._scratch = QTextEdit(self)
        self._scratch.hide()
        self._scratch.document().setDocumentMargin(8.0)

        self._slides: list[str] = [""]
        self._internal_slide_clipboard: str | None = None
        self._block_slide_list_sync = False
        self._refresh_list(select_row=0)

    def slide_editor(self) -> QTextEdit:
        return self._editor

    def slide_list_widget(self) -> QListWidget:
        """左侧幻灯片列表（供主窗挂接右键菜单等）。"""
        return self._list

    def add_slide(self) -> None:
        """新建幻灯片（与工具栏「新建幻灯片」相同）。"""
        self._new_slide()

    def delete_slide_interactive(self) -> None:
        """删除当前页（与工具栏相同，至少保留一页）。"""
        self._delete_current_slide()

    def duplicate_current_slide(self) -> None:
        """在当前页后插入一页相同内容（对标 PPT「复制幻灯片」快捷场景）。"""
        self._on_editor_text_changed()
        row = self._list.currentRow()
        if row < 0:
            row = 0
        if row >= len(self._slides):
            return
        snapshot = self._slides[row]
        self._slides.insert(row + 1, snapshot)
        self._refresh_list(select_row=row + 1)
        self._apply_slide_to_editor(self._slides[row + 1])
        self.contentChanged.emit()

    def copy_slide_to_internal_clipboard(self) -> None:
        """将当前页 HTML 存入应用内剪贴板，供「粘贴幻灯片」使用。"""
        self._on_editor_text_changed()
        row = self._list.currentRow()
        if row < 0:
            row = 0
        if row >= len(self._slides):
            return
        self._internal_slide_clipboard = self._slides[row]

    def paste_slide_from_internal_clipboard(self) -> None:
        """在当前页后插入应用内剪贴板中的整页内容。"""
        if not self._internal_slide_clipboard:
            QMessageBox.information(self, "演示", "请先在列表中右键「复制幻灯片」。")
            return
        self._on_editor_text_changed()
        row = self._list.currentRow()
        if row < 0:
            row = 0
        if row >= len(self._slides):
            row = len(self._slides) - 1
        self._slides.insert(row + 1, self._internal_slide_clipboard)
        self._refresh_list(select_row=row + 1)
        self._apply_slide_to_editor(self._slides[row + 1])
        self.contentChanged.emit()

    def move_current_slide_up(self) -> None:
        """将当前页与上一页交换顺序。"""
        self._on_editor_text_changed()
        row = self._list.currentRow()
        if row < 0:
            row = 0
        if row <= 0 or row >= len(self._slides):
            return
        self._slides[row - 1], self._slides[row] = self._slides[row], self._slides[row - 1]
        self._refresh_list(select_row=row - 1)
        self._apply_slide_to_editor(self._slides[row - 1])
        self.contentChanged.emit()

    def move_current_slide_down(self) -> None:
        """将当前页与下一页交换顺序。"""
        self._on_editor_text_changed()
        row = self._list.currentRow()
        if row < 0:
            row = 0
        if row >= len(self._slides) - 1:
            return
        self._slides[row], self._slides[row + 1] = self._slides[row + 1], self._slides[row]
        self._refresh_list(select_row=row + 1)
        self._apply_slide_to_editor(self._slides[row + 1])
        self.contentChanged.emit()

    def _sync_slide_order_after_list_drag(self) -> None:
        """拖拽重排列表项后，按条目的 UserRole（原下标）重建 _slides。"""
        if self._block_slide_list_sync:
            return
        n = self._list.count()
        if n != len(self._slides):
            return
        order: list[int] = []
        for i in range(n):
            it = self._list.item(i)
            if it is None:
                return
            j = it.data(Qt.UserRole)
            if not isinstance(j, int) or j < 0 or j >= n:
                return
            order.append(j)
        if sorted(order) != list(range(n)):
            return
        self._slides = [self._slides[j] for j in order]
        cr = max(0, self._list.currentRow())
        self._block_slide_list_sync = True
        try:
            self._refresh_list(select_row=cr)
            if 0 <= cr < len(self._slides):
                self._apply_slide_to_editor(self._slides[cr])
            self.contentChanged.emit()
        finally:
            self._block_slide_list_sync = False

    def set_slide_document_margin_px(self, px: float) -> None:
        m = max(0.0, float(px))
        self._editor.document().setDocumentMargin(m)
        self._scratch.document().setDocumentMargin(m)

    def _capture_slide_html(self) -> str:
        if not self._editor.toPlainText().strip():
            return ""
        return self._editor.toHtml()

    def _apply_slide_to_editor(self, stored: str) -> None:
        self._editor.blockSignals(True)
        if not stored or not stored.strip():
            self._editor.clear()
        elif stored.lstrip().startswith("<"):
            self._editor.setHtml(stored)
        else:
            self._editor.setPlainText(stored)
        self._editor.blockSignals(False)

    def _on_editor_text_changed(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            row = 0
        if row < len(self._slides):
            self._slides[row] = self._capture_slide_html()
            self._update_list_row_label(row)
        self.contentChanged.emit()

    def _update_list_row_label(self, row: int) -> None:
        if row < 0 or row >= self._list.count():
            return
        it = self._list.item(row)
        if it is None:
            return
        pv = _slide_plain_preview(self._slides[row] if row < len(self._slides) else "")
        it.setText(f"幻灯片 {row + 1}" + (f" · {pv}" if pv else ""))

    def _refresh_list(self, select_row: int = 0) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for i in range(len(self._slides)):
            pv = _slide_plain_preview(self._slides[i])
            label = f"幻灯片 {i + 1}" + (f" · {pv}" if pv else "")
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, i)
            self._list.addItem(it)
        self._list.blockSignals(False)
        if self._slides:
            self._list.setCurrentRow(min(select_row, len(self._slides) - 1))

    def _on_slide_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._slides):
            return
        self._apply_slide_to_editor(self._slides[row])

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

    def slides_storage(self) -> List[str]:
        return list(self._slides)

    def load_slides(self, slides: List[str]) -> None:
        self._slides = list(slides) if slides else [""]
        self._refresh_list(0)
        row = self._list.currentRow()
        if row < 0:
            row = 0
        self._on_slide_selected(row)
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
        scr = self._scratch
        scr.setFont(self._editor.font())
        scr.document().setDocumentMargin(self._editor.document().documentMargin())
        vw = max(1, self._editor.viewport().width())
        vh = max(1, self._editor.viewport().height())
        scr.resize(vw, vh)

        all_lines: List[LayoutLine] = []
        for i, stored in enumerate(self._slides):
            scr.blockSignals(True)
            if not stored or not stored.strip():
                scr.clear()
            elif stored.lstrip().startswith("<"):
                scr.setHtml(stored)
            else:
                scr.setPlainText(stored)
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
            self._apply_slide_to_editor(self._slides[row])
        return all_lines
