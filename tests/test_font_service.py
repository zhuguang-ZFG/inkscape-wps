from __future__ import annotations

import asyncio

from inkscape_wps.core.services.font_service import FontService
from inkscape_wps.core.types import VectorPath


def test_get_character_paths_returns_empty_for_missing_char() -> None:
    async def run() -> None:
        service = FontService(font_directories=[])
        service._fonts["demo"] = {"type": "json", "loaded": True, "path": None}
        service._font_cache["demo"] = {"characters": {"A": {"strokes": [[[0, 0], [1, 1]]]}}}
        assert await service.get_character_paths("Z", "demo") == []

    asyncio.run(run())


def test_get_character_paths_returns_scaled_vector_paths() -> None:
    async def run() -> None:
        service = FontService(font_directories=[])
        service._fonts["demo"] = {"type": "json", "loaded": True, "path": None}
        service._font_cache["demo"] = {
            "characters": {
                "A": {
                    "strokes": [
                        [[0, 0], [2, 3]],
                        [[4, 5]],
                    ]
                }
            }
        }

        paths = await service.get_character_paths("A", "demo", scale=2.0)
        assert len(paths) == 1
        assert isinstance(paths[0], VectorPath)
        assert [(p.x, p.y) for p in paths[0].points] == [(0.0, 0.0), (4.0, 6.0)]

    asyncio.run(run())


def test_parse_custom_json_font_stroke_counts() -> None:
    service = FontService(font_directories=[])
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
    parsed = service._parse_custom_json_font(mock_font_data)
    assert len(parsed["characters"]["A"]["strokes"]) == 2
    assert len(parsed["characters"]["B"]["strokes"]) == 1
