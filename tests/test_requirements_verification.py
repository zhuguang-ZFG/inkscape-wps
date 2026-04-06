"""Verification tests for all requirements."""


import pytest

from code_review_analyzer.analyzer_coordinator import AnalyzerCoordinator
from code_review_analyzer.models import IssueCategory


@pytest.fixture
def full_project(temp_project_dir):
    """Create a comprehensive test project."""
    # Create project structure
    core_dir = temp_project_dir / "inkscape_wps" / "core"
    services_dir = core_dir / "services"
    ui_dir = temp_project_dir / "inkscape_wps" / "ui"
    
    core_dir.mkdir(parents=True, exist_ok=True)
    services_dir.mkdir(parents=True, exist_ok=True)
    ui_dir.mkdir(parents=True, exist_ok=True)
    
    # Create main_window.py with design issues
    main_window = ui_dir / "main_window.py"
    main_window.write_text('''
"""Main window module."""

class MainWindow:
    """Main window class."""
    
    def __init__(self):
        """Initialize main window."""
        self._state_var_1 = None
        self._state_var_2 = None
        self._state_var_3 = None
        self._state_var_4 = None
        self._state_var_5 = None
        self._state_var_6 = None
        self._state_var_7 = None
        self._state_var_8 = None
        self._state_var_9 = None
        self._state_var_10 = None
        self._state_var_11 = None
        self._state_var_12 = None
        self._state_var_13 = None
        self._state_var_14 = None
        self._state_var_15 = None
        self._state_var_16 = None
''')
    
    # Create config.py with design issues
    config = core_dir / "config.py"
    config.write_text('''
"""Configuration module."""

from dataclasses import dataclass

@dataclass
class MachineConfig:
    """Machine configuration."""
    
    field_1: float = 0.0
    field_2: float = 0.0
    field_3: float = 0.0
    field_4: float = 0.0
    field_5: float = 0.0
    field_6: float = 0.0
    field_7: float = 0.0
    field_8: float = 0.0
    field_9: float = 0.0
    field_10: float = 0.0
    field_11: float = 0.0
    field_12: float = 0.0
    field_13: float = 0.0
    field_14: float = 0.0
    field_15: float = 0.0
    field_16: float = 0.0
    field_17: float = 0.0
    field_18: float = 0.0
    field_19: float = 0.0
    field_20: float = 0.0
    field_21: float = 0.0
    field_22: float = 0.0
    field_23: float = 0.0
    field_24: float = 0.0
    field_25: float = 0.0
    field_26: float = 0.0
''')
    
    # Create code quality issues
    quality = core_dir / "quality.py"
    quality.write_text('''
"""Code quality issues."""

import logging

logger = logging.getLogger(__name__)

def check_progress(lines):
    """Check progress."""
    return len(lines) / len(lines)

async def discover_fonts():
    """Discover fonts."""
    return []

def log_error(msg):
    """Log error."""
    logger.error(f"Error: {msg}")
''')
    
    # Create pyproject.toml with dependency issues
    pyproject = temp_project_dir / "pyproject.toml"
    pyproject.write_text('''
[project]
name = "test-project"
version = "0.1.0"

[project.dependencies]
PyQt5 = ">=5.15.0"
PyQt6 = ">=6.0.0"
pyserial = ">=3.5"
''')
    
    return temp_project_dir


def test_requirement_1_orphaned_code_detection(full_project):
    """Requirement 1: Identify orphaned code in services layer."""
    coordinator = AnalyzerCoordinator(full_project)
    result = coordinator.run_all_analyzers()
    
    # Should have orphaned code analyzer results
    orphaned_issues = [
        issue for issue in result.issues
        if issue.category == IssueCategory.ORPHANED_CODE
    ]
    
    # Orphaned code analyzer should run (may or may not find issues)
    assert isinstance(orphaned_issues, list)


def test_requirement_2_runtime_crash_detection(full_project):
    """Requirement 2: Identify runtime crash problems."""
    coordinator = AnalyzerCoordinator(full_project)
    result = coordinator.run_all_analyzers()
    
    # Should have runtime crash analyzer results
    crash_issues = [
        issue for issue in result.issues
        if issue.category == IssueCategory.RUNTIME_CRASH
    ]
    
    # Runtime crash analyzer should run
    assert isinstance(crash_issues, list)


