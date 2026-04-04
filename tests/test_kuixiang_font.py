"""奎享 JSON 字库解析回归。"""

from __future__ import annotations

import unittest

from inkscape_wps.core.kuixiang_font import (
    is_kuixiang_gfont_extract_payload,
    load_kuixiang_json_as_em_glyphs,
)


class TestKuixiangFont(unittest.TestCase):
    def test_extract_payload_splits_pen_lifts_and_normalizes_to_em(self) -> None:
        payload = {
            "glyphs": {
                "A": [
                    [
                        {"x": 0, "y": 0, "t": 1},
                        {"x": 10, "y": 20, "t": 1},
                        {"x": 20, "y": 0, "t": 0},
                        {"x": 5, "y": 10, "t": 1},
                        {"x": 15, "y": 10, "t": 1},
                    ]
                ]
            }
        }

        self.assertTrue(is_kuixiang_gfont_extract_payload(payload))

        glyphs = load_kuixiang_json_as_em_glyphs(payload, mm_per_unit=1.0, target_em=10.0)

        self.assertIn("A", glyphs)
        self.assertEqual(len(glyphs["A"]), 2)
        self.assertEqual(glyphs["A"][0], [(0.0, 0.0), (5.0, 10.0)])
        self.assertEqual(glyphs["A"][1], [(10.0, 0.0), (2.5, 5.0), (7.5, 5.0)])


if __name__ == "__main__":
    unittest.main()
