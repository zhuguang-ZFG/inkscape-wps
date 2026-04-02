"""写字机核心逻辑：无 GUI 依赖，可复用到移动端封装。"""

from .config import MachineConfig
from .config_io import load_machine_config, resolve_config_path, save_machine_config
from .coordinate_transform import transform_paths, transform_point
from .gcode import order_paths_nearest_neighbor, paths_to_gcode
from .grbl import GrblController, GrblSendError, verify_serial_responsive, wakeup_serial_port
from .serial_discovery import PortInfo, filter_ports, list_port_infos
from .hershey import HersheyFontMapper, map_document_lines
from .kdraw_paths import kdraw_app_gcode_fonts_dir, suggest_gcode_fonts_dirs
from .kuixiang_font import is_kuixiang_gfont_extract_payload, load_kuixiang_json_as_em_glyphs
from .types import Point, VectorPath, paths_bounding_box

__all__ = [
    "MachineConfig",
    "load_machine_config",
    "save_machine_config",
    "resolve_config_path",
    "transform_point",
    "transform_paths",
    "Point",
    "VectorPath",
    "paths_bounding_box",
    "HersheyFontMapper",
    "map_document_lines",
    "is_kuixiang_gfont_extract_payload",
    "load_kuixiang_json_as_em_glyphs",
    "suggest_gcode_fonts_dirs",
    "kdraw_app_gcode_fonts_dir",
    "order_paths_nearest_neighbor",
    "paths_to_gcode",
    "GrblController",
    "GrblSendError",
    "wakeup_serial_port",
    "verify_serial_responsive",
    "PortInfo",
    "list_port_infos",
    "filter_ports",
]
