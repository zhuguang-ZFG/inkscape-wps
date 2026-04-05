"""
PyQt5 版演示组件（对标 WPS 演示 / PPT）：左侧幻灯片列表 + 右侧每页富文本。
"""

from __future__ import annotations

from typing import Callable, List

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import (
    QFont,
    QKeyEvent,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFrame,
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
from inkscape_wps.ui.document_bridge_pyqt5 import (
    LayoutLine,
    apply_default_tab_stops,
    document_plain_text_skip_strike,
    text_edit_to_layout_lines,
    text_edit_to_outline_paths,
)
from inkscape_wps.core.types import Point, VectorPath


def _slide_plain_preview(stored: str, max_len: int = 18) -> str:
    if not stored or not stored.strip():
        return ""
    s = stored.lstrip()
    if s.startswith("<"):
        doc = QTextDocument()
        doc.setHtml(stored)
        t = document_plain_text_skip_strike(doc).strip().replace("\n", " ")
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
    currentSlideChanged = pyqtSignal(int, int)

    def __init__(self, cfg: MachineConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._slide_height_mm = 80.0
        self.setObjectName("WpsPresentationEditor")
        self.setStyleSheet(
            """
            QWidget#WpsPresentationEditor {
                background-color: #ffffff;
            }
            QListWidget {
                background-color: #f7fafc;
                border: 1px solid #d8e0e8;
                border-radius: 8px;
                padding: 6px;
            }
            QListWidget::item {
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 10px 10px;
                margin: 4px 0;
                background-color: #ffffff;
            }
            QListWidget::item:selected {
                background-color: #e6f4ea;
                border-color: #b7d8c2;
                color: #0f3d26;
            }
            QTextEdit {
                background-color: #ffffff;
                border: 1px solid #d8e0e8;
                border-radius: 10px;
                padding: 10px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self._btn_new = QPushButton("新建幻灯片")
        self._btn_new.setFixedHeight(30)
        self._btn_new.clicked.connect(self._new_slide)
        bar.addWidget(self._btn_new)
        self._btn_del = QPushButton("删除当前页")
        self._btn_del.setFixedHeight(30)
        self._btn_del.clicked.connect(self._delete_current_slide)
        bar.addWidget(self._btn_del)
        bar.addStretch(1)
        hint = QLabel(
            "每页独立富文本；G-code 合并各页并沿 Y 错开。"
            " 左侧列表可拖拽排序；列表聚焦时 Alt+↑ / Alt+↓ 上移/下移。"
        )
        hint.setStyleSheet(
            "color:#6b7280;font-size:12px;background:#f8fafc;"
            "border-radius:8px;padding:8px 10px;"
        )
        hint.setWordWrap(True)
        bar.addWidget(hint)
        self._meta = QLabel()
        self._meta.setStyleSheet("color:#44505c;font-size:12px;font-weight:600;")
        self._meta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bar.addWidget(self._meta)
        root.addLayout(bar)

        split = QSplitter()
        self._list = _SlideListWidget()
        self._list._host = self
        self._list.setMaximumWidth(220)
        self._list.setMinimumWidth(220)
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
        # P4-B-3：演示母版页眉/页脚（用于排版/预览/可选导出；不引入背景）
        self._master_header: str = ""
        self._master_footer: str = ""
        self._refresh_list(select_row=0)

    def slide_editor(self) -> QTextEdit:
        return self._editor

    def slide_list_widget(self) -> QListWidget:
        """左侧幻灯片列表（供主窗挂接右键菜单等）。"""
        return self._list

    def _build_slide_list_card(self, index: int, preview: str, *, selected: bool) -> QWidget:
        card = QFrame()
        card.setObjectName("SlideListCard")
        if selected:
            card.setStyleSheet(
                """
                QFrame#SlideListCard {
                    background-color: #eaf6ef;
                    border: 1px solid #9fc9ac;
                    border-radius: 8px;
                }
                """
            )
        else:
            card.setStyleSheet(
                """
                QFrame#SlideListCard {
                    background-color: #ffffff;
                    border: 1px solid #dce4eb;
                    border-radius: 8px;
                }
                """
            )
        row = QHBoxLayout(card)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(8)

        thumb = QFrame()
        thumb.setFixedSize(42, 52)
        thumb.setStyleSheet(
            (
                "background:#d9efdf;border:1px solid #9fc9ac;border-radius:6px;"
                if selected
                else "background:#f7fafc;border:1px solid #d8e0e8;border-radius:6px;"
            )
        )
        thumb_l = QVBoxLayout(thumb)
        thumb_l.setContentsMargins(0, 0, 0, 0)
        thumb_no = QLabel(str(index + 1))
        thumb_no.setAlignment(Qt.AlignCenter)
        thumb_no.setStyleSheet(
            "color:#134e31;font-size:16px;font-weight:700;"
            if selected
            else "color:#1c6b42;font-size:16px;font-weight:700;"
        )
        thumb_l.addStretch(1)
        thumb_l.addWidget(thumb_no)
        thumb_l.addStretch(1)
        row.addWidget(thumb)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        title = QLabel(f"第 {index + 1} 页")
        title.setStyleSheet(
            "color:#153a25;font-size:12px;font-weight:700;"
            if selected
            else "color:#2c333a;font-size:12px;font-weight:700;"
        )
        text_col.addWidget(title)
        preview_lb = QLabel(preview or "空白幻灯片")
        preview_lb.setWordWrap(True)
        preview_lb.setStyleSheet(
            "color:#42614d;font-size:11px;"
            if selected
            else "color:#74808c;font-size:11px;"
        )
        text_col.addWidget(preview_lb)
        text_col.addStretch(1)
        row.addLayout(text_col, 1)
        return card

    def _update_meta_label(self) -> None:
        count = len(self._slides)
        current = min(max(self._list.currentRow(), 0), max(count - 1, 0)) + 1
        parts = [f"{count} 页", f"当前第 {current} 页"]
        if self._master_header.strip() or self._master_footer.strip():
            parts.append("含母版")
        self._meta.setText("  |  ".join(parts))

    def _refresh_slide_card_selection(self) -> None:
        current_row = self._list.currentRow()
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is None:
                continue
            pv = _slide_plain_preview(self._slides[row] if row < len(self._slides) else "")
            item.setSizeHint(QSize(0, 72))
            self._list.setItemWidget(
                item,
                self._build_slide_list_card(row, pv, selected=row == current_row),
            )

    def _sync_toolbar_state(self) -> None:
        has_many = len(self._slides) > 1
        self._btn_del.setEnabled(has_many)
        self._btn_del.setToolTip("至少保留一页幻灯片" if not has_many else "")
        self._update_meta_label()

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
        text = f"第 {row + 1} 页"
        if pv:
            text = f"{text}\n{pv}"
        it.setText(text)
        it.setSizeHint(QSize(0, 72))
        self._list.setItemWidget(
            it,
            self._build_slide_list_card(row, pv, selected=row == self._list.currentRow()),
        )
        self._update_meta_label()

    def _refresh_list(self, select_row: int = 0) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for i in range(len(self._slides)):
            pv = _slide_plain_preview(self._slides[i])
            label = f"第 {i + 1} 页"
            if pv:
                label = f"{label}\n{pv}"
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, i)
            it.setSizeHint(QSize(0, 72))
            self._list.addItem(it)
            self._list.setItemWidget(it, self._build_slide_list_card(i, pv, selected=False))
        self._list.blockSignals(False)
        if self._slides:
            self._list.setCurrentRow(min(select_row, len(self._slides) - 1))
        self._refresh_slide_card_selection()
        self._sync_toolbar_state()

    def _on_slide_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._slides):
            return
        self._apply_slide_to_editor(self._slides[row])
        self._refresh_slide_card_selection()
        self._sync_toolbar_state()
        self.currentSlideChanged.emit(row, len(self._slides))

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
        self._refresh_list(select_row=min(row, len(self._slides) - 1))
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
        self._master_header = ""
        self._master_footer = ""
        self._refresh_list(0)
        self._editor.clear()
        self.contentChanged.emit()

    def slides_storage(self) -> List[str]:
        return list(self._slides)

    def slides_storage_for_export(self) -> List[str]:
        """用于 PPTX 导出的“纯文本版本”，自动套用母版页眉/页脚。"""
        out: List[str] = []
        for stored in self._slides:
            if not stored or not str(stored).strip():
                base = ""
            elif stored.lstrip().startswith("<"):
                doc = QTextDocument()
                doc.setHtml(stored)
                base = document_plain_text_skip_strike(doc)
            else:
                base = str(stored)
            parts: List[str] = []
            if self._master_header.strip():
                parts.append(self._master_header.strip())
            if base.strip():
                parts.append(base.strip())
            if self._master_footer.strip():
                parts.append(self._master_footer.strip())
            out.append("\n".join(parts))
        return out

    def master_storage(self) -> dict:
        return {"header": self._master_header, "footer": self._master_footer}

    def load_master_storage(self, d: dict | None) -> None:
        d = d or {}
        self._master_header = str(d.get("header", "") or "")
        self._master_footer = str(d.get("footer", "") or "")
        self._update_meta_label()
        self.contentChanged.emit()

    def set_master_header(self, header: str) -> None:
        self._master_header = str(header or "")
        self._update_meta_label()
        self.contentChanged.emit()

    def set_master_footer(self, footer: str) -> None:
        self._master_footer = str(footer or "")
        self._update_meta_label()
        self.contentChanged.emit()

    def clear_master(self) -> None:
        self._master_header = ""
        self._master_footer = ""
        self._update_meta_label()
        self.contentChanged.emit()

    def apply_theme_to_all_slides(
        self, char_fmt: QTextCharFormat, block_fmt: QTextBlockFormat
    ) -> None:
        """P4-B-2：把当前格式（字体/字号/对齐/段前后距）应用到所有幻灯片正文。

        实现策略：
        - 对每页 HTML/纯文本重建 QTextDocument
        - 对整页 merge 字符格式（仅字体族/字号等）
        - 对每个文本块 merge 段落块格式（对齐 + 段前/段后距）
        - 输出 HTML 回填 self._slides，并触发 contentChanged（由主窗非文字栈接管撤销/重做语义）
        """
        row = self._list.currentRow()
        if row < 0:
            row = 0
        if not self._slides:
            return

        new_slides: list[str] = []
        for stored in self._slides:
            doc = QTextDocument()
            if stored and str(stored).lstrip().startswith("<"):
                doc.setHtml(stored)
            else:
                doc.setPlainText(stored or "")

            # 字符级：对整页字符应用（通常只影响字体族/字号，不破坏列表结构）
            cur_all = QTextCursor(doc)
            cur_all.select(QTextCursor.Document)
            cur_all.mergeCharFormat(char_fmt)

            # 段落级：逐块应用对齐与段前/段后距，尽量用 merge 保留缩进/列表语义
            block = doc.firstBlock()
            while block.isValid():
                cur_b = QTextCursor(doc)
                cur_b.setPosition(block.position())
                cur_b.select(QTextCursor.BlockUnderCursor)
                cur_b.mergeBlockFormat(block_fmt)
                block = block.next()

            new_slides.append(doc.toHtml())

        self._slides = new_slides
        self._refresh_list(select_row=min(row, len(self._slides) - 1))
        self.contentChanged.emit()

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

            # P4-B-3：套用母版页眉/页脚到“离屏 QTextEdit”，从而影响预览/G-code。
            if self._master_header.strip() or self._master_footer.strip():
                doc = scr.document()
                cur = QTextCursor(doc)
                cur.beginEditBlock()
                if self._master_header.strip():
                    cur.movePosition(QTextCursor.Start)
                    cur.insertText(self._master_header.strip())
                    cur.insertBlock()
                if self._master_footer.strip():
                    cur.movePosition(QTextCursor.End)
                    cur.insertBlock()
                    cur.insertText(self._master_footer.strip())
                cur.endEditBlock()

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

    def to_outline_paths_all_slides(
        self,
        *,
        mm_per_px_resolver: Callable[[QTextEdit], float],
    ) -> List[VectorPath]:
        scr = self._scratch
        scr.setFont(self._editor.font())
        scr.document().setDocumentMargin(self._editor.document().documentMargin())
        vw = max(1, self._editor.viewport().width())
        vh = max(1, self._editor.viewport().height())
        scr.resize(vw, vh)

        out: List[VectorPath] = []
        for i, stored in enumerate(self._slides):
            scr.blockSignals(True)
            if not stored or not stored.strip():
                scr.clear()
            elif stored.lstrip().startswith("<"):
                scr.setHtml(stored)
            else:
                scr.setPlainText(stored)

            if self._master_header.strip() or self._master_footer.strip():
                doc = scr.document()
                cur = QTextCursor(doc)
                cur.beginEditBlock()
                if self._master_header.strip():
                    cur.movePosition(QTextCursor.Start)
                    cur.insertText(self._master_header.strip())
                    cur.insertBlock()
                if self._master_footer.strip():
                    cur.movePosition(QTextCursor.End)
                    cur.insertBlock()
                    cur.insertText(self._master_footer.strip())
                cur.endEditBlock()

            scr.blockSignals(False)
            slide_paths = text_edit_to_outline_paths(
                scr,
                self._cfg,
                mm_per_px=mm_per_px_resolver(scr),
            )
            dy = i * self._slide_height_mm
            for vp in slide_paths:
                pts = tuple(Point(p.x, p.y - dy) for p in vp.points)
                out.append(VectorPath(pts, pen_down=vp.pen_down))

        row = self._list.currentRow()
        if row < 0:
            row = 0
        if row < len(self._slides):
            self._apply_slide_to_editor(self._slides[row])
        return out
