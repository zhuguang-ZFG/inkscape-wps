"""
工程文件 JSON：文字 / 表格 / 演示 / 插入矢量 与标题。
不含机器配置，配置仍用 machine_config.toml。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from inkscape_wps.core.types import Point, VectorPath

FORMAT_ID = "inkscape-wps-project"
FORMAT_VERSION = 2


def validate_project_header(d: Dict[str, Any]) -> None:
    if d.get("format") != FORMAT_ID:
        raise ValueError("不是 inkscape-wps 工程文件")
    v = int(d.get("version", 0))
    if v not in (1, 2):
        raise ValueError(f"不支持的工程版本：{d.get('version')}")


def serialize_vector_paths(paths: List[VectorPath]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for vp in paths:
        out.append(
            {
                "pen_down": bool(vp.pen_down),
                "points": [[p.x, p.y] for p in vp.points],
            }
        )
    return out


def deserialize_vector_paths(data: List[Dict[str, Any]]) -> List[VectorPath]:
    paths: List[VectorPath] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        raw_pts = row.get("points") or []
        try:
            pts = tuple(Point(float(a[0]), float(a[1])) for a in raw_pts)
        except (TypeError, ValueError, IndexError):
            continue
        if len(pts) < 1:
            continue
        paths.append(VectorPath(pts, pen_down=bool(row.get("pen_down", True))))
    return paths


def save_project_file(
    path: Path | str,
    *,
    title: str,
    word_html: str,
    word_plain_text: str | None = None,
    table_blob: Dict[str, Any],
    slides: List[str],
    slides_master: Dict[str, Any] | None = None,
    sketch_blob: Dict[str, Any],
    insert_vector: Dict[str, Any] | None = None,
) -> None:
    payload: Dict[str, Any] = {
        "format": FORMAT_ID,
        "version": FORMAT_VERSION,
        "title": title,
        "word_html": word_html,
        "table": table_blob,
        "slides": slides,
        "slides_master": slides_master or {},
        "sketch": sketch_blob,
    }
    if word_plain_text is not None:
        payload["word_plain_text"] = str(word_plain_text)
    if insert_vector:
        payload["insert_vector"] = insert_vector
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    _atomic_write_text(Path(path), text)


def write_text_atomic(path: Path | str, text: str, *, encoding: str = "utf-8") -> None:
    """通用原子写文本（与工程保存相同策略，可供 G-code 导出等复用）。"""
    _atomic_write_text(Path(path), text, encoding=encoding)


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """先写临时文件再 replace，降低保存中断导致工程文件损坏的风险。"""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        suffix=".tmp",
        prefix=path.name + ".",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as f:
            f.write(text)
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.is_file():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def load_project_file(path: Path | str) -> Dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    d = json.loads(raw)
    if not isinstance(d, dict):
        raise ValueError("工程文件格式错误")
    validate_project_header(d)
    if "word_plain_text" not in d:
        raw_html = str(d.get("word_html", ""))
        text = raw_html.replace("<br/>", "\n").replace("<br>", "\n").replace("</p>", "\n")
        import re

        text = re.sub(r"<[^>]+>", "", text)
        d["word_plain_text"] = text.strip("\n")
    return d
