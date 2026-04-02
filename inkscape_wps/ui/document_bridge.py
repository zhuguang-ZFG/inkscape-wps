"""
将 QTextEdit 文档转为核心层可用的行布局（毫米、Y 向上）。
使用 QTextBlock / QTextLine 与文档布局坐标，按 TrueType 字宽生成 per-char advance，并传入 Hershey 映射。
"""

from __future__ import annotations

from typing import List, Tuple, Union

from PyQt6.QtGui import QFont, QFontMetricsF, QTextCursor
from PyQt6.QtWidgets import QTextEdit

from inkscape_wps.core.config import MachineConfig

# (text, ox_mm, baseline_y_mm, font_pt) 或含 ascent / 字宽
LayoutLine = Union[
    Tuple[str, float, float, float],
    Tuple[str, float, float, float, float],
    Tuple[str, float, float, float, float, Tuple[float, ...]],
]


def _font_layout_key(font: QFont) -> tuple:
    """同一段 run 内视为同一套排版度量（混排时按字号/字重/斜体拆分）。"""
    ps = float(font.pointSizeF() if font.pointSizeF() > 0 else font.pointSize() or 12)
    if ps <= 0:
        ps = 12.0
    return (font.family(), round(ps, 3), int(font.weight()), bool(font.italic()))


def apply_default_tab_stops(editor: QTextEdit, *, n_spaces: float = 4.0) -> None:
    """与常见「制表位 = N 个空格宽」对齐，改善 Tab 在 QTextLayout 中的占位。"""
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
    """
    返回每行布局元组；baseline_y_mm 为自纸张底边向上的距离（CNC 习惯）。
    当 QTextLayout 不可用时回退为按换行 + 字体度量的简化实现。
    """
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
            cur = QTextCursor(doc)
            j = 0
            while j < tlen:
                pos0 = line_start + j
                cur.setPosition(pos0)
                tf0 = cur.charFormat().font()
                key0 = _font_layout_key(tf0)
                j_end = j + 1
                while j_end < tlen:
                    cur.setPosition(line_start + j_end)
                    if _font_layout_key(cur.charFormat().font()) != key0:
                        break
                    j_end += 1

                pt = float(tf0.pointSizeF() if tf0.pointSizeF() > 0 else tf0.pointSize() or 12)
                if pt <= 0:
                    pt = 12.0
                fm = QFontMetricsF(tf0)
                ref_ascent_pt = pt * (fm.ascent() / max(fm.height(), 1e-6))

                rel0 = j
                x0 = line_x + line.cursorToX(rel0)
                ox_mm = m + x0 * mm_px_x

                chars: List[str] = []
                advs: List[float] = []
                for k in range(j, j_end):
                    pos = line_start + k
                    ch = doc.characterAt(pos)
                    if ch == "\u0000":
                        break
                    chars.append(ch)
                    w = line.cursorToX(k + 1) - line.cursorToX(k)
                    advs.append(w * mm_px_x)
                text = "".join(chars).replace("\u2029", "")

                if text:
                    if len(advs) == len(text):
                        out.append((text, ox_mm, baseline_up_mm, pt, ref_ascent_pt, tuple(advs)))
                    else:
                        out.append((text, ox_mm, baseline_up_mm, pt, ref_ascent_pt))
                j = j_end

        block = block.next()

    if out:
        return out

    return _fallback_plain_lines(editor, cfg, margin_mm=m, mm_per_px=mm_px_x)


def _fallback_plain_lines(
    editor: QTextEdit,
    cfg: MachineConfig,
    *,
    margin_mm: float,
    mm_per_px: float,
) -> List[LayoutLine]:
    from PyQt6.QtGui import QFontMetricsF as QFM

    font = editor.currentFont()
    fm = QFM(font)
    pt = float(font.pointSizeF() if font.pointSizeF() > 0 else font.pointSize())
    if pt <= 0:
        pt = 12.0
    vw = max(1, editor.viewport().width())
    scale = mm_per_px if mm_per_px > 0 else cfg.page_width_mm / float(vw)
    raw_lines = editor.toPlainText().split("\n")
    if not raw_lines:
        raw_lines = [""]
    line_height_px = fm.height()
    ascent_px = fm.ascent()
    ref_ascent_pt = pt * (fm.ascent() / max(fm.height(), 1e-6))
    doc_h = max(float(editor.document().size().height()), 1.0)
    mm_px_y_fb = cfg.page_height_mm / doc_h * float(cfg.layout_vertical_scale)
    out: List[LayoutLine] = []
    for i, text in enumerate(raw_lines):
        y_top_px = margin_mm / scale + i * line_height_px
        baseline_px = y_top_px + ascent_px
        baseline_up_mm = cfg.page_height_mm - baseline_px * mm_px_y_fb
        ox_mm = margin_mm
        out.append((text, ox_mm, baseline_up_mm, pt, ref_ascent_pt))
    return out
