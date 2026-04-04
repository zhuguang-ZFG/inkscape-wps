"""工程文件读写与矢量序列化（无 PyQt 依赖）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from inkscape_wps.core.project_io import (
    FORMAT_ID,
    FORMAT_VERSION,
    deserialize_vector_paths,
    load_project_file,
    save_project_file,
    serialize_vector_paths,
    validate_project_header,
    write_text_atomic,
)
from inkscape_wps.core.types import Point, VectorPath


class TestProjectIo(unittest.TestCase):
    _TABLE_BLOB = {
        "rows": 1,
        "cols": 1,
        "cell_w_mm": 10.0,
        "cell_h_mm": 10.0,
        "cells": [[{"text": "", "html": None}]],
    }

    def test_validate_header_ok(self) -> None:
        validate_project_header({"format": FORMAT_ID, "version": FORMAT_VERSION})

    def test_validate_header_v1_compat(self) -> None:
        validate_project_header({"format": FORMAT_ID, "version": 1})

    def test_validate_header_bad_format(self) -> None:
        with self.assertRaises(ValueError):
            validate_project_header({"format": "other", "version": 1})

    def test_validate_header_bad_version(self) -> None:
        with self.assertRaises(ValueError):
            validate_project_header({"format": FORMAT_ID, "version": 99})

    def test_vector_roundtrip(self) -> None:
        vps = [
            VectorPath((Point(0.0, 0.0), Point(1.0, 2.0)), pen_down=True),
            VectorPath((Point(3.0, 4.0),), pen_down=False),
        ]
        raw = serialize_vector_paths(vps)
        out = deserialize_vector_paths(raw)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].points, vps[0].points)
        self.assertEqual(out[0].pen_down, True)
        self.assertEqual(out[1].pen_down, False)

    def test_write_text_atomic_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "out.nc"
            write_text_atomic(p, "G0 X0\n")
            self.assertEqual(p.read_text(encoding="utf-8"), "G0 X0\n")

    def test_save_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.inkwps.json"
            save_project_file(
                p,
                title="测试",
                word_html="<p>a</p>",
                table_blob=self._TABLE_BLOB,
                slides=["<p>s</p>"],
                slides_master={},
                sketch_blob={},
                insert_vector=None,
            )
            d = load_project_file(p)
            self.assertEqual(d["title"], "测试")
            self.assertEqual(d["version"], FORMAT_VERSION)
            self.assertIn("word_html", d)
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(data["format"], FORMAT_ID)

    def test_sketch_paths_roundtrip_in_file(self) -> None:
        vps = [VectorPath((Point(0.0, 0.0), Point(1.0, 2.0)), pen_down=True)]
        sk = {"paths": serialize_vector_paths(vps)}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sk.inkwps.json"
            save_project_file(
                p,
                title="s",
                word_html="",
                table_blob=self._TABLE_BLOB,
                slides=[""],
                sketch_blob=sk,
                insert_vector=None,
            )
            raw = json.loads(p.read_text(encoding="utf-8"))
            self.assertIn("sketch", raw)
            self.assertEqual(len(raw["sketch"]["paths"]), 1)
            d = load_project_file(p)
            out = deserialize_vector_paths(d["sketch"]["paths"])
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0].points, vps[0].points)


if __name__ == "__main__":
    unittest.main()
