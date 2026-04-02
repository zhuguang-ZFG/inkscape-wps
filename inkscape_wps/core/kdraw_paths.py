"""本机奎享 KDraw 安装路径探测（macOS / Windows 常见位置）。

.gfont 为二进制，本仓库不解析；用户需用 grblapp 的 ``export_kuixiang_from_kdraw`` 或官方流程导出 JSON 后由 ``HersheyFontMapper`` 加载。
"""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import List


def kdraw_app_gcode_fonts_dir() -> Path | None:
    """macOS：KDraw.app 自带字库目录。"""
    p = Path("/Applications/KDraw.app/Contents/app/gcodeFonts")
    if p.is_dir():
        return p
    return None


def kdraw_windows_gcode_fonts_dirs() -> List[Path]:
    out: List[Path] = []
    pf = os.environ.get("ProgramFiles(x86)") or os.environ.get("ProgramFiles")
    if pf:
        for base in (Path(pf) / "kdraw", Path(pf) / "KDraw"):
            g = base / "gcodeFonts"
            if g.is_dir():
                out.append(g)
    return out


def suggest_gcode_fonts_dirs() -> List[Path]:
    """返回可能存在的 gcodeFonts 目录（用于「在访达中打开」等）。"""
    found: List[Path] = []
    if platform.system() == "Darwin":
        d = kdraw_app_gcode_fonts_dir()
        if d:
            found.append(d)
    elif platform.system() == "Windows":
        found.extend(kdraw_windows_gcode_fonts_dirs())
    return found


def kdraw_default_properties_path() -> Path | None:
    """macOS：与 grblapp 文档一致的 default.properties 路径。"""
    p = Path("/Applications/KDraw.app/Contents/app/default.properties")
    if p.is_file():
        return p
    return None
