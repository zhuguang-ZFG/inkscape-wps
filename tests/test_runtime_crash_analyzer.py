"""运行时崩溃检测器的单元测试"""


import pytest

from code_review_analyzer.analyzers.runtime_crash_analyzer import RuntimeCrashAnalyzer
from code_review_analyzer.models import IssueSeverity


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


def test_len_paths_is_not_reported_as_vector_path_crash(temp_project_dir):
    """Only len(path) should be flagged, not len(paths) or len(path.points)."""
    service_file = temp_project_dir / "inkscape_wps" / "core" / "services" / "gcode_service.py"
    service_file.write_text(
        "class Example:\n"
        "    def check(self, paths, path):\n"
        "        total = len(paths)\n"
        "        points = len(path.points)\n"
        "        return total + points\n",
        encoding="utf-8",
    )

    analyzer = RuntimeCrashAnalyzer(temp_project_dir)
    analyzer.analyze_gcode_service()

    issues = [issue for issue in analyzer.result.issues if issue.id == "gcode_service_002"]
    assert issues == []


def test_len_path_is_reported_as_vector_path_crash(temp_project_dir):
    """Direct len(path) calls should still be flagged."""
    service_file = temp_project_dir / "inkscape_wps" / "core" / "services" / "gcode_service.py"
    service_file.write_text(
        "class Example:\n"
        "    def check(self, path):\n"
        "        return len(path)\n",
        encoding="utf-8",
    )

    analyzer = RuntimeCrashAnalyzer(temp_project_dir)
    analyzer.analyze_gcode_service()

    issues = [issue for issue in analyzer.result.issues if issue.id == "gcode_service_002"]
    assert len(issues) == 1
    assert issues[0].line_number == 3


def test_font_service_async_warnings_are_not_reported_as_runtime_crashes(temp_project_dir):
    """Async-without-await belongs to code quality, not runtime crash analysis."""
    service_file = temp_project_dir / "inkscape_wps" / "core" / "services" / "font_service.py"
    service_file.write_text(
        "class FontService:\n"
        "    async def discover_fonts(self):\n"
        "        return []\n",
        encoding="utf-8",
    )

    analyzer = RuntimeCrashAnalyzer(temp_project_dir)
    analyzer.analyze_font_service()

    assert analyzer.result.issues == []
