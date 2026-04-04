"""文件打开/导入/导出相关的纯文本辅助函数。"""

from __future__ import annotations


def describe_document_kind(kind: str) -> str:
    return {
        "docx": "Word 文档（DOCX）",
        "xlsx": "Excel 表格（XLSX）",
        "pptx": "PowerPoint 演示（PPTX）",
        "wps": "WPS 文字（WPS）",
        "et": "WPS 表格（ET）",
        "dps": "WPS 演示（DPS）",
        "md": "Markdown（MD）",
        "unknown": "工程文件/其他",
    }.get(kind, "文件")
