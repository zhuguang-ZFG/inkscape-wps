"""经典 Hershey .jhf / .hf 文本解析（无 Qt 依赖）。

支持两种常见行格式：
1. 扩展行（与 chinese-hershey-font 的 .hf.txt 一致）：
   前 5 位 glyph 编号、3 位顶点数、左右承、坐标串。
2. 短行：仅 5 位编号 + 坐标串（无顶点数/承），按「 R」抬笔分段。

glyph 编号在部分字库中为 Unicode 码点，在部分 Roman 字库中为独立索引；可通过同目录可选映射文件
``<stem>.jhf.map.json``（字段 ``by_index``：Hershey 编号字符串 → 单字符）关联到字符键。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

# 可打印 ASCII 与常见 Roman .jhf 前若干 glyph 行序对齐（无 map 文件时的回退）
_ASCII_PRINTABLE = [chr(c) for c in range(32, 127)]

Glyph = List[List[Tuple[float, float]]]

_R = ord("R")


def _merge_wrapped_lines(raw_lines: List[str]) -> List[str]:
    glyphs: List[str] = []
    for line in raw_lines:
        if not line:
            continue
        if line[0] != " " or (len(line) > 5 and line[:5].strip().isdigit()):
            glyphs.append(line.rstrip("\n"))
        elif glyphs:
            glyphs[-1] += line.rstrip("\n")
    return glyphs


def _decode_coord_body(coords_str: str) -> List[List[Tuple[float, float]]]:
    strokes: List[List[Tuple[float, float]]] = []
    current: List[Tuple[float, float]] = []
    i = 0
    while i + 1 < len(coords_str):
        c1, c2 = coords_str[i], coords_str[i + 1]
        i += 2
        if c1 == " " and c2 == "R":
            if len(current) >= 2:
                strokes.append(current)
            current = []
            continue
        current.append((float(ord(c1) - _R), float(ord(c2) - _R)))
    if len(current) >= 2:
        strokes.append(current)
    return strokes


def _normalize_to_em(
    strokes: List[List[Tuple[float, float]]],
    *,
    left_val: float,
    right_val: float,
    em_height: float,
) -> Glyph:
    if not strokes:
        return []
    all_pts = [p for s in strokes for p in s]
    min_y = min(p[1] for p in all_pts)
    max_y = max(p[1] for p in all_pts)
    h = max(1e-6, max_y - min_y)
    sy = em_height / h
    sx = sy
    out: Glyph = []
    for stroke in strokes:
        out.append(
            [
                ((x - left_val) * sx, (y - min_y) * sy)
                for x, y in stroke
            ]
        )
    return out


def _parse_extended_record(glyph_str: str, em_height: float) -> Tuple[int, Glyph] | None:
    if len(glyph_str) < 10:
        return None
    try:
        glyph_id = int(glyph_str[:5].strip())
        n_verts = int(glyph_str[5:8].strip())
    except ValueError:
        return None
    left_c = glyph_str[8] if len(glyph_str) > 8 else "R"
    right_c = glyph_str[9] if len(glyph_str) > 9 else "R"
    left_val = float(ord(left_c) - _R)
    right_val = float(ord(right_c) - _R)
    coords_str = glyph_str[10:]
    strokes: List[List[Tuple[float, float]]] = []
    current: List[Tuple[float, float]] = []
    verts_read = 0
    i = 0
    while i + 1 < len(coords_str) and verts_read < n_verts - 1:
        c1, c2 = coords_str[i], coords_str[i + 1]
        i += 2
        verts_read += 1
        if c1 == " " and c2 == "R":
            if len(current) >= 2:
                strokes.append(current)
            current = []
            continue
        current.append((float(ord(c1) - _R), float(ord(c2) - _R)))
    if len(current) >= 2:
        strokes.append(current)
    if not strokes:
        return None
    g = _normalize_to_em(strokes, left_val=left_val, right_val=right_val, em_height=em_height)
    return glyph_id, g


def _parse_short_record(glyph_str: str, em_height: float) -> Tuple[int, Glyph] | None:
    m = re.match(r"^\s*(\d+)\s*(.*)$", glyph_str)
    if not m:
        return None
    gid = int(m.group(1))
    body = m.group(2).strip()
    if not body:
        return gid, []
    strokes = _decode_coord_body(body)
    if not strokes:
        return None
    all_pts = [p for s in strokes for p in s]
    min_x = min(p[0] for p in all_pts)
    max_x = max(p[0] for p in all_pts)
    left_val = min_x
    right_val = max_x
    g = _normalize_to_em(strokes, left_val=left_val, right_val=right_val, em_height=em_height)
    return gid, g


def iter_jhf_glyphs(path: Path, *, em_height: float = 10.0) -> List[Tuple[int, Glyph]]:
    """按文件内行序返回 (glyph_id, glyph)；与经典 Hershey 集「前 95 字 ≈ ASCII 32–126」顺序一致。"""
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    merged = _merge_wrapped_lines(raw_lines)
    out: List[Tuple[int, Glyph]] = []
    for rec in merged:
        parsed = _parse_extended_record(rec, em_height)
        if parsed is None:
            parsed = _parse_short_record(rec, em_height)
        if parsed is None:
            continue
        gid, glyph = parsed
        if glyph:
            out.append((gid, glyph))
    return out


def parse_jhf_file(path: Path, *, em_height: float = 10.0) -> Dict[int, Glyph]:
    """解析 .jhf/.hf 文件，返回 glyph_id → 归一化到高度 em_height 的多段折线（同 id 后者覆盖）。"""
    by_id: Dict[int, Glyph] = {}
    for gid, glyph in iter_jhf_glyphs(path, em_height=em_height):
        by_id[gid] = glyph
    return by_id


def load_jhf_map(path: Path) -> Dict[int, str]:
    """读取 ``<stem>.jhf.map.json``：``{\"by_index\": {\"2199\": \"A\", ...}}``。"""
    map_path = path.parent / f"{path.stem}.jhf.map.json"
    if not map_path.is_file():
        return {}
    try:
        raw = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    bi = raw.get("by_index")
    if not isinstance(bi, dict):
        return {}
    out: Dict[int, str] = {}
    for k, v in bi.items():
        try:
            idx = int(str(k).strip())
        except ValueError:
            continue
        if isinstance(v, str) and len(v) == 1:
            out[idx] = v
    return out


def jhf_to_char_glyphs(path: Path, *, em_height: float = 10.0) -> Tuple[Dict[str, Glyph], float]:
    """
    将 .jhf 转为与 ``HersheyFontMapper`` 兼容的 ``{字符: 折线}``。
    - 若存在 ``stem.jhf.map.json``：按 ``by_index`` 映射。
    - 否则：**按文件内顺序**将前 95 个 glyph 对应 ASCII 32–126
      （与 ``tools/generate_hershey_jhf_maps.py`` 规则一致）；
      再为 ``32 <= glyph_id <= 126`` 且尚未占用的字符补键（双保险）。
    """
    ordered = iter_jhf_glyphs(path, em_height=em_height)
    index_map = load_jhf_map(path)
    out: Dict[str, Glyph] = {}
    if index_map:
        for gid, gl in ordered:
            ch = index_map.get(gid)
            if ch is None and 32 <= gid <= 126:
                ch = chr(gid)
            if ch is None:
                continue
            out[ch] = gl
    else:
        for i, (_gid, gl) in enumerate(ordered):
            if i < len(_ASCII_PRINTABLE):
                out[_ASCII_PRINTABLE[i]] = gl
        for gid, gl in ordered:
            if 32 <= gid <= 126:
                ch = chr(gid)
                if ch not in out:
                    out[ch] = gl
    return out, em_height
