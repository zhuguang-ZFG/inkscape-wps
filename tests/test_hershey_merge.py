"""主编译 + 小文件合并字库。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from inkscape_wps.core.hershey import HersheyFontMapper
from inkscape_wps.core.types import Point, VectorPath


class TestHersheyMerge(unittest.TestCase):
    def test_merge_adds_cjk_glyph(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            merge = Path(td) / "m.json"
            merge.write_text(
                json.dumps(
                    {
                        "em_height": 10.0,
                        "glyphs": {"中": [[[0, 0], [10, 10]]]},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            m = HersheyFontMapper(None, merge_font_path=merge)
            paths = m.map_line("中", 0.0, 5.0, 12.0, mm_per_pt=1.0)
            self.assertTrue(any(len(vp.points) >= 2 for vp in paths))


if __name__ == "__main__":
    unittest.main()
