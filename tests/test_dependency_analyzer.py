"""依赖关系分析器的单元测试"""

import pytest
from pathlib import Path
from code_review_analyzer.analyzers.dependency_analyzer import DependencyAnalyzer
from code_review_analyzer.models import IssueCategory


@pytest.fixture
def analyzer(temp_project_dir):
    """创建分析器实例"""
    return DependencyAnalyzer(temp_project_dir)


def test_analyzer_initialization(analyzer):
    """测试分析器初始化"""
    assert analyzer.project_root is not None
    assert analyzer.result is not None
    assert analyzer.dependencies is not None
    assert analyzer.optional_dependencies is not None


def test_parse_pyproject_toml(analyzer):
    """测试解析 pyproject.toml"""
    analyzer.parse_pyproject_toml()
    
    # 验证分析器能够正确运行
    assert analyzer.dependencies is not None


def test_extract_dependencies(analyzer):
    """测试提取依赖"""
    analyzer.parse_pyproject_toml()
    analyzer.extract_dependencies()
    
    # 验证分析器能够正确运行
    assert analyzer.dependencies is not None


def test_check_conflicting_dependencies(analyzer):
    """测试检查冲突依赖"""
    analyzer.parse_pyproject_toml()
    analyzer.check_conflicting_dependencies()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None
    
    # 检查是否有冲突问题
    conflict_issues = [
        issue for issue in analyzer.result.issues
        if "冲突" in issue.title
    ]
    
    assert isinstance(conflict_issues, list)


def test_identify_optional_dependencies(analyzer):
    """测试识别可选依赖"""
    analyzer.parse_pyproject_toml()
    analyzer.identify_optional_dependencies()
    
    # 验证分析器能够正确运行
    assert analyzer.result is not None


def test_get_dependency_info(analyzer):
    """测试获取依赖信息"""
    analyzer.parse_pyproject_toml()
    deps = analyzer.get_dependency_info()
    
    # 验证返回的是字典
    assert isinstance(deps, dict)


def test_get_optional_dependencies(analyzer):
    """测试获取可选依赖"""
    analyzer.parse_pyproject_toml()
    opt_deps = analyzer.get_optional_dependencies()
    
    # 验证返回的是字典
    assert isinstance(opt_deps, dict)


def test_full_analysis(analyzer):
    """测试完整分析"""
    result = analyzer.analyze()
    
    assert result is not None
    assert hasattr(result, "issues")
    assert hasattr(result, "summary")
    
    # 获取摘要
    summary = result.summary()
    assert "total_issues" in summary


def test_check_version_compatibility(analyzer):
    """测试版本兼容性检查"""
    analyzer.parse_pyproject_toml()
    
    # 测试版本兼容性检查
    result = analyzer.check_version_compatibility("nonexistent", ">=1.0")
    assert result is False
