"""脱节代码检测器 - 识别与实际运行路径无关的代码"""

import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple

from ..models import AnalysisResult, Issue, IssueCategory, IssueSeverity
from .ast_utils import find_class_definitions, parse_python_file
from .base_analyzer import BaseAnalyzer


class OrphanedCodeAnalyzer(BaseAnalyzer):
    """脱节代码检测器 - 识别未被调用的代码"""
    
    def __init__(self, project_root: Path):
        super().__init__(project_root)
        self.call_graph: Dict[str, Set[str]] = {}  # 调用图：{caller: {callees}}
        self.defined_symbols: Dict[str, Tuple[str, int]] = {}  # 定义的符号：{name: (file, line)}
        self.used_symbols: Set[str] = set()  # 使用的符号
    
    def analyze(self) -> AnalysisResult:
        """执行分析"""
        # 第一步：构建调用图
        self._build_call_graph()
        
        # 第二步：识别脱节代码
        self._identify_orphaned_services()
        
        return self.result
    
    def _build_call_graph(self) -> None:
        """构建调用图"""
        # 获取所有 Python 文件
        python_files = self.get_python_files(self.project_root / "inkscape_wps")
        
        for filepath in python_files:
            tree = parse_python_file(filepath)
            if tree is None:
                continue
            
            # 提取类和函数定义
            classes = find_class_definitions(tree)
            for class_name, line_no, _ in classes:
                self.defined_symbols[class_name] = (str(filepath), line_no)
            
            # 分析调用关系
            self._analyze_calls(tree, filepath)
    
    def _analyze_calls(self, tree: ast.Module, filepath: Path) -> None:
        """分析文件中的调用关系"""
        
        class CallVisitor(ast.NodeVisitor):
            def __init__(self, analyzer):
                self.analyzer = analyzer
                self.current_context = None
            
            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                old_context = self.current_context
                self.current_context = node.name
                self.generic_visit(node)
                self.current_context = old_context
            
            def visit_Call(self, node: ast.Call) -> None:
                # 记录调用
                if isinstance(node.func, ast.Name):
                    callee = node.func.id
                    if self.current_context:
                        caller = self.current_context
                    else:
                        caller = str(filepath)
                    
                    if caller not in self.analyzer.call_graph:
                        self.analyzer.call_graph[caller] = set()
                    self.analyzer.call_graph[caller].add(callee)
                    self.analyzer.used_symbols.add(callee)
                
                elif isinstance(node.func, ast.Attribute):
                    # 记录属性调用
                    self.analyzer.used_symbols.add(node.func.attr)
                
                self.generic_visit(node)

            def visit_Import(self, node: ast.Import) -> None:
                for alias in node.names:
                    imported_name = alias.asname or alias.name.split(".")[-1]
                    self.analyzer.used_symbols.add(imported_name)
                self.generic_visit(node)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                for alias in node.names:
                    imported_name = alias.asname or alias.name
                    self.analyzer.used_symbols.add(imported_name)
                self.generic_visit(node)
        
        visitor = CallVisitor(self)
        visitor.visit(tree)
    
    def _identify_orphaned_services(self) -> None:
        """识别脱节的 services 层代码"""
        services_dir = self.project_root / "inkscape_wps" / "core" / "services"
        
        if not services_dir.exists():
            return
        
        # 检查 services 层的四个服务类
        service_classes = [
            ("GCodeService", "gcode_service.py"),
            ("SerialService", "serial_service.py"),
            ("FontService", "font_service.py"),
            ("PreviewService", "preview_service.py"),
        ]
        
        for class_name, filename in service_classes:
            filepath = services_dir / filename
            
            if not filepath.exists():
                continue
            
            # 检查该类是否被使用
            if class_name not in self.used_symbols:
                self.add_issue(Issue(
                    id=f"orphaned_{class_name.lower()}",
                    title=f"脱节代码：{class_name} 未被使用",
                    description=f"{class_name} 在 {filename} 中定义，但未被项目中的任何地方调用",
                    category=IssueCategory.ORPHANED_CODE,
                    severity=IssueSeverity.HIGH,
                    file_path=str(filepath),
                    suggestion=f"考虑删除 {class_name} 或将其集成到主窗口的工作流中",
                ))
    
    def trace_call_graph(self, symbol: str, depth: int = 0, max_depth: int = 5) -> List[str]:
        """追踪符号的调用链
        
        Args:
            symbol: 符号名称
            depth: 当前深度
            max_depth: 最大深度
            
        Returns:
            调用链列表
        """
        if depth > max_depth:
            return []
        
        chain = [f"{'  ' * depth}{symbol}"]
        
        if symbol in self.call_graph:
            for callee in self.call_graph[symbol]:
                chain.extend(self.trace_call_graph(callee, depth + 1, max_depth))
        
        return chain
