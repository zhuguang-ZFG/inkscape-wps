"""FontManagerDialog 回归测试。"""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

try:
    from inkscape_wps.ui.font.font_manager_dialog import FontManagerDialog
    from inkscape_wps.ui.qt_compat import QApplication
except Exception:  # pragma: no cover
    QApplication = None  # type: ignore[misc,assignment]
    FontManagerDialog = None  # type: ignore[misc,assignment]


class _FakeFontService:
    def __init__(self) -> None:
        self._fonts = {
            "demo": {
                "type": "json",
                "loaded": False,
                "metadata": {"description": "demo font"},
                "character_count": 1,
            }
        }

    async def discover_fonts(self) -> list[str]:
        return list(self._fonts.keys())

    async def load_font(self, font_name: str) -> bool:
        info = self._fonts.get(font_name)
        if info is None:
            return False
        info["loaded"] = True
        return True

    def get_font_info(self, font_name: str):  # noqa: ANN001
        return self._fonts.get(font_name)

    def get_character_set(self, font_name: str) -> list[str]:
        info = self._fonts.get(font_name)
        if not info or not info.get("loaded"):
            return []
        return ["A"]

    def get_available_fonts(self) -> list[str]:
        return list(self._fonts.keys())

    async def export_font(self, font_name: str, output_path) -> bool:  # noqa: ANN001
        del font_name, output_path
        return True

    async def merge_fonts(self, base_font: str, additional_font: str, output_name: str) -> bool:
        del base_font, additional_font
        self._fonts[output_name] = {
            "type": "merged",
            "loaded": True,
            "metadata": {"description": "merged font"},
            "character_count": 1,
        }
        return True


@unittest.skipUnless(QApplication is not None, "Qt 不可用")
class FontManagerDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _run_thread_inline(self, thread: threading.Thread) -> None:
        thread.run()

    def test_dialog_loads_font_list_without_asyncio_loop(self) -> None:
        with mock.patch.object(threading.Thread, "start", self._run_thread_inline):
            dialog = FontManagerDialog(_FakeFontService())

        self.assertEqual(dialog.font_list.count(), 1)
        self.assertEqual(dialog.font_list.item(0).text(), "demo")

    def test_selecting_font_loads_info_and_character_preview(self) -> None:
        with mock.patch.object(threading.Thread, "start", self._run_thread_inline):
            dialog = FontManagerDialog(_FakeFontService())
            dialog.font_list.setCurrentRow(0)
            dialog._on_font_selected()

        self.assertIn("已加载", dialog.font_info.text())
        self.assertEqual(dialog.char_preview.count(), 1)

    def test_import_font_files_copies_supported_fonts_and_clears_cache(self) -> None:
        service = _FakeFontService()
        service.clear_cache = mock.Mock()  # type: ignore[attr-defined]

        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            threading.Thread,
            "start",
            self._run_thread_inline,
        ):
            dialog = FontManagerDialog(service)
            src_dir = Path(td)
            json_font = src_dir / "demo.json"
            txt_file = src_dir / "ignore.txt"
            json_font.write_text("{}", encoding="utf-8")
            txt_file.write_text("x", encoding="utf-8")
            target_dir = src_dir / "fonts"

            with mock.patch.object(dialog, "_user_font_dir", return_value=target_dir):
                imported = dialog._import_font_files([json_font, txt_file])

        self.assertEqual(imported, 1)
        self.assertTrue((target_dir / "demo.json").is_file())
        service.clear_cache.assert_called_once()


if __name__ == "__main__":
    unittest.main()
