"""单线字形编辑布局：纯文本 -> 行布局。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from inkscape_wps.core.config import MachineConfig


@dataclass
class GlyphCell:
    ch: str
    index: int
    x_px: float
    y_px: float
    w_px: float
    h_px: float


@dataclass
class LayoutRow:
    text: str
    start: int
    end: int
    x_px: float
    y_px: float
    h_px: float
    # 行顶到基线（与 advances 同一文档单位，与编辑区 QWidget 坐标一致）
    baseline_du: float
    ascent_du: float
    descent_du: float
    cells: List[GlyphCell]
    advances_px: List[float]


class StrokeLayoutEngine:
    """单线字形布局：按字符 advance 换行，并按行聚合纵向度量。"""

    def __init__(self, *, font_px: float = 18.0, line_spacing: float = 1.45) -> None:
        self.font_px = max(8.0, float(font_px))
        self.line_spacing = max(1.0, float(line_spacing))

    @property
    def cell_w(self) -> float:
        return self.font_px * 0.62

    @property
    def line_h(self) -> float:
        return self.font_px * self.line_spacing

    def _leading_du(self) -> float:
        """行距增量：与字号成比例，并由 line_spacing 相对默认 1.45 缩放。"""
        base = max(2.0, self.font_px * 0.12)
        return base * max(0.5, float(self.line_spacing) / 1.45)

    def _default_vertical(self) -> Tuple[float, float, float]:
        pt = self.font_px * 0.75
        asc = pt * 0.82
        desc = pt * 0.18
        ld = self._leading_du()
        return asc, desc, asc + desc + ld

    def layout(
        self,
        text: str,
        viewport_width: float,
        margin_px: float = 12.0,
        advances_px: List[float] | None = None,
        vertical_for_row: Optional[Callable[[str], Tuple[float, float]]] = None,
    ) -> List[LayoutRow]:
        max_w = max(20.0, float(viewport_width) - margin_px * 2.0)
        out: List[LayoutRow] = []
        y = margin_px
        i = 0
        n = len(text)
        default_asc, default_desc, default_h = self._default_vertical()
        leading = self._leading_du()
        while i <= n:
            start = i
            line_chars: List[str] = []
            cells: List[GlyphCell] = []
            row_adv: List[float] = []
            x = margin_px
            while i < n:
                ch = text[i]
                if ch == "\n":
                    i += 1
                    break
                w = (
                    advances_px[i]
                    if advances_px is not None and i < len(advances_px)
                    else self.cell_w
                )
                if line_chars and (x + w - margin_px) > max_w:
                    break
                line_chars.append(ch)
                row_adv.append(w)
                x += w
                i += 1
            if i >= n and not line_chars and (start == n):
                # 空文档或尾部行
                out.append(
                    LayoutRow(
                        text="",
                        start=start,
                        end=start,
                        x_px=margin_px,
                        y_px=y,
                        h_px=default_h,
                        baseline_du=default_asc,
                        ascent_du=default_asc,
                        descent_du=default_desc,
                        cells=[],
                        advances_px=[],
                    )
                )
                break
            row_text = "".join(line_chars)
            # 仅换行产生的空行：固定用默认行盒，避免与有字行混排时高低不一造成抖动
            if not row_text:
                asc, desc = default_asc, default_desc
                h_row = default_h
            elif vertical_for_row is not None:
                asc, desc = vertical_for_row(row_text)
                asc = max(1.0, float(asc))
                desc = max(1.0, float(desc))
                h_row = max(default_h, asc + desc + leading)
            else:
                asc, desc = default_asc, default_desc
                h_row = asc + desc + leading
            for j, ch in enumerate(line_chars):
                idx = start + j
                w = row_adv[j] if j < len(row_adv) else self.cell_w
                ox = margin_px + sum(row_adv[:j]) if j else margin_px
                cells.append(GlyphCell(ch=ch, index=idx, x_px=ox, y_px=y, w_px=w, h_px=h_row))
            out.append(
                LayoutRow(
                    text=row_text,
                    start=start,
                    end=i,
                    x_px=margin_px,
                    y_px=y,
                    h_px=h_row,
                    baseline_du=asc,
                    ascent_du=asc,
                    descent_du=desc,
                    cells=cells,
                    advances_px=row_adv,
                )
            )
            y += h_row
            if i >= n:
                break
        return out

    def caret_rect(
        self,
        rows: List[LayoutRow],
        caret: int,
        margin_px: float = 12.0,
    ) -> Tuple[float, float, float, float]:
        if not rows:
            _a, _d, h = self._default_vertical()
            return margin_px, margin_px, 1.0, h
        for row in rows:
            if row.start <= caret <= row.end:
                if row.cells:
                    if caret <= row.cells[0].index:
                        x = row.cells[0].x_px
                    elif caret > row.cells[-1].index:
                        x = row.cells[-1].x_px + row.cells[-1].w_px
                    else:
                        x = row.cells[0].x_px
                        for c in row.cells:
                            if c.index < caret:
                                x = c.x_px + c.w_px
                            else:
                                break
                else:
                    x = row.x_px
                return x, row.y_px, 1.0, row.h_px
        last = rows[-1]
        x = last.x_px + (
            last.cells[-1].w_px + last.cells[-1].x_px - last.x_px if last.cells else 0.0
        )
        return x, last.y_px, 1.0, last.h_px

    def to_layout_lines(
        self,
        rows: List[LayoutRow],
        cfg: MachineConfig,
        *,
        viewport_width_px: float,
        viewport_height_px: float,
        margin_mm: float | None = None,
    ):
        """输出与 map_document_lines 兼容的 LayoutLine 序列。"""
        m = cfg.document_margin_mm if margin_mm is None else float(margin_mm)
        mm_px_x = cfg.page_width_mm / max(1.0, float(viewport_width_px))
        mm_px_y = cfg.page_height_mm / max(1.0, float(viewport_height_px))
        out = []
        pt = self.font_px * 0.75
        for row in rows:
            if not row.text:
                continue
            baseline_doc_y = row.y_px + row.baseline_du
            baseline_up_mm = cfg.page_height_mm - baseline_doc_y * mm_px_y
            ox_mm = m + row.x_px * mm_px_x
            advs = (
                tuple(a * mm_px_x for a in row.advances_px)
                if row.advances_px
                else tuple([self.cell_w * mm_px_x] * len(row.text))
            )
            ref_a = max(pt * 0.5, min(pt * 1.2, row.ascent_du))
            out.append((row.text, ox_mm, baseline_up_mm, pt, ref_a, advs))
        return out
