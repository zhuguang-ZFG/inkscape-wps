"""性能监控器 - 监控和分析代码审查的性能

本模块提供了性能监控功能，用于跟踪分析过程中的时间消耗、
内存使用等性能指标。
"""

import time
import psutil
import os
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PerformanceMetrics:
    """性能指标"""
    
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    
    # 时间指标
    total_duration: float = 0.0
    analyzer_durations: Dict[str, float] = field(default_factory=dict)
    
    # 内存指标
    start_memory_mb: float = 0.0
    peak_memory_mb: float = 0.0
    end_memory_mb: float = 0.0
    
    # 文件处理指标
    files_analyzed: int = 0
    issues_found: int = 0
    
    def __post_init__(self):
        """初始化性能指标"""
        process = psutil.Process(os.getpid())
        self.start_memory_mb = process.memory_info().rss / 1024 / 1024
        self.peak_memory_mb = self.start_memory_mb
    
    def record_analyzer_time(self, analyzer_name: str, duration: float) -> None:
        """记录分析器的执行时间
        
        Args:
            analyzer_name: 分析器名称
            duration: 执行时间（秒）
        """
        self.analyzer_durations[analyzer_name] = duration
    
    def finalize(self) -> None:
        """完成性能指标收集"""
        self.end_time = time.time()
        self.total_duration = self.end_time - self.start_time
        
        process = psutil.Process(os.getpid())
        current_memory = process.memory_info().rss / 1024 / 1024
        self.end_memory_mb = current_memory
        self.peak_memory_mb = max(self.peak_memory_mb, current_memory)
    
    def get_summary(self) -> Dict:
        """获取性能摘要
        
        Returns:
            包含性能指标的字典
        """
        return {
            "total_duration_seconds": f"{self.total_duration:.2f}",
            "files_analyzed": self.files_analyzed,
            "issues_found": self.issues_found,
            "files_per_second": f"{self.files_analyzed / self.total_duration:.1f}" if self.total_duration > 0 else "N/A",
            "memory_start_mb": f"{self.start_memory_mb:.1f}",
            "memory_peak_mb": f"{self.peak_memory_mb:.1f}",
            "memory_end_mb": f"{self.end_memory_mb:.1f}",
            "memory_delta_mb": f"{self.end_memory_mb - self.start_memory_mb:.1f}",
            "analyzer_times": self.analyzer_durations,
        }
    
    def print_summary(self) -> None:
        """打印性能摘要"""
        summary = self.get_summary()
        
        print("\n⏱️  性能指标:")
        print(f"  总耗时：{summary['total_duration_seconds']} 秒")
        print(f"  分析文件数：{summary['files_analyzed']}")
        print(f"  发现问题数：{summary['issues_found']}")
        print(f"  处理速度：{summary['files_per_second']} 文件/秒")
        
        print("\n💾 内存使用:")
        print(f"  初始内存：{summary['memory_start_mb']} MB")
        print(f"  峰值内存：{summary['memory_peak_mb']} MB")
        print(f"  最终内存：{summary['memory_end_mb']} MB")
        print(f"  内存增长：{summary['memory_delta_mb']} MB")
        
        if summary['analyzer_times']:
            print("\n🔍 分析器耗时:")
            for analyzer_name, duration in summary['analyzer_times'].items():
                print(f"  {analyzer_name}：{duration:.2f} 秒")


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        """初始化性能监控器"""
        self.metrics = PerformanceMetrics()
    
    def start_analyzer(self, analyzer_name: str) -> float:
        """开始分析器计时
        
        Args:
            analyzer_name: 分析器名称
            
        Returns:
            开始时间戳
        """
        return time.time()
    
    def end_analyzer(self, analyzer_name: str, start_time: float) -> None:
        """结束分析器计时
        
        Args:
            analyzer_name: 分析器名称
            start_time: 开始时间戳
        """
        duration = time.time() - start_time
        self.metrics.record_analyzer_time(analyzer_name, duration)
    
    def finalize(self) -> PerformanceMetrics:
        """完成监控并返回指标
        
        Returns:
            性能指标对象
        """
        self.metrics.finalize()
        return self.metrics
