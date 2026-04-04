"""Code Review Analyzer - A comprehensive code analysis tool for inkscape_wps project."""

__version__ = "0.1.0"
__author__ = "Code Review Team"

from .models import Issue, IssueSeverity, IssueCategory

__all__ = [
    "Issue",
    "IssueSeverity",
    "IssueCategory",
]
