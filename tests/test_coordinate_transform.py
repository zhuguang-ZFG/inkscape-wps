"""坐标变换（无 Qt）。"""

from __future__ import annotations

import unittest

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.core.coordinate_transform import transform_paths, transform_point
from inkscape_wps.core.types import Point, VectorPath


class TestCoordinateTransform(unittest.TestCase):
    def test_transform_point_mirror_scale_offset(self) -> None:
        cfg = MachineConfig(
            coord_mirror_x=True,
            coord_pivot_x_mm=0.0,
            coord_scale_x=2.0,
            coord_offset_x_mm=10.0,
        )
        p = transform_point(5.0, 0.0, cfg)
        self.assertAlmostEqual(p.x, 0.0)
        self.assertAlmostEqual(p.y, 0.0)

    def test_transform_paths_preserves_pen_down(self) -> None:
        cfg = MachineConfig(coord_offset_x_mm=1.0, coord_offset_y_mm=-2.0)
        paths = [
            VectorPath((Point(0.0, 0.0), Point(1.0, 0.0)), pen_down=False),
        ]
        out = transform_paths(paths, cfg)
        self.assertEqual(len(out), 1)
        self.assertFalse(out[0].pen_down)
        self.assertAlmostEqual(out[0].points[0].x, 1.0)
        self.assertAlmostEqual(out[0].points[0].y, -2.0)


if __name__ == "__main__":
    unittest.main()
