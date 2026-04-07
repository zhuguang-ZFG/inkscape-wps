"""机床配置 JSON/TOML 读写（无 Qt）。"""

from __future__ import annotations

import json
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

    def test_tcp_connection_fields_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            path = d / "machine_config.toml"
            cfg = MachineConfig(connection_mode="tcp", tcp_host="192.168.4.1", tcp_port=23)
            save_machine_config(cfg, path)
            loaded, _ = load_machine_config(d)
            self.assertEqual(loaded.connection_mode, "tcp")
            self.assertEqual(loaded.tcp_host, "192.168.4.1")
            self.assertEqual(loaded.tcp_port, 23)

    def test_json_load_with_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            path = d / "machine_config.json"
            path.write_text(
                "\ufeff" + json.dumps({"gcode_pen_mode": "m3m5", "gcode_m3_s_value": 321}),
                encoding="utf-8",
            )
            loaded, _ = load_machine_config(d)
            self.assertEqual(loaded.gcode_pen_mode, "m3m5")
            self.assertEqual(loaded.gcode_m3_s_value, 321)


if __name__ == "__main__":
    unittest.main()
