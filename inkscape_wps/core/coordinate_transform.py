"""
工作坐标变换：轴反向、镜像、平移。
在「文档坐标系」（mm，X 右、Y 上）下对点施加变换，再输出给 G-code 与预览。
顺序：镜像 X → 镜像 Y → 缩放（含 ±1 反向）→ 平移。
"""

from __future__ import annotations

from typing import List

from .config import MachineConfig
from .types import Point, VectorPath


def transform_point(x: float, y: float, cfg: MachineConfig) -> Point:
    if cfg.coord_mirror_x:
        x = 2.0 * cfg.coord_pivot_x_mm - x
    if cfg.coord_mirror_y:
        y = 2.0 * cfg.coord_pivot_y_mm - y
    x *= cfg.coord_scale_x
    y *= cfg.coord_scale_y
    x += cfg.coord_offset_x_mm
    y += cfg.coord_offset_y_mm
    return Point(x, y)


def transform_paths(paths: List[VectorPath], cfg: MachineConfig) -> List[VectorPath]:
    out: List[VectorPath] = []
    for vp in paths:
        pts = tuple(transform_point(q.x, q.y, cfg) for q in vp.points)
        out.append(VectorPath(pts, pen_down=vp.pen_down))
    return out
