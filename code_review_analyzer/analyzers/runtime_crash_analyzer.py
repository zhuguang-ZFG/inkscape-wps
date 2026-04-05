"""运行时崩溃问题检测器

本模块检测会导致运行时崩溃的代码问题，包括：
- 对 dataclass 对象调用不存在的方法（如 .get()）
- 对不支持的对象类型进行操作（如 len(VectorPath)）
- 访问不存在的属性
- 导入错误

这些问题被标记为 CRITICAL 严重程度，因为它们会导致程序无法运行。
"""

import ast
from pathlib import Path
from typing import List

from ..models import Issue, IssueSeverity, IssueCategory, AnalysisResult
from .base_analyzer import BaseAnalyzer
from .ast_utils import (
    parse_python_file,
    find_method_calls,
    find_attribute_access,
    find_imports,
    find_async_functions_without_await,
    get_all_exports,
)


class RuntimeCrashAnalyzer(BaseAnalyzer):
    """运行时崩溃问题检测器"""
    
    def analyze(self) -> AnalysisResult:
        """执行分析"""
        self.analyze_gcode_service()
        self.analyze_serial_service()
        self.analyze_font_service()
        self.analyze_qt_compat()
        return self.result
    
    def analyze_gcode_service(self) -> None:
        """分析 gcode_service.py 中的崩溃问题"""
        filepath = self.project_root / "inkscape_wps" / "core" / "services" / "gcode_service.py"
        
        if not filepath.exists():
            return
        
        tree = parse_python_file(filepath)
        if tree is None:
            return
        
        # 检查 .get() 调用（MachineConfig 是 dataclass，无 .get() 方法）
        get_calls = find_method_calls(tree, "get")
        for line_no, call_expr in get_calls:
            if "config" in call_expr.lower():
                self.add_issue(Issue(
                    id="gcode_service_001",
                    title="MachineConfig 对象调用 .get() 方法",
                    description="MachineConfig 是 dataclass，不支持 .get() 方法",
                    category=IssueCategory.RUNTIME_CRASH,
                    severity=IssueSeverity.CRITICAL,
                    file_path=str(filepath),
                    line_number=line_no,
                    code_snippet=call_expr,
                    error_type="AttributeError",
                    suggestion="使用 getattr(config, 'attr_name', default_value) 替代",
                ))
        
        # 检查 len() 调用（VectorPath 不支持 len()）
        len_calls = find_method_calls(tree, "len")
        for line_no, call_expr in len_calls:
            if "path" in call_expr.lower():
                self.add_issue(Issue(
                    id="gcode_service_002",
                    title="VectorPath 对象调用 len()",
                    description="VectorPath 不支持 len() 操作",
                    category=IssueCategory.RUNTIME_CRASH,
                    severity=IssueSeverity.CRITICAL,
                    file_path=str(filepath),
                    line_number=line_no,
                    code_snippet=call_expr,
                    error_type="TypeError",
                    suggestion="使用 len(path.points) 替代",
                ))
        
        # 检查不存在的属性访问
        problematic_attrs = ["gcode_g92_origin", "gcode_add_m30"]
        for attr in problematic_attrs:
            attr_accesses = find_attribute_access(tree, attr)
            for line_no, access_expr in attr_accesses:
                self.add_issue(Issue(
                    id=f"gcode_service_003_{attr}",
                    title=f"访问不存在的属性 {attr}",
                    description=f"MachineConfig 中不存在属性 {attr}",
                    category=IssueCategory.RUNTIME_CRASH,
                    severity=IssueSeverity.CRITICAL,
                    file_path=str(filepath),
                    line_number=line_no,
                    code_snippet=access_expr,
                    error_type="AttributeError",
                    suggestion=f"检查 MachineConfig 的实际属性名称",
                ))
    
    def analyze_serial_service(self) -> None:
        """分析 serial_service.py 中的崩溃问题"""
        filepath = self.project_root / "inkscape_wps" / "core" / "services" / "serial_service.py"
        
        if not filepath.exists():
            return
        
        tree = parse_python_file(filepath)
        if tree is None:
            return
        
        # 检查 async 函数中的问题
        async_funcs = find_async_functions_without_await(tree)
        for func_name, line_no in async_funcs:
            # 这可能是一个问题，但不一定是运行时崩溃
            pass
    
    def analyze_font_service(self) -> None:
        """分析 font_service.py 中的崩溃问题"""
        filepath = self.project_root / "inkscape_wps" / "core" / "services" / "font_service.py"
        
        if not filepath.exists():
            return
        
        tree = parse_python_file(filepath)
        if tree is None:
            return
        
        # 检查 async 函数中的问题
        async_funcs = find_async_functions_without_await(tree)
        for func_name, line_no in async_funcs:
            if func_name == "discover_fonts":
                self.add_issue(Issue(
                    id="font_service_001",
                    title="async 函数中无 await 调用",
                    description=f"函数 {func_name} 被标记为 async 但没有任何 await 调用",
                    category=IssueCategory.CODE_QUALITY,
                    severity=IssueSeverity.MEDIUM,
                    file_path=str(filepath),
                    line_number=line_no,
                    error_type="InconsistentAsyncDef",
                    suggestion="改为同步函数或添加 await 调用",
                ))
    
    def analyze_qt_compat(self) -> None:
        """分析 qt_compat.py 中的导入错误"""
        filepath = self.project_root / "inkscape_wps" / "ui" / "qt_compat.py"
        
        if not filepath.exists():
            return
        
        tree = parse_python_file(filepath)
        if tree is None:
            return
        
        # 检查 __all__ 中声明的导入
        all_exports = get_all_exports(tree)
        imports = find_imports(tree)
        imported_names = set()
        
        for line_no, module, alias in imports:
            # 提取导入的名称
            if "." in module:
                name = module.split(".")[-1]
            else:
                name = module
            imported_names.add(name)
        
        # 检查 __all__ 中是否有未导入的名称
        for export in all_exports:
            if export not in imported_names and export not in ["PYQT_VERSION"]:
                self.add_issue(Issue(
                    id=f"qt_compat_001_{export}",
                    title=f"__all__ 中声明但未导入的名称: {export}",
                    description=f"{export} 在 __all__ 中声明但未被导入",
                    category=IssueCategory.RUNTIME_CRASH,
                    severity=IssueSeverity.CRITICAL,
                    file_path=str(filepath),
                    error_type="ImportError",
                    suggestion=f"添加 {export} 的导入语句",
                ))
