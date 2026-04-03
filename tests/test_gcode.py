"""G-code 生成（无 Qt）。"""

from __future__ import annotations

import unittest

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.core.gcode import paths_to_gcode
from inkscape_wps.core.types import Point, VectorPath


class TestGcodePenMode(unittest.TestCase):
    def test_z_mode_uses_g1_z(self) -> None:
        cfg = MachineConfig(gcode_pen_mode="z", z_up_mm=1.0, z_down_mm=4.0)
        paths = [VectorPath((Point(0.0, 0.0), Point(10.0, 0.0)))]
        g = paths_to_gcode(paths, cfg, order=False)
        self.assertIn("G1 Z1.000", g)
        self.assertIn("G1 Z4.000", g)
        self.assertNotIn("M3 S", g)

    def test_m3m5_mode_uses_spindle_commands(self) -> None:
        cfg = MachineConfig(gcode_pen_mode="m3m5", gcode_m3_s_value=500, z_up_mm=1.0, z_down_mm=4.0)
        paths = [VectorPath((Point(0.0, 0.0), Point(10.0, 0.0)))]
        g = paths_to_gcode(paths, cfg, order=False)
        self.assertIn("M3 S500", g)
        self.assertIn("M5", g)
        self.assertNotIn("G1 Z4.000", g)

    def test_m3m5_mode_respects_custom_s_value(self) -> None:
        cfg = MachineConfig(gcode_pen_mode="m3m5", gcode_m3_s_value=123, z_up_mm=0.0, z_down_mm=3.0)
        paths = [VectorPath((Point(1.0, 1.0), Point(2.0, 1.0)))]
        g = paths_to_gcode(paths, cfg, order=False)
        self.assertIn("M3 S123", g)

    def test_program_prefix_suffix_lines(self) -> None:
        cfg = MachineConfig(
            gcode_program_prefix="M800\n(授权)\n",
            gcode_program_suffix="(end)\n",
        )
        paths = [VectorPath((Point(0.0, 0.0), Point(1.0, 0.0)))]
        g = paths_to_gcode(paths, cfg, order=False)
        self.assertIn("M800", g)
        self.assertIn("(授权)", g)
        self.assertIn("(end)", g)


if __name__ == "__main__":
    unittest.main()
