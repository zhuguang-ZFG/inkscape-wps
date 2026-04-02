#!/usr/bin/env python3
"""为 inkscape_wps/data/fonts 下非占位符的 .jhf 生成 stem.jhf.map.json。

上游 kamalmostafa/hershey-fonts 中部分 .jhf 每行索引为 12345，无法建映射，本脚本会跳过。
映射规则：文件内前 95 个有效行按顺序对应 ASCII 32–126（与 rowmans 等经典行序一致）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "inkscape_wps" / "data" / "fonts"
ASCII_PRINTABLE = "".join(chr(c) for c in range(32, 127))


def line_glyph_id(line: str) -> int | None:
    line = line.strip()
    if not line or line.startswith("12345"):
        return None
    m = re.match(r"(\d+)", line)
    return int(m.group(1)) if m else None


def build_map_for_jhf(path: Path) -> dict | None:
    ids: list[int] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        gid = line_glyph_id(ln)
        if gid is not None:
            ids.append(gid)
    if len(ids) < 95:
        return None
    by_index = {str(ids[i]): ASCII_PRINTABLE[i] for i in range(95)}
    return {"by_index": by_index}


def main() -> int:
    if not FONT_DIR.is_dir():
        print("missing", FONT_DIR, file=sys.stderr)
        return 1
    n = 0
    for jhf in sorted(FONT_DIR.glob("*.jhf")):
        data = build_map_for_jhf(jhf)
        if data is None:
            print("skip", jhf.name)
            continue
        out = jhf.with_name(jhf.stem + ".jhf.map.json")
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", out.name)
        n += 1
    print("done,", n, "maps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
