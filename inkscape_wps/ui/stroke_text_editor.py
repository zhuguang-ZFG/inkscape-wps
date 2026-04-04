"""单线字形文本编辑器（PyQt5）：输入、光标、选区、IME 与笔画渲染。"""

from __future__ import annotations

import html
import re
from typing import Optional

from PyQt5.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QInputMethodEvent, QKeyEvent, QMouseEvent, QPainter, QPen
from PyQt5.QtWidgets import QApplication, QWidget

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.core.hershey import HersheyFontMapper
from inkscape_wps.ui.stroke_layout import LayoutRow, StrokeLayoutEngine
from inkscape_wps.ui.stroke_text_model import StrokeTextModel


class StrokeTextEditor(QWidget):
    textChanged = pyqtSignal()

    def __init__(
        self,
        cfg: MachineConfig,
        mapper: HersheyFontMapper,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._mapper = mapper
        self._model = StrokeTextModel("")
        ls = float(getattr(cfg, "stroke_editor_line_spacing", 1.45))
        self._layout = StrokeLayoutEngine(font_px=18.0, line_spacing=ls)
        self._rows: list[LayoutRow] = []
        self._preedit_text = ""
        self._drag_selecting = False
        self._caret_visible = True
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self._blink = QTimer(self)
        self._blink.timeout.connect(self._on_blink)
        self._blink.start(530)
        self.setObjectName("StrokeTextEditor")
        _f0 = QFont()
        _f0.setPointSize(12)
        QWidget.setFont(self, _f0)
        self._relayout()

    def _mapper_mm_per_pt(self) -> float:
        """与预览、map_document_lines、G-code 一致，使用机床配置中的 mm/pt 缩放。"""
        try:
            v = float(getattr(self._cfg, "mm_per_pt", 1.0))
        except (TypeError, ValueError):
            v = 1.0
        return max(0.01, min(20.0, v))

    def set_stroke_font_point_size(self, pt: float) -> None:
        """屏幕编辑区字号（pt）；内部布局像素与 pt 近似换算，影响单线排版疏密。"""
        pt = max(6.0, min(200.0, float(pt)))
        self._layout.font_px = max(8.0, pt * 1.5)
        f = QFont(self.font())
        f.setPointSizeF(pt)
        QWidget.setFont(self, f)
        self._emit_changed()

    def set_stroke_font_family(self, family: str) -> None:
        """
        同步 QWidget 字体族；
        单线笔画轮廓仍由当前 Hershey/奎享字库与 mm/pt 决定，
        与写字机一致。
        """
        fam = (family or "").strip() or self.font().family()
        f = QFont(self.font())
        f.setFamily(fam)
        QWidget.setFont(self, f)
        self._emit_changed()

    def stroke_font_point_size(self) -> float:
        ps = self.font().pointSizeF()
        if ps > 0:
            return float(ps)
        ps2 = self.font().pointSize()
        if ps2 > 0:
            return float(ps2)
        return max(6.0, self._layout.font_px / 1.5)

    def set_line_spacing(self, value: float) -> None:
        """与 MachineConfig.stroke_editor_line_spacing 同步；立即重排。"""
        self._layout.line_spacing = max(1.0, min(3.0, float(value)))
        setattr(self._cfg, "stroke_editor_line_spacing", self._layout.line_spacing)
        self._emit_changed()

    def _on_blink(self) -> None:
        self._caret_visible = not self._caret_visible
        self.update()

    def _relayout(self) -> None:
        txt = self._model.text
        if self._preedit_text:
            c = self._model.caret
            txt = txt[:c] + self._preedit_text + txt[c:]
        fs = self._layout.font_px * 0.75
        ref_a = self._layout.font_px * 0.62
        mpp = self._mapper_mm_per_pt()
        advs, _, _ = self._mapper.estimate_advances_and_vertical_metrics(
            txt,
            fs,
            mm_per_pt=mpp,
            reference_ascent_pt=ref_a,
        )

        def _row_vertical(sub: str) -> tuple[float, float]:
            _adv, asc, desc = self._mapper.estimate_advances_and_vertical_metrics(
                sub,
                fs,
                mm_per_pt=mpp,
                reference_ascent_pt=ref_a,
            )
            del _adv
            return asc, desc

        self._rows = self._layout.layout(
            txt,
            max(1.0, float(self.width())),
            margin_px=14.0,
            advances_px=advs,
            vertical_for_row=_row_vertical,
        )

    def _emit_changed(self) -> None:
        self._caret_visible = True
        self._relayout()
        self.textChanged.emit()
        self.update()

    # -------- compatibility api (for old QTextEdit call sites) --------
    def toPlainText(self) -> str:  # noqa: N802
        return self._model.text

    def setPlainText(self, text: str) -> None:  # noqa: N802
        self._model.set_text(text)
        self._preedit_text = ""
        self._emit_changed()

    def insert_plain(self, text: str) -> None:
        """在光标处插入纯文本（符号面板等）。"""
        self.setFocus(Qt.StrongFocus)
        self._model.insert_text(text)
        self._emit_changed()

    def clear(self) -> None:
        self.setPlainText("")

    def toHtml(self) -> str:  # noqa: N802
        esc = html.escape(self._model.text).replace("\n", "<br/>")
        return f"<p>{esc}</p>"

    def setHtml(self, src: str) -> None:  # noqa: N802
        t = re.sub(r"<br\s*/?>", "\n", src, flags=re.IGNORECASE)
        t = re.sub(r"</p\s*>", "\n", t, flags=re.IGNORECASE)
        t = re.sub(r"<[^>]+>", "", t)
        t = html.unescape(t).strip("\n")
        self.setPlainText(t)

    def selectAll(self) -> None:  # noqa: N802
        self._model.select_all()
        self.update()

    def canUndo(self) -> bool:  # noqa: N802
        return self._model.can_undo()

    def canRedo(self) -> bool:  # noqa: N802
        return self._model.can_redo()

    def undo(self) -> None:
        if self._model.undo():
            self._emit_changed()

    def redo(self) -> None:
        if self._model.redo():
            self._emit_changed()

    def find(self, needle: str) -> bool:
        if not needle:
            return False
        start = self._model.selection_range()[1]
        idx = self._model.text.find(needle, start)
        if idx < 0:
            return False
        self._model.move_caret(idx, keep_selection=False)
        self._model.move_caret(idx + len(needle), keep_selection=True)
        self.update()
        return True

    def replace_selection(self, text: str) -> None:
        self._model.replace_selection(text, record_undo=True)
        self._emit_changed()

    def edit_cut(self) -> None:
        """菜单「剪切」：与 Ctrl+X 一致。"""
        QApplication.clipboard().setText(self._model.selected_text())
        self.replace_selection("")

    def edit_copy(self) -> None:
        """菜单「复制」：与 Ctrl+C 一致。"""
        QApplication.clipboard().setText(self._model.selected_text())

    def edit_paste(self) -> None:
        """菜单「粘贴」：与 Ctrl+V 一致。"""
        self._model.insert_text(QApplication.clipboard().text() or "")
        self._emit_changed()

    def move_caret(self, pos: int, *, keep_selection: bool = False) -> None:
        self._model.move_caret(pos, keep_selection=keep_selection)
        self.update()

    def selected_text(self) -> str:
        return self._model.selected_text()

    def to_layout_lines(self):
        self._relayout()
        return self._layout.to_layout_lines(
            self._rows,
            self._cfg,
            viewport_width_px=max(1.0, float(self.width())),
            viewport_height_px=max(1.0, float(self.height())),
        )

    # -------- ime --------
    def inputMethodEvent(self, e: QInputMethodEvent) -> None:  # noqa: N802
        commit = e.commitString()
        if commit:
            self._model.insert_text(commit)
        self._preedit_text = e.preeditString()
        self._emit_changed()

    def inputMethodQuery(self, query):  # noqa: N802
        self._relayout()
        cx, cy, cw, ch = self._layout.caret_rect(self._rows, self._model.caret, margin_px=14.0)
        rect = QRect(int(cx), int(cy), max(1, int(cw)), max(1, int(ch)))
        if query == Qt.ImCursorRectangle:
            return rect
        if query == Qt.ImCursorPosition:
            return self._model.caret
        if query == Qt.ImSurroundingText:
            return self._model.text
        if query == Qt.ImCurrentSelection:
            return self._model.selected_text()
        return super().inputMethodQuery(query)

    # -------- events --------
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        self._caret_visible = True
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            idx = self._index_at(event.pos())
            self._model.move_caret(idx, keep_selection=False)
            self._drag_selecting = True
            self._caret_visible = True
            self.update()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_selecting:
            idx = self._index_at(event.pos())
            self._model.move_caret(idx, keep_selection=True)
            self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_selecting = False
            self.update()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        mod = e.modifiers()
        ctrl = bool(mod & (Qt.ControlModifier | Qt.MetaModifier))
        shift = bool(mod & Qt.ShiftModifier)
        k = e.key()
        if ctrl and k == Qt.Key_A:
            self.selectAll()
            return
        if ctrl and k == Qt.Key_C:
            QApplication.clipboard().setText(self._model.selected_text())
            return
        if ctrl and k == Qt.Key_X:
            QApplication.clipboard().setText(self._model.selected_text())
            self.replace_selection("")
            return
        if ctrl and k == Qt.Key_V:
            self._model.insert_text(QApplication.clipboard().text() or "")
            self._emit_changed()
            return
        if ctrl and k == Qt.Key_Z:
            self.undo()
            return
        if ctrl and k == Qt.Key_Y:
            self.redo()
            return
        if k == Qt.Key_Backspace:
            self._model.backspace()
            self._emit_changed()
            return
        if k == Qt.Key_Delete:
            self._model.delete()
            self._emit_changed()
            return
        if k == Qt.Key_Left:
            self._model.move_caret(self._model.caret - 1, keep_selection=shift)
            self.update()
            return
        if k == Qt.Key_Right:
            self._model.move_caret(self._model.caret + 1, keep_selection=shift)
            self.update()
            return
        if k == Qt.Key_Home:
            self._model.move_caret(0, keep_selection=shift)
            self.update()
            return
        if k == Qt.Key_End:
            self._model.move_caret(len(self._model.text), keep_selection=shift)
            self.update()
            return
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self._model.insert_text("\n")
            self._emit_changed()
            return

        txt = e.text()
        if txt and not ctrl:
            self._model.insert_text(txt)
            self._emit_changed()
            return
        super().keyPressEvent(e)

    def paintEvent(self, e) -> None:  # noqa: N802
        del e
        self._relayout()
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#ffffff"))
        try:
            page_w = max(1.0, float(getattr(self._cfg, "page_width_mm", 210.0)))
            margin_mm = max(0.0, float(getattr(self._cfg, "document_margin_mm", 0.0)))
            margin_px = min(float(self.width()) * 0.45, float(self.width()) * margin_mm / page_w)
        except (TypeError, ValueError):
            margin_px = 0.0
        if margin_px > 0.5:
            guide = QColor("#d9e6dc")
            p.fillRect(QRectF(0.0, 0.0, margin_px, float(self.height())), QColor("#f8fbf9"))
            p.setPen(QPen(guide, 1.0, Qt.DashLine))
            p.drawLine(QPointF(margin_px, 0.0), QPointF(margin_px, float(self.height())))
            right_x = max(margin_px, float(self.width()) - margin_px)
            p.drawLine(QPointF(right_x, 0.0), QPointF(right_x, float(self.height())))
        # selection
        if self._model.has_selection():
            s, t = self._model.selection_range()
            for row in self._rows:
                for c in row.cells:
                    if s <= c.index < t:
                        p.fillRect(QRectF(c.x_px, c.y_px, c.w_px, c.h_px), QColor("#e6f4ea"))
        # strokes
        pen = QPen(QColor("#1a1a1a"))
        pen.setWidthF(1.15)
        p.setPen(pen)
        mpp = self._mapper_mm_per_pt()
        for row in self._rows:
            if not row.text:
                continue
            lines = self._mapper.map_line(
                row.text,
                row.x_px,
                row.y_px + row.baseline_du,
                self._layout.font_px * 0.75,
                mm_per_pt=mpp,
                reference_ascent_pt=self._layout.font_px * 0.62,
                per_char_advances_mm=row.advances_px,
            )
            for vp in lines:
                if len(vp.points) < 2:
                    continue
                q = [QPointF(pt.x, pt.y) for pt in vp.points]
                for i in range(1, len(q)):
                    p.drawLine(q[i - 1], q[i])
        # preedit underline
        if self._preedit_text:
            cx, cy, _, ch = self._layout.caret_rect(self._rows, self._model.caret, margin_px=14.0)
            pre_w = sum(
                self._mapper.estimate_advances(
                    self._preedit_text,
                    self._layout.font_px * 0.75,
                    mm_per_pt=mpp,
                    reference_ascent_pt=self._layout.font_px * 0.62,
                )
            )
            p.setPen(QPen(QColor("#2767c6"), 1.0, Qt.DashLine))
            p.drawLine(QPointF(cx, cy + ch - 2), QPointF(cx + pre_w, cy + ch - 2))
        # caret
        if self.hasFocus() and self._caret_visible:
            cx, cy, cw, ch = self._layout.caret_rect(self._rows, self._model.caret, margin_px=14.0)
            p.fillRect(QRectF(cx, cy, max(1.0, cw), ch), QColor("#1f2328"))
        p.end()

    def _index_at(self, pt: QPoint) -> int:
        self._relayout()
        if not self._rows:
            return 0
        y = float(pt.y())
        row = self._rows[0]
        for r in self._rows:
            if r.y_px <= y < r.y_px + r.h_px:
                row = r
                break
            if y >= r.y_px:
                row = r
        if not row.cells:
            return row.start
        x = float(pt.x())
        for c in row.cells:
            mid = c.x_px + c.w_px * 0.5
            if x < mid:
                return c.index
        return row.cells[-1].index + 1
