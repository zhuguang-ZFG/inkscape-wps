import json
from pathlib import Path

from inkscape_wps.core.project_io import (
    FORMAT_ID,
    FORMAT_VERSION,
    load_project_file,
    save_project_file,
)


def test_save_and_load_word_plain_text(tmp_path: Path):
    p = tmp_path / "a.inkwps.json"
    save_project_file(
        p,
        title="t",
        word_html="<p>a</p>",
        word_plain_text="a",
        table_blob={},
        slides=[],
        sketch_blob={},
    )
    d = load_project_file(p)
    assert d["word_plain_text"] == "a"


def test_load_old_file_fallback_plain_text(tmp_path: Path):
    p = tmp_path / "old.inkwps.json"
    p.write_text(
        json.dumps(
            {
                "format": FORMAT_ID,
                "version": FORMAT_VERSION,
                "title": "old",
                "word_html": "<p>Hello<br/>World</p>",
                "table": {},
                "slides": [],
                "sketch": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    d = load_project_file(p)
    assert d["word_plain_text"] == "Hello\nWorld"
    assert d["render_modes"] == {}


def test_load_project_file_with_utf8_bom(tmp_path: Path):
    p = tmp_path / "bom.inkwps.json"
    p.write_text(
        "\ufeff"
        + json.dumps(
            {
                "format": FORMAT_ID,
                "version": FORMAT_VERSION,
                "title": "bom",
                "word_html": "<p>Hi</p>",
                "table": {},
                "slides": [],
                "sketch": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    d = load_project_file(p)
    assert d["title"] == "bom"
    assert d["word_plain_text"] == "Hi"
