"""问题数据模型定义"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class IssueSeverity(Enum):
    """问题严重程度"""
    CRITICAL = "critical"  # 运行时必崩
    HIGH = "high"  # 设计问题
    MEDIUM = "medium"  # 代码质量问题
    LOW = "low"  # 建议改进


class IssueCategory(Enum):
    """问题分类"""
    RUNTIME_CRASH = "runtime_crash"  # 运行时崩溃
    DESIGN = "design"  # 设计问题
    CODE_QUALITY = "code_quality"  # 代码质量
    DEPENDENCY = "dependency"  # 依赖关系
    ORPHANED_CODE = "orphaned_code"  # 脱节代码


@dataclass
class Issue:
    """代码审查问题"""
    
    # 基本信息
    id: str  # 问题唯一标识
    title: str  # 问题标题
    description: str  # 问题描述
    
    # 分类和严重程度
    category: IssueCategory  # 问题分类
    severity: IssueSeverity  # 严重程度
    
    # 位置信息
    file_path: str  # 文件路径
    line_number: Optional[int] = None  # 行号
    column_number: Optional[int] = None  # 列号
    
    # 详细信息
    code_snippet: Optional[str] = None  # 代码片段
    error_type: Optional[str] = None  # 错误类型（如 AttributeError）
    
    # 改进建议
    suggestion: Optional[str] = None  # 改进建议
    
    # 相关信息
    related_issues: List[str] = field(default_factory=list)  # 相关问题 ID
    
    def __str__(self) -> str:
        """字符串表示"""
        location = f"{self.file_path}"
        if self.line_number:
            location += f":{self.line_number}"
        return f"[{self.severity.value.upper()}] {self.title} ({location})"
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column_number": self.column_number,
            "code_snippet": self.code_snippet,
            "error_type": self.error_type,
            "suggestion": self.suggestion,
            "related_issues": self.related_issues,
        }


@dataclass
class AnalysisResult:
    """分析结果"""
    
    issues: List[Issue] = field(default_factory=list)  # 发现的问题列表
    total_files_analyzed: int = 0  # 分析的文件总数
    analysis_duration_seconds: float = 0.0  # 分析耗时（秒）
    
    def add_issue(self, issue: Issue) -> None:
        """添加问题"""
        self.issues.append(issue)
    
    def get_issues_by_severity(self, severity: IssueSeverity) -> List[Issue]:
        """按严重程度获取问题"""
        return [issue for issue in self.issues if issue.severity == severity]
    
    def get_issues_by_category(self, category: IssueCategory) -> List[Issue]:
        """按分类获取问题"""
        return [issue for issue in self.issues if issue.category == category]
    
    def summary(self) -> dict:
        """生成摘要"""
        return {
            "total_issues": len(self.issues),
            "critical": len(self.get_issues_by_severity(IssueSeverity.CRITICAL)),
            "high": len(self.get_issues_by_severity(IssueSeverity.HIGH)),
            "medium": len(self.get_issues_by_severity(IssueSeverity.MEDIUM)),
            "low": len(self.get_issues_by_severity(IssueSeverity.LOW)),
            "total_files_analyzed": self.total_files_analyzed,
            "analysis_duration_seconds": self.analysis_duration_seconds,
        }
