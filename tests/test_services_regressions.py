from __future__ import annotations

import asyncio

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.core.services.gcode_service import GCodeService
from inkscape_wps.core.services.preview_service import PreviewService
from inkscape_wps.core.types import Point, VectorPath


def test_gcode_service_path_helpers_work_with_vector_path_dataclass() -> None:
    service = GCodeService(MachineConfig())
    path1 = VectorPath((Point(0, 0), Point(3, 4)))
    path2 = VectorPath((Point(3, 4), Point(6, 8)))

    assert service._path_length(path1) == 5.0
    assert service._paths_adjacent(path1, path2) is True
    merged = service._merge_two_paths(path1, path2)
    assert [(p.x, p.y) for p in merged.points] == [(0, 0), (3, 4), (3, 4), (6, 8)]


def test_preview_service_simulation_reports_real_progress() -> None:
    async def run() -> None:
        service = PreviewService(MachineConfig())
        seen_progress: list[float] = []
        service.add_preview_callback(
            lambda payload: (
                seen_progress.append(payload["progress"]) if "progress" in payload else None
            )
        )
        service._current_gcode = "G0 X0 Y0\nG1 X1 Y1\n"
        await service.simulate_execution(speed_multiplier=0)
        assert seen_progress == [0.5, 1.0]

    asyncio.run(run())


def test_gcode_service_estimate_execution_time_uses_motion_and_feedrate() -> None:
    service = GCodeService(MachineConfig(draw_feed_rate=1200))
    gcode = "G0 X0 Y0\nG1 X3 Y4 F600\nG1 X6 Y8\n"
    assert service.estimate_execution_time(gcode) == 1.0


def test_gcode_service_optimize_paths_reads_config_via_attributes() -> None:
    cfg = MachineConfig(draw_feed_rate=1000)
    setattr(cfg, "min_path_length", 2.0)
    setattr(cfg, "merge_adjacent_paths", False)
    service = GCodeService(cfg)
    paths = [
        VectorPath((Point(0, 0), Point(1, 0))),
        VectorPath((Point(0, 0), Point(3, 4))),
    ]
    optimized = service.optimize_paths(paths)
    assert len(optimized) == 1
    assert [(p.x, p.y) for p in optimized[0].points] == [(0, 0), (3, 4)]


def test_gcode_service_generate_from_paths_uses_current_machine_config_fields() -> None:
    service = GCodeService(MachineConfig())
    paths = [VectorPath((Point(0, 0), Point(1, 1)))]

    gcode = service.generate_from_paths(paths, optimize=False)

    assert "G21" in gcode
    assert "M2" in gcode
