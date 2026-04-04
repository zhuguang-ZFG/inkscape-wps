"""Hershey / 单线字形映射：仅标准库。支持内置、JSON、JHF、奎享导出 JSON（与 grblapp 格式兼容）。"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from .hershey_glyphs_builtin import build_builtin_glyphs
from .hershey_jhf import jhf_to_char_glyphs
from .kuixiang_font import is_kuixiang_gfont_extract_payload, load_kuixiang_json_as_em_glyphs
from .types import Point, VectorPath

_log = logging.getLogger(__name__)

# 内置字形坐标系的大致字高（用于与 TrueType 视觉对齐的比例基准）
BUILTIN_EM_HEIGHT_UNITS = 10.0

# 超过此大小的 JSON 延迟到首次排版再读盘，避免启动阻塞（奎享合并库常达数十 MB）
LAZY_JSON_BYTES = 400 * 1024


class HersheyFontMapper:
    """
    将文本映射为 List[VectorPath]。
    坐标为「文档平面」毫米：X 向右，Y 向上（与常见 CNC 一致，便于直接出 G-code）。
    调用方负责把 QTextEdit 的 Y 向下坐标转换为 Y 向上（见 ui 层）。
    """

    def __init__(
        self,
        font_path: Path | None = None,
        *,
        merge_font_path: Path | str | None = None,
        kuixiang_mm_per_unit: float = 0.01530,
    ) -> None:
        self._kuixiang_mm_per_unit = float(kuixiang_mm_per_unit)
        self._lock = threading.Lock()
        self._builtin: Dict[str, List[List[Tuple[float, float]]]] = {}
        self._glyphs: Dict[str, List[List[Tuple[float, float]]]] = {}
        self._em_height = BUILTIN_EM_HEIGHT_UNITS
        self._lazy_json_path: Path | None = None
        self._lazy_json_loaded = False
        self._lazy_merge_path: Path | None = None
        self._lazy_merge_loaded = False
        self._pending_small_merge: Path | None = None

        self._load_builtin_as_dict()

        if font_path is not None and font_path.is_file():
            suf = font_path.suffix.lower()
            if suf in (".jhf", ".hf"):
                self._load_jhf(font_path)
            elif suf == ".json":
                try:
                    big = font_path.stat().st_size >= LAZY_JSON_BYTES
                except OSError:
                    big = False
                if big:
                    self._lazy_json_path = font_path
                else:
                    self._apply_json_file(font_path)
            # 未知扩展名：保持内置

        mp = None
        if merge_font_path is not None and str(merge_font_path).strip():
            mp = Path(merge_font_path).expanduser()
        if mp is not None and mp.is_file():
            self._attach_merge_path(mp)

    def set_kuixiang_mm_per_unit(self, value: float) -> None:
        """
        更新奎享 JSON 解析时的 font 单位→毫米系数。
        已载入内存的奎享字形不会自动重算，需重开字库或重启应用。
        """
        self._kuixiang_mm_per_unit = float(value)

    def _load_builtin_as_dict(self) -> None:
        built = build_builtin_glyphs()
        self._builtin = {k: [list(poly) for poly in v] for k, v in built.items()}
        self._glyphs = {k: [list(poly) for poly in v] for k, v in self._builtin.items()}
        self._em_height = BUILTIN_EM_HEIGHT_UNITS

    def _apply_json_file(self, path: Path) -> None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as e:
            _log.error("读取字库文件失败：%s (%s)", path, e)
            raise
        except json.JSONDecodeError as e:
            _log.error("字库 JSON 解析失败：%s (%s)", path, e)
            raise
        self._apply_json_payload(raw, path_hint=path)

    def _apply_json_payload(self, raw: dict, *, path_hint: Path | None = None) -> None:
        del path_hint  # 预留日志
        merged = {k: [list(poly) for poly in v] for k, v in self._builtin.items()}
        if is_kuixiang_gfont_extract_payload(raw):
            extra = load_kuixiang_json_as_em_glyphs(
                raw,
                mm_per_unit=self._kuixiang_mm_per_unit,
                target_em=BUILTIN_EM_HEIGHT_UNITS,
            )
            for ch, polys in extra.items():
                merged[ch] = [list(p) for p in polys]
            self._glyphs = merged
            self._em_height = BUILTIN_EM_HEIGHT_UNITS
            return
        self._em_height = float(raw.get("em_height", BUILTIN_EM_HEIGHT_UNITS))
        glyphs = raw.get("glyphs", {})
        for k, v in glyphs.items():
            merged[str(k)] = v
        self._glyphs = merged

    def _attach_merge_path(self, mp: Path) -> None:
        try:
            big = mp.stat().st_size >= LAZY_JSON_BYTES
        except OSError:
            return
        suf = mp.suffix.lower()
        if suf not in (".json",):
            return
        if big:
            self._lazy_merge_path = mp
            return
        if self._lazy_json_path is not None and not self._lazy_json_loaded:
            self._pending_small_merge = mp
        else:
            self._merge_json_file(mp)

    def _merge_json_file(self, path: Path) -> None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as e:
            _log.error("读取合并字库失败：%s (%s)", path, e)
            raise
        except json.JSONDecodeError as e:
            _log.error("合并字库 JSON 无效：%s (%s)", path, e)
            raise
        if not isinstance(raw, dict):
            return
        if is_kuixiang_gfont_extract_payload(raw):
            extra = load_kuixiang_json_as_em_glyphs(
                raw,
                mm_per_unit=self._kuixiang_mm_per_unit,
                target_em=BUILTIN_EM_HEIGHT_UNITS,
            )
            for ch, polys in extra.items():
                self._glyphs[ch] = [list(p) for p in polys]
            return
        glyphs = raw.get("glyphs", {})
        if not isinstance(glyphs, dict):
            return
        for k, v in glyphs.items():
            self._glyphs[str(k)] = v

    def _ensure_lazy_json(self) -> None:
        with self._lock:
            if self._lazy_json_path is not None and not self._lazy_json_loaded:
                self._apply_json_file(self._lazy_json_path)
                self._lazy_json_loaded = True
            if self._pending_small_merge is not None:
                self._merge_json_file(self._pending_small_merge)
                self._pending_small_merge = None
            if self._lazy_merge_path is not None and not self._lazy_merge_loaded:
                self._merge_json_file(self._lazy_merge_path)
                self._lazy_merge_loaded = True

    def preload_background(self) -> None:
        """在后台线程加载延迟 JSON，缩短首次排版等待（守护线程）。"""
        if self._lazy_json_path is None or self._lazy_json_loaded:
            return

        def _run() -> None:
            self._ensure_lazy_json()

        threading.Thread(target=_run, daemon=True, name="font-json-preload").start()

    def _load_jhf(self, path: Path) -> None:
        merged = {k: [list(poly) for poly in v] for k, v in self._builtin.items()}
        try:
            glyphs, em = jhf_to_char_glyphs(path, em_height=BUILTIN_EM_HEIGHT_UNITS)
        except OSError as e:
            _log.warning("加载 JHF 失败，保留内置字形：%s (%s)", path, e)
            return
        if not glyphs:
            return
        for ch, polys in glyphs.items():
            merged[ch] = [list(p) for p in polys]
        self._glyphs = merged
        self._em_height = float(em)

    @staticmethod
    def export_builtin_json(path: Path) -> None:
        """将内置字形写入 JSON，便于替换或外置编辑。"""
        built = build_builtin_glyphs()
        payload = {
            "em_height": BUILTIN_EM_HEIGHT_UNITS,
            "glyphs": {k: v for k, v in built.items()},
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _glyph_for_char(self, ch: str) -> List[List[Tuple[float, float]]]:
        self._ensure_lazy_json()
        if ch in self._glyphs:
            return self._glyphs[ch]
        if ch.upper() in self._glyphs:
            return self._glyphs[ch.upper()]
        return self._glyphs.get(" ", [])

    def has_glyph(self, ch: str) -> bool:
        self._ensure_lazy_json()
        return ch in self._glyphs or ch.upper() in self._glyphs

    def missing_text_chars(self, text: str) -> List[str]:
        self._ensure_lazy_json()
        missing: List[str] = []
        seen: set[str] = set()
        for ch in text:
            if ch.isspace() or ch in seen:
                continue
            if self.has_glyph(ch):
                continue
            seen.add(ch)
            missing.append(ch)
        return missing

    def estimate_advances(
        self,
        text: str,
        font_size_pt: float,
        *,
        mm_per_pt: float = 1.0,
        reference_ascent_pt: float | None = None,
    ) -> List[float]:
        """估算每个字符的前进宽度（与 map_line 使用同一比例体系）。"""
        adv, _asc, _desc = self.estimate_advances_and_vertical_metrics(
            text,
            font_size_pt,
            mm_per_pt=mm_per_pt,
            reference_ascent_pt=reference_ascent_pt,
        )
        return adv

    def estimate_advances_and_vertical_metrics(
        self,
        text: str,
        font_size_pt: float,
        *,
        mm_per_pt: float = 1.0,
        reference_ascent_pt: float | None = None,
    ) -> Tuple[List[float], float, float]:
        """估算每字符宽度，以及文本对应的上伸/下伸量（相对基线，单位与 map_line 一致）。"""
        self._ensure_lazy_json()
        if self._em_height <= 0:
            return [font_size_pt * 0.6 for _ in text], font_size_pt * 0.8, font_size_pt * 0.2
        unit = self._scale_mm_per_pt(font_size_pt, reference_ascent_pt)
        scale = unit * mm_per_pt * (font_size_pt / self._em_height)
        fallback = (6.5 / BUILTIN_EM_HEIGHT_UNITS) * font_size_pt * mm_per_pt * unit
        out: List[float] = []
        min_y: float | None = None
        max_y: float | None = None
        for ch in text:
            polys = self._glyph_for_char(ch)
            if not polys:
                out.append(fallback * 0.6)
                continue
            min_x: float | None = None
            max_x: float | None = None
            for poly in polys:
                for px, py in poly:
                    min_x = px if min_x is None else min(min_x, px)
                    max_x = px if max_x is None else max(max_x, px)
                    min_y = py if min_y is None else min(min_y, py)
                    max_y = py if max_y is None else max(max_y, py)
            if min_x is None or max_x is None:
                out.append(fallback)
                continue
            w = max(1.0, (max_x - min_x) + 1.2) * scale
            out.append(max(0.5, w))
        if min_y is None or max_y is None:
            ascent = font_size_pt * 0.82
            descent = font_size_pt * 0.18
        else:
            ascent = max(1.0, max_y * scale)
            descent = max(1.0, -min_y * scale if min_y < 0 else 0.22 * font_size_pt)
        return out, ascent, descent

    def map_line(
        self,
        text: str,
        origin_x_mm: float,
        baseline_y_mm: float,
        font_size_pt: float,
        *,
        mm_per_pt: float = 1.0,
        reference_ascent_pt: float | None = None,
        advance_per_char_mm: float | None = None,
        per_char_advances_mm: Sequence[float] | None = None,
    ) -> List[VectorPath]:
        """
        将一行文本转为路径。
        - font_size_pt: 编辑器字号（点）
        - reference_ascent_pt: 可选，TrueType 的 ascent（点），
          用于更精细的视觉补偿；缺省则按 em 框缩放
        - advance_per_char_mm: 可选，强制统一字符间距（mm）；
          与 per_char_advances_mm 互斥优先后者
        - per_char_advances_mm: 可选，与 QTextLayout 字宽一致的长度须等于 len(text)
        """
        self._ensure_lazy_json()
        if self._em_height <= 0:
            raise ValueError("em_height 必须为正")

        unit = self._scale_mm_per_pt(font_size_pt, reference_ascent_pt)
        scale = unit * mm_per_pt * (font_size_pt / self._em_height)

        paths: List[VectorPath] = []
        x_cursor = origin_x_mm
        default_adv = (6.5 / BUILTIN_EM_HEIGHT_UNITS) * font_size_pt * mm_per_pt * unit
        use_layout_adv = (
            per_char_advances_mm is not None and len(per_char_advances_mm) == len(text)
        )

        for i, ch in enumerate(text):
            polylines = self._glyph_for_char(ch)
            if use_layout_adv:
                adv = per_char_advances_mm[i]
            else:
                adv = advance_per_char_mm if advance_per_char_mm is not None else default_adv
            if not polylines:
                x_cursor += adv * 0.6
                continue
            for poly in polylines:
                if len(poly) < 2:
                    if len(poly) == 1:
                        pt = poly[0]
                        paths.append(
                            VectorPath(
                                (
                                    Point(x_cursor + pt[0] * scale, baseline_y_mm + pt[1] * scale),
                                    Point(x_cursor + pt[0] * scale, baseline_y_mm + pt[1] * scale),
                                )
                            )
                        )
                    continue
                pts = tuple(
                    Point(x_cursor + px * scale, baseline_y_mm + py * scale) for px, py in poly
                )
                paths.append(VectorPath(pts))
            x_cursor += adv
        return paths

    def _scale_mm_per_pt(self, font_size_pt: float, reference_ascent_pt: float | None) -> float:
        """产品约定：默认 1 pt ≈ 1 mm 书写高度（可在 MachineConfig.mm_per_pt 覆盖，由 UI 传入）。"""
        del font_size_pt
        if reference_ascent_pt and reference_ascent_pt > 0:
            return 1.0 * (reference_ascent_pt / self._em_height)
        return 1.0


def map_document_lines(
    mapper: HersheyFontMapper,
    lines: Sequence[Tuple],
    *,
    mm_per_pt: float = 1.0,
) -> List[VectorPath]:
    """
    批量映射多行。每行元组可为：
    - (text, origin_x_mm, baseline_y_mm, font_size_pt)
    - 以上 + reference_ascent_pt
    - 以上 + per_char_advances_mm（tuple/list，长度须等于 len(text)）
    """
    out: List[VectorPath] = []
    for row in lines:
        if len(row) == 4:
            text, ox, by, fs = row
            ref_a: float | None = None
            advs = None
        elif len(row) == 5:
            text, ox, by, fs, ref_a = row  # type: ignore[misc]
            advs = None
        elif len(row) == 6:
            text, ox, by, fs, ref_a, advs = row  # type: ignore[misc]
        else:
            continue
        out.extend(
            mapper.map_line(
                text,
                ox,
                by,
                fs,
                mm_per_pt=mm_per_pt,
                reference_ascent_pt=ref_a,
                per_char_advances_mm=advs,
            )
        )
    return out
