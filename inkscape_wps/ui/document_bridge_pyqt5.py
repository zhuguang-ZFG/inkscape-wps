"""
PyQt5 版本的 document_bridge：将 QTextEdit 文档转为核心层可用的行布局（毫米、Y 向上）。

说明：
- 代码结构与 PyQt6 版本保持一致，避免在同一进程混用 PyQt6 类型导致崩溃/不兼容。
"""

from __future__ import annotations

from typing import List, Tuple, Union

from PyQt5.QtGui import QFont, QFontMetricsF, QPainterPath, QTextCharFormat, QTextDocument
from PyQt5.QtWidgets import QTextEdit

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.core.types import Point, VectorPath

# (text, ox_mm, baseline_y_mm, font_pt) 或含 ascent / 字宽
LayoutLine = Union[
    Tuple[str, float, float, float],
    Tuple[str, float, float, float, float],
    Tuple[str, float, float, float, float, Tuple[float, ...]],
]


def _font_layout_key(font: QFont) -> tuple:
    ps = float(font.pointSizeF() if font.pointSizeF() > 0 else font.pointSize() or 12)
    if ps <= 0:
        ps = 12.0
    return (font.family(), round(ps, 3), int(font.weight()), bool(font.italic()))


def _line_cursor_to_x(line, rel: int) -> float:
    """兼容部分 PyQt5 绑定中 `QTextLine.cursorToX` 返回 `(x, trailing)` 元组的情况。"""
    v = line.cursorToX(rel)
    if isinstance(v, (tuple, list)):
        return float(v[0])
    return float(v)


def _char_format_at_doc_pos(doc: QTextDocument, pos: int):
    """取某索引处字符的格式。

    注意：`QTextCursor.charFormat()` 在无选区时表示「将要输入」的格式，
    不能用于判断已有字符是否删除线。
    """
    ch = doc.characterAt(pos)
    if ch == "\u0000":
        return QTextCharFormat()
    block = doc.findBlock(pos)
    if not block.isValid():
        return QTextCharFormat()
    it = block.begin()
    while it != block.end():
        frag = it.fragment()
        if frag.isValid():
            start = frag.position()
            end = start + frag.length()
            if start <= pos < end:
                return frag.charFormat()
        it += 1
    return QTextCharFormat()


def _char_run_layout_key(doc: QTextDocument, pos: int) -> tuple:
    """Run 分组键：字体 + 删除线（修订「删除」痕迹不进入 LayoutLine / G-code）。"""
    cf = _char_format_at_doc_pos(doc, pos)
    return (_font_layout_key(cf.font()), bool(cf.fontStrikeOut()))


def document_plain_text_skip_strike(doc: QTextDocument) -> str:
    """与 `text_edit_to_layout_lines` 一致：块间换行，省略带删除线的片段（用于导出纯文本等）。"""
    lines: List[str] = []
    block = doc.firstBlock()
    while block.isValid():
        pieces: List[str] = []
        it = block.begin()
        while it != block.end():
            frag = it.fragment()
            if frag.isValid() and not frag.charFormat().fontStrikeOut():
                pieces.append(frag.text())
            it += 1
        lines.append("".join(pieces))
        block = block.next()
    return "\n".join(lines)


def apply_default_tab_stops(editor: QTextEdit, *, n_spaces: float = 4.0) -> None:
    fm = editor.fontMetrics()
    sp = max(1, fm.horizontalAdvance(" "))
    editor.setTabStopDistance(float(sp) * n_spaces)


