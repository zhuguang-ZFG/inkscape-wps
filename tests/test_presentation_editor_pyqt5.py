"""WpsPresentationEditorPyQt5 交互回归测试。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["INKSCAPE_WPS_QT_BINDING"] = "pyqt5"

try:
    from PyQt5.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    QApplication = None  # type: ignore[misc, assignment]

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.core.gcode import paths_to_gcode
from inkscape_wps.core.hershey import HersheyFontMapper, map_document_lines
from inkscape_wps.ui.presentation_editor_pyqt5 import WpsPresentationEditorPyQt5, _slide_plain_preview


@unittest.skipUnless(QApplication is not None, "PyQt5 不可用")
class PresentationEditorPyQt5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_current_slide_changed_emits_on_selection(self) -> None:
        editor = WpsPresentationEditorPyQt5(MachineConfig())
        editor.load_slides(["第一页", "第二页"])

        seen: list[tuple[int, int]] = []
        editor.currentSlideChanged.connect(lambda row, count: seen.append((row, count)))

        editor.slide_list_widget().setCurrentRow(1)

        self.assertEqual(editor.status_line(), "幻灯片 2 / 2")
        self.assertIn((1, 2), seen)

    def test_delete_current_slide_keeps_following_slide_selected(self) -> None:
        editor = WpsPresentationEditorPyQt5(MachineConfig())
        editor.load_slides(["第一页", "第二页", "第三页"])
        editor.slide_list_widget().setCurrentRow(1)

        editor.delete_slide_interactive()

        self.assertEqual(editor.current_slide_index(), 1)
        self.assertEqual(editor.slide_count(), 2)
        self.assertEqual(editor.slide_editor().toPlainText().strip(), "第三页")

    def test_master_state_is_reflected_in_meta_label(self) -> None:
        editor = WpsPresentationEditorPyQt5(MachineConfig())
        editor.set_master_header("页眉")

        self.assertIn("含母版", editor._meta.text())  # noqa: SLF001

    def test_slide_plain_preview_skips_strike_text(self) -> None:
        preview = _slide_plain_preview("<p>保留<s>删除</s>文本</p>")
        self.assertEqual(preview, "保留文本")

    def test_ascii_slide_content_can_flow_into_gcode(self) -> None:
        editor = WpsPresentationEditorPyQt5(MachineConfig())
        editor.resize(900, 600)
        editor.load_slides(["ABC"])

        lines = editor.to_layout_lines_all_slides(mm_per_px_resolver=lambda _ed: 0.25)
        paths = map_document_lines(HersheyFontMapper(), lines, mm_per_pt=1.0)
        gcode = paths_to_gcode(paths, MachineConfig(), order=False)

        self.assertTrue(paths)
        self.assertIn("G0 X", gcode)
        self.assertIn("G1 X", gcode)

    def test_outline_paths_all_slides_include_master_text(self) -> None:
        editor = WpsPresentationEditorPyQt5(MachineConfig())
        editor.resize(900, 600)
        editor.load_slides(["ABC"])
        editor.set_master_header("HDR")

        paths = editor.to_outline_paths_all_slides(mm_per_px_resolver=lambda _ed: 0.25)

        self.assertTrue(paths)
        self.assertTrue(any(len(p.points) >= 2 for p in paths))


if __name__ == "__main__":
    unittest.main()
