"""ViewModel：把核心 VectorPath 转为 QGraphicsItem，供仿真预览。"""

from __future__ import annotations

from typing import List, Tuple

from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsScene

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.core.types import Point, VectorPath


class DrawingViewModel:
    def __init__(self, cfg: MachineConfig) -> None:
        self._cfg = cfg

    def paths_to_scene_items(
        self,
        paths: List[VectorPath],
        *,
        mm_per_px: float,
    ) -> Tuple[QGraphicsScene, List[QGraphicsLineItem]]:
        """
        视图坐标 Y 向下：scene 坐标 = 纸张左上角为 (0,0)，向右向下。
        核心路径为 Y 向上毫米，故 y_px = (page_h - y_mm) / mm_per_px
        """
        scene = QGraphicsScene(
            0,
            0,
            self._cfg.page_width_mm / mm_per_px,
            self._cfg.page_height_mm / mm_per_px,
        )
        items: List[QGraphicsLineItem] = []
        pen_draw = QPen(Qt.GlobalColor.black)
        pen_draw.setWidthF(1.0)
        pen_draw.setCosmetic(True)
        pen_rapid = QPen(Qt.GlobalColor.red)
        pen_rapid.setStyle(Qt.PenStyle.DashLine)
        pen_rapid.setWidthF(1.0)
        pen_rapid.setCosmetic(True)

        def mm_to_scene(p: Point) -> QPointF:
            x_px = p.x / mm_per_px
            y_px = (self._cfg.page_height_mm - p.y) / mm_per_px
            return QPointF(x_px, y_px)

        last_end: Point | None = None
        for vp in paths:
            if len(vp.points) < 2:
                last_end = vp.points[0] if vp.points else last_end
                continue
            start = vp.points[0]
            if last_end is not None:
                a = mm_to_scene(last_end)
                b = mm_to_scene(start)
                li = QGraphicsLineItem(QLineF(a, b))
                li.setPen(pen_rapid)
                scene.addItem(li)
                items.append(li)
            for i in range(len(vp.points) - 1):
                a = mm_to_scene(vp.points[i])
                b = mm_to_scene(vp.points[i + 1])
                li = QGraphicsLineItem(QLineF(a, b))
                li.setPen(pen_draw)
                scene.addItem(li)
                items.append(li)
            last_end = vp.points[-1]

        return scene, items
