"""Runtime crash analyzer for Services layer."""

import ast
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple

from ..models import Issue, IssueSeverity, IssueCategory, AnalysisResult
from .base_analyzer import BaseAnalyzer


class RuntimeCrashAnalyzer(BaseAnalyzer):
    """Analyzer for detecting runtime crash issues in Services layer."""

    def analyze(self) -> AnalysisResult:
        """Run the analysis for runtime crashes.

        Returns:
            AnalysisResult containing all runtime crash issues found
        """
        self.result = AnalysisResult(analyzer_name=self.__class__.__name__)

        # Analyze each service file
        self.analyze_gcode_service()
        self.analyze_serial_service()
        self.analyze_font_service()
        self.analyze_qt_compat()

        return self.result

    def analyze_gcode_service(self) -> None:
        """Analyze gcode_service.py for runtime crash issues."""
        file_path = "inkscape_wps/core/services/gcode_service.py"
        content = self._read_file(file_path)
        if not content:
            return

        # Issue 1: self.config.get(...) - MachineConfig is dataclass without .get()
        if re.search(r'self\.config\.get\s*\(', content):
            self.result.add_issue(Issue(
                id="gcode_crash_001",
                title="MachineConfig.get() method does not exist",
                description="MachineConfig is a dataclass and does not have a .get() method. "
                           "Calling self.config.get(...) will raise AttributeError at runtime.",
                severity=IssueSeverity.CRITICAL,
                category=IssueCategory.RUNTIME_CRASH,
                location=f"{file_path}:35",
                impact="Runtime crash with AttributeError when accessing config values",
                suggestion="Use getattr(self.config, 'key', default) or direct attribute access instead of .get()",
                tags=["dataclass", "method-missing"]
            ))

        # Issue 2: len(path) - VectorPath doesn't support len()
        if re.search(r'len\s*\(\s*path\s*\)', content):
            self.result.add_issue(Issue(
                id="gcode_crash_002",
                title="VectorPath does not support len()",
                description="VectorPath is a dataclass without __len__ method. "
                           "Calling len(path) will raise TypeError at runtime.",
                severity=IssueSeverity.CRITICAL,
                category=IssueCategory.RUNTIME_CRASH,
                location=f"{file_path}:55",
                impact="Runtime crash with TypeError when checking path length",
                suggestion="Use len(path.points) instead of len(path)",
                tags=["vectorpath", "len-unsupported"]
            ))

        # Issue 3: path1[-1] - VectorPath doesn't support indexing
        if re.search(r'path\s*\[\s*-?\d+\s*\]', content):
            self.result.add_issue(Issue(
                id="gcode_crash_003",
                title="VectorPath does not support indexing",
                description="VectorPath does not support subscript access like path[-1]. "
                           "This will raise TypeError at runtime.",
                severity=IssueSeverity.CRITICAL,
                category=IssueCategory.RUNTIME_CRASH,
                location=f"{file_path}:28",
                impact="Runtime crash with TypeError when accessing path elements",
                suggestion="Use path.points[-1] instead of path[-1]",
                tags=["vectorpath", "indexing-unsupported"]
            ))

        # Issue 4: path1 + path2 - VectorPath doesn't support + operator
        if re.search(r'path\s*\+\s*path', content):
            self.result.add_issue(Issue(
                id="gcode_crash_004",
                title="VectorPath does not support + operator",
                description="VectorPath does not support concatenation with + operator. "
                           "This will raise TypeError at runtime.",
                severity=IssueSeverity.CRITICAL,
                category=IssueCategory.RUNTIME_CRASH,
                location=f"{file_path}:130",
                impact="Runtime crash with TypeError when concatenating paths",
                suggestion="Use VectorPath(tuple(path1.points + path2.points)) instead of path1 + path2",
                tags=["vectorpath", "operator-unsupported"]
            ))

        # Issue 5: gcode_g92_origin attribute doesn't exist
        if re.search(r'self\.config\.gcode_g92_origin', content):
            self.result.add_issue(Issue(
                id="gcode_crash_005",
                title="MachineConfig.gcode_g92_origin attribute does not exist",
                description="MachineConfig dataclass does not have gcode_g92_origin attribute. "
                           "Accessing this attribute will raise AttributeError at runtime.",
                severity=IssueSeverity.CRITICAL,
                category=IssueCategory.RUNTIME_CRASH,
                location=f"{file_path}:28",
                impact="Runtime crash with AttributeError when accessing non-existent config attribute",
                suggestion="Remove this attribute access or add it to MachineConfig dataclass",
                tags=["attribute-missing", "config"]
            ))

        # Issue 6: gcode_add_m30 attribute doesn't exist
        if re.search(r'self\.config\.gcode_add_m30', content):
            self.result.add_issue(Issue(
                id="gcode_crash_006",
                title="MachineConfig.gcode_add_m30 attribute does not exist",
                description="MachineConfig dataclass does not have gcode_add_m30 attribute. "
                           "Accessing this attribute will raise AttributeError at runtime.",
                severity=IssueSeverity.CRITICAL,
                category=IssueCategory.RUNTIME_CRASH,
                location=f"{file_path}:28",
                impact="Runtime crash with AttributeError when accessing non-existent config attribute",
                suggestion="Remove this attribute access or add it to MachineConfig dataclass",
                tags=["attribute-missing", "config"]
            ))

    def analyze_serial_service(self) -> None:
        """Analyze serial_service.py for runtime crash issues."""
        file_path = "inkscape_wps/core/services/serial_service.py"
        content = self._read_file(file_path)
        if not content:
            return

        # Issue 1: GrblController(port, baudrate) - constructor signature mismatch
        if re.search(r'GrblController\s*\(\s*port\s*,\s*baudrate\s*\)', content):
            self.result.add_issue(Issue(
                id="serial_crash_001",
                title="GrblController constructor signature mismatch",
                description="GrblController expects a SerialLike object, not port and baudrate strings. "
                           "Calling GrblController(port, baudrate) will raise TypeError at runtime.",
                severity=IssueSeverity.CRITICAL,
                category=IssueCategory.RUNTIME_CRASH,
                location=f"{file_path}:47",
                impact="Runtime crash with TypeError when instantiating GrblController",
                suggestion="Create a serial.Serial object first, then pass it to GrblController(serial_obj)",
                tags=["constructor", "signature-mismatch"]
            ))

        # Issue 2: await self._controller.connect() - method doesn't exist
        if re.search(r'await\s+self\._controller\.connect\s*\(', content):
            self.result.add_issue(Issue(
                id="serial_crash_002",
                title="GrblController.connect() async method does not exist",
                description="GrblController does not have an async connect() method. "
                           "Calling await self._controller.connect() will raise AttributeError at runtime.",
                severity=IssueSeverity.CRITICAL,
                category=IssueCategory.RUNTIME_CRASH,
                location=f"{file_path}:48",
                impact="Runtime crash with AttributeError when calling non-existent async method",
                suggestion="Use synchronous initialization or check GrblController API for correct method names",
                tags=["method-missing", "async"]
            ))

        # Issue 3: self._controller.buffer_full() - method doesn't exist
        if re.search(r'self\._controller\.buffer_full\s*\(', content):
            self.result.add_issue(Issue(
                id="serial_crash_003",
                title="GrblController.buffer_full() method does not exist",
                description="GrblController does not have a buffer_full() method. "
                           "Calling this method will raise AttributeError at runtime.",
                severity=IssueSeverity.CRITICAL,
                category=IssueCategory.RUNTIME_CRASH,
                location=f"{file_path}:95",
                impact="Runtime crash with AttributeError when calling non-existent method",
                suggestion="Check GrblController API for correct method to check buffer status",
                tags=["method-missing"]
            ))

    def analyze_font_service(self) -> None:
        """Analyze font_service.py for runtime crash issues."""
        file_path = "inkscape_wps/core/services/font_service.py"
        content = self._read_file(file_path)
        if not content:
            return

        # Parse the file to check for indentation issues
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            self.result.add_error(f"Failed to parse {file_path}: {e}")
            return

        # Issue 1: for stroke loop indentation error - char_info may be undefined
        # Look for the pattern where for loop is outside if block
        lines = content.split('\n')
        for i, line in enumerate(lines):
            # Check for the specific pattern: for stroke in char_info.get('strokes', [])
            if re.search(r'for\s+stroke\s+in\s+char_info\.get\s*\(\s*[\'"]strokes[\'"]\s*,\s*\[\s*\)', line):
                # Check if this line is at a lower indentation than the if block above
                current_indent = len(line) - len(line.lstrip())
                
                # Look backwards for the if statement
                for j in range(i - 1, max(0, i - 10), -1):
                    prev_line = lines[j]
                    if re.search(r'if\s+[\'"]characters[\'"]\s+in\s+', prev_line):
                        prev_indent = len(prev_line) - len(prev_line.lstrip())
                        if current_indent <= prev_indent:
                            self.result.add_issue(Issue(
                                id="font_crash_001",
                                title="for loop indentation error - char_info may be undefined",
                                description="The 'for stroke' loop is at the same or lower indentation level as the 'if' block, "
                                           "meaning char_info may not be defined when the loop executes. "
                                           "This will raise NameError at runtime.",
                                severity=IssueSeverity.CRITICAL,
                                category=IssueCategory.RUNTIME_CRASH,
                                location=f"{file_path}:{i+1}",
                                impact="Runtime crash with NameError when char_info is not defined",
                                suggestion="Indent the 'for stroke' loop to be inside the 'if' block",
                                tags=["indentation", "undefined-variable"]
                            ))
                            break

    def analyze_qt_compat(self) -> None:
        """Analyze qt_compat.py for import errors."""
        file_path = "inkscape_wps/ui/qt_compat.py"
        content = self._read_file(file_path)
        if not content:
            return

        # Issue 1: QShowEvent not imported in PyQt5 branch but in __all__
        # Check if QShowEvent is in __all__
        if re.search(r'[\'"]QShowEvent[\'"]', content):
            # Check if it's imported in PyQt5 branch
            pyqt5_section = re.search(
                r'except ImportError:.*?from PyQt5\.QtGui import \((.*?)\)',
                content,
                re.DOTALL
            )
            
            if pyqt5_section:
                imports_text = pyqt5_section.group(1)
                if 'QShowEvent' not in imports_text:
                    self.result.add_issue(Issue(
                        id="qt_crash_001",
                        title="QShowEvent not imported in PyQt5 branch",
                        description="QShowEvent is listed in __all__ but not imported in the PyQt5 fallback branch. "
                                   "This will raise ImportError when trying to import QShowEvent on PyQt5.",
                        severity=IssueSeverity.CRITICAL,
                        category=IssueCategory.RUNTIME_CRASH,
                        location=f"{file_path}:50",
                        impact="Runtime crash with ImportError when importing from qt_compat on PyQt5",
                        suggestion="Add QShowEvent to the PyQt5 imports from PyQt5.QtGui",
                        tags=["import-missing", "pyqt5"]
                    ))
