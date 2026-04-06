"""基础报告生成器类"""

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import AnalysisResult


class BaseReporter(ABC):
    """所有报告生成器的基类"""
    
    def __init__(self, result: AnalysisResult):
        """初始化报告生成器
        
        Args:
            result: 分析结果
        """
        self.result = result
    
    @abstractmethod
    def generate(self) -> str:
        """生成报告
        
        Returns:
            报告内容
        """
        pass

    def save(self, output_path: Path) -> None:
        """保存报告到文件。"""
        report = self.generate()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"报告已保存到：{output_path}")
