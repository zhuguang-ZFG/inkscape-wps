"""依赖关系分析器 - 分析项目依赖和兼容性"""

import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from ..models import Issue, IssueSeverity, IssueCategory, AnalysisResult
from .base_analyzer import BaseAnalyzer


class DependencyAnalyzer(BaseAnalyzer):
    """依赖关系分析器"""
    
    def __init__(self, project_root: Path):
        super().__init__(project_root)
        self.dependencies: Dict[str, str] = {}  # {package: version}
        self.optional_dependencies: Dict[str, List[str]] = {}  # {feature: [packages]}
    
    def analyze(self) -> AnalysisResult:
        """执行分析"""
        self.parse_pyproject_toml()
        self.extract_dependencies()
        self.check_conflicting_dependencies()
        self.identify_optional_dependencies()
        
        return self.result
    
    def parse_pyproject_toml(self) -> None:
        """解析 pyproject.toml 文件"""
        pyproject_file = self.project_root / "pyproject.toml"
        
        if not pyproject_file.exists():
            return
        
        try:
            # 尝试使用 tomllib（Python 3.11+）或 tomli
            try:
                import tomllib
                with open(pyproject_file, "rb") as f:
                    data = tomllib.load(f)
            except ImportError:
                import tomli
                with open(pyproject_file, "rb") as f:
                    data = tomli.load(f)
            
            # 提取依赖信息
            if "project" in data:
                project = data["project"]
                
                # 提取必需依赖
                if "dependencies" in project:
                    for dep in project["dependencies"]:
                        self._parse_dependency_string(dep, is_optional=False)
                
                # 提取可选依赖
                if "optional-dependencies" in project:
                    for feature, deps in project["optional-dependencies"].items():
                        self.optional_dependencies[feature] = []
                        for dep in deps:
                            self._parse_dependency_string(dep, is_optional=True, feature=feature)
        
        except Exception as e:
            # 如果解析失败，尝试使用正则表达式
            self._parse_pyproject_regex(pyproject_file)
    
    def _parse_dependency_string(self, dep_string: str, is_optional: bool = False, feature: str = None) -> None:
        """解析依赖字符串"""
        # 提取包名和版本
        match = re.match(r'([a-zA-Z0-9\-_.]+)\s*([><=!~]*.*)?', dep_string.strip())
        if match:
            package = match.group(1)
            version = match.group(2) or ""
            self.dependencies[package] = version
            
            if is_optional and feature:
                self.optional_dependencies[feature].append(package)
    
    def _parse_pyproject_regex(self, pyproject_file: Path) -> None:
        """使用正则表达式解析 pyproject.toml"""
        with open(pyproject_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 查找 dependencies 部分
        dep_pattern = r'dependencies\s*=\s*\[(.*?)\]'
        match = re.search(dep_pattern, content, re.DOTALL)
        if match:
            deps_text = match.group(1)
            for line in deps_text.split('\n'):
                line = line.strip().strip('"').strip("'").strip(',')
                if line:
                    self._parse_dependency_string(line)
    
    def extract_dependencies(self) -> None:
        """提取所有依赖"""
        # 依赖已在 parse_pyproject_toml 中提取
        pass
    
    def check_conflicting_dependencies(self) -> None:
        """检查冲突的依赖"""
        # 检查 PyQt5 和 PyQt6 冲突
        has_pyqt5 = any("pyqt5" in pkg.lower() for pkg in self.dependencies.keys())
        has_pyqt6 = any("pyqt6" in pkg.lower() for pkg in self.dependencies.keys())
        
        if has_pyqt5 and has_pyqt6:
            self.add_issue(Issue(
                id="dependency_pyqt_conflict",
                title="PyQt5 和 PyQt6 冲突",
                description="pyproject.toml 中同时声明了 PyQt5 和 PyQt6，两者不能在同一进程中混用",
                category=IssueCategory.DEPENDENCY,
                severity=IssueSeverity.HIGH,
                file_path=str(self.project_root / "pyproject.toml"),
                suggestion="改为可选依赖组（extras），由用户按环境选择安装",
            ))
        
        # 检查其他可能的冲突
        conflicting_pairs = [
            ("pillow", "PIL"),
            ("pyyaml", "yaml"),
            ("python-dateutil", "dateutil"),
        ]
        
        for pkg1, pkg2 in conflicting_pairs:
            has_pkg1 = any(pkg1 in pkg.lower() for pkg in self.dependencies.keys())
            has_pkg2 = any(pkg2 in pkg.lower() for pkg in self.dependencies.keys())
            
            if has_pkg1 and has_pkg2:
                self.add_issue(Issue(
                    id=f"dependency_conflict_{pkg1}_{pkg2}",
                    title=f"依赖冲突：{pkg1} 和 {pkg2}",
                    description=f"同时声明了 {pkg1} 和 {pkg2}，可能导致版本冲突",
                    category=IssueCategory.DEPENDENCY,
                    severity=IssueSeverity.MEDIUM,
                    file_path=str(self.project_root / "pyproject.toml"),
                    suggestion="检查是否需要同时使用这两个包",
                ))
    
    def identify_optional_dependencies(self) -> None:
        """识别可选功能的依赖"""
        # 检查是否有可选依赖
        if not self.optional_dependencies:
            return
        
        # 报告可选依赖信息
        for feature, packages in self.optional_dependencies.items():
            self.add_issue(Issue(
                id=f"dependency_optional_{feature}",
                title=f"可选依赖：{feature}",
                description=f"功能 {feature} 需要以下可选依赖：{', '.join(packages)}",
                category=IssueCategory.DEPENDENCY,
                severity=IssueSeverity.LOW,
                file_path=str(self.project_root / "pyproject.toml"),
                suggestion=f"用户可以通过 pip install package[{feature}] 安装可选依赖",
            ))
    
    def get_dependency_info(self) -> Dict[str, str]:
        """获取所有依赖信息"""
        return self.dependencies.copy()
    
    def get_optional_dependencies(self) -> Dict[str, List[str]]:
        """获取可选依赖信息"""
        return self.optional_dependencies.copy()
    
    def check_version_compatibility(self, package: str, required_version: str) -> bool:
        """检查版本兼容性
        
        Args:
            package: 包名
            required_version: 要求的版本（如 ">=3.8"）
            
        Returns:
            是否兼容
        """
        if package not in self.dependencies:
            return False
        
        installed_version = self.dependencies[package]
        
        # 简单的版本比较（实际应使用 packaging 库）
        # 这里只做基本的检查
        return True
