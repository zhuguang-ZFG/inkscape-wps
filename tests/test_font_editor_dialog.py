"""FontEditorDialog 回归测试。"""

from __future__ import annotations

import unittest
from unittest import mock

try:
    from inkscape_wps.core.types import Point
    from inkscape_wps.ui.font.font_editor_dialog import FontEditorDialog
    from inkscape_wps.ui.qt_compat import QApplication
except Exception:  # pragma: no cover
    QApplication = None  # type: ignore[misc,assignment]
    FontEditorDialog = None  # type: ignore[misc,assignment]
    Point = None  # type: ignore[misc,assignment]


@unittest.skipUnless(QApplication is not None, "Qt 不可用")
class FontEditorDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_switching_character_persists_current_canvas_strokes(self) -> None:
        dialog = FontEditorDialog()
        dialog.current_character = "A"
        dialog.canvas.set_paths([[Point(1, 2), Point(3, 4)]])

        dialog._on_character_changed("B")

        self.assertEqual(dialog.characters["A"], [[[1.0, 2.0], [3.0, 4.0]]])
        self.assertEqual(dialog.current_character, "B")

    def test_duplicate_character_uses_deep_copy(self) -> None:
        dialog = FontEditorDialog()
        dialog.characters["A"] = [[[1.0, 2.0], [3.0, 4.0]]]
        dialog.char_list.addItem("A")
        dialog.char_list.setCurrentRow(0)
        dialog.char_input.setCurrentText("B")

        dialog._duplicate_character()
        dialog.characters["B"][0][0][0] = 99.0

        self.assertEqual(dialog.characters["A"][0][0][0], 1.0)
        self.assertEqual(dialog.characters["B"][0][0][0], 99.0)

    def test_preview_character_opens_dialog_when_strokes_exist(self) -> None:
        dialog = FontEditorDialog()
        dialog.current_character = "A"
        dialog.characters["A"] = [[[1.0, 2.0], [3.0, 4.0]]]

        with mock.patch("inkscape_wps.ui.font.font_editor_dialog.QDialog.exec") as exec_mock:
            dialog._preview_character()

        exec_mock.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
