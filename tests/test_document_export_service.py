from __future__ import annotations

from pathlib import Path

import pytest

from inkscape_wps.core.office_export import DocParagraph, DocRun
from inkscape_wps.core.services.document_export_service import DocumentExportService
from inkscape_wps.core.services.document_file_service import DocumentFileService


def test_validate_source_accepts_matching_page() -> None:
    service = DocumentExportService()

    service.validate_source("table", "table", "XLSX")


def test_validate_source_rejects_mismatched_page() -> None:
    service = DocumentExportService()

    with pytest.raises(ValueError):
        service.validate_source("word", "table", "XLSX")


def test_export_docx_document_delegates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service = DocumentExportService()
    out = tmp_path / "a.docx"
    seen: dict[str, object] = {}

    def fake_export_docx(path: Path, *, paragraphs, html_text, prefer_soffice: bool) -> None:
        seen["path"] = path
        seen["paragraphs"] = paragraphs
        seen["html_text"] = html_text
        seen["prefer_soffice"] = prefer_soffice

    monkeypatch.setattr(
        "inkscape_wps.core.services.document_export_service.export_docx",
        fake_export_docx,
    )

    paras = [DocParagraph(runs=[DocRun(text="A")])]
    service.export_docx_document(out, paragraphs=paras, html_text="<p>A</p>")

    assert seen["path"] == out
    assert seen["paragraphs"] == paras
    assert seen["html_text"] == "<p>A</p>"
    assert seen["prefer_soffice"] is True


def test_export_markdown_document_delegates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service = DocumentExportService()
    out = tmp_path / "a.md"
    seen: dict[str, object] = {}

    def fake_export_markdown(path: Path, *, body: str) -> None:
        seen["path"] = path
        seen["body"] = body

    monkeypatch.setattr(
        "inkscape_wps.core.services.document_export_service.export_markdown",
        fake_export_markdown,
    )

    service.export_markdown_document(out, body="hello")

    assert seen == {"path": out, "body": "hello"}


def test_export_service_reports_capabilities_and_tooltips() -> None:
    service = DocumentExportService()

    assert service.can_export("xlsx", "table") is True
    assert service.can_export("xlsx", "word") is False
    assert "表格" in service.export_tooltip(
        kind="xlsx",
        content_label="文字",
        enabled=False,
        button=False,
    )
    assert "演示" in service.export_tooltip(
        kind="pptx",
        content_label="演示",
        enabled=True,
        button=True,
    )
    state = service.build_export_state("table", "表格")
    assert state.docx is True
    assert state.xlsx is True
    assert state.pptx is False
    assert "当前来源：表格" in state.summary_hint


def test_export_service_summary_hint_mentions_scope() -> None:
    service = DocumentExportService()

    assert "3 页" in service.export_summary_hint(
        "DOCX",
        source_label="演示",
        source_pid="slides",
        slide_count=3,
    )
    assert "2 × 4" in service.export_summary_hint(
        "XLSX",
        source_label="表格",
        source_pid="table",
        table_rows=2,
        table_cols=4,
    )
    assert "DOCX 已生成" in service.success_message(
        "DOCX",
        "a.docx",
        detail="DOCX 将按当前“文字”内容导出。",
    )


def test_import_service_success_tip_matches_kind() -> None:
    service = DocumentFileService()

    assert "表格" in service.import_success_tip("xlsx", "表格")
    assert "每页" in service.import_success_tip("md", "演示")
