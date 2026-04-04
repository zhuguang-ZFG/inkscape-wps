"""Tests for data models."""

from code_review_analyzer.models import (
    AnalysisResult,
    FullAnalysisResult,
    Issue,
    IssueCategory,
    IssueSeverity,
)


class TestIssueSeverity:
    """Tests for IssueSeverity enum."""

    def test_severity_values(self):
        """Test that all severity levels are defined."""
        assert IssueSeverity.CRITICAL.value == "critical"
        assert IssueSeverity.HIGH.value == "high"
        assert IssueSeverity.MEDIUM.value == "medium"
        assert IssueSeverity.LOW.value == "low"


class TestIssueCategory:
    """Tests for IssueCategory enum."""

    def test_category_values(self):
        """Test that all categories are defined."""
        assert IssueCategory.RUNTIME_CRASH.value == "runtime_crash"
        assert IssueCategory.ORPHANED_CODE.value == "orphaned_code"
        assert IssueCategory.DESIGN_PROBLEM.value == "design_problem"
        assert IssueCategory.CODE_QUALITY.value == "code_quality"
        assert IssueCategory.DEPENDENCY.value == "dependency"


class TestIssue:
    """Tests for Issue model."""

    def test_issue_creation(self):
        """Test creating an issue."""
        issue = Issue(
            id="issue_001",
            title="Test Issue",
            description="This is a test issue",
            severity=IssueSeverity.CRITICAL,
            category=IssueCategory.RUNTIME_CRASH,
            location="test.py:10",
            impact="Application crash",
            suggestion="Fix the bug",
        )
        assert issue.id == "issue_001"
        assert issue.title == "Test Issue"
        assert issue.severity == IssueSeverity.CRITICAL
        assert issue.category == IssueCategory.RUNTIME_CRASH

    def test_issue_string_representation(self):
        """Test string representation of issue."""
        issue = Issue(
            id="issue_001",
            title="Test Issue",
            description="This is a test issue",
            severity=IssueSeverity.CRITICAL,
            category=IssueCategory.RUNTIME_CRASH,
            location="test.py:10",
            impact="Application crash",
            suggestion="Fix the bug",
        )
        assert "[CRITICAL]" in str(issue)
        assert "Test Issue" in str(issue)
        assert "test.py:10" in str(issue)

    def test_issue_with_tags(self):
        """Test issue with tags."""
        issue = Issue(
            id="issue_001",
            title="Test Issue",
            description="This is a test issue",
            severity=IssueSeverity.HIGH,
            category=IssueCategory.DESIGN_PROBLEM,
            location="test.py:10",
            impact="Design flaw",
            suggestion="Refactor",
            tags=["refactoring", "architecture"],
        )
        assert "refactoring" in issue.tags
        assert "architecture" in issue.tags


class TestAnalysisResult:
    """Tests for AnalysisResult model."""

    def test_analysis_result_creation(self):
        """Test creating an analysis result."""
        result = AnalysisResult(analyzer_name="TestAnalyzer")
        assert result.analyzer_name == "TestAnalyzer"
        assert len(result.issues) == 0
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_add_issue(self):
        """Test adding an issue to result."""
        result = AnalysisResult(analyzer_name="TestAnalyzer")
        issue = Issue(
            id="issue_001",
            title="Test Issue",
            description="This is a test issue",
            severity=IssueSeverity.CRITICAL,
            category=IssueCategory.RUNTIME_CRASH,
            location="test.py:10",
            impact="Application crash",
            suggestion="Fix the bug",
        )
        result.add_issue(issue)
        assert result.issue_count() == 1
        assert result.has_issues()

    def test_add_error(self):
        """Test adding an error message."""
        result = AnalysisResult(analyzer_name="TestAnalyzer")
        result.add_error("Test error")
        assert len(result.errors) == 1
        assert "Test error" in result.errors

    def test_add_warning(self):
        """Test adding a warning message."""
        result = AnalysisResult(analyzer_name="TestAnalyzer")
        result.add_warning("Test warning")
        assert len(result.warnings) == 1
        assert "Test warning" in result.warnings


class TestFullAnalysisResult:
    """Tests for FullAnalysisResult model."""

    def test_full_analysis_result_creation(self):
        """Test creating a full analysis result."""
        result = FullAnalysisResult()
        assert result.total_issues == 0
        assert result.critical_issues == 0
        assert result.high_issues == 0

    def test_add_result_with_issues(self):
        """Test adding analyzer results."""
        full_result = FullAnalysisResult()
        analyzer_result = AnalysisResult(analyzer_name="TestAnalyzer")

        issue1 = Issue(
            id="issue_001",
            title="Critical Issue",
            description="This is critical",
            severity=IssueSeverity.CRITICAL,
            category=IssueCategory.RUNTIME_CRASH,
            location="test.py:10",
            impact="Crash",
            suggestion="Fix",
        )
        issue2 = Issue(
            id="issue_002",
            title="High Issue",
            description="This is high",
            severity=IssueSeverity.HIGH,
            category=IssueCategory.DESIGN_PROBLEM,
            location="test.py:20",
            impact="Design flaw",
            suggestion="Refactor",
        )

        analyzer_result.add_issue(issue1)
        analyzer_result.add_issue(issue2)
        full_result.add_result(analyzer_result)

        assert full_result.total_issues == 2
        assert full_result.critical_issues == 1
        assert full_result.high_issues == 1

    def test_get_issues_by_severity(self):
        """Test filtering issues by severity."""
        full_result = FullAnalysisResult()
        analyzer_result = AnalysisResult(analyzer_name="TestAnalyzer")

        issue1 = Issue(
            id="issue_001",
            title="Critical Issue",
            description="This is critical",
            severity=IssueSeverity.CRITICAL,
            category=IssueCategory.RUNTIME_CRASH,
            location="test.py:10",
            impact="Crash",
            suggestion="Fix",
        )
        issue2 = Issue(
            id="issue_002",
            title="High Issue",
            description="This is high",
            severity=IssueSeverity.HIGH,
            category=IssueCategory.DESIGN_PROBLEM,
            location="test.py:20",
            impact="Design flaw",
            suggestion="Refactor",
        )

        analyzer_result.add_issue(issue1)
        analyzer_result.add_issue(issue2)
        full_result.add_result(analyzer_result)

        critical_issues = full_result.get_issues_by_severity(IssueSeverity.CRITICAL)
        assert len(critical_issues) == 1
        assert critical_issues[0].id == "issue_001"

    def test_get_issues_by_category(self):
        """Test filtering issues by category."""
        full_result = FullAnalysisResult()
        analyzer_result = AnalysisResult(analyzer_name="TestAnalyzer")

        issue1 = Issue(
            id="issue_001",
            title="Runtime Issue",
            description="This is runtime",
            severity=IssueSeverity.CRITICAL,
            category=IssueCategory.RUNTIME_CRASH,
            location="test.py:10",
            impact="Crash",
            suggestion="Fix",
        )
        issue2 = Issue(
            id="issue_002",
            title="Design Issue",
            description="This is design",
            severity=IssueSeverity.HIGH,
            category=IssueCategory.DESIGN_PROBLEM,
            location="test.py:20",
            impact="Design flaw",
            suggestion="Refactor",
        )

        analyzer_result.add_issue(issue1)
        analyzer_result.add_issue(issue2)
        full_result.add_result(analyzer_result)

        runtime_issues = full_result.get_issues_by_category(
            IssueCategory.RUNTIME_CRASH
        )
        assert len(runtime_issues) == 1
        assert runtime_issues[0].id == "issue_001"
