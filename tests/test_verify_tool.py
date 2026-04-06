"""Tests for the local verification entrypoint."""

from __future__ import annotations

from pathlib import Path

from tools import verify


def test_pytest_style_test_files_detects_pytest_features(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    pytest_file = tests_dir / "test_pytest_style.py"
    pytest_file.write_text(
        "import pytest\n\n@pytest.fixture\ndef sample():\n    return 1\n",
        encoding="utf-8",
    )
    unittest_file = tests_dir / "test_unittest_style.py"
    unittest_file.write_text(
        "import unittest\n\nclass Demo(unittest.TestCase):\n    pass\n",
        encoding="utf-8",
    )

    matches = verify._pytest_style_test_files(tmp_path)

    assert matches == [pytest_file]


def test_pytest_style_test_files_ignores_non_test_files(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    helper = tests_dir / "helper.py"
    helper.write_text("import pytest\n", encoding="utf-8")

    matches = verify._pytest_style_test_files(tmp_path)

    assert matches == []
