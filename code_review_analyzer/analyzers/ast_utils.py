"""AST 解析工具

本模块提供了一系列 AST 解析工具函数，用于分析 Python 代码的结构和特性。
这些工具被各个分析器使用，以识别代码中的问题。

主要功能：
- 解析 Python 文件为 AST（支持缓存）
- 查找特定的代码模式（方法调用、属性访问、导入等）
- 提取代码结构信息（函数、类、方法等）
- 检测特定的代码问题（重复分支、async 无 await 等）

性能优化：
- 支持 AST 缓存，避免重复解析
- 基于文件内容哈希的缓存失效检测
"""

import ast
import locale
from pathlib import Path
from typing import List, Optional, Tuple

# 全局缓存管理器（延迟初始化）
_cache_manager = None


def _read_python_source(filepath: Path) -> str:
    """Read Python source with a pragmatic fallback for local legacy encodings."""
    encodings = ["utf-8", locale.getpreferredencoding(False)]
    tried: set[str] = set()
    last_error: UnicodeDecodeError | None = None

    for encoding in encodings:
        normalized = (encoding or "").strip()
        if not normalized or normalized in tried:
            continue
        tried.add(normalized)
        try:
            with open(filepath, "r", encoding=normalized) as f:
                return f.read()
        except UnicodeDecodeError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def set_cache_manager(cache_manager) -> None:
    """设置全局缓存管理器
    
    Args:
        cache_manager: CacheManager 实例
    """
    global _cache_manager
    _cache_manager = cache_manager


def parse_python_file(filepath: Path) -> Optional[ast.Module]:
    """解析 Python 文件为 AST
    
    支持缓存以提高性能。如果设置了缓存管理器，将使用缓存。
    
    Args:
        filepath: Python 文件路径
        
    Returns:
        AST Module 对象，如果解析失败返回 None
    """
    # 尝试从缓存获取
    if _cache_manager is not None:
        cached_tree = _cache_manager.get_cached_ast(filepath)
        if cached_tree is not None:
            return cached_tree
    
    try:
        source = _read_python_source(filepath)
        tree = ast.parse(source)
        
        # 缓存结果
        if _cache_manager is not None:
            _cache_manager.cache_ast(filepath, tree)
        
        return tree
    except (SyntaxError, UnicodeDecodeError, IOError):
        return None


def find_method_calls(tree: ast.Module, method_name: str) -> List[Tuple[int, str]]:
    """查找特定方法调用
    
    Args:
        tree: AST Module
        method_name: 方法名称
        
    Returns:
        (行号, 调用表达式) 列表
    """
    if tree is None:
        return []
    calls = []
    
    class MethodCallVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            # 检查是否是属性调用（如 obj.method()）
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == method_name:
                    calls.append((node.lineno, ast.unparse(node)))
            # 检查是否是直接函数调用
            elif isinstance(node.func, ast.Name):
                if node.func.id == method_name:
                    calls.append((node.lineno, ast.unparse(node)))
            self.generic_visit(node)
    
    visitor = MethodCallVisitor()
    visitor.visit(tree)
    return calls


def find_attribute_access(tree: ast.Module, attr_name: str) -> List[Tuple[int, str]]:
    """查找属性访问
    
    Args:
        tree: AST Module
        attr_name: 属性名称
        
    Returns:
        (行号, 属性访问表达式) 列表
    """
    if tree is None:
        return []
    accesses = []
    
    class AttributeVisitor(ast.NodeVisitor):
        def visit_Attribute(self, node: ast.Attribute) -> None:
            if node.attr == attr_name:
                accesses.append((node.lineno, ast.unparse(node)))
            self.generic_visit(node)
    
    visitor = AttributeVisitor()
    visitor.visit(tree)
    return accesses


def find_function_definitions(tree: ast.Module | None) -> List[Tuple[str, int, int]]:
    """提取函数定义
    
    Args:
        tree: AST Module
        
    Returns:
        (函数名, 起始行号, 结束行号) 列表
    """
    if tree is None:
        return []
    functions = []
    
    class FunctionVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            end_line = node.end_lineno or node.lineno
            functions.append((node.name, node.lineno, end_line))
            self.generic_visit(node)
        
        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            end_line = node.end_lineno or node.lineno
            functions.append((node.name, node.lineno, end_line))
            self.generic_visit(node)
    
    visitor = FunctionVisitor()
    visitor.visit(tree)
    return functions


def find_class_definitions(tree: ast.Module | None) -> List[Tuple[str, int, int]]:
    """提取类定义
    
    Args:
        tree: AST Module
        
    Returns:
        (类名, 起始行号, 结束行号) 列表
    """
    if tree is None:
        return []
    classes = []
    
    class ClassVisitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            end_line = node.end_lineno or node.lineno
            classes.append((node.name, node.lineno, end_line))
            self.generic_visit(node)
    
    visitor = ClassVisitor()
    visitor.visit(tree)
    return classes


