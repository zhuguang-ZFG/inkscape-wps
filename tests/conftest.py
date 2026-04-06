"""Pytest 配置和共享 fixtures"""

import tempfile
from pathlib import Path

import pytest

from code_review_analyzer.cache_manager import CacheManager
from code_review_analyzer.performance_monitor import PerformanceMonitor


@pytest.fixture
def temp_project_dir():
    """创建临时项目目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        # 创建项目结构
        (project_dir / "inkscape_wps").mkdir()
        (project_dir / "inkscape_wps" / "core").mkdir()
        (project_dir / "inkscape_wps" / "core" / "services").mkdir()
        (project_dir / "inkscape_wps" / "ui").mkdir()
        
        yield project_dir


@pytest.fixture
def cache_manager():
    """创建缓存管理器"""
    return CacheManager()


@pytest.fixture
def performance_monitor():
    """创建性能监控器"""
    return PerformanceMonitor()


@pytest.fixture
def sample_python_file(temp_project_dir):
    """创建示例 Python 文件"""
    filepath = temp_project_dir / "inkscape_wps" / "core" / "sample.py"
    
    code = '''
"""示例模块"""

def hello_world():
    """打印 Hello World"""
    print("Hello World")

class SampleClass:
    """示例类"""
    
    def __init__(self):
        self.value = 42
    
    def get_value(self):
        """获取值"""
        return self.value
'''
    
    filepath.write_text(code)
    return filepath


@pytest.fixture
def sample_project_structure(temp_project_dir):
    """创建带有基础源码文件的示例项目结构。"""
    types_file = temp_project_dir / "inkscape_wps" / "core" / "types.py"
    types_file.write_text(
        '"""types module"""\n\n'
        "class VectorPath:\n"
        "    pass\n",
        encoding="utf-8",
    )
    return temp_project_dir


@pytest.fixture
def sample_config_file(temp_project_dir):
    """创建示例配置文件"""
    filepath = temp_project_dir / "pyproject.toml"
    
    config = '''
[project]
name = "test-project"
version = "0.1.0"

[project.dependencies]
PyQt5 = ">=5.15.0"
pyserial = ">=3.5"
'''
    
    filepath.write_text(config)
    return filepath
