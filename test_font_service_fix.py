#!/usr/bin/env python3
"""字体服务修复验证测试。"""

import asyncio

from inkscape_wps.core.services.font_service import FontService


async def _run_font_service_checks() -> None:
    font_service = FontService()

    font_names = await font_service.discover_fonts()
    assert isinstance(font_names, list)

    if font_names:
        first_font = font_names[0]
        assert font_service.get_character_set(first_font) == []
        font_info = font_service.get_font_info(first_font)
        assert font_info is not None

    mock_font_data = {
        "metadata": {"name": "test_font"},
        "characters": {
            "A": {
                "strokes": [
                    [[0, 0], [5, 10], [10, 0]],
                    [[2, 6], [8, 6]],
                ],
                "width": 10,
                "height": 10,
            },
            "B": {
                "strokes": [
                    [[0, 0]],
                    [[0, 0], [0, 10]],
                ],
                "width": 10,
                "height": 10,
            },
        },
    }

    parsed = font_service._parse_custom_json_font(mock_font_data)
    assert len(parsed["characters"]["A"]["strokes"]) == 2
    assert len(parsed["characters"]["B"]["strokes"]) == 1


def test_font_service_fixes() -> None:
    asyncio.run(_run_font_service_checks())


if __name__ == "__main__":
    asyncio.run(_run_font_service_checks())
