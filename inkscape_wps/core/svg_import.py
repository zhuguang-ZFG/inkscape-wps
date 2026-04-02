"""SVG → ``VectorPath``（标准库 xml + 轻量解析，无矢量库依赖）。

- ``<path d>``：``M L H V C Z`` 及相对命令。
- 另支持 ``<line>``、``<polyline>``、``<polygon>``、``<rect>``、``<circle>``、``<ellipse>``（圆/椭圆为多边形近似）。

坐标按 SVG（Y 向下）读入，输出为文档毫米、**Y 向上**；**不经过 Hershey/单线字库**，供笔式矢量直接 ``paths_to_gcode``。
缩放：``viewBox`` / ``width``×``height`` 映射到纸张，保持纵横比居中。
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Sequence, Tuple

from .types import Point, VectorPath

_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")


def _is_number(tok: str) -> bool:
    try:
        float(tok)
        return True
    except (TypeError, ValueError):
        return False


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[-1]
    return tag


def _tokenize_path_d(d: str) -> List[str]:
    s = d.replace(",", " ")
    s = re.sub(r"(?<=\d)(?=-)", " ", s)
    out: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in " \t\n\r":
            i += 1
            continue
        if c in "MmLlHhVvCcZz":
            out.append(c)
            i += 1
            continue
        m = _NUM.match(s, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        i += 1
    return out


def _subpaths_from_tokens(
    tokens: Sequence[str],
) -> List[List[Tuple[float, float]]]:
    """每条子路径为折线顶点列表（SVG 坐标系，Y 向下）。"""
    subpaths: List[List[Tuple[float, float]]] = []
    cur: List[Tuple[float, float]] = []
    i = 0
    x = y = 0.0
    sx = sy = 0.0
    last_cmd = ""

    def ensure_move() -> None:
        nonlocal cur
        if cur:
            subpaths.append(cur)
            cur = []

    while i < len(tokens):
        t = tokens[i]
        if t in "MmLlHhVvCcZz":
            cmd = t
            i += 1
        else:
            cmd = last_cmd
            if cmd.lower() == "z" or not cmd:
                i += 1
                continue

        rel = cmd.islower()
        cu = cmd.upper()
        last_cmd = cmd

        if cu == "Z":
            if len(cur) >= 2 and cur[0] != cur[-1]:
                cur.append(cur[0])
            ensure_move()
            x, y = sx, sy
            continue

        if cu == "M":
            nums: List[float] = []
            while i < len(tokens) and _is_number(tokens[i]):
                nums.append(float(tokens[i]))
                i += 1
            if len(nums) < 2:
                continue
            if not rel:
                x, y = nums[0], nums[1]
            else:
                x, y = x + nums[0], y + nums[1]
            sx, sy = x, y
            ensure_move()
            cur.append((x, y))
            j = 2
            while j + 1 < len(nums):
                if not rel:
                    x, y = nums[j], nums[j + 1]
                else:
                    x, y = x + nums[j], y + nums[j + 1]
                cur.append((x, y))
                j += 2
            last_cmd = "L" if not rel else "l"
            continue

        if cu == "L":
            while i + 1 < len(tokens) and _is_number(tokens[i]) and _is_number(tokens[i + 1]):
                nx = float(tokens[i])
                ny = float(tokens[i + 1])
                i += 2
                if rel:
                    x, y = x + nx, y + ny
                else:
                    x, y = nx, ny
                cur.append((x, y))
            continue

        if cu == "H":
            while i < len(tokens) and _is_number(tokens[i]):
                nx = float(tokens[i])
                i += 1
                if rel:
                    x += nx
                else:
                    x = nx
                cur.append((x, y))
            continue

        if cu == "V":
            while i < len(tokens) and _is_number(tokens[i]):
                ny = float(tokens[i])
                i += 1
                if rel:
                    y += ny
                else:
                    y = ny
                cur.append((x, y))
            continue

        if cu == "C":
            while i + 5 < len(tokens) and all(_is_number(tokens[i + k]) for k in range(6)):
                x1, y1, x2, y2, x3, y3 = (float(tokens[i + j]) for j in range(6))
                i += 6
                if rel:
                    x1, y1 = x + x1, y + y1
                    x2, y2 = x + x2, y + y2
                    x3, y3 = x + x3, y + y3
                for t in (1, 2, 3, 4, 5, 6, 7, 8):
                    s = t / 8.0
                    o = 1.0 - s
                    px = o**3 * x + 3 * o**2 * s * x1 + 3 * o * s**2 * x2 + s**3 * x3
                    py = o**3 * y + 3 * o**2 * s * y1 + 3 * o * s**2 * y2 + s**3 * y3
                    cur.append((px, py))
                x, y = x3, y3
            continue

        i += 1

    if cur:
        subpaths.append(cur)
    return [sp for sp in subpaths if len(sp) >= 2]


def polylines_from_svg_path_d(d: str) -> List[List[Tuple[float, float]]]:
    return _subpaths_from_tokens(_tokenize_path_d(d))


def _parse_float_attr(raw: str | None, default: float) -> float:
    if not raw:
        return default
    raw = raw.strip()
    if raw.endswith("%"):
        return default
    m = _NUM.match(raw)
    return float(m.group(0)) if m else default


def _viewbox(svg: ET.Element) -> Tuple[float, float, float, float]:
    vb = (svg.get("viewBox") or "").strip().split()
    if len(vb) == 4:
        return tuple(float(x) for x in vb)  # type: ignore[return-value]
    w = _parse_float_attr(svg.get("width"), 100.0)
    h = _parse_float_attr(svg.get("height"), 100.0)
    return (0.0, 0.0, w, h)


def _parse_points_attr(raw: str | None) -> List[Tuple[float, float]]:
    if not raw:
        return []
    parts = raw.replace(",", " ").split()
    nums: List[float] = []
    for p in parts:
        if _is_number(p):
            nums.append(float(p))
    out: List[Tuple[float, float]] = []
    for i in range(0, len(nums) - 1, 2):
        out.append((nums[i], nums[i + 1]))
    return out


def _circle_poly(cx: float, cy: float, r: float, segments: int = 48) -> List[Tuple[float, float]]:
    if r <= 0:
        return []
    poly: List[Tuple[float, float]] = []
    for i in range(segments + 1):
        t = 2.0 * math.pi * i / segments
        poly.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return poly


def _ellipse_poly(cx: float, cy: float, rx: float, ry: float, segments: int = 48) -> List[Tuple[float, float]]:
    if rx <= 0 or ry <= 0:
        return []
    poly: List[Tuple[float, float]] = []
    for i in range(segments + 1):
        t = 2.0 * math.pi * i / segments
        poly.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return poly


def _polylines_from_element(el: ET.Element) -> List[List[Tuple[float, float]]]:
    tag = _local_tag(el.tag)
    if tag == "path":
        d = el.get("d") or ""
        return polylines_from_svg_path_d(d.strip()) if d.strip() else []
    if tag == "line":
        x1 = _parse_float_attr(el.get("x1"), 0.0)
        y1 = _parse_float_attr(el.get("y1"), 0.0)
        x2 = _parse_float_attr(el.get("x2"), 0.0)
        y2 = _parse_float_attr(el.get("y2"), 0.0)
        return [[(x1, y1), (x2, y2)]]
    if tag == "polyline":
        pts = _parse_points_attr(el.get("points"))
        return [pts] if len(pts) >= 2 else []
    if tag == "polygon":
        pts = list(_parse_points_attr(el.get("points")))
        if len(pts) >= 2 and pts[0] != pts[-1]:
            pts.append(pts[0])
        return [pts] if len(pts) >= 2 else []
    if tag == "rect":
        x = _parse_float_attr(el.get("x"), 0.0)
        y = _parse_float_attr(el.get("y"), 0.0)
        w = _parse_float_attr(el.get("width"), 0.0)
        h = _parse_float_attr(el.get("height"), 0.0)
        if w <= 0 or h <= 0:
            return []
        ring = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
        return [ring]
    if tag == "circle":
        cx = _parse_float_attr(el.get("cx"), 0.0)
        cy = _parse_float_attr(el.get("cy"), 0.0)
        r = _parse_float_attr(el.get("r"), 0.0)
        pl = _circle_poly(cx, cy, r)
        return [pl] if len(pl) >= 2 else []
    if tag == "ellipse":
        cx = _parse_float_attr(el.get("cx"), 0.0)
        cy = _parse_float_attr(el.get("cy"), 0.0)
        rx = _parse_float_attr(el.get("rx"), 0.0)
        ry = _parse_float_attr(el.get("ry"), 0.0)
        pl = _ellipse_poly(cx, cy, rx, ry)
        return [pl] if len(pl) >= 2 else []
    return []


def collect_polylines_from_svg_element_tree(svg_root: ET.Element) -> List[List[Tuple[float, float]]]:
    """遍历 ``<svg>`` 子树，收集所有可绘制折线（SVG 用户坐标，Y 向下）。"""
    root = svg_root
    if _local_tag(root.tag) != "svg":
        for el in root.iter():
            if _local_tag(el.tag) == "svg":
                root = el
                break
    out: List[List[Tuple[float, float]]] = []
    for el in root.iter():
        t = _local_tag(el.tag)
        if t in ("svg", "g", "defs", "title", "desc", "style", "metadata"):
            continue
        out.extend(_polylines_from_element(el))
    return out


def _svg_root_from_file_or_string(path_or_xml: Path | str, *, is_path: bool) -> ET.Element:
    if is_path:
        tree = ET.parse(Path(path_or_xml))
        root = tree.getroot()
    else:
        root = ET.fromstring(str(path_or_xml))
    if _local_tag(root.tag) != "svg":
        for el in root.iter():
            if _local_tag(el.tag) == "svg":
                return el
    return root


def vector_paths_from_svg_file(
    path: Path | str,
    *,
    page_width_mm: float,
    page_height_mm: float,
) -> List[VectorPath]:
    """
    读取 SVG 文件，转为 ``VectorPath`` 列表（毫米、Y 向上、居中缩放至纸内）。
    不经单线字库，直接用于 ``paths_to_gcode``。
    """
    root = _svg_root_from_file_or_string(path, is_path=True)
    return _vector_paths_from_svg_root(root, page_width_mm=page_width_mm, page_height_mm=page_height_mm)


def vector_paths_from_svg_string(
    xml_text: str,
    *,
    page_width_mm: float,
    page_height_mm: float,
) -> List[VectorPath]:
    """从 SVG 字符串解析（例如 Potrace 输出）。"""
    root = _svg_root_from_file_or_string(xml_text, is_path=False)
    return _vector_paths_from_svg_root(root, page_width_mm=page_width_mm, page_height_mm=page_height_mm)


def _vector_paths_from_svg_root(
    root: ET.Element,
    *,
    page_width_mm: float,
    page_height_mm: float,
) -> List[VectorPath]:
    min_x, min_y, vb_w, vb_h = _viewbox(root)
    if vb_w <= 0 or vb_h <= 0:
        vb_w, vb_h = 100.0, 100.0

    sx = float(page_width_mm) / vb_w
    sy = float(page_height_mm) / vb_h
    sc = min(sx, sy)
    off_x = (float(page_width_mm) - vb_w * sc) / 2.0
    off_y = (float(page_height_mm) - vb_h * sc) / 2.0

    vps: List[VectorPath] = []
    for poly in collect_polylines_from_svg_element_tree(root):
        pts: List[Point] = []
        for ux, uy in poly:
            x_mm = (ux - min_x) * sc + off_x
            y_svg = (uy - min_y) * sc + off_y
            y_mm = float(page_height_mm) - y_svg
            pts.append(Point(x_mm, y_mm))
        if len(pts) >= 2:
            vps.append(VectorPath(tuple(pts), pen_down=True))
    return vps
