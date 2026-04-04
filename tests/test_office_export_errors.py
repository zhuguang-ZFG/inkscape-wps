"""office_export 错误分支回归。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from inkscape_wps.core.office_export import DocParagraph, DocRun, OfficeExportError, export_docx, export_pptx, export_xlsx


class TestOfficeExportErrors(unittest.TestCase):
    def test_export_docx_wraps_oserror_as_office_export_error(self) -> None:
        fake_doc = mock.Mock()
        fake_doc.add_paragraph.return_value = mock.Mock()
        fake_doc.save.side_effect = OSError("disk full")

        with tempfile.TemporaryDirectory(prefix="inkscape-wps-docx-") as td:
            out = Path(td) / "out.docx"
            with mock.patch("docx.Document", return_value=fake_doc):
                with self.assertRaises(OfficeExportError) as ctx:
                    export_docx(out, paragraphs=[DocParagraph(runs=[DocRun(text="A")])])

        self.assertIn("DOCX 写入失败", str(ctx.exception))

    @unittest.skipUnless(__import__("importlib").util.find_spec("openpyxl") is not None, "openpyxl 未安装")
    def test_export_xlsx_wraps_oserror_as_office_export_error(self) -> None:
        with tempfile.TemporaryDirectory(prefix="inkscape-wps-xlsx-") as td:
            out = Path(td) / "out.xlsx"
            with mock.patch("openpyxl.workbook.workbook.Workbook.save", side_effect=OSError("disk full")):
                with self.assertRaises(OfficeExportError) as ctx:
                    export_xlsx(
                        out,
                        table_blob={
                            "rows": 1,
                            "cols": 1,
                            "cell_w_mm": 28.0,
                            "cell_h_mm": 12.0,
                            "cells": [[{"text": "X", "html": None}]],
                        },
                    )

        self.assertIn("XLSX 写入失败", str(ctx.exception))

    def test_export_pptx_wraps_oserror_as_office_export_error(self) -> None:
        fake_prs = mock.Mock()
        fake_shape = mock.Mock()
        fake_shape.has_text_frame = True
        fake_shape.text_frame = mock.Mock()
        fake_para = mock.Mock()
        fake_shape.text_frame.paragraphs = [fake_para]
        fake_title = mock.Mock()
        fake_slide = mock.Mock()
        fake_shapes = mock.Mock()
        fake_shapes.title = fake_title
        fake_shapes.__iter__ = mock.Mock(return_value=iter([fake_title, fake_shape]))
        fake_slide.shapes = fake_shapes
        fake_prs.slide_layouts = [mock.Mock(), mock.Mock()]
        fake_prs.slides.add_slide.return_value = fake_slide
        fake_prs.save.side_effect = OSError("disk full")
        fake_title.text = ""

        with tempfile.TemporaryDirectory(prefix="inkscape-wps-pptx-") as td:
            out = Path(td) / "out.pptx"
            with mock.patch("pptx.Presentation", return_value=fake_prs):
                with self.assertRaises(OfficeExportError) as ctx:
                    export_pptx(out, slides=["A"])

        self.assertIn("PPTX 写入失败", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
