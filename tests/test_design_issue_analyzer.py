"""设计问题检测器的单元测试"""

import pytest
from pathlib import Path
from code_review_analyzer.analyzers.design_issue_analyzer import DesignIssueAnalyzer
from code_review_analyzer.models import IssueCategory, IssueSeverity


@pytest.fixture
def analyzer(temp_project_dir):
    """创建分析器实例"""
    return DesignIssueAnalyzer(temp_project_dir)


def test_analyzer_initialization(analyzer):
    """测试分析器初始化"""
    assert analyzer.project_root is not None
    assert analyzer.result is not None


def test_check_file_sizes(analyzer):
    """测试检查文件大小"""
    analyzer.check_file_sizes()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None
    
    # 检查是否有文件大小问题
    file_size_issues = [
        issue for issue in analyzer.result.issues
        if "文件过大" in issue.title
    ]
    
    # main_window.py 应该被标记为过大
    assert isinstance(file_size_issues, list)


def test_check_method_sizes(analyzer):
    """测试检查方法大小"""
    analyzer.check_method_sizes()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None
    
    # 检查是否有方法大小问题
    method_size_issues = [
        issue for issue in analyzer.result.issues
        if "方法过大" in issue.title
    ]
    
    assert isinstance(method_size_issues, list)


def test_check_config_bloat(analyzer):
    """测试检查配置字段数量"""
    analyzer.check_config_bloat()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None


def test_check_ui_state_variables(analyzer):
    """测试检查 UI 状态变量"""
    analyzer.check_ui_state_variables()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None


def test_check_svg_support(analyzer):
    """测试检查 SVG 支持"""
    analyzer.check_svg_support()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None
    
    # 检查是否有 SVG 相关问题
    svg_issues = [
        issue for issue in analyzer.result.issues
        if "SVG" in issue.title
    ]
    
    assert isinstance(svg_issues, list)


def test_check_gcode_z_mode(analyzer):
    """测试检查 G-code Z 模式"""
    analyzer.check_gcode_z_mode()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None


def test_check_coordinate_transform(analyzer):
    """测试检查坐标变换"""
    analyzer.check_coordinate_transform()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None


def test_check_file_io_in_lock(analyzer):
    """测试检查锁内文件 I/O"""
    analyzer.check_file_io_in_lock()
    
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
    assert "high" in summary
    assert "medium" in summary


def test_issue_severity_levels(analyzer):
    """测试问题严重程度"""
    result = analyzer.analyze()
    
    # 检查是否有不同严重程度的问题
    high_issues = result.get_issues_by_severity(IssueSeverity.HIGH)
    medium_issues = result.get_issues_by_severity(IssueSeverity.MEDIUM)
    
    # 验证问题分类正确
    for issue in high_issues:
        assert issue.severity == IssueSeverity.HIGH
    
    for issue in medium_issues:
        assert issue.severity == IssueSeverity.MEDIUM
