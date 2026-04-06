"""代码质量检测器的单元测试"""


import pytest

from code_review_analyzer.analyzers.code_quality_analyzer import CodeQualityAnalyzer
from code_review_analyzer.models import IssueSeverity


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


def test_public_framework_hook_is_not_reported_as_unused_method(temp_project_dir):
    """Public framework callbacks should not be treated as unused methods."""
    ui_file = temp_project_dir / "inkscape_wps" / "ui" / "window.py"
    ui_file.write_text(
        "class MainWindow:\n"
        "    def closeEvent(self, event):\n"
        "        event.accept()\n",
        encoding="utf-8",
    )

    analyzer = CodeQualityAnalyzer(temp_project_dir)
    analyzer.check_unused_methods()

    titles = [issue.title for issue in analyzer.result.issues]
    assert "未使用的方法" not in titles


def test_unused_private_helper_is_reported(temp_project_dir):
    """Unused private helpers should still be reported."""
    ui_file = temp_project_dir / "inkscape_wps" / "ui" / "helper.py"
    ui_file.write_text(
        "class Helper:\n"
        "    def _never_called(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )

    analyzer = CodeQualityAnalyzer(temp_project_dir)
    analyzer.check_unused_methods()

    issues = [issue for issue in analyzer.result.issues if issue.title == "未使用的方法"]
    assert len(issues) == 1
    assert issues[0].line_number == 2


def test_debug_logging_fstring_is_reported(temp_project_dir):
    """Debug logging with f-strings should be reported."""
    core_file = temp_project_dir / "inkscape_wps" / "core" / "logging_case.py"
    core_file.write_text(
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "def run(value):\n"
        "    logger.debug(f'value={value}')\n",
        encoding="utf-8",
    )

    analyzer = CodeQualityAnalyzer(temp_project_dir)
    analyzer.check_logging_fstring()

    issues = [issue for issue in analyzer.result.issues if issue.title == "日志调用中使用 f-string"]
    assert len(issues) == 1
    assert issues[0].line_number == 4


def test_error_logging_fstring_is_not_reported(temp_project_dir):
    """Error logging is currently excluded to avoid noisy low-value findings."""
    core_file = temp_project_dir / "inkscape_wps" / "core" / "logging_case.py"
    core_file.write_text(
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "def run(value):\n"
        "    logger.error(f'value={value}')\n",
        encoding="utf-8",
    )

    analyzer = CodeQualityAnalyzer(temp_project_dir)
    analyzer.check_logging_fstring()

    issues = [issue for issue in analyzer.result.issues if issue.title == "日志调用中使用 f-string"]
    assert issues == []
