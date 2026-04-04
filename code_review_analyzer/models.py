"""Data models for code review analysis."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class IssueSeverity(Enum):
    """Severity levels for issues."""

    CRITICAL = "critical"  # Runtime crashes
    HIGH = "high"  # Design problems
    MEDIUM = "medium"  # Code quality issues
    LOW = "low"  # Minor issues


class IssueCategory(Enum):
    """Categories of issues."""

    RUNTIME_CRASH = "runtime_crash"
    ORPHANED_CODE = "orphaned_code"
    DESIGN_PROBLEM = "design_problem"
    CODE_QUALITY = "code_quality"
    DEPENDENCY = "dependency"


@dataclass
class Issue:
    """Represents a single issue found during analysis."""

    id: str
    title: str
    description: str
    severity: IssueSeverity
    category: IssueCategory
    location: str  # File path and line number, e.g., "gcode_service.py:35"
    impact: str  # Description of the impact
    suggestion: str  # Improvement suggestion
    details: Optional[str] = None  # Additional details
    tags: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        """String representation of the issue."""
        return f"[{self.severity.value.upper()}] {self.title} ({self.location})"


@dataclass
class AnalysisResult:
    """Result of a single analyzer."""

    analyzer_name: str
    issues: List[Issue] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_issue(self, issue: Issue) -> None:
        """Add an issue to the result."""
        self.issues.append(issue)

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)

    def has_issues(self) -> bool:
        """Check if there are any issues."""
        return len(self.issues) > 0

    def issue_count(self) -> int:
        """Get the total number of issues."""
        return len(self.issues)


@dataclass
class FullAnalysisResult:
    """Complete analysis result from all analyzers."""

    results: List[AnalysisResult] = field(default_factory=list)
    total_issues: int = 0
    critical_issues: int = 0
    high_issues: int = 0
    medium_issues: int = 0
    low_issues: int = 0

    def add_result(self, result: AnalysisResult) -> None:
        """Add an analyzer result."""
        self.results.append(result)
        for issue in result.issues:
            self.total_issues += 1
            if issue.severity == IssueSeverity.CRITICAL:
                self.critical_issues += 1
            elif issue.severity == IssueSeverity.HIGH:
                self.high_issues += 1
            elif issue.severity == IssueSeverity.MEDIUM:
                self.medium_issues += 1
            elif issue.severity == IssueSeverity.LOW:
                self.low_issues += 1

    def get_issues_by_severity(self, severity: IssueSeverity) -> List[Issue]:
        """Get all issues of a specific severity."""
        issues = []
        for result in self.results:
            issues.extend([i for i in result.issues if i.severity == severity])
        return issues

    def get_issues_by_category(self, category: IssueCategory) -> List[Issue]:
        """Get all issues of a specific category."""
        issues = []
        for result in self.results:
            issues.extend([i for i in result.issues if i.category == category])
        return issues
