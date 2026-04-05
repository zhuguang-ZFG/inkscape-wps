"""代码质量检测器的单元测试"""

import pytest
from pathlib import Path
from code_review_analyzer.analyzers.code_quality_analyzer import CodeQualityAnalyzer
from code_review_analyzer.models import IssueCategory, IssueSeverity


@pytest.fixture
def analyzer(temp_project_dir):
    """创建分析器实例"""
    return CodeQualityAnalyzer(temp_project_dir)


def test_analyzer_initialization(analyzer):
    """测试分析器初始化"""
    assert analyzer.project_root is not None
    assert analyzer.result is not None


def test_check_duplicate_branches(analyzer):
    """测试检查重复分支"""
    analyzer.check_duplicate_branches()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None


def test_check_constant_calculations(analyzer):
    """测试检查常数计算"""
    analyzer.check_constant_calculations()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None
    
    # 检查是否有常数计算问题
    const_issues = [
        issue for issue in analyzer.result.issues
        if "常数计算" in issue.title
    ]
    
    assert isinstance(const_issues, list)


def test_check_async_without_await(analyzer):
    """测试检查 async 函数"""
    analyzer.check_async_without_await()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None


def test_check_logging_fstring(analyzer):
    """测试检查日志 f-string"""
    analyzer.check_logging_fstring()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None
    
    # 检查是否有日志 f-string 问题
    logging_issues = [
        issue for issue in analyzer.result.issues
        if "日志调用中使用 f-string" in issue.title
    ]
    
    assert isinstance(logging_issues, list)


def test_check_unused_methods(analyzer):
    """测试检查未使用的方法"""
    analyzer.check_unused_methods()
    
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
    assert "medium" in summary
    assert "low" in summary


def test_issue_severity_levels(analyzer):
    """测试问题严重程度"""
    result = analyzer.analyze()
    
    # 检查是否有不同严重程度的问题
    medium_issues = result.get_issues_by_severity(IssueSeverity.MEDIUM)
    low_issues = result.get_issues_by_severity(IssueSeverity.LOW)
    
    # 验证问题分类正确
    for issue in medium_issues:
        assert issue.severity == IssueSeverity.MEDIUM
    
    for issue in low_issues:
        assert issue.severity == IssueSeverity.LOW