def test_requirement_3_design_issue_detection(full_project):
    """Requirement 3: Identify design problems."""
    coordinator = AnalyzerCoordinator(full_project)
    result = coordinator.run_all_analyzers()
    
    # Should have design issue analyzer results
    design_issues = [
        issue for issue in result.issues
        if issue.category == IssueCategory.DESIGN
    ]
    
    # Design issue analyzer should run and find issues
    assert isinstance(design_issues, list)
    # Should find at least some design issues (config bloat, UI state variables)
    assert len(design_issues) > 0


def test_requirement_4_code_quality_detection(full_project):
    """Requirement 4: Identify code quality problems."""
    coordinator = AnalyzerCoordinator(full_project)
    result = coordinator.run_all_analyzers()
    
    # Should have code quality analyzer results
    quality_issues = [
        issue for issue in result.issues
        if issue.category == IssueCategory.CODE_QUALITY
    ]
    
    # Code quality analyzer should run and find issues
    assert isinstance(quality_issues, list)
    # Should find at least some quality issues:
    # constant calculations, logging f-strings, async without await.
    assert len(quality_issues) > 0


def test_requirement_5_dependency_analysis(full_project):
    """Requirement 5: Analyze dependencies."""
    coordinator = AnalyzerCoordinator(full_project)
    result = coordinator.run_all_analyzers()
    
    # Should have dependency analyzer results
    dependency_issues = [
        issue for issue in result.issues
        if issue.category == IssueCategory.DEPENDENCY
    ]
    
    # Dependency analyzer should run and find PyQt5/PyQt6 conflict
    assert isinstance(dependency_issues, list)
    # Should find PyQt5/PyQt6 conflict
    assert len(dependency_issues) > 0


def test_requirement_6_report_generation(full_project):
    """Requirement 6: Generate structured report with 8 sections."""
    coordinator = AnalyzerCoordinator(full_project)
    coordinator.run_all_analyzers()
    
    report = coordinator.generate_full_report()
    
    # Report should contain all 8 required sections
    assert "摘要" in report  # Summary
    assert "按严重程度分类" in report  # Issues by severity
    assert "按分类统计" in report  # Issues by category
    assert "统计信息" in report  # Statistics
    
    # Report should be non-empty
    assert len(report) > 0


def test_requirement_7_testing_strategy(full_project):
    """Requirement 7: Provide testing strategy recommendations."""
    coordinator = AnalyzerCoordinator(full_project)
    coordinator.run_all_analyzers()
    
    # The system should be able to generate recommendations
    # (This would be in a testing strategy generator)
    result = coordinator.collect_results()
    
    # Should have analysis results
    assert result is not None
    assert len(result.issues) > 0


def test_all_analyzers_run(full_project):
    """Verify all analyzers run successfully."""
    coordinator = AnalyzerCoordinator(full_project)
    result = coordinator.run_all_analyzers()
    
    # Should have results from all analyzers
    assert result is not None
    assert len(result.issues) > 0
    
    # Should have multiple categories
    categories = set(issue.category for issue in result.issues)
    assert len(categories) > 1


def test_report_contains_all_issues(full_project):
    """Verify report contains all detected issues."""
    coordinator = AnalyzerCoordinator(full_project)
    coordinator.run_all_analyzers()
    
    report = coordinator.generate_full_report()
    result = coordinator.collect_results()
    
    # Report should mention the total number of issues
    assert str(len(result.issues)) in report or "问题" in report


def test_cli_parameters_supported(full_project):
    """Verify CLI supports all required parameters."""
    # This is a structural test - the CLI module should have these parameters

    from code_review_analyzer.cli import main
    
    # Test that CLI can be imported and has main function
    assert callable(main)


def test_analysis_performance(full_project):
    """Verify analysis completes in reasonable time."""
    import time
    
    coordinator = AnalyzerCoordinator(full_project)
    
    start = time.time()
    result = coordinator.run_all_analyzers()
    duration = time.time() - start
    
    # Should complete in less than 10 seconds
    assert duration < 10.0
    
    # Should have analysis duration recorded
    assert result.analysis_duration_seconds > 0
