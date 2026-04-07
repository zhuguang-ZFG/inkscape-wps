"""Markdown 导入（office_import）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from inkscape_wps.core.office_import import (
    detect_office_kind,
    html_fragment_to_plain_text,
    import_markdown_string_to_plain,
    import_markdown_to_plain,
    split_markdown_into_slides,
)


class TestMarkdownIo(unittest.TestCase):
    def test_detect_md(self) -> None:
        self.assertEqual(detect_office_kind(Path("a.md")), "md")
        self.assertEqual(detect_office_kind(Path("b.markdown")), "md")

    def test_html_to_plain(self) -> None:
        h = "<p>Hello</p><h2>Title</h2><p>Line</p>"
        t = html_fragment_to_plain_text(h)
        self.assertIn("Hello", t)
        self.assertIn("Title", t)
        self.assertIn("Line", t)

    def test_import_markdown_file(self) -> None:
        try:
            import markdown  # noqa: F401
        except ImportError:
            self.skipTest("markdown 未安装")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.md"
            p.write_text("# Hi\n\n**Bold** text.\n", encoding="utf-8")
            plain = import_markdown_to_plain(p)
        self.assertIn("Hi", plain)
        self.assertIn("Bold", plain)
        self.assertIn("text", plain)

    def test_import_markdown_file_with_utf8_bom(self) -> None:
        try:
            import markdown  # noqa: F401
        except ImportError:
            self.skipTest("markdown 未安装")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bom.md"
            p.write_text("\ufeff# 标题\n\n内容\n", encoding="utf-8")
            plain = import_markdown_to_plain(p)
        self.assertIn("标题", plain)
        self.assertIn("内容", plain)

    def test_split_slides(self) -> None:
        raw = "# A\n\nx\n\n---\n\n# B\n"
        parts = split_markdown_into_slides(raw)
        self.assertIsNotNone(parts)
        assert parts is not None
        self.assertEqual(len(parts), 2)

    def test_string_plain(self) -> None:
        try:
            import markdown  # noqa: F401
        except ImportError:
            self.skipTest("markdown 未安装")
        t = import_markdown_string_to_plain("## T\n\nok")
        self.assertIn("T", t)
        self.assertIn("ok", t)


if __name__ == "__main__":
    unittest.main()
