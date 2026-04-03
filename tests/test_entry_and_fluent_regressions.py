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


if __name__ == "__main__":
    unittest.main()
