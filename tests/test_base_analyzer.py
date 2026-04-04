"""Tests for base analyzer."""

from code_review_analyzer.analyzers.base_analyzer import BaseAnalyzer
from code_review_analyzer.models import AnalysisResult


class ConcreteAnalyzer(BaseAnalyzer):
    """Concrete implementation of BaseAnalyzer for testing."""

    def analyze(self) -> AnalysisResult:
        """Implement abstract method."""
        return self.result


class TestBaseAnalyzer:
    """Tests for BaseAnalyzer class."""

    def test_analyzer_initialization(self, temp_project_dir):
        """Test initializing an analyzer."""
        analyzer = ConcreteAnalyzer(temp_project_dir)
        assert analyzer.project_path == temp_project_dir
        assert analyzer.result.analyzer_name == "ConcreteAnalyzer"

    def test_get_result(self, temp_project_dir):
        """Test getting analysis result."""
        analyzer = ConcreteAnalyzer(temp_project_dir)
        result = analyzer.get_result()
        assert isinstance(result, AnalysisResult)
        assert result.analyzer_name == "ConcreteAnalyzer"

    def test_get_file_path_exists(self, sample_project_structure):
        """Test getting path to existing file."""
        analyzer = ConcreteAnalyzer(sample_project_structure)
        file_path = analyzer._get_file_path("core/types.py")
        assert file_path is not None
        assert file_path.exists()

    def test_get_file_path_not_exists(self, sample_project_structure):
        """Test getting path to non-existing file."""
        analyzer = ConcreteAnalyzer(sample_project_structure)
        file_path = analyzer._get_file_path("nonexistent.py")
        assert file_path is None

    def test_read_file(self, sample_project_structure):
        """Test reading a file."""
        analyzer = ConcreteAnalyzer(sample_project_structure)
        content = analyzer._read_file("core/types.py")
        assert content is not None
        assert "types module" in content

    def test_read_file_not_exists(self, sample_project_structure):
        """Test reading non-existing file."""
        analyzer = ConcreteAnalyzer(sample_project_structure)
        content = analyzer._read_file("nonexistent.py")
        assert content is None

    def test_analyze_method(self, temp_project_dir):
        """Test analyze method."""
        analyzer = ConcreteAnalyzer(temp_project_dir)
        result = analyzer.analyze()
        assert isinstance(result, AnalysisResult)
        assert result.analyzer_name == "ConcreteAnalyzer"
