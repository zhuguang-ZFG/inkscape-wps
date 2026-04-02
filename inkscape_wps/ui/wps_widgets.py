"""WPS 风格杂项控件（标尺条等）。"""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel


def make_horizontal_ruler_mm(max_mm: int = 210) -> QLabel:
    """简易水平标尺刻度（文本），约 A4 宽度。"""
    ticks = list(range(0, max_mm + 1, 20))
    if ticks[-1] != max_mm:
        ticks.append(max_mm)
    text = " ".join(f"{t:>3}" for t in ticks) + "   (mm)"
    lb = QLabel(text)
    lb.setObjectName("RulerBar")
    lb.setMinimumHeight(20)
    return lb
