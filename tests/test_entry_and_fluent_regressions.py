"""回归测试：入口回退与 Fluent 表格统计。"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock


class TestEntrypointFallback(unittest.TestCase):
    def test_run_pyqt6_starts_app_window_and_event_loop(self) -> None:
        from inkscape_wps import __main__ as entry

        app = mock.Mock()
        window = mock.Mock()
        qtwidgets_mod = types.ModuleType("PyQt6.QtWidgets")
        qtwidgets_mod.QApplication = mock.Mock(return_value=app)
        main_window_mod = types.ModuleType("inkscape_wps.ui.main_window")
        main_window_mod.MainWindow = mock.Mock(return_value=window)

        with mock.patch.dict(
            sys.modules,
            {
                "PyQt6": types.ModuleType("PyQt6"),
                "PyQt6.QtCore": types.SimpleNamespace(Qt=object()),
                "PyQt6.QtGui": types.ModuleType("PyQt6.QtGui"),
                "PyQt6.QtWidgets": qtwidgets_mod,
                "inkscape_wps.ui.main_window": main_window_mod,
            },
        ), mock.patch("sys.exit") as exit_mock:
            app.exec.return_value = 7
            entry._run_pyqt6()

        qtwidgets_mod.QApplication.assert_called_once()
        main_window_mod.MainWindow.assert_called_once()
        window.show.assert_called_once_with()
        app.exec.assert_called_once_with()
        exit_mock.assert_called_once_with(7)


class TestFluentDocStatsRegression(unittest.TestCase):
    def test_no_stale_table_widget_symbol_in_fluent_ui(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertNotIn("self._table_widget", code)


class TestFluentNonWordUndoRegression(unittest.TestCase):
    def test_insert_vector_blob_is_captured_in_nonword_state(self) -> None:
        from inkscape_wps.ui.nonword_undo_pyqt5 import capture_nonword_state_pyqt5

        state = capture_nonword_state_pyqt5(
            {"rows": 2},
            ["slide 1"],
            {"header": "H"},
            [{"points": []}],
            {"paths": [{"points": []}], "scale": 1.25, "dx_mm": 3.0, "dy_mm": 4.0},
        )

        self.assertEqual(len(state), 5)
        self.assertIn('"scale": 1.25', state[4])

    def test_fluent_undo_anchor_shape_matches_captured_state(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn(
            'self._nonword_undo_anchor: tuple[str, str, str, str, str] = ("", "", "", "", "")',
            code,
        )


class TestFluentPreviewZoomRegression(unittest.TestCase):
    def test_preview_zoom_signal_is_declared_and_wired(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("zoomChanged = pyqtSignal(float)", code)
        self.assertIn("self._preview.zoomChanged.connect(self._on_preview_zoom_changed)", code)
        self.assertGreaterEqual(code.count("self.zoomChanged.emit(self._zoom)"), 2)


class TestFluentPreviewSourceRegression(unittest.TestCase):
    def test_non_editor_pages_keep_last_content_mode_for_preview(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _current_content_page_id(self) -> str:", code)
        self.assertIn('if page in ("文字", "表格", "演示"):', code)
        self.assertIn('extra = f"   预览来源：{content_label}"', code)
        self.assertIn("content_pid = self._current_content_page_id()", code)


class TestFluentContextAndUndoRegression(unittest.TestCase):
    def test_slide_list_focus_refreshes_undo_state(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("sl.installEventFilter(self)", code)
        self.assertIn(
            "if event.type() == QEvent.FocusIn and obj is self._presentation_editor.slide_list_widget():",
            code,
        )

    def test_common_edit_round_menu_uses_context_enable_state(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _has_selection_for_current_edit_context(self) -> bool:", code)
        self.assertIn("def _can_paste_in_current_edit_context(self) -> bool:", code)
        self.assertIn("a_u.setEnabled(bool(self._act_undo.isEnabled()))", code)
        self.assertIn("a_cut.setEnabled(self._has_selection_for_current_edit_context())", code)
        self.assertIn("a_paste.setEnabled(self._can_paste_in_current_edit_context())", code)

    def test_non_editor_pages_do_not_route_undo_or_select_all_to_hidden_word_editor(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn('elif pid == "word":', code)
        self.assertIn("self._act_undo.setEnabled(False)", code)
        self.assertIn("self._act_redo.setEnabled(False)", code)
        self.assertIn('if name == "word" or not name:', code)

    def test_backstage_slide_stats_skip_revision_strike_text(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("t = document_plain_text_skip_strike(d)", code)

    def test_status_and_backstage_word_count_share_visible_char_rule(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _count_visible_chars(text: str) -> int:", code)
        self.assertIn('return f"字数：{_count_visible_chars(self._word_editor.toPlainText())}"', code)
        self.assertIn("words = _count_visible_chars(text)", code)

    def test_markdown_export_uses_current_content_source(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _table_plain_to_markdown(self) -> str:", code)
        self.assertIn("name = self._current_content_page_id()", code)
        self.assertIn('elif name == "table":', code)
        self.assertIn("body = self._table_plain_to_markdown()", code)

    def test_gcode_export_and_send_use_checked_work_paths_and_job_summary(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _current_work_paths_checked(self) -> List[VectorPath]:", code)
        self.assertIn("def _build_job_summary(self, paths: List[VectorPath]) -> str:", code)
        self.assertIn("paths = self._current_work_paths_checked()", code)
        self.assertIn('self._notify_error("导出失败", str(e))', code)
        self.assertIn('self._notify_error("发送失败", str(e))', code)
        self.assertIn('f"{self._build_job_summary(paths)}\\n\\n"', code)

    def test_docx_export_uses_current_content_source_instead_of_hidden_editor(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _docx_export_payload(self) -> tuple[List[DocParagraph], str | None]:", code)
        self.assertIn("paragraphs, src_html = self._docx_export_payload()", code)
        self.assertIn('if name == "table":', code)
        self.assertIn(
            "return self._docx_paragraphs_from_editor_widget(self._word_editor), self._word_editor.toHtml()",
            code,
        )

    def test_paste_is_not_enabled_for_non_editor_pages(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn('return self._current_page_id() in ("table", "slides", "word")', code)

    def test_send_actions_report_missing_device_connection(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn('self._notify_error("发送失败", "请先连接设备，再发送当前 G-code。")', code)
        self.assertIn('self._notify_error("断点续发失败", "当前未连接设备。")', code)
        self.assertIn('self._notify_error("软复位失败", "请先连接设备。")', code)

    def test_format_specific_exports_require_matching_content_source(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn(
            'def _require_export_source(self, expected_pid: str, target_name: str) -> None:',
            code,
        )
        self.assertIn('self._require_export_source("table", "XLSX")', code)
        self.assertIn('self._require_export_source("slides", "PPTX")', code)
        self.assertIn('self._notify_error("导出失败", str(e))', code)

    def test_export_actions_and_buttons_refresh_from_current_content_source(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _refresh_export_action_states(self) -> None:", code)
        self.assertIn("self._btn_export_xlsx.setEnabled(can_xlsx)", code)
        self.assertIn("self._btn_export_pptx.setEnabled(can_pptx)", code)
        self.assertIn("self._act_export_xlsx.setEnabled(can_xlsx)", code)
        self.assertIn("self._act_export_pptx.setEnabled(can_pptx)", code)
        self.assertIn("self._refresh_export_action_states()", code)

    def test_table_paths_append_optional_grid_gcode_paths(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("text_paths = map_document_lines(", code)
        self.assertIn("return list(text_paths) + list(self._table_editor.to_grid_paths())", code)

    def test_status_line_shows_glyph_coverage_hint(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _glyph_status_hint(self, pid: str) -> str:", code)
        self.assertIn("def _glyph_warning_summary(self, pid: str) -> str:", code)
        self.assertIn('return "字形：完整"', code)
        self.assertIn('return f"缺字形：{len(missing)}（{preview}）"', code)

    def test_job_summary_and_export_surface_missing_glyph_warning(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn('summary += f"\\n注意：{glyph_warning}"', code)
        self.assertIn('self._notify_warning(', code)
        self.assertIn('"字形提醒"', code)

    def test_help_page_and_menu_offer_missing_glyph_checker(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _show_missing_glyphs_dialog(self) -> None:", code)
        self.assertIn('btn_missing = PushButton("查看缺失字符")', code)
        self.assertIn('a_missing = Action(text="查看缺失字符")', code)
        self.assertIn('QMessageBox.warning(', code)

    def test_status_line_exposes_missing_glyph_shortcut_link(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _on_status_line_link_activated(self, link: str) -> None:", code)
        self.assertIn('self._status_line.linkActivated.connect(self._on_status_line_link_activated)', code)
        self.assertIn('href="missing-glyphs"', code)

    def test_table_editor_supports_grid_gcode_modes(self) -> None:
        code = Path("inkscape_wps/ui/table_editor_pyqt5.py").read_text(encoding="utf-8")
        self.assertIn('self._grid_gcode_mode.addItem("仅外框", "outer")', code)
        self.assertIn('self._grid_gcode_mode.addItem("全部网格", "all")', code)
        self.assertIn('if mode == "outer":', code)


if __name__ == "__main__":
    unittest.main()
