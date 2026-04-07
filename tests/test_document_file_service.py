from __future__ import annotations

from pathlib import Path

import pytest

from inkscape_wps.core.office_import import OfficeImportError
from inkscape_wps.core.services.document_file_service import DocumentFileService


def test_markdown_slide_import_returns_slides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service = DocumentFileService()
    path = tmp_path / "demo.md"
    path.write_text("# A", encoding="utf-8")

    monkeypatch.setattr(
        "inkscape_wps.core.services.document_file_service.try_convert_wps_private_to_office",
        lambda p: p,
    )
    monkeypatch.setattr(
        "inkscape_wps.core.services.document_file_service.detect_office_kind",
        lambda p: "md",
    )
    monkeypatch.setattr(
        "inkscape_wps.core.services.document_file_service.import_markdown_file_to_slides_plain",
        lambda p: ["slide 1", "slide 2"],
    )

    imported = service.import_document(path)

    assert imported.kind == "md"
    assert imported.target_mode == "演示"
    assert imported.slides == ["slide 1", "slide 2"]
    assert imported.title == "demo"


def test_markdown_document_import_returns_plain_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = DocumentFileService()
    path = tmp_path / "notes.md"
    path.write_text("# Notes", encoding="utf-8")

    monkeypatch.setattr(
        "inkscape_wps.core.services.document_file_service.try_convert_wps_private_to_office",
        lambda p: p,
    )
    monkeypatch.setattr(
        "inkscape_wps.core.services.document_file_service.detect_office_kind",
        lambda p: "md",
    )
    monkeypatch.setattr(
        "inkscape_wps.core.services.document_file_service.import_markdown_file_to_slides_plain",
        lambda p: None,
    )
    monkeypatch.setattr(
        "inkscape_wps.core.services.document_file_service.import_markdown_to_plain",
        lambda p: "Notes",
    )

    imported = service.import_document(path)

    assert imported.target_mode == "文字"
    assert imported.word_plain_text == "Notes"
    assert imported.word_html is None


def test_wps_import_uses_converted_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service = DocumentFileService()
    original = tmp_path / "demo.wps"
    converted = tmp_path / "demo.docx"
    original.write_text("placeholder", encoding="utf-8")
    converted.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        "inkscape_wps.core.services.document_file_service.try_convert_wps_private_to_office",
        lambda p: converted,
    )
    monkeypatch.setattr(
        "inkscape_wps.core.services.document_file_service.detect_office_kind",
        lambda p: "docx",
    )
    monkeypatch.setattr(
        "inkscape_wps.core.services.document_file_service.import_docx_to_html",
        lambda p: "<p>converted</p>",
    )

    imported = service.import_document(original)

    assert imported.source_path == original
    assert imported.effective_path == converted
    assert imported.word_html == "<p>converted</p>"


def test_unknown_kind_raises_office_import_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = DocumentFileService()
    path = tmp_path / "demo.bin"
    path.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        "inkscape_wps.core.services.document_file_service.try_convert_wps_private_to_office",
        lambda p: p,
    )
    monkeypatch.setattr(
        "inkscape_wps.core.services.document_file_service.detect_office_kind",
        lambda p: "unknown",
    )

    with pytest.raises(OfficeImportError):
        service.import_document(path)
