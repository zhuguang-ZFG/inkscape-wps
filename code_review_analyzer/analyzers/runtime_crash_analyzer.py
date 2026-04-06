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

from ..models import AnalysisResult, Issue, IssueCategory, IssueSeverity
from .ast_utils import (
    find_async_functions_without_await,
    find_attribute_access,
    find_imports,
    find_method_calls,
    get_all_exports,
    parse_python_file,
)
from .base_analyzer import BaseAnalyzer


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
                self._add_issue_pair(
                    primary_id="gcode_service_001",
                    legacy_id="gcode_crash_001",
                    title="MachineConfig 对象调用 .get() 方法",
                    description="MachineConfig 是 dataclass，不支持 .get() 方法",
                    file_path=filepath,
                    line_number=line_no,
                    code_snippet=call_expr,
                    error_type="AttributeError",
                    suggestion="使用 getattr(config, 'attr_name', default_value) 替代",
                )

        # 检查 len(path) 调用（VectorPath 不支持 len()）
        for line_no, call_expr in self._find_len_calls_on_path_variables(tree):
            self._add_issue_pair(
                primary_id="gcode_service_002",
                legacy_id="gcode_crash_002",
                title="VectorPath 对象调用 len()",
                description="VectorPath 不支持 len() 操作",
                file_path=filepath,
                line_number=line_no,
                code_snippet=call_expr,
                error_type="TypeError",
                suggestion="使用 len(path.points) 替代",
            )

        self._report_first_path_index_issue(tree, filepath)
        self._report_first_path_concat_issue(tree, filepath)

        # 检查不存在的属性访问
        legacy_attr_ids = {
            "gcode_g92_origin": "gcode_crash_005",
            "gcode_add_m30": "gcode_crash_006",
        }
        for attr, legacy_id in legacy_attr_ids.items():
            attr_accesses = find_attribute_access(tree, attr)
            for line_no, access_expr in attr_accesses:
                self._add_issue_pair(
                    primary_id=f"gcode_service_003_{attr}",
                    legacy_id=legacy_id,
                    title=f"访问不存在的属性 {attr}",
                    description=f"MachineConfig 中不存在属性 {attr}",
                    file_path=filepath,
                    line_number=line_no,
                    code_snippet=access_expr,
                    error_type="AttributeError",
                    suggestion="检查 MachineConfig 的实际属性名称",
                )

    def _find_len_calls_on_path_variables(self, tree: ast.Module) -> list[tuple[int, str]]:
        matches = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "len":
                continue
            if len(node.args) != 1 or node.keywords:
                continue

            arg = node.args[0]
            if isinstance(arg, ast.Name) and arg.id == "path":
                matches.append((node.lineno, ast.unparse(node)))

        return matches

    def _report_first_path_index_issue(self, tree: ast.Module, filepath: Path) -> None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript) or not isinstance(node.value, ast.Name):
                continue
            if not node.value.id.startswith("path"):
                continue
            self.add_issue(Issue(
                id="gcode_crash_003",
                title="VectorPath 被当作可下标序列访问",
                description="VectorPath 不支持通过索引直接访问首尾元素",
                category=IssueCategory.RUNTIME_CRASH,
                severity=IssueSeverity.CRITICAL,
                file_path=str(filepath),
                line_number=node.lineno,
                code_snippet=ast.unparse(node),
                error_type="TypeError",
                suggestion="改为访问 path.points[0] 或 path.points[-1]",
            ))
            return

    def _report_first_path_concat_issue(self, tree: ast.Module, filepath: Path) -> None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Add):
                continue
            if not isinstance(node.left, ast.Name) or not isinstance(node.right, ast.Name):
                continue
            if not (node.left.id.startswith("path") and node.right.id.startswith("path")):
                continue
            self.add_issue(Issue(
                id="gcode_crash_004",
                title="VectorPath 被直接拼接",
                description="VectorPath 对象不支持直接使用 + 运算进行合并",
                category=IssueCategory.RUNTIME_CRASH,
                severity=IssueSeverity.CRITICAL,
                file_path=str(filepath),
                line_number=node.lineno,
                code_snippet=ast.unparse(node),
                error_type="TypeError",
                suggestion="改为拼接 path.points 或使用专用合并逻辑",
            ))
            return

    def analyze_serial_service(self) -> None:
        """分析 serial_service.py 中的崩溃问题"""
        filepath = self.project_root / "inkscape_wps" / "core" / "services" / "serial_service.py"

        if not filepath.exists():
            return

        tree = parse_python_file(filepath)
        if tree is None:
            return

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "GrblController"
            ):
                if len(node.args) >= 2:
                    self.add_issue(Issue(
                        id="serial_crash_001",
                        title="GrblController 构造参数与当前接口不匹配",
                        description="直接传入 port, baudrate 可能与控制器当前构造签名不一致",
                        category=IssueCategory.RUNTIME_CRASH,
                        severity=IssueSeverity.CRITICAL,
                        file_path=str(filepath),
                        line_number=node.lineno,
                        code_snippet=ast.unparse(node),
                        error_type="TypeError",
                        suggestion="检查 GrblController 的构造签名并使用兼容参数",
                    ))
                    break

        for node in ast.walk(tree):
            if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
                call = node.value
                if isinstance(call.func, ast.Attribute) and call.func.attr == "connect":
                    if (
                        isinstance(call.func.value, ast.Attribute)
                        and call.func.value.attr == "_controller"
                    ):
                        self.add_issue(Issue(
                            id="serial_crash_002",
                            title="控制器 connect() 调用方式可能不兼容",
                            description="控制器对象可能不存在可 await 的 connect() 方法",
                            category=IssueCategory.RUNTIME_CRASH,
                            severity=IssueSeverity.CRITICAL,
                            file_path=str(filepath),
                            line_number=node.lineno,
                            code_snippet=ast.unparse(node),
                            error_type="AttributeError",
                            suggestion="核对控制器连接接口是否由外层服务负责",
                        ))
                        break

        for line_no, call_expr in find_method_calls(tree, "buffer_full"):
            if "_controller" not in call_expr:
                continue
            self.add_issue(Issue(
                id="serial_crash_003",
                title="控制器 buffer_full() 调用可能不存在",
                description="控制器对象可能未暴露 buffer_full() 方法",
                category=IssueCategory.RUNTIME_CRASH,
                severity=IssueSeverity.CRITICAL,
                file_path=str(filepath),
                line_number=line_no,
                code_snippet=call_expr,
                error_type="AttributeError",
                suggestion="改为使用当前协议层提供的缓冲区状态接口",
            ))
            break

        # async 无 await 仍归类为代码质量，不在此报告为崩溃问题
        _ = find_async_functions_without_await(tree)

    def analyze_font_service(self) -> None:
        """分析 font_service.py 中的崩溃问题"""
        filepath = self.project_root / "inkscape_wps" / "core" / "services" / "font_service.py"

        if not filepath.exists():
            return

        tree = parse_python_file(filepath)
        if tree is None:
            return

        for node in ast.walk(tree):
            if not isinstance(node, ast.For):
                continue
            if not isinstance(node.iter, ast.Call):
                continue
            if not isinstance(node.iter.func, ast.Attribute):
                continue
            if node.iter.func.attr != "get":
                continue
            if (
                not isinstance(node.iter.func.value, ast.Name)
                or node.iter.func.value.id != "char_info"
            ):
                continue
            self.add_issue(Issue(
                id="font_crash_001",
                title="char_info 可能在循环前未定义",
                description=(
                    "循环直接依赖 char_info.get(...)，"
                    "当条件未命中时会触发 UnboundLocalError"
                ),
                category=IssueCategory.RUNTIME_CRASH,
                severity=IssueSeverity.CRITICAL,
                file_path=str(filepath),
                line_number=node.lineno,
                code_snippet=ast.unparse(node.iter),
                error_type="UnboundLocalError",
                suggestion="将循环放入条件分支内部，或提前初始化 char_info",
            ))
            return

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

        source = filepath.read_text(encoding="utf-8")
        if "'QShowEvent'" in source or '"QShowEvent"' in source:
            pyqt5_branch = self._extract_except_import_block(source)
            if pyqt5_branch and "QShowEvent" not in pyqt5_branch:
                self.add_issue(Issue(
                    id="qt_crash_001",
                    title="PyQt5 分支缺少 QShowEvent 导入",
                    description=(
                        "qt_compat.py 在 PyQt5 回退分支中未导入 QShowEvent，"
                        "但 __all__ 暴露了该名称"
                    ),
                    category=IssueCategory.RUNTIME_CRASH,
                    severity=IssueSeverity.CRITICAL,
                    file_path=str(filepath),
                    error_type="ImportError",
                    suggestion="在 PyQt5 分支补充 QShowEvent 导入或移出 __all__",
                ))

    def _extract_except_import_block(self, source: str) -> str:
        in_except = False
        collected: list[str] = []
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("except ImportError"):
                in_except = True
                continue
            if in_except and stripped.startswith("__all__"):
                break
            if in_except:
                collected.append(line)
        return "\n".join(collected)

    def _add_issue_pair(
        self,
        *,
        primary_id: str,
        legacy_id: str,
        title: str,
        description: str,
        file_path: Path,
        line_number: int | None,
        code_snippet: str | None,
        error_type: str,
        suggestion: str,
    ) -> None:
        for issue_id in (primary_id, legacy_id):
            self.add_issue(Issue(
                id=issue_id,
                title=title,
                description=description,
                category=IssueCategory.RUNTIME_CRASH,
                severity=IssueSeverity.CRITICAL,
                file_path=str(file_path),
                line_number=line_number,
                code_snippet=code_snippet,
                error_type=error_type,
                suggestion=suggestion,
            ))
