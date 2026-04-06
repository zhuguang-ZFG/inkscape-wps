"""基础分析器类

本模块定义了所有分析器的基类，提供了通用的分析框架和工具方法。

分析器职责：
- 遍历项目中的 Python 文件
- 使用 AST 解析和分析代码
- 识别特定类型的代码问题
- 将问题添加到分析结果中

所有具体的分析器（如 RuntimeCrashAnalyzer、DesignIssueAnalyzer 等）
都应该继承自 BaseAnalyzer 并实现 analyze() 方法。
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from ..models import AnalysisResult, Issue


class BaseAnalyzer(ABC):
    """所有分析器的基类"""

    def __init__(self, project_root: Path):
        """初始化分析器

        Args:
            project_root: 项目根目录路径
        """
        self.project_root = Path(project_root)
        # `project_path` 和 `analyzer_name` 是历史测试与调用方仍在使用的兼容接口。
        self.project_path = self.project_root
        self.result = AnalysisResult(analyzer_name=self.__class__.__name__)
    
    @abstractmethod
    def analyze(self) -> AnalysisResult:
        """执行分析

        Returns:
            分析结果
        """
        pass

    def add_issue(self, issue: Issue) -> None:
        """添加问题到结果中"""
        self.result.add_issue(issue)

    def get_result(self) -> AnalysisResult:
        """返回当前分析结果。"""
        return self.result

    def _get_file_path(self, relative_path: str) -> Path | None:
        """解析项目内文件路径。

        优先按项目根解析；若传入的是 `core/foo.py` 这类旧式相对路径，
        则兼容补全到 `inkscape_wps/core/foo.py`。
        """
        candidate = self.project_root / relative_path
        if candidate.exists():
            return candidate

        source_candidate = self.project_root / "inkscape_wps" / relative_path
        if source_candidate.exists():
            return source_candidate

        return None

    def _read_file(self, relative_path: str) -> str | None:
        """读取项目内文件内容，不存在时返回 `None`。"""
        file_path = self._get_file_path(relative_path)
        if file_path is None:
            return None
        return file_path.read_text(encoding="utf-8")

    def get_python_files(self, directory: Path = None) -> List[Path]:
        """获取目录下的所有 Python 文件

        Args:
            directory: 目录路径，默认为项目根目录

        Returns:
            Python 文件路径列表
        """
        if directory is None:
            directory = self.project_root

        return list(directory.rglob("*.py"))
