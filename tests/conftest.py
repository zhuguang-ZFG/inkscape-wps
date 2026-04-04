"""Pytest configuration and fixtures."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_project_structure(temp_project_dir):
    """Create a sample project structure for testing."""
    # Create core directory structure
    (temp_project_dir / "core").mkdir()
    (temp_project_dir / "core" / "services").mkdir()
    (temp_project_dir / "ui").mkdir()

    # Create sample files
    (temp_project_dir / "core" / "types.py").write_text("# types module\n")
    (temp_project_dir / "core" / "config.py").write_text("# config module\n")
    (temp_project_dir / "core" / "gcode.py").write_text("# gcode module\n")
    (temp_project_dir / "core" / "services" / "gcode_service.py").write_text(
        "# gcode_service module\n"
    )
    (temp_project_dir / "core" / "services" / "serial_service.py").write_text(
        "# serial_service module\n"
    )
    (temp_project_dir / "ui" / "main_window.py").write_text("# main_window module\n")

    return temp_project_dir
