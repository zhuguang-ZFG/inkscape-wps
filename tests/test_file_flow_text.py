"""file_flow_text 纯文本辅助回归测试。"""

from __future__ import annotations

import unittest

from inkscape_wps.ui.file_flow_text import describe_document_kind


class FileFlowTextTests(unittest.TestCase):
    def test_describe_document_kind_known_types(self) -> None:
        self.assertEqual(describe_document_kind("docx"), "Word 文档（DOCX）")
        self.assertEqual(describe_document_kind("pptx"), "PowerPoint 演示（PPTX）")
        self.assertEqual(describe_document_kind("md"), "Markdown（MD）")

    def test_describe_document_kind_unknown_type_falls_back(self) -> None:
        self.assertEqual(describe_document_kind("abc"), "文件")


if __name__ == "__main__":
    unittest.main()
