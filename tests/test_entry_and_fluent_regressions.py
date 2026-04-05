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


class TestLegacyMainWindowParityRegression(unittest.TestCase):
    def test_legacy_main_window_appends_table_grid_paths(self) -> None:
        code = Path("inkscape_wps/ui/main_window.py").read_text(encoding="utf-8")
        self.assertIn(") + list(self._table_editor.to_grid_paths())", code)

    def test_legacy_main_window_checks_missing_glyphs_before_export_and_send(self) -> None:
        code = Path("inkscape_wps/ui/main_window.py").read_text(encoding="utf-8")
        self.assertIn("def _current_work_paths_checked(self) -> List[VectorPath]:", code)
        self.assertIn("def _build_job_summary(self, paths: List[VectorPath]) -> str:", code)
        self.assertIn('m_tool.addAction("查看缺失字符…", self._show_missing_glyphs_dialog)', code)
        self.assertIn('m_help.addAction("查看缺失字符…", self._show_missing_glyphs_dialog)', code)

    def test_legacy_main_window_table_context_menu_matches_core_actions(self) -> None:
        code = Path("inkscape_wps/ui/main_window.py").read_text(encoding="utf-8")
        self.assertIn("tw.customContextMenuRequested.connect(self._open_table_context_menu)", code)
        self.assertIn("def _open_table_context_menu(self, pos) -> None:", code)
        self.assertIn("idx = tw.indexAt(pos)", code)
        self.assertIn("if not in_selection:", code)
        self.assertIn('menu.addAction("合并选区单元格", self._table_editor.merge_selected_cells)', code)
        self.assertIn('menu.addAction("拆分当前合并", self._table_editor.split_current_merged_cell)', code)

    def test_legacy_table_editor_supports_grid_gcode_modes(self) -> None:
        code = Path("inkscape_wps/ui/table_editor.py").read_text(encoding="utf-8")
        self.assertIn('self._grid_gcode_mode.addItem("仅外框", "outer")', code)
        self.assertIn("def to_grid_paths(self) -> List[VectorPath]:", code)
        self.assertIn("def merge_selected_cells(self) -> None:", code)
        self.assertIn("def insert_row_above(self) -> None:", code)
        self.assertIn("def delete_current_column(self) -> None:", code)
        self.assertIn('if (r, c) in covered and (r, c) not in anchor_cells:', code)
        self.assertIn('"spans": spans,', code)
        self.assertIn("self._grid_gcode_mode.setCurrentIndex(0)", code)

    def test_legacy_slide_glyph_check_uses_export_plain_text(self) -> None:
        pres_code = Path("inkscape_wps/ui/presentation_editor.py").read_text(encoding="utf-8")
        window_code = Path("inkscape_wps/ui/main_window.py").read_text(encoding="utf-8")
        self.assertIn("def slides_storage_for_export(self) -> List[str]:", pres_code)
        self.assertIn('return "\\n".join(self._presentation_editor.slides_storage_for_export())', window_code)


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
        self.assertIn('f"字数：{_count_visible_chars(self._word_editor.toPlainText())}"', code)
        self.assertIn('f"   模式：{self._word_render_mode_label()}"', code)
        self.assertIn("words = _count_visible_chars(text)", code)

    def test_markdown_export_uses_current_content_source(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _table_plain_to_markdown(self) -> str:", code)
        self.assertIn("name = self._current_content_page_id()", code)
        self.assertIn('elif name == "table":', code)
        self.assertIn("body = self._table_plain_to_markdown()", code)

    def test_project_save_and_open_include_render_modes(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        project_code = Path("inkscape_wps/core/project_io.py").read_text(encoding="utf-8")
        self.assertIn("def _capture_render_modes(self) -> dict:", code)
        self.assertIn("def _apply_render_modes(self, data: dict | None) -> None:", code)
        self.assertIn("render_modes=self._capture_render_modes()", code)
        self.assertIn('self._apply_render_modes(d.get("render_modes"))', code)
        self.assertIn('f" 当前模式：文字 {self._word_render_mode_label()}，"', code)
        self.assertIn('f"表格 {self._table_render_mode_label()}，演示 {self._slides_render_mode_label()}。"', code)
        self.assertIn("render_modes: Dict[str, Any] | None = None,", project_code)
        self.assertIn('"render_modes": render_modes or {},', project_code)
        self.assertIn('d["render_modes"] = {}', project_code)

    def test_office_export_success_messages_explain_scope(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _office_export_tip(self, target_name: str) -> str:", code)
        self.assertIn("DOCX 将按整套", code)
        self.assertIn("PPTX 将按", code)
        self.assertIn("XLSX 将按", code)
        self.assertIn('return f"{target_name} 将按当前“{source}”内容导出。"', code)
        self.assertIn("f\"DOCX 已生成：{Path(path).name}。{self._office_export_tip('DOCX')}\"", code)
        self.assertIn("f\"XLSX 已生成：{Path(path).name}。{self._office_export_tip('XLSX')}\"", code)
        self.assertIn("f\"PPTX 已生成：{Path(path).name}。{self._office_export_tip('PPTX')}\"", code)
        self.assertIn("f\"Markdown 已生成：{Path(path).name}。{self._office_export_tip('Markdown')}\"", code)

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
        self.assertIn('if name == "slides":', code)
        self.assertIn("return self._slides_docx_paragraphs(), None", code)
        self.assertIn("def _slides_docx_paragraphs(self) -> List[DocParagraph]:", code)
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
        self.assertIn('if str(getattr(self._cfg, "table_render_mode", "stroke") or "stroke").strip().lower() == "outline":', code)
        self.assertIn("text_paths = self._table_editor.to_outline_paths(mm_per_px)", code)
        self.assertIn("return list(text_paths) + list(self._table_editor.to_grid_paths())", code)

    def test_slides_paths_support_outline_mode(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn('if str(getattr(self._cfg, "slides_render_mode", "stroke") or "stroke").strip().lower() == "outline":', code)
        self.assertIn("return self._presentation_editor.to_outline_paths_all_slides(mm_per_px_resolver=_mm_px)", code)

    def test_status_line_shows_glyph_coverage_hint(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _glyph_status_hint(self, pid: str) -> str:", code)
        self.assertIn("def _glyph_warning_summary(self, pid: str) -> str:", code)
        self.assertIn('return "字形：完整"', code)
        self.assertIn('return f"缺字形：{len(missing)}（{preview}）"', code)

    def test_render_mode_guidance_is_exposed_in_preflight_and_export(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _render_mode_tip(self, mode: str) -> str:", code)
        self.assertIn("def _current_render_mode_label(self, pid: str) -> str:", code)
        self.assertIn("def _current_render_mode_tip(self, pid: str) -> str:", code)
        self.assertIn('infos.append(f"模式说明：{self._current_render_mode_tip(pid)}")', code)
        self.assertIn('f"\\n当前模式：{self._current_render_mode_label(pid)}"', code)
        self.assertIn('f"\\n{self._current_render_mode_tip(pid)}"', code)
        self.assertIn('f"当前模式：{self._current_render_mode_label(pid)}。"', code)
        self.assertIn('f"{self._current_render_mode_tip(pid)} 建议先做小范围试写。"', code)

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

    def test_help_and_device_pages_offer_preflight_and_diagnostics(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn('PushButton("开始加工前检查")', code)
        self.assertIn('PushButton("查看诊断")', code)
        self.assertIn('PushButton("SVG 导入诊断")', code)
        self.assertIn('PushButton("奎享/字库诊断")', code)
        self.assertIn("def _show_preflight_report(self) -> None:", code)
        self.assertIn("def _show_diagnostics_report(self) -> None:", code)
        self.assertIn("def _show_svg_diagnostics(self) -> None:", code)
        self.assertIn("def _show_font_diagnostics(self) -> None:", code)
        self.assertIn("btn_svg = box.addButton(\"重新导入 SVG\", QMessageBox.ActionRole)", code)
        self.assertIn("btn_trace = box.addButton(\"重新描摹图片\", QMessageBox.ActionRole)", code)
        self.assertIn("btn_clear = box.addButton(\"清除插图\", QMessageBox.ActionRole)", code)
        self.assertIn("btn_reset = box.addButton(\"恢复默认字库\", QMessageBox.ActionRole)", code)
        self.assertIn("btn_clear_merge = box.addButton(\"清除合并字库\", QMessageBox.ActionRole)", code)
        self.assertIn("btn_kdraw = box.addButton(\"打开 KDraw 字库目录\", QMessageBox.ActionRole)", code)
        self.assertIn("def _refresh_diagnostic_summary(self) -> None:", code)

    def test_status_line_exposes_missing_glyph_shortcut_link(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        self.assertIn("def _on_status_line_link_activated(self, link: str) -> None:", code)
        self.assertIn('self._status_line.linkActivated.connect(self._on_status_line_link_activated)', code)
        self.assertIn('href="missing-glyphs"', code)
        self.assertIn('href="preflight-report"', code)
        self.assertIn('elif target == "preflight-report":', code)

    def test_table_editor_supports_grid_gcode_modes(self) -> None:
        code = Path("inkscape_wps/ui/table_editor_pyqt5.py").read_text(encoding="utf-8")
        self.assertIn('self._grid_gcode_mode.addItem("仅外框", "outer")', code)
        self.assertIn('self._grid_gcode_mode.addItem("全部网格", "all")', code)
        self.assertIn('if mode == "outer":', code)
        self.assertIn("self._grid_gcode_mode.setCurrentIndex(0)", code)

    def test_fluent_diagnostics_use_structured_log_and_preflight_report(self) -> None:
        code = Path("inkscape_wps/ui/main_window_fluent.py").read_text(encoding="utf-8")
        stroke_code = Path("inkscape_wps/ui/stroke_text_editor.py").read_text(encoding="utf-8")
        self.assertIn("def _log_event(self, category: str, message: str, *, level: str = \"INFO\") -> None:", code)
        self.assertIn("datetime.now().strftime(\"%H:%M:%S\")", code)
        self.assertIn("self._log_records: List[tuple[str, str]] = []", code)
        self.assertIn("self._log_filter = \"全部\"", code)
        self.assertIn("def _render_log_views(self) -> None:", code)
        self.assertIn("def _set_log_filter(self, value: str) -> None:", code)
        self.assertIn("def _clear_logs(self) -> None:", code)
        self.assertIn("self._log_filter_combo = ComboBox()", code)
        self.assertIn("self._dev_log_filter_combo = ComboBox()", code)
        self.assertIn("for item in (\"全部\", \"导出\", \"发送\", \"设备\", \"预检\", \"诊断\", \"运行\"):", code)
        self.assertIn("def _preflight_report(self) -> tuple[str, List[str]]:", code)
        self.assertIn("def _svg_diagnostic_lines(self) -> List[str]:", code)
        self.assertIn("def _font_diagnostic_lines(self) -> List[str]:", code)
        self.assertIn("def _remap_stroke_font(self) -> None:", code)
        self.assertIn("self._word_editor.set_mapper(self._mapper)", code)
        self.assertIn("def set_mapper(self, mapper: HersheyFontMapper) -> None:", stroke_code)
        self.assertIn("def _clear_stroke_merge_json(self) -> None:", code)
        self.assertIn("def _reset_stroke_font_to_bundled(self) -> None:", code)
        self.assertIn("def _open_kdraw_gcode_fonts_dir(self) -> None:", code)
        self.assertIn('box.setDetailedText(', code)
        self.assertIn('"\\n\\nSVG / 位图导入诊断\\n"', code)
        self.assertIn('"\\n\\n奎享 / 字库诊断\\n"', code)
        self.assertIn("def _health_status_payload(self) -> tuple[str, str, str, List[str]]:", code)
        self.assertIn("def _health_primary_action_spec(self) -> tuple[str, str, str]:", code)
        self.assertIn("def _run_health_primary_action(self) -> None:", code)
        self.assertIn("def _refresh_health_action_button(self, button: QPushButton) -> None:", code)
        self.assertIn("self._word_render_mode_combo = ComboBox()", code)
        self.assertIn('self._word_render_mode_combo.addItem("单线雕刻", "stroke")', code)
        self.assertIn('self._word_render_mode_combo.addItem("视觉复刻", "outline")', code)
        self.assertIn("self._table_render_mode_combo = ComboBox()", code)
        self.assertIn('self._table_render_mode_combo.addItem("单线雕刻", "stroke")', code)
        self.assertIn('self._table_render_mode_combo.addItem("视觉复刻", "outline")', code)
        self.assertIn('self._table_render_mode_combo.setToolTip(', code)
        self.assertIn('table_note = QLabel("单线雕刻适合表格走线；视觉复刻保留字体外观，适合版式确认。")', code)
        self.assertIn("self._slides_render_mode_combo = ComboBox()", code)
        self.assertIn('self._slides_render_mode_combo.addItem("单线雕刻", "stroke")', code)
        self.assertIn('self._slides_render_mode_combo.addItem("视觉复刻", "outline")', code)
        self.assertIn('self._slides_render_mode_combo.setToolTip(', code)
        self.assertIn('slide_note = QLabel("单线雕刻更适合加工；视觉复刻会连同母版文字一起更接近演示外观。")', code)
        self.assertIn("def _on_word_render_mode_changed(self, _index: int = 0) -> None:", code)
        self.assertIn("def _on_table_render_mode_changed(self, _index: int = 0) -> None:", code)
        self.assertIn("def _on_slides_render_mode_changed(self, _index: int = 0) -> None:", code)
        self.assertIn('if hasattr(self, "_word_editor") and self._word_editor.render_mode() == "outline":', code)
        self.assertIn("base = self._word_editor.to_outline_paths()", code)
        self.assertIn('summary += f"\\n文字模式：{self._word_render_mode_label()}"', code)
        self.assertIn('summary += f"\\n表格模式：{self._table_render_mode_label()}"', code)
        self.assertIn('summary += f"\\n演示模式：{self._slides_render_mode_label()}"', code)
        self.assertIn("def _word_render_mode_label(self) -> str:", code)
        self.assertIn("def _table_render_mode_label(self) -> str:", code)
        self.assertIn("def _slides_render_mode_label(self) -> str:", code)
        self.assertIn('self._word_render_mode_combo.setToolTip(', code)
        self.assertIn("def set_render_mode(self, mode: str) -> None:", stroke_code)
        self.assertIn("def render_mode(self) -> str:", stroke_code)
        self.assertIn("def to_outline_paths(self) -> list[VectorPath]:", stroke_code)
        self.assertIn("path.addText(QPointF(row.x_px, row.y_px + row.baseline_du), font, row.text)", stroke_code)
        table_code = Path("inkscape_wps/ui/table_editor_pyqt5.py").read_text(encoding="utf-8")
        bridge_code = Path("inkscape_wps/ui/document_bridge_pyqt5.py").read_text(encoding="utf-8")
        slides_code = Path("inkscape_wps/ui/presentation_editor_pyqt5.py").read_text(encoding="utf-8")
        self.assertIn("def to_outline_paths(self, mm_per_px: float) -> List[VectorPath]:", table_code)
        self.assertIn("html_fragment_to_outline_paths(", table_code)
        self.assertIn("def to_outline_paths_all_slides(", slides_code)
        self.assertIn("text_edit_to_outline_paths(", slides_code)
        self.assertIn("def html_fragment_to_outline_paths(", bridge_code)
        self.assertIn("def text_edit_to_outline_paths(", bridge_code)
        self.assertIn("path.addText(x0, baseline_doc_y, font, text)", bridge_code)
        self.assertIn("def _set_health_card_state(self, card: QFrame, title: QLabel, detail: QLabel) -> None:", code)
        self.assertIn('return "error", "#c23b32", "需先处理"', code)
        self.assertIn('return "warn", "#b06a12", "建议确认"', code)
        self.assertIn('return "ok", "#217346", "可以开始"', code)
        self.assertIn('return "missing", "查看缺失字符"', code)
        self.assertIn('return "device", "去连接设备"', code)
        self.assertIn('return "preflight", "查看完整检查"', code)
        self.assertIn("self._home_health_card = QFrame()", code)
        self.assertIn("self._dev_health_card = QFrame()", code)
        self.assertIn("self._home_health_action_btn = PrimaryPushButton(\"查看完整检查\")", code)
        self.assertIn("self._dev_health_action_btn = PrimaryPushButton(\"查看完整检查\")", code)
        self.assertIn("self._log_append(f\"{stamp} [{category}/{level}] {message}\", category=category)", code)
        self.assertIn("self._log_records.append((str(category or \"运行\"), str(s)))", code)
        self.assertIn('lines.append("排查顺序：先看内容来源与缺字形，再看纸张/抬落笔，最后看设备连接与告警。")', code)
        self.assertIn('self._log_event("导出", "开始导出 G-code", level="INFO")', code)
        self.assertIn('self._log_event("发送", "开始发送当前 G-code", level="INFO")', code)


if __name__ == "__main__":
    unittest.main()
