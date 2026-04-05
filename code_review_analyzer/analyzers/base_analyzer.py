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
        self.result = AnalysisResult()
    
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
