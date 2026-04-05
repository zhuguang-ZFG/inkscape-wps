"""运行时崩溃检测器的单元测试"""

import pytest
from pathlib import Path
from code_review_analyzer.analyzers.runtime_crash_analyzer import RuntimeCrashAnalyzer
from code_review_analyzer.models import IssueSeverity, IssueCategory


@pytest.fixture
def analyzer(temp_project_dir):
    """创建分析器实例"""
    return RuntimeCrashAnalyzer(temp_project_dir)


def test_analyzer_initialization(analyzer):
    """测试分析器初始化"""
    assert analyzer.project_root is not None
    assert analyzer.result is not None


def test_analyze_gcode_service(analyzer):
    """测试分析 gcode_service.py"""
    analyzer.analyze_gcode_service()
    
    # 由于代码已经修正，应该没有问题
    # 但我们可以验证分析器能够正确运行
    assert analyzer.result is not None


def test_analyze_qt_compat(analyzer):
    """测试分析 qt_compat.py"""
    analyzer.analyze_qt_compat()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None


def test_full_analysis(analyzer):
    """测试完整分析"""
    result = analyzer.analyze()
    
    assert result is not None
    assert hasattr(result, "issues")
    assert hasattr(result, "summary")
    
    # 获取摘要
    summary = result.summary()
    assert "total_issues" in summary
    assert "critical" in summary
    assert "high" in summary


def test_issue_severity_levels(analyzer):
    """测试问题严重程度"""
    result = analyzer.analyze()
    
    # 检查是否有不同严重程度的问题
    critical_issues = result.get_issues_by_severity(IssueSeverity.CRITICAL)
    high_issues = result.get_issues_by_severity(IssueSeverity.HIGH)
    medium_issues = result.get_issues_by_severity(IssueSeverity.MEDIUM)
    
    # 验证问题分类正确
    for issue in critical_issues:
        assert issue.severity == IssueSeverity.CRITICAL
    
    for issue in high_issues:
        assert issue.severity == IssueSeverity.HIGH
    
    for issue in medium_issues:
        assert issue.severity == IssueSeverity.MEDIUM
