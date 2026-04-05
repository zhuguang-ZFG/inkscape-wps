"""Tests for report generator."""

from code_review_analyzer.models import AnalysisResult, Issue, IssueSeverity, IssueCategory
from code_review_analyzer.reporters.report_generator import ReportGenerator


def test_report_generator_initialization():
    """Test initializing a report generator."""
    result = AnalysisResult()
    generator = ReportGenerator(result)
    assert generator.result == result


def test_generate_empty_report():
    """Test generating an empty report."""
    result = AnalysisResult()
    generator = ReportGenerator(result)
    report = generator.generate()
    assert "inkscape_wps 代码审查分析报告" in report
    assert "摘要" in report


def test_generate_report_with_issues():
    """Test generating a report with issues."""
    result = AnalysisResult()
    issue = Issue(
        id="test_1",
        title="Test Issue",
        description="This is a test issue",
        category=IssueCategory.CODE_QUALITY,
        severity=IssueSeverity.MEDIUM,
        file_path="test.py",
        line_number=10,
        suggestion="Fix this issue"
    )
    result.add_issue(issue)
    
    generator = ReportGenerator(result)
    report = generator.generate()
    
    assert "Test Issue" in report
    assert "test.py" in report
    assert "Fix this issue" in report
