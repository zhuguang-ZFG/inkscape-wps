"""位图 → SVG：通过外部开源工具 **Potrace** / **Autotrace** 子进程（与 grblapp/Inkscape 工作流类似）。

本模块不链接 Potrace 库，仅调用命令行；用户需自行安装（如 ``brew install potrace``、
Windows 下将 ``potrace.exe`` 加入 PATH）。可选依赖 **Pillow** 用于把常见图片转为 Potrace 可读的 BMP。

Potrace 为 GPL 许可；本仓库以子进程方式调用，不将其源码并入产品。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple


def _which(names: Tuple[str, ...]) -> Optional[str]:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _bitmap_to_bmp_mono(src: Path, bmp_out: Path, *, threshold: int = 180) -> None:
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError(
            "位图矢量化需要安装 Pillow：pip install Pillow"
        ) from e

    im = Image.open(src)
    im = im.convert("RGB")
    gray = im.convert("L")
    # 前景黑、背景白 → Potrace 默认跟踪黑色区域
    bw = gray.point(lambda p: 0 if p < threshold else 255, mode="1")
    max_side = 2048
    w, h = bw.size
    if max(w, h) > max_side:
        scale = max_side / float(max(w, h))
        nw = max(1, int(w * scale))
        nh = max(1, int(h * scale))
        bw = bw.resize((nw, nh), Image.Resampling.LANCZOS)
    bmp_out.parent.mkdir(parents=True, exist_ok=True)
    bw.save(bmp_out, format="BMP")


def trace_image_to_svg(
    image_path: Path | str,
    *,
    threshold: int = 180,
    turdsize: int = 2,
) -> str:
    """
    将位图转为 SVG 字符串。

    依次尝试：**potrace**（``potrace -s``）、**autotrace**（``autotrace --output-format svg``）。
    失败时抛出 ``RuntimeError``，提示安装方式。
    """
    src = Path(image_path)
    if not src.is_file():
        raise FileNotFoundError(str(src))

    potrace = _which(("potrace", "potrace.exe"))
    autotrace = _which(("autotrace", "autotrace.exe"))

    with tempfile.TemporaryDirectory(prefix="inkscape-wps-trace-") as td:
        tdir = Path(td)
        bmp = tdir / "trace_in.bmp"
        out_svg = tdir / "trace_out.svg"
        _bitmap_to_bmp_mono(src, bmp, threshold=threshold)

        if potrace:
            cmd = [
                potrace,
                "-s",
                "-o",
                str(out_svg),
                "-t",
                str(max(0, turdsize)),
                str(bmp),
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"potrace 执行失败：{e.stderr or e.stdout or e}"
                ) from e
            if not out_svg.is_file():
                raise RuntimeError("potrace 未生成 SVG 文件")
            return out_svg.read_text(encoding="utf-8", errors="replace")

        if autotrace:
            cmd = [
                autotrace,
                "-output-file",
                str(out_svg),
                "-output-format",
                "svg",
                str(bmp),
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"autotrace 执行失败：{e.stderr or e.stdout or e}"
                ) from e
            if not out_svg.is_file():
                raise RuntimeError("autotrace 未生成 SVG 文件")
            return out_svg.read_text(encoding="utf-8", errors="replace")

    raise RuntimeError(
        "未找到 potrace 或 autotrace 可执行文件。\n"
        "• macOS：brew install potrace\n"
        "• Windows：自 http://potrace.sourceforge.net 下载并加入 PATH\n"
        "亦可安装 autotrace（http://autotrace.sourceforge.net）。"
    )
