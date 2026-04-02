"""纯数据结构：禁止依赖 PyQt / GUI。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass
class VectorPath:
    """单段连续笔画（落笔后沿 points 顺序绘制）。"""

    points: Tuple[Point, ...]
    pen_down: bool = True

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("VectorPath 至少需要一个点")


def paths_bounding_box(paths: List[VectorPath]) -> Tuple[float, float, float, float]:
    """返回 (min_x, min_y, max_x, max_y)。忽略抬笔占位路径。"""
    xs: List[float] = []
    ys: List[float] = []
    for p in paths:
        if not p.pen_down:
            continue
        for q in p.points:
            xs.append(q.x)
            ys.append(q.y)
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))
