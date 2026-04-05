"""机器与文档配置：JSON / TOML 持久化，避免 QSettings。"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

import tomli_w

from .grbl_firmware_ref import GRBL_ESP32_DEFAULT_RX_BUFFER_SIZE

_log = logging.getLogger(__name__)


@dataclass
class MachineConfig:
    """与 Grbl_Esp32 custom_3axis_hr4988.h / CLOUD_WRITER_INTEGRATION.md 对齐。"""

    z_up_mm: float = 0.0
    z_down_mm: float = 5.0
    draw_feed_rate: int = 2000
    z_feed_rate: int = 300
    dwell_after_pen_down_s: float = 0.05
    dwell_after_pen_up_s: float = 0.03
    rapid_after_pen_up: bool = True
    grbl_buffer_target: int = 30  # 历史字段；流式发送时若未单独配置 rx 大小可从此迁移
    # 默认对齐 Grbl_Esp32 Serial.h 的 RX_BUFFER_SIZE（见 grbl_firmware_ref）
    grbl_rx_buffer_size: int = GRBL_ESP32_DEFAULT_RX_BUFFER_SIZE
    grbl_streaming: bool = False  # True 时在仍逐条等 ok 的前提下尽量填满固件缓冲
    grbl_line_timeout_s: float = 30.0

    # --- G-code 程序头/尾（写字机：G92 + 不换纸默认 M2）---
    gcode_use_g92: bool = True
    gcode_end_m30: bool = False
    # 抬落笔：z = G1 Z（默认）；m3m5 = M5 抬笔 / M3 S… 落笔（伺服笔等固件）
    gcode_pen_mode: str = "z"
    gcode_m3_s_value: int = 1000
    # 插入到 F 行之后、笔画之前 / 结尾抬笔之后、M2·M30 之前（每行一条，可含 [ESP…]）
    gcode_program_prefix: str = ""
    gcode_program_suffix: str = ""
    page_width_mm: float = 210.0
    page_height_mm: float = 297.0
    mm_per_pt: float = 1.0
    document_margin_mm: float = 15.0
    # 文档纵向像素 → 纸张 mm 时额外乘数，用于与物理纸长对齐标定（默认 1）
    layout_vertical_scale: float = 1.0

    # --- 坐标系：文档 mm（Y 向上）→ 机床/work ---
    coord_mirror_x: bool = False
    coord_mirror_y: bool = False
    coord_pivot_x_mm: float = 105.0
    coord_pivot_y_mm: float = 148.5
    coord_scale_x: float = 1.0
    coord_scale_y: float = 1.0
    coord_offset_x_mm: float = 0.0
    coord_offset_y_mm: float = 0.0

    # --- 串口 UI ---
    connection_mode: str = "serial"
    tcp_host: str = ""
    tcp_port: int = 23
    serial_show_bluetooth_only: bool = False

    # --- 单线字库（空字符串则使用包内 data/hershey_roman.json）---
    stroke_font_json_path: str = ""
    # 可选第二路 JSON/JHF：在主编译结果上合并字形（覆盖同码位），便于大包中文库与 ASCII 字库叠加
    stroke_font_merge_json_path: str = ""
    # 奎享导出 JSON 解析时的 font 单位→毫米系数（与 grblapp gfont_loader 默认一致）
    kuixiang_mm_per_unit: float = 0.01530

    # 单线字形编辑区行距系数（相对内置基准 1.45，见 StrokeLayoutEngine._leading_du）
    stroke_editor_line_spacing: float = 1.45
    # 文字页路径模式：stroke=单线雕刻；outline=视觉复刻（字体轮廓）
    word_render_mode: str = "stroke"
    # 表格页路径模式：stroke=单线雕刻；outline=视觉复刻（字体轮廓）
    table_render_mode: str = "stroke"
    # 演示页路径模式：stroke=单线雕刻；outline=视觉复刻（字体轮廓）
    slides_render_mode: str = "stroke"

    def to_json_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, d: Dict[str, Any]) -> MachineConfig:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        if "grbl_rx_buffer_size" not in filtered and "grbl_buffer_target" in d:
            try:
                filtered["grbl_rx_buffer_size"] = max(16, int(d["grbl_buffer_target"]))
            except (TypeError, ValueError) as e:
                _log.warning(
                    "忽略无效的 grbl_buffer_target=%r，未写入 grbl_rx_buffer_size：%s",
                    d.get("grbl_buffer_target"),
                    e,
                )
        return cls(**filtered)

    def save_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, path: Path) -> MachineConfig:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_json_dict(data)

    def save_toml(self, path: Path) -> None:
        path.write_text(tomli_w.dumps(self.to_json_dict()), encoding="utf-8")

    @classmethod
    def load_toml(cls, path: Path) -> MachineConfig:
        with path.open("rb") as f:
            data = tomllib.load(f)
        if not isinstance(data, dict):
            return cls()
        return cls.from_json_dict(data)
