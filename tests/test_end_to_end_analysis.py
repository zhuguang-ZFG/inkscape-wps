"""End-to-end integration tests for the code review analyzer."""

import pytest
from pathlib import Path
from code_review_analyzer.analyzer_coordinator import AnalyzerCoordinator
from code_review_analyzer.models import IssueSeverity, IssueCategory


@pytest.fixture
def project_with_issues(temp_project_dir):
    """Create a test project with various issues."""
    # Create a Python file with issues
    core_dir = temp_project_dir / "inkscape_wps" / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a file with code quality issues
    test_file = core_dir / "test_module.py"
    test_file.write_text('''
"""Test module with various issues."""

import logging

logger = logging.getLogger(__name__)

class TestClass:
    """Test class."""
    
    def method_one(self):
        """First method."""
        return 42
    
    def method_two(self):
        """Second method."""
        return 42
    
    async def async_method(self):
        """Async method without await."""
        return 42
    
    def log_message(self, msg):
        """Log a message."""
        logger.error(f"Error: {msg}")
''')
    
    # Create pyproject.toml with dependencies
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


def test_coordinator_initialization(temp_project_dir):
    """Test initializing the analyzer coordinator."""
    coordinator = AnalyzerCoordinator(temp_project_dir)
    assert coordinator.project_root == temp_project_dir
    assert coordinator.result is not None


def test_run_all_analyzers(project_with_issues):
    """Test running all analyzers."""
    coordinator = AnalyzerCoordinator(project_with_issues)
    result = coordinator.run_all_analyzers()
    
    assert result is not None
    assert hasattr(result, "issues")
    assert hasattr(result, "summary")
    
    # Verify summary
    summary = result.summary()
    assert "total_issues" in summary
    assert "critical" in summary
    assert "high" in summary
    assert "medium" in summary
    assert "low" in summary


def test_analyzer_finds_issues(project_with_issues):
    """Test that analyzers find issues."""
    coordinator = AnalyzerCoordinator(project_with_issues)
    result = coordinator.run_all_analyzers()
    
    # Should find at least some issues
    assert len(result.issues) > 0


def test_issue_categorization(project_with_issues):
    """Test that issues are properly categorized."""
    coordinator = AnalyzerCoordinator(project_with_issues)
    result = coordinator.run_all_analyzers()
    
    # Check that we have different categories
    categories = set()
    for issue in result.issues:
        categories.add(issue.category)
    
    # Should have at least one category
    assert len(categories) > 0
    
    # All categories should be valid
    for category in categories:
        assert isinstance(category, IssueCategory)


def test_issue_severity_levels(project_with_issues):
    """Test that issues have proper severity levels."""
    coordinator = AnalyzerCoordinator(project_with_issues)
    result = coordinator.run_all_analyzers()
    
    # Check severity levels
    severities = set()
    for issue in result.issues:
        severities.add(issue.severity)
    
    # All severities should be valid
    for severity in severities:
        assert isinstance(severity, IssueSeverity)


def test_generate_report(project_with_issues):
    """Test generating a report."""
    coordinator = AnalyzerCoordinator(project_with_issues)
    coordinator.run_all_analyzers()
    
    report = coordinator.generate_full_report()
    
    assert report is not None
    assert isinstance(report, str)
    assert len(report) > 0
    assert "inkscape_wps 代码审查分析报告" in report


def test_save_report(project_with_issues, tmp_path):
    """Test saving a report to file."""
    coordinator = AnalyzerCoordinator(project_with_issues)
    coordinator.run_all_analyzers()
    
    output_file = tmp_path / "report.md"
    coordinator.save_report(output_file)
    
    assert output_file.exists()
    content = output_file.read_text()
    assert len(content) > 0
    assert "inkscape_wps 代码审查分析报告" in content


def test_collect_results(project_with_issues):
    """Test collecting analysis results."""
    coordinator = AnalyzerCoordinator(project_with_issues)
    coordinator.run_all_analyzers()
    
    result = coordinator.collect_results()
    
    assert result is not None
    assert len(result.issues) > 0
    
    # Verify result structure
    summary = result.summary()
    assert summary["total_issues"] == len(result.issues)