def get_function_size(tree: ast.Module | None, func_name: str) -> Optional[int]:
    """获取函数的行数
    
    Args:
        tree: AST Module
        func_name: 函数名称
        
    Returns:
        函数行数，如果未找到返回 None
    """
    for name, start, end in find_function_definitions(tree):
        if name == func_name:
            return end - start + 1
    return None


def get_class_methods(tree: ast.Module | None, class_name: str) -> List[Tuple[str, int, int]]:
    """获取类的所有方法
    
    Args:
        tree: AST Module
        class_name: 类名称
        
    Returns:
        (方法名, 起始行号, 结束行号) 列表
    """
    if tree is None:
        return []
    methods = []
    
    class MethodVisitor(ast.NodeVisitor):
        def __init__(self):
            self.current_class = None
        
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            if node.name == class_name:
                self.current_class = class_name
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        end_line = item.end_lineno or item.lineno
                        methods.append((item.name, item.lineno, end_line))
                self.current_class = None
            self.generic_visit(node)
    
    visitor = MethodVisitor()
    visitor.visit(tree)
    return methods


def find_imports(tree: ast.Module | None) -> List[Tuple[int, str, Optional[str]]]:
    """查找所有导入语句
    
    Args:
        tree: AST Module
        
    Returns:
        (行号, 模块名, 别名) 列表
    """
    if tree is None:
        return []
    imports = []
    
    class ImportVisitor(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                imports.append((node.lineno, alias.name, alias.asname))
            self.generic_visit(node)
        
        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            module = node.module or ""
            for alias in node.names:
                imports.append((node.lineno, f"{module}.{alias.name}", alias.asname))
            self.generic_visit(node)
    
    visitor = ImportVisitor()
    visitor.visit(tree)
    return imports


def find_async_functions_without_await(tree: ast.Module | None) -> List[Tuple[str, int]]:
    """查找没有 await 调用的 async 函数
    
    Args:
        tree: AST Module
        
    Returns:
        (函数名, 行号) 列表
    """
    if tree is None:
        return []
    async_funcs_without_await = []
    
    class AsyncVisitor(ast.NodeVisitor):
        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            has_await = False
            
            class AwaitVisitor(ast.NodeVisitor):
                def visit_Await(self, node: ast.Await) -> None:
                    nonlocal has_await
                    has_await = True
            
            AwaitVisitor().visit(node)
            
            if not has_await:
                async_funcs_without_await.append((node.name, node.lineno))
            
            self.generic_visit(node)
    
    visitor = AsyncVisitor()
    visitor.visit(tree)
    return async_funcs_without_await


def count_lines(filepath: Path) -> int:
    """计算文件行数
    
    Args:
        filepath: 文件路径
        
    Returns:
        文件行数
    """
    try:
        return len(_read_python_source(filepath).splitlines())
    except (IOError, UnicodeDecodeError):
        return 0


def count_dataclass_fields(tree: ast.Module | None, class_name: str) -> int:
    """计算 dataclass 的字段数量
    
    Args:
        tree: AST Module
        class_name: 类名称
        
    Returns:
        字段数量
    """
    if tree is None:
        return 0
    count = 0
    
    class FieldVisitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            nonlocal count
            if node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.AnnAssign):
                        count += 1
            self.generic_visit(node)
    
    FieldVisitor().visit(tree)
    return count


def count_instance_variables(tree: ast.Module | None, class_name: str) -> int:
    """计算类的实例变量数量
    
    Args:
        tree: AST Module
        class_name: 类名称
        
    Returns:
        实例变量数量
    """
    if tree is None:
        return 0
    count = 0
    
    class VarVisitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            nonlocal count
            if node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        for stmt in ast.walk(item):
                            if isinstance(stmt, ast.Assign):
                                for target in stmt.targets:
                                    if isinstance(target, ast.Attribute):
                                        if (
                                            isinstance(target.value, ast.Name)
                                            and target.value.id == "self"
                                        ):
                                            count += 1
            self.generic_visit(node)
    
    VarVisitor().visit(tree)
    return count


def get_all_exports(tree: ast.Module | None) -> List[str]:
    """获取 __all__ 中声明的导出
    
    Args:
        tree: AST Module
        
    Returns:
        导出名称列表
    """
    if tree is None:
        return []
    exports = []
    
    class AllVisitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, ast.List):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant):
                                exports.append(elt.value)
            self.generic_visit(node)
    
    AllVisitor().visit(tree)
    return exports


def find_duplicate_branches(tree: ast.Module | None) -> List[Tuple[int, str]]:
    """查找重复的条件分支
    
    Args:
        tree: AST Module
        
    Returns:
        (行号, 分支类型) 列表
    """
    if tree is None:
        return []
    duplicates = []
    
    class BranchVisitor(ast.NodeVisitor):
        def visit_If(self, node: ast.If) -> None:
            if node.orelse:
                if_code = ast.unparse(node.body)
                else_code = ast.unparse(node.orelse)
                
                if if_code == else_code:
                    duplicates.append((node.lineno, "if-else"))
            
            self.generic_visit(node)
    
    BranchVisitor().visit(tree)
    return duplicates
