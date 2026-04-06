"""Unit tests for RuntimeCrashAnalyzer."""


import pytest

from code_review_analyzer.analyzers.runtime_crash_analyzer import RuntimeCrashAnalyzer
from code_review_analyzer.models import IssueCategory, IssueSeverity


class TestRuntimeCrashAnalyzer:
    """Test cases for RuntimeCrashAnalyzer."""

    @pytest.fixture
    def analyzer(self, tmp_path):
        """Create a RuntimeCrashAnalyzer instance with a temporary project path."""
        return RuntimeCrashAnalyzer(tmp_path)

    def test_analyze_gcode_service_config_get_method(self, analyzer, tmp_path):
        """Test detection of self.config.get() call on dataclass."""
        # Create a mock gcode_service.py with the issue
        services_dir = tmp_path / "inkscape_wps" / "core" / "services"
        services_dir.mkdir(parents=True)
        
        gcode_file = services_dir / "gcode_service.py"
        gcode_file.write_text("""
class GCodeService:
    def __init__(self, config):
        self.config = config
    
    def optimize_paths(self, paths):
        min_length = self.config.get('min_path_length', 0.1)
        return paths
""")
        
        result = analyzer.analyze()
        
        # Check that the issue was detected
        issues = [i for i in result.issues if i.id == "gcode_crash_001"]
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.CRITICAL
        assert issues[0].category == IssueCategory.RUNTIME_CRASH

    def test_analyze_gcode_service_len_path(self, analyzer, tmp_path):
        """Test detection of len(path) call on VectorPath."""
        services_dir = tmp_path / "inkscape_wps" / "core" / "services"
        services_dir.mkdir(parents=True)
        
        gcode_file = services_dir / "gcode_service.py"
        gcode_file.write_text("""
class GCodeService:
    def _path_length(self, path):
        if len(path) < 2:
            return 0.0
        return 1.0
""")
        
        result = analyzer.analyze()
        
        issues = [i for i in result.issues if i.id == "gcode_crash_002"]
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.CRITICAL

    def test_analyze_gcode_service_path_indexing(self, analyzer, tmp_path):
        """Test detection of path[-1] indexing on VectorPath."""
        services_dir = tmp_path / "inkscape_wps" / "core" / "services"
        services_dir.mkdir(parents=True)
        
        gcode_file = services_dir / "gcode_service.py"
        gcode_file.write_text("""
class GCodeService:
    def _paths_adjacent(self, path1, path2):
        end_point = path1[-1]
        start_point = path2[0]
        return True
""")
        
        result = analyzer.analyze()
        
        issues = [i for i in result.issues if i.id == "gcode_crash_003"]
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.CRITICAL

    def test_analyze_gcode_service_path_concatenation(self, analyzer, tmp_path):
        """Test detection of path1 + path2 concatenation."""
        services_dir = tmp_path / "inkscape_wps" / "core" / "services"
        services_dir.mkdir(parents=True)
        
        gcode_file = services_dir / "gcode_service.py"
        gcode_file.write_text("""
class GCodeService:
    def _merge_two_paths(self, path1, path2):
        return path1 + path2
""")
        
        result = analyzer.analyze()
        
        issues = [i for i in result.issues if i.id == "gcode_crash_004"]
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.CRITICAL

    def test_analyze_gcode_service_missing_attributes(self, analyzer, tmp_path):
        """Test detection of missing gcode_g92_origin and gcode_add_m30 attributes."""
        services_dir = tmp_path / "inkscape_wps" / "core" / "services"
        services_dir.mkdir(parents=True)
        
        gcode_file = services_dir / "gcode_service.py"
        gcode_file.write_text("""
class GCodeService:
    def generate_from_paths(self, paths):
        gcode = paths_to_gcode(
            g92_origin=self.config.gcode_g92_origin,
            add_m30=self.config.gcode_add_m30
        )
        return gcode
""")
        
        result = analyzer.analyze()
        
        # Check for both missing attributes
        g92_issues = [i for i in result.issues if i.id == "gcode_crash_005"]
        m30_issues = [i for i in result.issues if i.id == "gcode_crash_006"]
        
        assert len(g92_issues) == 1
        assert len(m30_issues) == 1
        assert g92_issues[0].severity == IssueSeverity.CRITICAL
        assert m30_issues[0].severity == IssueSeverity.CRITICAL

    def test_analyze_serial_service_constructor_signature(self, analyzer, tmp_path):
        """Test detection of GrblController(port, baudrate) constructor call."""
        services_dir = tmp_path / "inkscape_wps" / "core" / "services"
        services_dir.mkdir(parents=True)
        
        serial_file = services_dir / "serial_service.py"
        serial_file.write_text("""
class SerialService:
    async def connect(self, port, baudrate):
        self._controller = GrblController(port, baudrate)
        return True
""")
        
        result = analyzer.analyze()
        
        issues = [i for i in result.issues if i.id == "serial_crash_001"]
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.CRITICAL

    def test_analyze_serial_service_connect_method(self, analyzer, tmp_path):
        """Test detection of await self._controller.connect() call."""
        services_dir = tmp_path / "inkscape_wps" / "core" / "services"
        services_dir.mkdir(parents=True)
        
        serial_file = services_dir / "serial_service.py"
        serial_file.write_text("""
class SerialService:
    async def connect(self, port):
        await self._controller.connect()
        return True
""")
        
        result = analyzer.analyze()
        
        issues = [i for i in result.issues if i.id == "serial_crash_002"]
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.CRITICAL

    def test_analyze_serial_service_buffer_full_method(self, analyzer, tmp_path):
        """Test detection of self._controller.buffer_full() call."""
        services_dir = tmp_path / "inkscape_wps" / "core" / "services"
        services_dir.mkdir(parents=True)
        
        serial_file = services_dir / "serial_service.py"
        serial_file.write_text("""
class SerialService:
    async def send_gcode_streaming(self, gcode):
        while self._controller.buffer_full():
            await asyncio.sleep(0.01)
        return True
""")
        
        result = analyzer.analyze()
        
        issues = [i for i in result.issues if i.id == "serial_crash_003"]
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.CRITICAL

    def test_analyze_font_service_indentation_error(self, analyzer, tmp_path):
        """Test detection of for loop indentation error in font_service.py."""
        services_dir = tmp_path / "inkscape_wps" / "core" / "services"
        services_dir.mkdir(parents=True)
        
        font_file = services_dir / "font_service.py"
        font_file.write_text("""
class FontService:
    async def get_character_paths(self, char, font_name):
        font_data = self._font_cache.get(font_name)
        if 'characters' in font_data and char in font_data['characters']:
            char_info = font_data['characters'][char]
        for stroke in char_info.get('strokes', []):
            path = []
            for point_data in stroke:
                path.append(Point(point_data[0], point_data[1]))
        return []
""")
        
        result = analyzer.analyze()
        
        issues = [i for i in result.issues if i.id == "font_crash_001"]
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.CRITICAL

    def test_analyze_qt_compat_missing_import(self, analyzer, tmp_path):
        """Test detection of QShowEvent not imported in PyQt5 branch."""
        ui_dir = tmp_path / "inkscape_wps" / "ui"
        ui_dir.mkdir(parents=True)
        
        qt_compat_file = ui_dir / "qt_compat.py"
        qt_compat_file.write_text("""
try:
    from PyQt6.QtGui import QShowEvent
except ImportError:
    from PyQt5.QtGui import (
        QBrush, QColor, QFont, QIcon, QKeyEvent, QKeySequence,
        QMouseEvent, QPainter, QPen, QPixmap
    )

__all__ = [
    'QShowEvent',
    'QBrush',
    'QColor'
]
""")
        
        result = analyzer.analyze()
        
        issues = [i for i in result.issues if i.id == "qt_crash_001"]
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.CRITICAL

    def test_analyze_no_issues_when_files_missing(self, analyzer, tmp_path):
        """Test that analyzer handles missing files gracefully."""
        result = analyzer.analyze()
        
        # Should not crash, just return empty result
        assert result.analyzer_name == "RuntimeCrashAnalyzer"
        assert len(result.errors) == 0

    def test_analyze_returns_analysis_result(self, analyzer, tmp_path):
        """Test that analyze() returns an AnalysisResult object."""
        result = analyzer.analyze()
        
        assert result is not None
        assert hasattr(result, 'issues')
        assert hasattr(result, 'errors')
        assert hasattr(result, 'warnings')
        assert result.analyzer_name == "RuntimeCrashAnalyzer"

    def test_issue_has_required_fields(self, analyzer, tmp_path):
        """Test that detected issues have all required fields."""
        services_dir = tmp_path / "inkscape_wps" / "core" / "services"
        services_dir.mkdir(parents=True)
        
        gcode_file = services_dir / "gcode_service.py"
        gcode_file.write_text("""
class GCodeService:
    def optimize_paths(self, paths):
        min_length = self.config.get('min_path_length', 0.1)
        return paths
""")
        
        result = analyzer.analyze()
        
        assert len(result.issues) > 0
        issue = result.issues[0]
        
        # Check all required fields
        assert issue.id is not None
        assert issue.title is not None
        assert issue.description is not None
        assert issue.severity is not None
        assert issue.category is not None
        assert issue.location is not None
        assert issue.impact is not None
        assert issue.suggestion is not None
