"""Document export orchestration service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inkscape_wps.core.office_export import (
    DocParagraph,
    export_docx,
    export_markdown,
    export_pptx,
    export_xlsx,
    has_soffice,
)


@dataclass(frozen=True)
class ExportSupportState:
    """Resolved export availability for the current content source."""

    docx: bool
    xlsx: bool
    pptx: bool
    markdown: bool
    summary_hint: str


class DocumentExportService:
    """Coordinate document export flows outside the UI layer."""

    _SUPPORTED_SOURCES = {
        "docx": frozenset({"word", "slides", "table"}),
        "xlsx": frozenset({"table"}),
        "pptx": frozenset({"slides"}),
        "markdown": frozenset({"word", "slides", "table"}),
    }

    def can_export(self, kind: str, current_pid: str) -> bool:
        return current_pid in self._SUPPORTED_SOURCES.get(kind.lower(), frozenset())

    def build_export_state(self, current_pid: str, content_label: str) -> ExportSupportState:
        docx = self.can_export("docx", current_pid)
        xlsx = self.can_export("xlsx", current_pid)
        pptx = self.can_export("pptx", current_pid)
        markdown = self.can_export("markdown", current_pid)
        summary_hint = (
            "会根据当前内容来源导出对应格式。"
            f" 当前来源：{content_label}；"
            f" DOCX：{'可用' if docx else '不可用'}；"
            f" XLSX：{'可用' if xlsx else '仅表格'}；"
            f" PPTX：{'可用' if pptx else '仅演示'}；"
            f" Markdown：{'可用' if markdown else '不可用'}。"
        )
        return ExportSupportState(
            docx=docx,
            xlsx=xlsx,
            pptx=pptx,
            markdown=markdown,
            summary_hint=summary_hint,
        )

    def validate_source(self, current_pid: str, expected_pid: str, target_name: str) -> None:
        if current_pid == expected_pid:
            return
        raise ValueError(
            f"{target_name} 导出仅适用于“{expected_pid}”内容；当前预览来源是“{current_pid}”。"
        )

    def export_tooltip(
        self,
        *,
        kind: str,
        content_label: str,
        enabled: bool,
        button: bool,
    ) -> str:
        kind = kind.lower()
        if kind == "xlsx":
            if enabled:
                return "当前来源为表格，可导出 XLSX。"
            return (
                f"请先切到表格；当前来源：{content_label}。"
                if button
                else f"XLSX 仅支持表格；当前来源：{content_label}。"
            )
        if kind == "pptx":
            if enabled:
                return "当前来源为演示，可导出 PPTX。"
            return (
                f"请先切到演示；当前来源：{content_label}。"
                if button
                else f"PPTX 仅支持演示；当前来源：{content_label}。"
            )
        if enabled:
            return f"当前来源为{content_label}，可导出。"
        return f"当前来源：{content_label}。"

    def export_summary_hint(
        self,
        target_name: str,
        *,
        source_label: str,
        source_pid: str,
        slide_count: int = 0,
        table_rows: int = 0,
        table_cols: int = 0,
    ) -> str:
        if target_name == "PPTX":
            return f"PPTX 将按“{source_label}”内容导出，当前共 {max(1, slide_count)} 页，并套用母版页眉/页脚。"
        if target_name == "XLSX":
            return f"XLSX 将按“{source_label}”内容导出，当前表格为 {max(1, table_rows)} × {max(1, table_cols)}。"
        if target_name == "DOCX":
            if source_pid == "slides":
                return f"DOCX 将按整套“{source_label}”内容导出，当前共 {max(1, slide_count)} 页。"
            return f"DOCX 将按当前“{source_label}”内容导出。"
        return f"{target_name} 将按当前“{source_label}”内容导出。"

    def backend_hint(self) -> str:
        if has_soffice():
            return "已检测到 soffice（高保真导出已启用）"
        return "未检测到 soffice（使用纯 Python 导出）"

    def success_message(self, target_name: str, filename: str, *, detail: str) -> str:
        return f"{target_name} 已生成：{filename}。{detail}"

    def export_docx_document(
        self,
        path: Path,
        *,
        paragraphs: list[DocParagraph],
        html_text: str | None,
    ) -> None:
        export_docx(path, paragraphs=paragraphs, html_text=html_text, prefer_soffice=True)

    def export_xlsx_document(self, path: Path, *, table_blob: dict[str, Any]) -> None:
        export_xlsx(path, table_blob=table_blob, prefer_soffice=True)

    def export_pptx_document(self, path: Path, *, slides: list[str]) -> None:
        export_pptx(path, slides=slides, prefer_soffice=True)

    def export_markdown_document(self, path: Path, *, body: str) -> None:
        export_markdown(path, body=body)
