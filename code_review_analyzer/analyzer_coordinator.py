"""分析协调器 - 整合所有分析器

本模块协调所有分析器的执行，按优先级运行分析器，
并收集和合并分析结果。

性能优化：
- 支持 AST 缓存
- 性能监控和统计
- 详细的执行时间跟踪
"""

import time
from pathlib import Path
from typing import List

from .models import AnalysisResult, Issue
from .analyzers.runtime_crash_analyzer import RuntimeCrashAnalyzer
from .analyzers.orphaned_code_analyzer import OrphanedCodeAnalyzer
from .analyzers.design_issue_analyzer import DesignIssueAnalyzer
from .analyzers.code_quality_analyzer import CodeQualityAnalyzer
from .analyzers.dependency_analyzer import DependencyAnalyzer
from .reporters.report_generator import ReportGenerator
from .cache_manager import CacheManager
from .performance_monitor import PerformanceMonitor
from .analyzers import ast_utils


class AnalyzerCoordinator:
    """分析协调器 - 按优先级运行所有分析器"""
    
    def __init__(self, project_root: Path, enable_cache: bool = True, enable_monitoring: bool = True):
        """初始化协调器
        
        Args:
            project_root: 项目根目录路径
            enable_cache: 是否启用缓存
            enable_monitoring: 是否启用性能监控
        """
        self.project_root = Path(project_root)
        self.result = AnalysisResult()
        self.analyzers = []
        
        # 初始化缓存
        self.cache_manager = CacheManager() if enable_cache else None
        if self.cache_manager:
            ast_utils.set_cache_manager(self.cache_manager)
        
        # 初始化性能监控
        self.performance_monitor = PerformanceMonitor() if enable_monitoring else None
    
    def run_all_analyzers(self) -> AnalysisResult:
        """按优先级运行所有分析器
        
        Returns:
            合并后的分析结果
        """
        start_time = time.time()
        
        # P0 优先级：运行时崩溃检测
        print("运行 P0 优先级分析器...")
        self._run_analyzer(RuntimeCrashAnalyzer(self.project_root), "运行时崩溃检测")
        
        # P1 优先级：脱节代码和设计问题
        print("运行 P1 优先级分析器...")
        self._run_analyzer(OrphanedCodeAnalyzer(self.project_root), "脱节代码检测")
        self._run_analyzer(DesignIssueAnalyzer(self.project_root), "设计问题检测")
        
        # P2 优先级：代码质量和依赖关系
        print("运行 P2 优先级分析器...")
        self._run_analyzer(CodeQualityAnalyzer(self.project_root), "代码质量检测")
        self._run_analyzer(DependencyAnalyzer(self.project_root), "依赖关系分析")
        
        # 计算分析耗时
        duration = time.time() - start_time
        self.result.analysis_duration_seconds = duration
        
        # 记录性能指标
        if self.performance_monitor:
            self.performance_monitor.metrics.total_duration = duration
            self.performance_monitor.metrics.issues_found = len(self.result.issues)
            self.performance_monitor.metrics.finalize()
        
        return self.result
    
    def _run_analyzer(self, analyzer, analyzer_name: str) -> None:
        """运行单个分析器
        
        Args:
            analyzer: 分析器实例
            analyzer_name: 分析器名称
        """
        try:
            # 开始计时
            start_time = None
            if self.performance_monitor:
                start_time = self.performance_monitor.start_analyzer(analyzer_name)
            
            result = analyzer.analyze()
            
            # 结束计时
            if self.performance_monitor and start_time:
                self.performance_monitor.end_analyzer(analyzer_name, start_time)
            
            # 合并结果
            self.result.issues.extend(result.issues)
            self.result.total_files_analyzed += result.total_files_analyzed
            
            print(f"  ✓ {analyzer_name}：发现 {len(result.issues)} 个问题")
        
        except Exception as e:
            print(f"  ✗ {analyzer_name} 失败：{str(e)}")
    
    def collect_results(self) -> AnalysisResult:
        """收集所有分析结果
        
        Returns:
            合并后的分析结果
        """
        return self.result
    
    def generate_full_report(self) -> str:
        """生成完整报告
        
        Returns:
            报告内容（Markdown 格式）
        """
        generator = ReportGenerator(self.result)
        return generator.generate()
    
    def save_report(self, output_path: Path) -> None:
        """保存报告到文件
        
        Args:
            output_path: 输出文件路径
        """
        generator = ReportGenerator(self.result)
        generator.save(output_path)
    
    def print_performance_stats(self) -> None:
        """打印性能统计信息"""
        if self.performance_monitor:
            self.performance_monitor.metrics.print_summary()
        
        if self.cache_manager:
            self.cache_manager.print_stats()
