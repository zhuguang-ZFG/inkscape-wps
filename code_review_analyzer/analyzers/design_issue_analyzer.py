"""设计问题检测器

本模块检测代码中的设计问题，包括：
- 文件过大（>2000 行）
- 方法过大（>600 行）
- 数据类字段过多（>25 个）
- UI 状态变量过多（>15 个）
- 缺少必要的功能支持（如 SVG transform）
- 坐标变换顺序问题
- 锁内执行阻塞操作

这些问题被标记为 HIGH 或 MEDIUM 严重程度，影响代码的可维护性和性能。
"""

import ast
from pathlib import Path
from typing import List

from ..models import Issue, IssueSeverity, IssueCategory, AnalysisResult
from .base_analyzer import BaseAnalyzer
from .ast_utils import (
    parse_python_file,
    count_lines,
    find_function_definitions,
    find_class_definitions,
    find_attribute_access,
    find_method_calls,
    count_dataclass_fields,
    count_instance_variables,
)


class DesignIssueAnalyzer(BaseAnalyzer):
    """设计问题检测器"""
    
    def analyze(self) -> AnalysisResult:
        """执行分析"""
        self.check_file_sizes()
        self.check_method_sizes()
        self.check_config_bloat()
        self.check_ui_state_variables()
        self.check_svg_support()
        self.check_gcode_z_mode()
        self.check_coordinate_transform()
        self.check_file_io_in_lock()
        
        return self.result
    
    def check_file_sizes(self) -> None:
        """检查文件大小（>2000 行标记为问题）"""
        python_files = self.get_python_files(self.project_root / "inkscape_wps")
        
        for filepath in python_files:
            lines = count_lines(filepath)
            if lines > 2000:
                self.add_issue(Issue(
                    id=f"design_file_size_{filepath.name}",
                    title=f"文件过大：{filepath.name}",
                    description=f"文件 {filepath.name} 包含 {lines} 行代码，超过 2000 行的建议上限",
                    category=IssueCategory.DESIGN,
                    severity=IssueSeverity.HIGH,
                    file_path=str(filepath),
                    suggestion="考虑按功能拆分文件，遵循单一职责原则",
                ))
    
    def check_method_sizes(self) -> None:
        """检查方法大小（>600 行标记为问题）"""
        python_files = self.get_python_files(self.project_root / "inkscape_wps")
        
        for filepath in python_files:
            tree = parse_python_file(filepath)
            if tree is None:
                continue
            
            functions = find_function_definitions(tree)
            for func_name, start_line, end_line in functions:
                size = end_line - start_line + 1
                if size > 600:
                    self.add_issue(Issue(
                        id=f"design_method_size_{filepath.name}_{func_name}",
                        title=f"方法过大：{func_name}",
                        description=f"方法 {func_name} 在 {filepath.name} 中包含 {size} 行代码，超过 600 行的建议上限",
                        category=IssueCategory.DESIGN,
                        severity=IssueSeverity.HIGH,
                        file_path=str(filepath),
                        line_number=start_line,
                        suggestion="考虑将方法拆分为多个较小的方法",
                    ))
    
    def check_config_bloat(self) -> None:
        """检查 MachineConfig 字段数量（>25 个标记为问题）"""
        config_file = self.project_root / "inkscape_wps" / "core" / "config.py"
        
        if not config_file.exists():
            return
        
        tree = parse_python_file(config_file)
        if tree is None:
            return
        
        # 查找 MachineConfig 类
        classes = find_class_definitions(tree)
        for class_name, start_line, end_line in classes:
            if class_name == "MachineConfig":
                # 计算字段数量
                field_count = count_dataclass_fields(tree, class_name)
                if field_count > 25:
                    self.add_issue(Issue(
                        id="design_config_bloat",
                        title="MachineConfig 字段过多",
                        description=f"MachineConfig 包含 {field_count} 个字段，超过 25 个的建议上限",
                        category=IssueCategory.DESIGN,
                        severity=IssueSeverity.HIGH,
                        file_path=str(config_file),
                        line_number=start_line,
                        suggestion="考虑拆分为 MachineConfig（硬件参数）和 AppPreferences（UI 状态）",
                    ))
    
    def check_ui_state_variables(self) -> None:
        """检查 MainWindow 状态变量数量（>15 个标记为问题）"""
        main_window_file = self.project_root / "inkscape_wps" / "ui" / "main_window.py"
        
        if not main_window_file.exists():
            return
        
        tree = parse_python_file(main_window_file)
        if tree is None:
            return
        
        # 查找 MainWindow 类中的状态变量
        state_vars = count_instance_variables(tree, "MainWindow")
        if state_vars > 15:
            self.add_issue(Issue(
                id="design_ui_state_bloat",
                title="MainWindow 状态变量过多",
                description=f"MainWindow 包含 {state_vars} 个状态变量，超过 15 个的建议上限",
                category=IssueCategory.DESIGN,
                severity=IssueSeverity.HIGH,
                file_path=str(main_window_file),
                suggestion="考虑提取状态变量为独立的状态管理类",
            ))
    
    def check_svg_support(self) -> None:
        """检查 SVG transform 和 use 元素支持"""
        svg_file = self.project_root / "inkscape_wps" / "core" / "svg_import.py"
        
        if not svg_file.exists():
            return
        
        tree = parse_python_file(svg_file)
        if tree is None:
            return
        
        # 检查 transform 属性支持 - 查找 transform 相关的处理
        functions = find_function_definitions(tree)
        has_transform_support = False
        has_use_support = False
        
        for func_name, _, _ in functions:
            if "transform" in func_name.lower():
                has_transform_support = True
            if "use" in func_name.lower():
                has_use_support = True
        
        # 检查源代码中的 transform 处理
        with open(svg_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        if "transform" not in content or "matrix" not in content:
            self.add_issue(Issue(
                id="design_svg_transform",
                title="SVG transform 属性不支持",
                description="svg_import.py 不支持 SVG transform 属性（translate、rotate、scale、matrix）",
                category=IssueCategory.DESIGN,
                severity=IssueSeverity.HIGH,
                file_path=str(svg_file),
                suggestion="添加基础矩阵变换支持，处理 SVG transform 属性",
            ))
        
        # 检查 use 元素支持
        if "<use>" not in content and "use" not in content.lower():
            self.add_issue(Issue(
                id="design_svg_use",
                title="SVG use 元素不支持",
                description="svg_import.py 不支持 SVG <use> 元素（符号引用）",
                category=IssueCategory.DESIGN,
                severity=IssueSeverity.HIGH,
                file_path=str(svg_file),
                suggestion="添加对 SVG <use> 元素的支持",
            ))
    
    def check_gcode_z_mode(self) -> None:
        """检查 Z 模式下是否发送 M5 命令"""
        gcode_file = self.project_root / "inkscape_wps" / "core" / "gcode.py"
        
        if not gcode_file.exists():
            return
        
        tree = parse_python_file(gcode_file)
        if tree is None:
            return
        
        # 查找 paths_to_gcode 函数
        functions = find_function_definitions(tree)
        for func_name, start_line, end_line in functions:
            if func_name == "paths_to_gcode":
                # 检查是否有条件发送 M5
                with open(gcode_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    func_content = "".join(lines[start_line-1:end_line])
                
                # 检查是否有 "if use_m3m5" 条件
                if "if use_m3m5" in func_content and 'lines.append("M5")' in func_content:
                    # 已修正，不报告问题
                    pass
                elif 'lines.append("M5")' in func_content and "if use_m3m5" not in func_content:
                    # 未修正，报告问题
                    self.add_issue(Issue(
                        id="design_gcode_m5",
                        title="Z 模式下仍然发送 M5 命令",
                        description="gcode.py 在 Z 轴模式下仍然发送 M5 命令，与 Z 轴模式的设计不一致",
                        category=IssueCategory.DESIGN,
                        severity=IssueSeverity.HIGH,
                        file_path=str(gcode_file),
                        line_number=start_line,
                        suggestion="改为仅在 M3/M5 模式下发送 M5 命令",
                    ))
    
    def check_coordinate_transform(self) -> None:
        """检查坐标变换顺序问题"""
        coord_file = self.project_root / "inkscape_wps" / "core" / "coordinate_transform.py"
        
        if not coord_file.exists():
            return
        
        with open(coord_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 检查是否有镜像后缩放的问题
        if "mirror" in content and "scale" in content:
            # 检查顺序
            mirror_pos = content.find("mirror")
            scale_pos = content.find("scale")
            
            if mirror_pos < scale_pos:
                self.add_issue(Issue(
                    id="design_coord_transform",
                    title="坐标变换顺序问题",
                    description="coordinate_transform.py 中镜像后缩放的顺序导致枢轴点偏移",
                    category=IssueCategory.DESIGN,
                    severity=IssueSeverity.MEDIUM,
                    file_path=str(coord_file),
                    suggestion="明确文档说明当前行为，或修正为'以枢轴为中心缩放'",
                ))
    
    def check_file_io_in_lock(self) -> None:
        """检查锁内文件 I/O 操作"""
        hershey_file = self.project_root / "inkscape_wps" / "core" / "hershey.py"
        
        if not hershey_file.exists():
            return
        
        tree = parse_python_file(hershey_file)
        if tree is None:
            return
        
        # 查找在锁内执行文件 I/O 的代码
        with open(hershey_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 简单的启发式检查：查找 with lock 和 open 的组合
        if "with" in content and "lock" in content and "open(" in content:
            # 检查是否在同一个 with 块中
            lines = content.split("\n")
            in_lock_block = False
            for i, line in enumerate(lines):
                if "with" in line and "lock" in line:
                    in_lock_block = True
                    # 检查接下来的 10 行是否有 open()
                    for j in range(i, min(i+10, len(lines))):
                        if "open(" in lines[j]:
                            self.add_issue(Issue(
                                id="design_file_io_in_lock",
                                title="锁内执行文件 I/O 操作",
                                description="hershey.py 在锁内执行文件 I/O 操作，可能阻塞 UI 线程",
                                category=IssueCategory.DESIGN,
                                severity=IssueSeverity.MEDIUM,
                                file_path=str(hershey_file),
                                line_number=i+1,
                                suggestion="改为锁外读文件、锁内更新状态，或使用后台线程",
                            ))
                            return
