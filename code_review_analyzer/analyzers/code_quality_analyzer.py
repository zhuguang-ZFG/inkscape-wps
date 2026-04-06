"""代码质量检测器

本模块检测代码中的质量问题，包括：
- 条件分支代码重复
- 永远为常数的计算
- async 函数中无 await 调用
- 日志调用中使用 f-string（应使用参数化日志）

这些问题被标记为 MEDIUM 或 LOW 严重程度，影响代码的质量和效率。
"""

import ast
import re

from ..models import AnalysisResult, Issue, IssueCategory, IssueSeverity
from .ast_utils import (
    find_async_functions_without_await,
    find_duplicate_branches,
    parse_python_file,
)
from .base_analyzer import BaseAnalyzer


class CodeQualityAnalyzer(BaseAnalyzer):
    """代码质量检测器"""
    
    def analyze(self) -> AnalysisResult:
        """执行分析"""
        self.check_duplicate_branches()
        self.check_constant_calculations()
        self.check_async_without_await()
        self.check_logging_fstring()
        self.check_unused_methods()
        
        return self.result
    
    def check_duplicate_branches(self) -> None:
        """检查条件分支代码重复"""
        python_files = self.get_python_files(self.project_root / "inkscape_wps")
        
        for filepath in python_files:
            tree = parse_python_file(filepath)
            if tree is None:
                continue
            
            # 查找 if-else 分支
            duplicates = find_duplicate_branches(tree)
            for line_no, branch_type in duplicates:
                self.add_issue(Issue(
                    id=f"quality_dup_branch_{filepath.name}_{line_no}",
                    title="条件分支代码重复",
                    description=(
                        f"在 {filepath.name} 的第 {line_no} 行，"
                        f"{branch_type} 分支的代码完全相同"
                    ),
                    category=IssueCategory.CODE_QUALITY,
                    severity=IssueSeverity.MEDIUM,
                    file_path=str(filepath),
                    line_number=line_no,
                    suggestion="合并重复的分支代码或提取为公共方法",
                ))
    
    def check_constant_calculations(self) -> None:
        """检查永远为常数的计算"""
        python_files = self.get_python_files(self.project_root / "inkscape_wps")
        
        for filepath in python_files:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 检查 len(x) / len(x) 的模式
            pattern = r'len\((\w+)\)\s*/\s*len\(\1\)'
            matches = re.finditer(pattern, content)
            
            for match in matches:
                line_no = content[:match.start()].count('\n') + 1
                self.add_issue(Issue(
                    id=f"quality_const_calc_{filepath.name}_{line_no}",
                    title="常数计算",
                    description=(
                        f"在 {filepath.name} 的第 {line_no} 行，"
                        f"计算 {match.group(0)} 永远为 1.0"
                    ),
                    category=IssueCategory.CODE_QUALITY,
                    severity=IssueSeverity.MEDIUM,
                    file_path=str(filepath),
                    line_number=line_no,
                    code_snippet=match.group(0),
                    suggestion="检查计算逻辑是否正确，应该使用不同的变量",
                ))
    
    def check_async_without_await(self) -> None:
        """检查 async 函数中无 await 调用"""
        python_files = self.get_python_files(self.project_root / "inkscape_wps")
        
        for filepath in python_files:
            tree = parse_python_file(filepath)
            if tree is None:
                continue
            
            async_funcs = find_async_functions_without_await(tree)
            for func_name, line_no in async_funcs:
                self.add_issue(Issue(
                    id=f"quality_async_no_await_{filepath.name}_{func_name}",
                    title="async 函数中无 await 调用",
                    description=(
                        f"函数 {func_name} 在 {filepath.name} 中被标记为 async，"
                        "但没有任何 await 调用"
                    ),
                    category=IssueCategory.CODE_QUALITY,
                    severity=IssueSeverity.MEDIUM,
                    file_path=str(filepath),
                    line_number=line_no,
                    error_type="InconsistentAsyncDef",
                    suggestion="改为同步函数或添加 await 调用",
                ))
    
    def check_logging_fstring(self) -> None:
        """检查日志调用中的 f-string 使用"""
        python_files = self.get_python_files(self.project_root / "inkscape_wps")
        
        for filepath in python_files:
            tree = parse_python_file(filepath)
            if tree is None:
                continue

            class LoggingVisitor(ast.NodeVisitor):
                def __init__(self, analyzer):
                    self.analyzer = analyzer

                def visit_Call(self, node: ast.Call) -> None:
                    if (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr == "debug"
                        and node.args
                        and isinstance(node.args[0], ast.JoinedStr)
                    ):
                        self.analyzer.add_issue(Issue(
                            id=f"quality_log_fstring_{filepath.name}_{node.lineno}",
                            title="日志调用中使用 f-string",
                            description=(
                                f"在 {filepath.name} 的第 {node.lineno} 行，"
                                "debug 日志调用中使用了 f-string"
                            ),
                            category=IssueCategory.CODE_QUALITY,
                            severity=IssueSeverity.LOW,
                            file_path=str(filepath),
                            line_number=node.lineno,
                            code_snippet=ast.unparse(node),
                            suggestion="改为参数化日志：logger.debug('message %s', var)",
                        ))
                    self.generic_visit(node)

            LoggingVisitor(self).visit(tree)

    
    def check_unused_methods(self) -> None:
        """检查未使用的方法"""
        python_files = self.get_python_files(self.project_root / "inkscape_wps")
        
        # 只检查私有 helper。公共方法可能由框架回调、反射或外部调用触发，
        # 简单静态搜索很容易造成大量误报。
        defined_methods = {}
        used_method_names = set()
        
        for filepath in python_files:
            tree = parse_python_file(filepath)
            if tree is None:
                continue
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            method_name = item.name
                            if method_name.startswith("_") and not (
                                method_name.startswith("__") and method_name.endswith("__")
                            ):
                                defined_methods[f"{node.name}.{method_name}"] = (
                                    filepath,
                                    item.lineno,
                                )
        
        for filepath in python_files:
            tree = parse_python_file(filepath)
            if tree is None:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    used_method_names.add(node.attr)
        
        for method_name, (filepath, line_no) in defined_methods.items():
            _, func_name = method_name.split(".")
            if func_name not in used_method_names:
                self.add_issue(Issue(
                    id=f"quality_unused_method_{method_name}",
                    title="未使用的方法",
                    description=f"方法 {method_name} 在 {filepath.name} 中定义但未被使用",
                    category=IssueCategory.CODE_QUALITY,
                    severity=IssueSeverity.LOW,
                    file_path=str(filepath),
                    line_number=line_no,
                    suggestion="考虑删除未使用的方法或检查是否应该被调用",
                ))
