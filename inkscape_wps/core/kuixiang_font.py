"""奎享 kdraw 导出 JSON 字库（与 grblapp `gfont_loader` / `font_schema` 对齐）。

仅解析 **已导出** 的 JSON（含 glyphs → 多段折线 → 点 dict 含 x,y,t）；不解析二进制 .gfont。
坐标经 `font_points_to_layout_strokes` 转为以字心为原点的毫米笔画，
再归一化到与 Hershey 一致的 em 框便于共用 `map_line`。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

PointDict = Dict[str, Any]
StrokeMM = List[Tuple[float, float]]
GlyphMM = List[List[StrokeMM]]


def is_kuixiang_gfont_extract_payload(payload: Any) -> bool:
    """识别奎享提取格式：顶层 glyphs 为 dict，值为多段折线，点为 {x,y,...}。"""
    if not isinstance(payload, dict):
        return False
    glyphs = payload.get("glyphs")
    if not isinstance(glyphs, dict) or not glyphs:
        return False
    for v in glyphs.values():
        if not isinstance(v, list) or not v:
            continue
        first = v[0]
        if isinstance(first, list) and first and isinstance(first[0], dict):
            p0 = first[0]
            return "x" in p0 and "y" in p0
    return False


def _split_polyline_by_pen(raw: List[PointDict]) -> List[List[Tuple[float, float]]]:
    """按 t=0（抬笔移动）拆分为多段连续折线。"""
    if not raw:
        return []
    segments: List[List[Tuple[float, float]]] = []
    current: List[Tuple[float, float]] = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        fx = float(p.get("x", 0.0))
        fy = float(p.get("y", 0.0))
        t = int(p.get("t", 1))
        if t == 0 and current:
            if len(current) >= 2:
                segments.append(current)
            current = [(fx, fy)]
        else:
            current.append((fx, fy))
    if len(current) >= 2:
        segments.append(current)
    return segments


def _char_global_bounds(polylines: List[Any]) -> Tuple[float, float, float, float] | None:
    xs: List[float] = []
    ys: List[float] = []
    for raw in polylines:
        if not isinstance(raw, list):
            continue
        for p in raw:
            if not isinstance(p, dict):
                continue
            xs.append(float(p.get("x", 0.0)))
            ys.append(float(p.get("y", 0.0)))
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def font_points_to_layout_strokes(
    segments_font_xy: List[List[Tuple[float, float]]],
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    *,
    mm_per_unit: float = 0.01530,
) -> List[List[Tuple[float, float]]]:
    """
    奎享 font 单位 → 以字心为原点的毫米坐标（与 grblapp 一致）。
    不做 XY 交换；镜像/翻转由 `coordinate_transform` 处理。
    """
    cx = (max_x + min_x) / 2.0
    cy = (max_y + min_y) / 2.0
    out: List[List[Tuple[float, float]]] = []
    for seg in segments_font_xy:
        if len(seg) < 2:
            continue
        layout: List[Tuple[float, float]] = []
        for fx, fy in seg:
            px = (fx - cx) * mm_per_unit
            py = (fy - cy) * mm_per_unit
            layout.append((px, py))
        out.append(layout)
    return out


def kuixiang_extract_payload_to_strokes_mm(
    payload: Dict[str, Any],
    *,
    mm_per_unit: float = 0.01530,
) -> Dict[str, List[List[Tuple[float, float]]]]:
    """导出 JSON → 字符 → 毫米笔画（字心原点）。"""
    glyphs = payload.get("glyphs")
    if not isinstance(glyphs, dict):
        return {}
    result: Dict[str, List[List[Tuple[float, float]]]] = {}
    for ch, polylines in glyphs.items():
        if not isinstance(ch, str) or len(ch) != 1:
            continue
        if not isinstance(polylines, list):
            continue
        bounds = _char_global_bounds(polylines)
        if bounds is None:
            continue
        min_x, min_y, max_x, max_y = bounds
        char_strokes: List[List[Tuple[float, float]]] = []
        for raw_poly in polylines:
            if not isinstance(raw_poly, list) or not raw_poly:
                continue
            for seg in _split_polyline_by_pen(raw_poly):
                char_strokes.extend(
                    font_points_to_layout_strokes(
                        [seg], min_x, min_y, max_x, max_y, mm_per_unit=mm_per_unit
                    )
                )
        if char_strokes:
            result[ch] = char_strokes
    return result


def normalize_mm_glyphs_to_em(
    glyphs_mm: Dict[str, List[List[Tuple[float, float]]]],
    *,
    target_em: float = 10.0,
) -> Dict[str, List[List[Tuple[float, float]]]]:
    """将每字毫米笔画平移到左下为参考、高度缩放到 target_em，与内置 Hershey JSON 习惯一致。"""
    out: Dict[str, List[List[Tuple[float, float]]]] = {}
    for ch, polys in glyphs_mm.items():
        if not polys:
            continue
        xs = [x for p in polys for x, _ in p]
        ys = [y for p in polys for _, y in p]
        if not xs:
            continue
        min_x = min(xs)
        min_y, max_y = min(ys), max(ys)
        h = max(max_y - min_y, 1e-6)
        new_polys: List[List[Tuple[float, float]]] = []
        for poly in polys:
            if len(poly) < 2:
                continue
            new_polys.append(
                [((x - min_x) / h * target_em, (y - min_y) / h * target_em) for x, y in poly]
            )
        if new_polys:
            out[ch] = new_polys
    return out


def load_kuixiang_json_as_em_glyphs(
    payload: Dict[str, Any],
    *,
    mm_per_unit: float = 0.01530,
    target_em: float = 10.0,
) -> Dict[str, List[List[Tuple[float, float]]]]:
    mm_g = kuixiang_extract_payload_to_strokes_mm(payload, mm_per_unit=mm_per_unit)
    return normalize_mm_glyphs_to_em(mm_g, target_em=target_em)