def text_edit_to_layout_lines(
    editor: QTextEdit,
    cfg: MachineConfig,
    *,
    margin_mm: float | None = None,
    mm_per_px: float | None = None,
) -> List[LayoutLine]:
    m = cfg.document_margin_mm if margin_mm is None else margin_mm
    doc = editor.document()
    doc.adjustSize()

    vw = max(1, editor.viewport().width())
    mm_px_x = mm_per_px if mm_per_px is not None else cfg.page_width_mm / float(vw)
    doc_h = max(float(doc.size().height()), 1.0)
    mm_px_y = cfg.page_height_mm / doc_h * float(cfg.layout_vertical_scale)

    out: List[LayoutLine] = []
    doc_layout = doc.documentLayout()
    block = doc.firstBlock()

    while block.isValid():
        blo = block.layout()
        if blo is None or blo.lineCount() == 0:
            block = block.next()
            continue

        block_rect = doc_layout.blockBoundingRect(block)
        offset = block_rect.topLeft()

        for li in range(blo.lineCount()):
            line = blo.lineAt(li)
            tlen = line.textLength()
            line_x = offset.x() + line.x()
            line_y_top = offset.y() + line.y()
            baseline_doc_y = line_y_top + line.ascent()
            baseline_up_mm = cfg.page_height_mm - baseline_doc_y * mm_px_y
            line_start = block.position() + line.textStart()
            j = 0
            while j < tlen:
                pos0 = line_start + j
                key0 = _char_run_layout_key(doc, pos0)
                j_end = j + 1
                while j_end < tlen:
                    if _char_run_layout_key(doc, line_start + j_end) != key0:
                        break
                    j_end += 1

                if key0[1]:
                    j = j_end
                    continue

                tf0 = _char_format_at_doc_pos(doc, pos0).font()
                pt = float(tf0.pointSizeF() if tf0.pointSizeF() > 0 else tf0.pointSize() or 12)
                if pt <= 0:
                    pt = 12.0
                fm = QFontMetricsF(tf0)
                ref_ascent_pt = pt * (fm.ascent() / max(fm.height(), 1e-6))

                rel0 = j
                x0 = line_x + _line_cursor_to_x(line, rel0)
                ox_mm = m + x0 * mm_px_x

                chars: List[str] = []
                advs: List[float] = []
                for k in range(j, j_end):
                    pos = line_start + k
                    ch = doc.characterAt(pos)
                    if ch == "\u0000":
                        break
                    chars.append(ch)
                    w = _line_cursor_to_x(line, k + 1) - _line_cursor_to_x(line, k)
                    advs.append(w * mm_px_x)
                text = "".join(chars).replace("\u2029", "")

                if text:
                    if len(advs) == len(text):
                        out.append((text, ox_mm, baseline_up_mm, pt, ref_ascent_pt, tuple(advs)))
                    else:
                        out.append((text, ox_mm, baseline_up_mm, pt, ref_ascent_pt))
                j = j_end

        block = block.next()

    return out


def text_edit_to_outline_paths(
    editor: QTextEdit,
    cfg: MachineConfig,
    *,
    margin_mm: float | None = None,
    mm_per_px: float | None = None,
) -> List[VectorPath]:
    """将 QTextEdit 富文本直接转为字体轮廓路径，保留 run 级字体差异并跳过删除线。"""
    m = cfg.document_margin_mm if margin_mm is None else margin_mm
    doc = editor.document()
    doc.adjustSize()

    vw = max(1, editor.viewport().width())
    mm_px_x = mm_per_px if mm_per_px is not None else cfg.page_width_mm / float(vw)
    doc_h = max(float(doc.size().height()), 1.0)
    mm_px_y = cfg.page_height_mm / doc_h * float(cfg.layout_vertical_scale)

    out: List[VectorPath] = []
    doc_layout = doc.documentLayout()
    block = doc.firstBlock()

    while block.isValid():
        blo = block.layout()
        if blo is None or blo.lineCount() == 0:
            block = block.next()
            continue

        block_rect = doc_layout.blockBoundingRect(block)
        offset = block_rect.topLeft()

        for li in range(blo.lineCount()):
            line = blo.lineAt(li)
            tlen = line.textLength()
            line_x = offset.x() + line.x()
            line_y_top = offset.y() + line.y()
            baseline_doc_y = line_y_top + line.ascent()
            line_start = block.position() + line.textStart()
            j = 0
            while j < tlen:
                pos0 = line_start + j
                key0 = _char_run_layout_key(doc, pos0)
                j_end = j + 1
                while j_end < tlen:
                    if _char_run_layout_key(doc, line_start + j_end) != key0:
                        break
                    j_end += 1

                if key0[1]:
                    j = j_end
                    continue

                tf0 = _char_format_at_doc_pos(doc, pos0).font()
                pt = float(
                    tf0.pointSizeF()
                    if tf0.pointSizeF() > 0
                    else tf0.pointSize() or 12.0
                )
                if pt <= 0:
                    pt = 12.0
                font = QFont(tf0)
                font.setPointSizeF(pt)

                rel0 = j
                x0 = line_x + _line_cursor_to_x(line, rel0)
                chars: List[str] = []
                for k in range(j, j_end):
                    ch = doc.characterAt(line_start + k)
                    if ch == "\u0000":
                        break
                    chars.append(ch)
                text = "".join(chars).replace("\u2029", "")
                if text:
                    path = QPainterPath()
                    path.addText(x0, baseline_doc_y, font, text)
                    for poly in path.toSubpathPolygons():
                        if poly.size() < 2:
                            continue
                        pts: List[Point] = []
                        for qpt in poly:
                            x_mm = float(m) + float(qpt.x()) * mm_px_x
                            y_mm = float(cfg.page_height_mm) - float(qpt.y()) * mm_px_y
                            pts.append(Point(x_mm, y_mm))
                        if len(pts) >= 2 and (pts[0].x != pts[-1].x or pts[0].y != pts[-1].y):
                            pts.append(Point(pts[0].x, pts[0].y))
                        if len(pts) >= 2:
                            out.append(VectorPath(tuple(pts)))
                j = j_end

        block = block.next()

    return out


