"""工程文件 JSON：文字 / 表格 / 演示 / 手绘 与标题（不含机器配置，配置仍用 machine_config.toml）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

FORMAT_ID = "inkscape-wps-project"
FORMAT_VERSION = 1


def validate_project_header(d: Dict[str, Any]) -> None:
    if d.get("format") != FORMAT_ID:
        raise ValueError("不是 inkscape-wps 工程文件")
    if int(d.get("version", 0)) != FORMAT_VERSION:
        raise ValueError(f"不支持的工程版本：{d.get('version')}")


def save_project_file(
    path: Path | str,
    *,
    title: str,
    word_html: str,
    table_blob: Dict[str, Any],
    slides: List[str],
    sketch_blob: Dict[str, Any],
) -> None:
    payload = {
        "format": FORMAT_ID,
        "version": FORMAT_VERSION,
        "title": title,
        "word_html": word_html,
        "table": table_blob,
        "slides": slides,
        "sketch": sketch_blob,
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project_file(path: Path | str) -> Dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    d = json.loads(raw)
    if not isinstance(d, dict):
        raise ValueError("工程文件格式错误")
    validate_project_header(d)
    return d
