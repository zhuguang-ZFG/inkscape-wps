"""SVG 导入到 G-code 的核心回归。"""

from __future__ import annotations

import unittest

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.core.gcode import paths_to_gcode
from inkscape_wps.core.svg_import import vector_paths_from_svg_string


class TestSvgImportToGcode(unittest.TestCase):
    def test_rect_svg_generates_closed_path_and_gcode(self) -> None:
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">
          <rect x="0" y="0" width="100" height="50" />
        </svg>
        """

        paths = vector_paths_from_svg_string(svg, page_width_mm=200.0, page_height_mm=100.0)

        self.assertEqual(len(paths), 1)
        pts = paths[0].points
        self.assertEqual(len(pts), 5)
        self.assertAlmostEqual(pts[0].x, 0.0)
        self.assertAlmostEqual(pts[0].y, 100.0)
        self.assertAlmostEqual(pts[2].x, 200.0)
        self.assertAlmostEqual(pts[2].y, 0.0)
        self.assertAlmostEqual(pts[0].x, pts[-1].x)
        self.assertAlmostEqual(pts[0].y, pts[-1].y)

        cfg = MachineConfig(
            page_width_mm=200.0,
            page_height_mm=100.0,
            dwell_after_pen_down_s=0.0,
            dwell_after_pen_up_s=0.0,
        )
        gcode = paths_to_gcode(paths, cfg, order=False)

        self.assertIn("G0 X0.0000 Y100.0000", gcode)
        self.assertIn("G1 X200.0000 Y100.0000 F2000", gcode)
        self.assertIn("G1 X200.0000 Y0.0000 F2000", gcode)


if __name__ == "__main__":
    unittest.main()