def html_fragment_to_layout_lines(
    html: str,
    cfg: MachineConfig,
    *,
    cell_left_mm: float,
    cell_top_from_page_top_mm: float,
    cell_width_mm: float,
    cell_height_mm: float,
    mm_per_px_x: float,
    default_pt: float = 12.0,
) -> List[LayoutLine]:
    """将单元格内 HTML 排成 LayoutLine（与 PyQt6 版 document_bridge 语义一致）。"""
    if not html or not html.strip():
        return []

    doc = QTextDocument()
    doc.setDefaultFont(QFont())
    width_px = max(24.0, float(cell_width_mm) / max(mm_per_px_x, 1e-9))
    doc.setTextWidth(width_px)
    doc.setHtml(html)
    doc.adjustSize()

    doc_h = max(float(doc.size().height()), 1.0)
    inner_h = max(float(cell_height_mm) * 0.92, 1e-6)
    mm_px_y = inner_h / doc_h * float(cfg.layout_vertical_scale)

    out: List[LayoutLine] = []
    doc_layout = doc.documentLayout()
    block = doc.firstBlock()

    while block.isValid():
        blo = block.layout()
        if blo is None or blo.lineCount() == 0:
            block = block.next()
            continue

        block_rect = doc_layout.blockBoundingRect(block)
        offset = block_rect.topLeft()

        for li in range(blo.lineCount()):
            line = blo.lineAt(li)
            tlen = line.textLength()
            line_x = offset.x() + line.x()
            line_y_top = offset.y() + line.y()
            baseline_doc_y = line_y_top + line.ascent()
            baseline_from_cell_top_mm = baseline_doc_y * mm_px_y
            baseline_up_mm = float(cfg.page_height_mm) - (
                float(cell_top_from_page_top_mm) + baseline_from_cell_top_mm
            )
            line_start = block.position() + line.textStart()
            j = 0
            while j < tlen:
                pos0 = line_start + j
                key0 = _char_run_layout_key(doc, pos0)
                j_end = j + 1
                while j_end < tlen:
                    if _char_run_layout_key(doc, line_start + j_end) != key0:
                        break
                    j_end += 1

                if key0[1]:
                    j = j_end
                    continue

                tf0 = _char_format_at_doc_pos(doc, pos0).font()
                pt = float(
                    tf0.pointSizeF()
                    if tf0.pointSizeF() > 0
                    else tf0.pointSize() or default_pt
                )
                if pt <= 0:
                    pt = default_pt
                fm = QFontMetricsF(tf0)
                ref_ascent_pt = pt * (fm.ascent() / max(fm.height(), 1e-6))

                rel0 = j
                x0 = line_x + _line_cursor_to_x(line, rel0)
                ox_mm = float(cell_left_mm) + x0 * mm_per_px_x

                chars: List[str] = []
                advs: List[float] = []
                for k in range(j, j_end):
                    pos = line_start + k
                    ch = doc.characterAt(pos)
                    if ch == "\u0000":
                        break
                    chars.append(ch)
                    w = _line_cursor_to_x(line, k + 1) - _line_cursor_to_x(line, k)
                    advs.append(w * mm_per_px_x)
                text = "".join(chars).replace("\u2029", "")

                if text:
                    if len(advs) == len(text):
                        out.append((text, ox_mm, baseline_up_mm, pt, ref_ascent_pt, tuple(advs)))
                    else:
                        out.append((text, ox_mm, baseline_up_mm, pt, ref_ascent_pt))
                j = j_end

        block = block.next()

    if not out:
        plain = QTextDocument(html).toPlainText().strip()
        if not plain:
            return []
        line = plain.split("\n")[0].split("\r")[0]
        if not line:
            return []
        fm = QFontMetricsF(QFont())
        pt = float(default_pt) if default_pt > 0 else 12.0
        ref_ascent_pt = pt * (fm.ascent() / max(fm.height(), 1e-6))
        line_h_mm = max(float(cell_height_mm) * 0.72, pt * float(cfg.mm_per_pt) * 0.85)
        baseline_up_mm = float(cfg.page_height_mm) - (
            float(cell_top_from_page_top_mm) + line_h_mm * 0.15
        )
        default_adv = (6.5 / 10.0) * pt * float(cfg.mm_per_pt)
        advs = tuple(default_adv for _ in line)
        return [(line, float(cell_left_mm) + 0.5, baseline_up_mm, pt, ref_ascent_pt, advs)]

    return out


