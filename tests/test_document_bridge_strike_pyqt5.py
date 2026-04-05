"""document_bridge_pyqt5：删除线（修订删除）不参与 LayoutLine / 导出纯文本。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["INKSCAPE_WPS_QT_BINDING"] = "pyqt5"

try:
    from PyQt5.QtGui import QTextDocument
    from PyQt5.QtWidgets import QApplication, QTextEdit
except ImportError:  # pragma: no cover
    QApplication = None  # type: ignore[misc, assignment]

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.ui.document_bridge_pyqt5 import (
    document_plain_text_skip_strike,
    html_fragment_to_layout_lines,
    text_edit_to_layout_lines,
)


@unittest.skipUnless(QApplication is not None, "PyQt5 不可用")
class DocumentBridgeStrikePyQt5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_document_plain_text_skip_strike(self) -> None:
        doc = QTextDocument()
        doc.setHtml("<p>a<s>b</s>c</p>")
        self.assertEqual(document_plain_text_skip_strike(doc).replace("\u2029", ""), "ac")

    def test_text_edit_layout_skips_strike(self) -> None:
        te = QTextEdit()
        te.resize(600, 400)
        te.setHtml(
            '<p style="font-size:12pt">XY<span style="text-decoration: line-through">Z</span>W</p>'
        )
        cfg = MachineConfig()
        lines = text_edit_to_layout_lines(te, cfg)
        joined = "".join(str(t[0]) for t in lines if t and t[0])
        self.assertNotIn("Z", joined)
        self.assertIn("XY", joined)
        self.assertIn("W", joined)

    def test_html_fragment_layout_skips_strike(self) -> None:
        cfg = MachineConfig()
        html = '<span style="font-size:12pt">a<s>x</s>b</span>'
        lines = html_fragment_to_layout_lines(
            html,
            cfg,
            cell_left_mm=10.0,
            cell_top_from_page_top_mm=20.0,
            cell_width_mm=80.0,
            cell_height_mm=40.0,
            mm_per_px_x=0.2,
        )
        joined = "".join(str(t[0]) for t in lines if t and t[0])
        self.assertNotIn("x", joined)
        self.assertIn("a", joined)
        self.assertIn("b", joined)


if __name__ == "__main__":
    unittest.main()
