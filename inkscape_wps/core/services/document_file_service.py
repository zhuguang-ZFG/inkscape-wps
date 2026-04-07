"""Document file import orchestration service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from inkscape_wps.core.office_import import (
    OfficeImportError,
    detect_office_kind,
    import_docx_to_html,
    import_markdown_file_to_slides_plain,
    import_markdown_to_plain,
    import_pptx_to_slides,
    import_xlsx_to_table_blob,
    try_convert_wps_private_to_office,
)


@dataclass(frozen=True)
class ImportedDocument:
    """Normalized import result for the UI/application layer."""

    source_path: Path
    effective_path: Path
    kind: str
    target_mode: str
    title: str
    word_html: str | None = None
    word_plain_text: str | None = None
    table_blob: dict[str, Any] = field(default_factory=dict)
    slides: list[str] = field(default_factory=list)


class DocumentFileService:
    """Handle document import dispatch outside the UI layer."""

    def import_success_tip(self, kind: str, target_mode: str) -> str:
        if kind == "xlsx":
            return "建议先检查表格尺寸、网格线与右侧预览，再导出或发送。"
        if kind == "pptx":
            return "建议先翻看页数、母版文字和右侧预览，再导出或发送。"
        if kind == "md":
            if target_mode == "演示":
                return "Markdown 已按分节导入到演示，建议先检查每页内容与预览。"
            return "建议先检查段落换行与字形覆盖，再导出或发送。"
        return "建议先检查排版、字形覆盖和右侧预览，再导出或发送。"

    def import_document(self, path: Path) -> ImportedDocument:
        source_path = Path(path)
        effective_path = try_convert_wps_private_to_office(source_path)
        kind = detect_office_kind(effective_path)

        if kind == "docx":
            return ImportedDocument(
                source_path=source_path,
                effective_path=effective_path,
                kind=kind,
                target_mode="文字",
                title=effective_path.stem,
                word_html=import_docx_to_html(effective_path),
            )
        if kind == "xlsx":
            return ImportedDocument(
                source_path=source_path,
                effective_path=effective_path,
                kind=kind,
                target_mode="表格",
                title=effective_path.stem,
                table_blob=import_xlsx_to_table_blob(effective_path),
            )
        if kind == "pptx":
            return ImportedDocument(
                source_path=source_path,
                effective_path=effective_path,
                kind=kind,
                target_mode="演示",
                title=effective_path.stem,
                slides=import_pptx_to_slides(effective_path),
            )
        if kind == "md":
            slides = import_markdown_file_to_slides_plain(effective_path)
            if slides is not None:
                return ImportedDocument(
                    source_path=source_path,
                    effective_path=effective_path,
                    kind=kind,
                    target_mode="演示",
                    title=effective_path.stem,
                    slides=slides,
                )
            return ImportedDocument(
                source_path=source_path,
                effective_path=effective_path,
                kind=kind,
                target_mode="文字",
                title=effective_path.stem,
                word_plain_text=import_markdown_to_plain(effective_path),
            )

        raise OfficeImportError("不支持的文件类型。")
