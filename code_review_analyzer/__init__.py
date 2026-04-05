"""inkscape_wps 项目代码审查分析工具"""

__version__ = "0.1.0"
__author__ = "Code Review Analyzer"

from .models import Issue, IssueSeverity, IssueCategory

__all__ = ["Issue", "IssueSeverity", "IssueCategory"]
