"""字体服务。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from inkscape_wps.core.hershey_jhf import jhf_to_char_glyphs
from inkscape_wps.core.types import Point, VectorPath


class FontService:
    """字体管理服务"""

    def __init__(self, font_directories: Optional[List[Path]] = None):
        self.font_directories = font_directories or []
        self._fonts: Dict[str, dict[str, Any]] = {}  # 字体名称 -> 字体数据
        self._font_cache: Dict[str, dict[str, Any]] = {}  # 缓存解析结果
        self._logger = logging.getLogger(__name__)

        # 添加默认字体目录
        self._add_default_font_directories()

    def _add_default_font_directories(self) -> None:
        """添加默认字体目录"""
        # 包内字体目录
        package_dir = Path(__file__).parent.parent.parent
        data_fonts_dir = package_dir / 'data' / 'fonts'
        if data_fonts_dir.exists():
            self.font_directories.append(data_fonts_dir)

        # 用户字体目录
        user_fonts_dir = Path.home() / '.config' / 'inkscape-wps' / 'fonts'
        if user_fonts_dir.exists():
            self.font_directories.append(user_fonts_dir)

    async def discover_fonts(self) -> List[str]:
        """发现可用字体"""
        font_names = []

        for font_dir in self.font_directories:
            if not font_dir.exists():
                continue

            try:
                for font_file in font_dir.glob('*.json'):
                    font_name = font_file.stem
                    if font_name not in self._fonts:
                        self._fonts[font_name] = {
                            'path': font_file,
                            'type': 'json',
                            'loaded': False
                        }
                        font_names.append(font_name)

                for font_file in font_dir.glob('*.jhf'):
                    font_name = font_file.stem
                    if font_name not in self._fonts:
                        self._fonts[font_name] = {
                            'path': font_file,
                            'type': 'jhf',
                            'loaded': False
                        }
                        font_names.append(font_name)

            except Exception as e:
                self._logger.error(f"扫描字体目录失败 {font_dir}: {e}")

        return font_names

    async def load_font(self, font_name: str) -> bool:
        """加载指定字体"""
        if font_name not in self._fonts:
            return False

        font_info = self._fonts[font_name]
        if font_info['loaded']:
            return True

        try:
            font_path = font_info['path']

            if font_info['type'] == 'json':
                with open(font_path, 'r', encoding='utf-8') as f:
                    font_data = json.load(f)

                # 解析JSON字体（假设是自定义格式）
                parsed_font = self._parse_custom_json_font(font_data)
                self._font_cache[font_name] = parsed_font

            elif font_info['type'] == 'jhf':
                self._font_cache[font_name] = self._parse_jhf_font(Path(font_path))

            font_info['loaded'] = True
            self._logger.info(f"字体加载成功: {font_name}")
            return True

        except Exception as e:
            self._logger.error(f"加载字体失败 {font_name}: {e}")
            return False

    async def get_character_paths(self, char: str, font_name: str,
                                scale: float = 1.0) -> List[VectorPath]:
        """获取字符的笔划路径"""
        if font_name not in self._fonts:
            return []

        # 确保字体已加载
        if not self._fonts[font_name]['loaded']:
            if not await self.load_font(font_name):
                return []

        font_data = self._font_cache.get(font_name)
        if not font_data:
            return []

        char_info = (font_data.get('characters') or {}).get(char)
        if not isinstance(char_info, dict):
            return []

        char_paths: List[VectorPath] = []
        for stroke in char_info.get('strokes', []):
            path: list[Point] = []
            for point_data in stroke:
                if isinstance(point_data, (list, tuple)) and len(point_data) >= 2:
                    x, y = point_data[0] * scale, point_data[1] * scale
                    path.append(Point(x, y))
            if len(path) >= 2:
                char_paths.append(VectorPath(tuple(path)))

        return char_paths

    def get_font_info(self, font_name: str) -> Optional[dict]:
        """获取字体信息"""
        if font_name not in self._fonts:
            return None

        font_info = self._fonts[font_name].copy()

        # 添加缓存的字体元数据
        if font_name in self._font_cache:
            cached_font = self._font_cache[font_name]
            font_info['metadata'] = cached_font.get('metadata', {})
            font_info['character_count'] = len(cached_font.get('characters', {}))

        return font_info

    def get_available_fonts(self) -> List[str]:
        """获取可用字体列表"""
        return list(self._fonts.keys())

    def get_character_set(self, font_name: str) -> List[str]:
        """获取字体的字符集"""
        if font_name not in self._fonts:
            return []

        # 如果字体未加载，返回空列表
        if not self._fonts[font_name]['loaded']:
            return []

        font_data = self._font_cache.get(font_name, {})
        return list(font_data.get('characters', {}).keys())

    async def merge_fonts(self, base_font: str, additional_font: str,
                         output_name: str) -> bool:
        """合并两个字体"""
        try:
            # 确保两个字体都已加载
            if not await self.load_font(base_font):
                return False
            if not await self.load_font(additional_font):
                return False

            base_data = self._font_cache[base_font].copy()
            additional_data = self._font_cache[additional_font]

            # 合并字符集
            if 'characters' in additional_data:
                if 'characters' not in base_data:
                    base_data['characters'] = {}

                base_data['characters'].update(additional_data['characters'])

            # 保存合并后的字体
            self._font_cache[output_name] = base_data
            self._fonts[output_name] = {
                'type': 'merged',
                'loaded': True,
                'source_fonts': [base_font, additional_font]
            }

            self._logger.info(f"字体合并成功: {base_font} + {additional_font} = {output_name}")
            return True

        except Exception as e:
            self._logger.error(f"字体合并失败: {e}")
            return False

    def create_font_preview(self, font_name: str, sample_text: str = "AaBbCc") -> dict:
        """创建字体预览数据"""
        if font_name not in self._fonts or not self._fonts[font_name]['loaded']:
            return {}

        font_data = self._font_cache.get(font_name, {})
        preview_data = {
            'font_name': font_name,
            'characters': {},
            'metadata': font_data.get('metadata', {}),
            'sample_paths': []
        }

        # 生成示例字符的路径
        for char in sample_text:
            if 'characters' in font_data and char in font_data['characters']:
                char_info = font_data['characters'][char]
                preview_data['characters'][char] = {
                    'width': char_info.get('width', 0),
                    'height': char_info.get('height', 0),
                    'stroke_count': len(char_info.get('strokes', []))
                }

        return preview_data

    async def export_font(self, font_name: str, output_path: Path) -> bool:
        """导出字体到文件"""
        if font_name not in self._font_cache:
            return False

        try:
            font_data = self._font_cache[font_name]

            # 导出为JSON格式
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(font_data, f, ensure_ascii=False, indent=2)

            self._logger.info(f"字体导出成功: {output_path}")
            return True

        except Exception as e:
            self._logger.error(f"字体导出失败: {e}")
            return False

    def clear_cache(self) -> None:
        """清除字体缓存"""
        self._font_cache.clear()
        for font_info in self._fonts.values():
            font_info['loaded'] = False

    def _parse_custom_json_font(self, font_data: dict) -> dict:
        """解析自定义JSON字体格式"""
        parsed = {
            'metadata': font_data.get('metadata', {}),
            'characters': {}
        }

        # 处理字符数据
        characters = font_data.get('characters', {})
        for char, char_data in characters.items():
            if isinstance(char_data, dict) and 'strokes' in char_data:
                # 转换笔画数据格式
                strokes = []
                for stroke in char_data['strokes']:
                    if isinstance(stroke, list):
                        # 确保每个笔画是点坐标的列表
                        converted_stroke = []
                        for point in stroke:
                            if isinstance(point, (list, tuple)) and len(point) >= 2:
                                converted_stroke.append((float(point[0]), float(point[1])))
                        # 至少需要两个点才能形成有效笔画
                        if len(converted_stroke) >= 2:
                            strokes.append(converted_stroke)

                if strokes:
                    parsed['characters'][char] = {
                        'strokes': strokes,
                        'width': char_data.get('width', 10.0),
                        'height': char_data.get('height', 10.0)
                    }

        return parsed

    def _parse_jhf_font(self, font_path: Path) -> dict:
        """解析 Hershey JHF 字体为统一缓存格式。"""
        glyphs, em_height = jhf_to_char_glyphs(font_path, em_height=10.0)
        parsed: dict[str, Any] = {
            'metadata': {
                'name': font_path.stem,
                'source': 'jhf',
                'em_height': em_height,
            },
            'characters': {},
        }
        for char, strokes in glyphs.items():
            flat_points = [pt for stroke in strokes for pt in stroke]
            if flat_points:
                xs = [float(x) for x, _y in flat_points]
                ys = [float(y) for _x, y in flat_points]
                width = max(xs) - min(xs)
                height = max(ys) - min(ys)
            else:
                width = 0.0
                height = 0.0
            parsed['characters'][char] = {
                'strokes': [
                    [[float(x), float(y)] for x, y in stroke]
                    for stroke in strokes
                ],
                'width': float(width),
                'height': float(height),
            }
        return parsed

    def get_cache_size(self) -> int:
        """获取缓存大小（字符数）"""
        total_chars = 0
        for font_data in self._font_cache.values():
            if 'characters' in font_data:
                total_chars += len(font_data['characters'])
        return total_chars
