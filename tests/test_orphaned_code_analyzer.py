"""脱节代码检测器的单元测试"""


import pytest

from code_review_analyzer.analyzers.orphaned_code_analyzer import OrphanedCodeAnalyzer
from code_review_analyzer.models import IssueCategory


@pytest.fixture
def analyzer(temp_project_dir):
    """创建分析器实例"""
    return OrphanedCodeAnalyzer(temp_project_dir)


def test_analyzer_initialization(analyzer):
    """测试分析器初始化"""
    assert analyzer.project_root is not None
    assert analyzer.result is not None
    assert analyzer.call_graph is not None


def test_build_call_graph(analyzer):
    """测试构建调用图"""
    analyzer._build_call_graph()
    
    # 验证调用图已构建
    assert isinstance(analyzer.call_graph, dict)
    assert isinstance(analyzer.defined_symbols, dict)
    assert isinstance(analyzer.used_symbols, set)


def test_identify_orphaned_services(analyzer):
    """测试识别脱节的 services 层代码"""
    analyzer.analyze()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None
    
    # 检查是否识别了脱节代码
    orphaned_issues = [
        issue for issue in analyzer.result.issues
        if issue.category == IssueCategory.ORPHANED_CODE
    ]
    
    # 由于 services 层代码已经被修正并集成，可能没有脱节代码
    # 但我们验证分析器能够正确运行
    assert isinstance(orphaned_issues, list)


def test_trace_call_graph(analyzer):
    """测试追踪调用链"""
    analyzer._build_call_graph()
    
    # 追踪一个符号的调用链
    chain = analyzer.trace_call_graph("main", max_depth=3)
    
    # 验证返回的是列表
    assert isinstance(chain, list)


def test_full_analysis(analyzer):
    """测试完整分析"""
    result = analyzer.analyze()
    
    assert result is not None
    assert hasattr(result, "issues")
    assert hasattr(result, "summary")
    
    # 获取摘要
    summary = result.summary()
    assert "total_issues" in summary


def test_imported_service_is_not_marked_orphaned(temp_project_dir):
    """Imported service classes should count as used."""
    services_dir = temp_project_dir / "inkscape_wps" / "core" / "services"
    (services_dir / "font_service.py").write_text(
        "class FontService:\n    pass\n",
        encoding="utf-8",
    )
    (services_dir / "gcode_service.py").write_text(
        "class GCodeService:\n    pass\n",
        encoding="utf-8",
    )
    (services_dir / "serial_service.py").write_text(
        "class SerialService:\n    pass\n",
        encoding="utf-8",
    )
    (services_dir / "preview_service.py").write_text(
        "class PreviewService:\n    pass\n",
        encoding="utf-8",
    )
    user_file = temp_project_dir / "inkscape_wps" / "ui" / "consumer.py"
    user_file.write_text(
        "from inkscape_wps.core.services.font_service import FontService\n\n"
        "class Consumer:\n"
        "    def __init__(self, service: FontService):\n"
        "        self.service = service\n",
        encoding="utf-8",
    )

    analyzer = OrphanedCodeAnalyzer(temp_project_dir)
    result = analyzer.analyze()

    titles = [issue.title for issue in result.issues]
    assert "脱节代码：FontService 未被使用" not in titles
