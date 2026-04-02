"""G-code 生成：纯数学与字符串，无 Qt。

与 grblapp `gcode.py::_generate_kuixiang` 一致的核心序列：
- 可选 **G92 X0 Y0 Z0**：将当前机位设为程序零点（用户需在正确位置再运行）。
- **G21 G90 G94**，默认 XY 进给 F；连续两次 **G1 抬笔 Z**。
- 每笔：**G1 抬笔 Z** → **G0** 到起点 → **G1 落笔 Z** → **G1** 连到后续点（不重复首点）。
- 结尾：**G1 抬笔** → **G0 X0 Y0** → **M5**（笔）→ **M2**（不换纸）或 **M30**（换纸任务，见配置）。
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from .config import MachineConfig
from .types import Point, VectorPath


def _gcode_extra_lines(block: str) -> List[str]:
    return [ln.strip() for ln in block.replace("\r\n", "\n").split("\n") if ln.strip()]


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _dedupe_points(points: Sequence[Point], eps: float = 1e-4) -> Tuple[Point, ...]:
    if not points:
        return ()
    out: List[Point] = [points[0]]
    for q in points[1:]:
        if _dist(q, out[-1]) > eps:
            out.append(q)
    return tuple(out)


def order_paths_nearest_neighbor(paths: Sequence[VectorPath]) -> List[VectorPath]:
    """最近邻排序：以每段路径起点为参考，减小空移（启发式）。"""
    draw_paths = [p for p in paths if p.pen_down and len(p.points) >= 2]
    if not draw_paths:
        return list(paths)

    remaining = list(draw_paths)
    ordered: List[VectorPath] = []
    current_end = Point(0.0, 0.0)

    while remaining:
        best_i = 0
        best_d = float("inf")
        for i, p in enumerate(remaining):
            d = _dist(current_end, p.points[0])
            if d < best_d:
                best_d = d
                best_i = i
        nxt = remaining.pop(best_i)
        ordered.append(nxt)
        current_end = nxt.points[-1]

    extras = [p for p in paths if not p.pen_down or len(p.points) < 2]
    return ordered + extras


def paths_to_gcode(
    paths: Sequence[VectorPath],
    cfg: MachineConfig,
    *,
    order: bool = True,
) -> str:
    """
    生成 GRBL 兼容 G-code。
    - Z 模式：抬笔 = G1 Z z_up，落笔 = G1 Z z_down
    - M3/M5 模式：抬笔 = M5，落笔 = M3 S…（不写 Z，供伺服笔等）
    - G4 的 P 单位为秒
    """
    z_up = cfg.z_up_mm
    z_down = cfg.z_down_mm
    f_xy = float(cfg.draw_feed_rate)
    f_z = float(cfg.z_feed_rate)
    use_m3m5 = (cfg.gcode_pen_mode or "z").strip().lower() in ("m3m5", "m3", "spindle")

    lines: List[str] = [
        "(inkscape-wps; kuixiang-style + G92 program zero)",
    ]
    if cfg.gcode_use_g92:
        lines.append("G92 X0.0 Y0.0 Z0")
    lines.extend(
        [
            "G21",
            "G90",
            "G94",
            f"F{f_xy:.0f}",
        ]
    )
    lines.extend(_gcode_extra_lines(cfg.gcode_program_prefix))

    work = order_paths_nearest_neighbor(paths) if order else list(paths)

    pen_is_down = False

    def travel_z() -> None:
        nonlocal pen_is_down
        if use_m3m5:
            lines.append("M5")
        else:
            lines.append(f"G1 Z{z_up:.3f} F{f_z:.0f}")
        if pen_is_down and cfg.dwell_after_pen_up_s > 0:
            lines.append(f"G4 P{cfg.dwell_after_pen_up_s:.3f}")
        pen_is_down = False

    def rapid(x: float, y: float) -> None:
        lines.append(f"G0 X{x:.3f} Y{y:.3f}")

    def line_to(x: float, y: float) -> None:
        lines.append(f"G1 X{x:.3f} Y{y:.3f} F{f_xy:.0f}")

    def pen_down() -> None:
        nonlocal pen_is_down
        if use_m3m5:
            s = max(0, int(cfg.gcode_m3_s_value))
            lines.append(f"M3 S{s}")
        else:
            lines.append(f"G1 Z{z_down:.3f} F{f_z:.0f}")
        if cfg.dwell_after_pen_down_s > 0:
            lines.append(f"G4 P{cfg.dwell_after_pen_down_s:.3f}")
        pen_is_down = True

    travel_z()
    travel_z()

    for vp in work:
        if not vp.pen_down:
            continue
        pts = _dedupe_points(vp.points)
        if len(pts) < 2:
            continue

        travel_z()
        if cfg.rapid_after_pen_up:
            rapid(pts[0].x, pts[0].y)
        else:
            lines.append(f"G1 X{pts[0].x:.3f} Y{pts[0].y:.3f} F{f_xy:.0f}")

        pen_down()
        for q in pts[1:]:
            line_to(q.x, q.y)

    travel_z()
    lines.extend(_gcode_extra_lines(cfg.gcode_program_suffix))
    lines.append("G0 X0.000 Y0.000")
    lines.append("M5")
    if cfg.gcode_end_m30:
        lines.append("M30")
    else:
        lines.append("M2")
    return "\n".join(lines) + "\n"
