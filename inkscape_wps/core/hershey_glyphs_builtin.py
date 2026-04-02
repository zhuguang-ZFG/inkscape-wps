"""内置单线字形（JSON 可由此脚本导出）。坐标为字形局部单位，原点在左下角附近，高约 9 单位。"""

from __future__ import annotations

from typing import Dict, List, Tuple

Glyph = List[List[Tuple[float, float]]]


def _seg(a: Tuple[float, float], b: Tuple[float, float]) -> List[Tuple[float, float]]:
    return [a, b]


def _digit_7seg() -> Dict[str, Glyph]:
    """7 段数码管风格，宽 6 高 10。"""
    o = 0.0
    w, h = 6.0, 10.0
    a = (o + 0.5, h)
    b = (o + w - 0.5, h)
    c = (o + w - 0.5, h * 0.55)
    d = (o + w - 0.5, o)
    e = (o + 0.5, o)
    f = (o + 0.5, h * 0.45)
    g = (o + 0.5, h * 0.5)
    segs = {"a": _seg(a, b), "b": _seg(b, c), "c": _seg(c, d), "d": _seg(e, d), "e": _seg(f, e), "f": _seg(a, f), "g": _seg(f, c)}
    masks = {
        "0": "abcedf",
        "1": "bc",
        "2": "abged",
        "3": "abgcd",
        "4": "fgbc",
        "5": "afgcd",
        "6": "afgedc",
        "7": "abc",
        "8": "abcdefg",
        "9": "abfgcd",
    }
    out: Dict[str, Glyph] = {}
    for ch, m in masks.items():
        out[ch] = [segs[s] for s in m]
    return out


def _letters_simple() -> Dict[str, Glyph]:
    """极简大写笔画，便于书写机演示。"""
    g: Dict[str, Glyph] = {}

    def poly(*pts: Tuple[float, float]) -> List[Tuple[float, float]]:
        return list(pts)

    # 宽 6 高 10 的骨架
    g["A"] = [poly((0, 0), (3, 10), (6, 0)), poly((1, 4), (5, 4))]
    g["B"] = [poly((0, 0), (0, 10), (4, 10), (5, 8), (4, 5), (0, 5)), poly((4, 5), (5, 2), (4, 0), (0, 0))]
    g["C"] = [poly((6, 8), (4, 10), (1, 10), (0, 5), (1, 0), (4, 0), (6, 2))]
    g["D"] = [poly((0, 0), (0, 10), (4, 10), (6, 7), (6, 3), (4, 0), (0, 0))]
    g["E"] = [poly((6, 10), (0, 10), (0, 0), (6, 0)), poly((0, 5), (4, 5))]
    g["F"] = [poly((0, 0), (0, 10), (6, 10)), poly((0, 5), (4, 5))]
    g["G"] = [poly((5, 8), (4, 10), (1, 10), (0, 5), (1, 0), (4, 0), (6, 2), (6, 4), (3, 4))]
    g["H"] = [poly((0, 0), (0, 10)), poly((6, 0), (6, 10)), poly((0, 5), (6, 5))]
    g["I"] = [poly((3, 0), (3, 10)), poly((1, 10), (5, 10)), poly((1, 0), (5, 0))]
    g["J"] = [poly((1, 10), (5, 10), (5, 2), (3, 0), (0, 2))]
    g["K"] = [poly((0, 0), (0, 10)), poly((6, 10), (0, 4)), poly((2, 6), (6, 0))]
    g["L"] = [poly((0, 10), (0, 0), (6, 0))]
    g["M"] = [poly((0, 0), (0, 10), (3, 5), (6, 10), (6, 0))]
    g["N"] = [poly((0, 0), (0, 10), (6, 0), (6, 10))]
    g["O"] = [poly((3, 10), (1, 9), (0, 5), (1, 1), (3, 0), (5, 1), (6, 5), (5, 9), (3, 10))]
    g["P"] = [poly((0, 0), (0, 10), (4, 10), (5, 8), (4, 6), (0, 6))]
    g["Q"] = [poly((3, 10), (1, 9), (0, 5), (1, 1), (3, 0), (5, 1), (6, 5), (5, 9), (3, 10)), poly((4, 2), (6, 0))]
    g["R"] = [poly((0, 0), (0, 10), (4, 10), (5, 8), (4, 6), (0, 6)), poly((3, 6), (6, 0))]
    g["S"] = [poly((6, 9), (4, 10), (1, 10), (0, 7), (3, 5), (6, 3), (5, 0), (2, 0), (0, 1))]
    g["T"] = [poly((0, 10), (6, 10)), poly((3, 10), (3, 0))]
    g["U"] = [poly((0, 10), (0, 2), (3, 0), (6, 2), (6, 10))]
    g["V"] = [poly((0, 10), (3, 0), (6, 10))]
    g["W"] = [poly((0, 10), (0, 0), (3, 4), (6, 0), (6, 10))]
    g["X"] = [poly((0, 10), (6, 0)), poly((6, 10), (0, 0))]
    g["Y"] = [poly((0, 10), (3, 5), (6, 10)), poly((3, 5), (3, 0))]
    g["Z"] = [poly((0, 10), (6, 10), (0, 0), (6, 0))]
    return g


def build_builtin_glyphs() -> Dict[str, Glyph]:
    digits = _digit_7seg()
    letters = _letters_simple()
    out: Dict[str, Glyph] = {}
    out[" "] = []
    for d, glyph in digits.items():
        out[d] = glyph
    for ch, glyph in letters.items():
        out[ch] = glyph
        out[ch.lower()] = glyph
    # 常用标点（极简）
    out["."] = [[(3, 0), (3, 0.01)]]  # 点
    out[","] = [[(3, 0), (2, -2)]]
    out["-"] = [[(1, 5), (5, 5)]]
    out["_"] = [[(0, -1), (6, -1)]]
    out["!"] = [[(3, 10), (3, 3)], [(3, 0), (3, 0.01)]]
    out["?"] = [
        [(1, 8), (3, 10), (5, 8), (5, 6), (3, 4)],
        [(3, 0), (3, 0.01)],
    ]
    return out
