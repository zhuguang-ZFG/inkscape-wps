"""G-code 生成：纯数学与字符串，无 Qt。

与 grblapp `src/grbl_writer/core/gcode.py::_generate_kuixiang` 对齐的核心笔序：
- **G21 G90**，XY 进给 F；抬笔/落笔用 **G1 Z**（或 M3/M5 笔模式）；每笔 **G0 到起点 → 落笔 → G1 连到后续点**（不重复首点）。
- 程序头尾可插 **前缀/后缀**、可选 **G92**、结尾 **G0 X0 Y0** 与 **M2/M30**。

与 grblapp 的差异摘要（便于对照现场能写字的固件习惯）：
- **G92**：grblapp 奎享模式固定写 `G92 X0 Y0 Z0`；本仓库由 `MachineConfig.gcode_use_g92` 控制，可关闭。
- **G94**：本仓库显式发 `G94`；grblapp 奎享片段里未单独强调（依赖固件默认）。
- **行格式**：grblapp 常用紧凑行如 `G1G90 Z…F…`、`G0 X…Y…F…`；本仓库用带空格的标准写法；语义等价，部分解析器对 G0+F 的容忍度不同。
- **结尾 M5**：本仓库在 **M2/M30 前固定发 M5**（伺服笔/主轴语义）；grblapp 奎享模式 **不发 M5**，纯 Z 抬落笔。若固件把 M5 当激光关断，一般无害；若固件异常响应 M5，可改为可配置关闭。
- **笔画顺序**：grblapp 按 **字符 → 笔画** 顺序生成，并在 `path_optimizer` 内做字符内/间优化；本仓库对 `VectorPath` 列表可做 **全局最近邻**（`order_paths_nearest_neighbor`），顺序可能与「按字阅读顺序」不同。
- **坐标变换**：grblapp 在出 G-code 前经 `coordinate_transform.transform_characters`（原点模式、翻转、旋转等）；本仓库在 UI/核心侧用 `MachineConfig` 坐标字段在路径阶段变换，需保证与对零方式一致。

参考仓库路径（本地克隆）：`…/grblapp/src/grbl_writer/core/gcode.py`。
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
            lines.append(f"G1 Z{z_up:.4f} F{f_z:.0f}")
        if pen_is_down and cfg.dwell_after_pen_up_s > 0:
            lines.append(f"G4 P{cfg.dwell_after_pen_up_s:.3f}")
        pen_is_down = False

    def rapid(x: float, y: float) -> None:
        lines.append(f"G0 X{x:.4f} Y{y:.4f}")

    def line_to(x: float, y: float) -> None:
        lines.append(f"G1 X{x:.4f} Y{y:.4f} F{f_xy:.0f}")

    def pen_down() -> None:
        nonlocal pen_is_down
        if use_m3m5:
            s = max(0, int(cfg.gcode_m3_s_value))
            lines.append(f"M3 S{s}")
        else:
            lines.append(f"G1 Z{z_down:.4f} F{f_z:.0f}")
        if cfg.dwell_after_pen_down_s > 0:
            lines.append(f"G4 P{cfg.dwell_after_pen_down_s:.3f}")
        pen_is_down = True

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
            lines.append(f"G1 X{pts[0].x:.4f} Y{pts[0].y:.4f} F{f_xy:.0f}")

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