def html_fragment_to_outline_paths(
    html: str,
    cfg: MachineConfig,
    *,
    cell_left_mm: float,
    cell_top_from_page_top_mm: float,
    cell_width_mm: float,
    cell_height_mm: float,
    mm_per_px_x: float,
    default_pt: float = 12.0,
) -> List[VectorPath]:
    """将单元格 HTML 直接转为字体轮廓路径，用于表格视觉复刻模式。"""
    if not html or not html.strip():
        return []

    doc = QTextDocument()
    doc.setDefaultFont(QFont())
    width_px = max(24.0, float(cell_width_mm) / max(mm_per_px_x, 1e-9))
    doc.setTextWidth(width_px)
    doc.setHtml(html)
    doc.adjustSize()

    doc_h = max(float(doc.size().height()), 1.0)
    inner_h = max(float(cell_height_mm) * 0.92, 1e-6)
    mm_px_y = inner_h / doc_h * float(cfg.layout_vertical_scale)

    out: List[VectorPath] = []
    doc_layout = doc.documentLayout()
    block = doc.firstBlock()

    while block.isValid():
        blo = block.layout()
        if blo is None or blo.lineCount() == 0:
            block = block.next()
            continue

        block_rect = doc_layout.blockBoundingRect(block)
        offset = block_rect.topLeft()

        for li in range(blo.lineCount()):
            line = blo.lineAt(li)
            tlen = line.textLength()
            line_x = offset.x() + line.x()
            line_y_top = offset.y() + line.y()
            baseline_doc_y = line_y_top + line.ascent()
            line_start = block.position() + line.textStart()
            j = 0
            while j < tlen:
                pos0 = line_start + j
                key0 = _char_run_layout_key(doc, pos0)
                j_end = j + 1
                while j_end < tlen:
                    if _char_run_layout_key(doc, line_start + j_end) != key0:
                        break
                    j_end += 1

                if key0[1]:
                    j = j_end
                    continue

                tf0 = _char_format_at_doc_pos(doc, pos0).font()
                pt = float(
                    tf0.pointSizeF()
                    if tf0.pointSizeF() > 0
                    else tf0.pointSize() or default_pt
                )
                if pt <= 0:
                    pt = default_pt
                font = QFont(tf0)
                font.setPointSizeF(pt)

                rel0 = j
                x0 = line_x + _line_cursor_to_x(line, rel0)
                chars: List[str] = []
                for k in range(j, j_end):
                    ch = doc.characterAt(line_start + k)
                    if ch == "\u0000":
                        break
                    chars.append(ch)
                text = "".join(chars).replace("\u2029", "")
                if text:
                    path = QPainterPath()
                    path.addText(x0, baseline_doc_y, font, text)
                    for poly in path.toSubpathPolygons():
                        if poly.size() < 2:
                            continue
                        pts: List[Point] = []
                        for qpt in poly:
                            x_mm = float(cell_left_mm) + float(qpt.x()) * mm_per_px_x
                            y_mm = float(cfg.page_height_mm) - (
                                float(cell_top_from_page_top_mm) + float(qpt.y()) * mm_px_y
                            )
                            pts.append(Point(x_mm, y_mm))
                        if len(pts) >= 2 and (pts[0].x != pts[-1].x or pts[0].y != pts[-1].y):
                            pts.append(Point(pts[0].x, pts[0].y))
                        if len(pts) >= 2:
                            out.append(VectorPath(tuple(pts)))
                j = j_end

        block = block.next()

    return out


def stroke_editor_to_layout_lines(editor, cfg: MachineConfig):
    """StrokeTextEditor 版本桥接。"""
    if hasattr(editor, "to_layout_lines"):
        return editor.to_layout_lines()
    return text_edit_to_layout_lines(editor, cfg)
