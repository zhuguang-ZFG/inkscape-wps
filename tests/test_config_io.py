"""机床配置 JSON/TOML 读写（无 Qt）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.core.config_io import load_machine_config, save_machine_config


class TestConfigIo(unittest.TestCase):
    def test_json_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            path = d / "machine_config.json"
            cfg = MachineConfig(gcode_pen_mode="m3m5", gcode_m3_s_value=777)
            save_machine_config(cfg, path)
            loaded, p = load_machine_config(d)
            self.assertEqual(p.resolve(), path.resolve())
            self.assertEqual(loaded.gcode_pen_mode, "m3m5")
            self.assertEqual(loaded.gcode_m3_s_value, 777)

    def test_toml_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            path = d / "machine_config.toml"
            cfg = MachineConfig(coord_mirror_x=True, draw_feed_rate=1500)
            save_machine_config(cfg, path)
            loaded, p = load_machine_config(d)
            self.assertEqual(p.resolve(), path.resolve())
            self.assertTrue(loaded.coord_mirror_x)
            self.assertEqual(loaded.draw_feed_rate, 1500)


if __name__ == "__main__":
    unittest.main()
