"""PyQt5 表格网格线导出回归。"""

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
from inkscape_wps.ui.table_editor_pyqt5 import WpsTableEditorPyQt5


@unittest.skipUnless(QApplication is not None, "PyQt5 不可用")
class TableEditorGridPyQt5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_single_cell_grid_exports_outer_border_segments(self) -> None:
        editor = WpsTableEditorPyQt5(MachineConfig())
        editor.from_project_blob({"rows": 1, "cols": 1, "grid_gcode_mode": "all"})

        paths = editor.to_grid_paths()

        self.assertEqual(len(paths), 4)
        segments = {
            ((p.points[0].x, p.points[0].y), (p.points[-1].x, p.points[-1].y))
            for p in paths
        }
        self.assertEqual(
            segments,
            {
                ((15.0, 282.0), (43.0, 282.0)),
                ((15.0, 270.0), (15.0, 282.0)),
                ((15.0, 270.0), (43.0, 270.0)),
                ((43.0, 270.0), (43.0, 282.0)),
            },
        )

    def test_merged_cells_do_not_emit_hidden_internal_grid_segment(self) -> None:
        editor = WpsTableEditorPyQt5(MachineConfig())
        editor.from_project_blob({"rows": 2, "cols": 2, "grid_gcode_mode": "all"})
        editor.table_widget().setSpan(0, 0, 1, 2)

        segments = {
            ((p.points[0].x, p.points[0].y), (p.points[-1].x, p.points[-1].y))
            for p in editor.to_grid_paths()
        }

        self.assertNotIn(((43.0, 270.0), (43.0, 282.0)), segments)
        self.assertIn(((43.0, 258.0), (43.0, 270.0)), segments)

    def test_outer_grid_mode_only_exports_table_border(self) -> None:
        editor = WpsTableEditorPyQt5(MachineConfig())
        editor.from_project_blob({"rows": 2, "cols": 2, "grid_gcode_mode": "outer"})

        paths = editor.to_grid_paths()
        segments = {
            ((p.points[0].x, p.points[0].y), (p.points[-1].x, p.points[-1].y))
            for p in paths
        }

        self.assertEqual(len(paths), 4)
        self.assertEqual(
            segments,
            {
                ((15.0, 282.0), (71.0, 282.0)),
                ((71.0, 258.0), (71.0, 282.0)),
                ((15.0, 258.0), (71.0, 258.0)),
                ((15.0, 258.0), (15.0, 282.0)),
            },
        )

    def test_table_outline_paths_export_text_contours(self) -> None:
        editor = WpsTableEditorPyQt5(MachineConfig())
        editor.from_project_blob(
            {
                "rows": 1,
                "cols": 1,
                "grid_gcode_mode": "none",
                "cells": [[{"text": "A", "html": "<p>A</p>"}]],
            }
        )

        paths = editor.to_outline_paths(mm_per_px=0.25)

        self.assertTrue(paths)
        self.assertTrue(any(len(p.points) >= 2 for p in paths))


if __name__ == "__main__":
    unittest.main()
