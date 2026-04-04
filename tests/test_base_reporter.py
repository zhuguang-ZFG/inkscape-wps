"""Tests for base reporter."""

from pathlib import Path
from tempfile import TemporaryDirectory

from code_review_analyzer.models import FullAnalysisResult
from code_review_analyzer.reporters.base_reporter import BaseReporter


class ConcreteReporter(BaseReporter):
    """Concrete implementation of BaseReporter for testing."""

    def generate(self, analysis_result: FullAnalysisResult) -> str:
        """Implement abstract method."""
        return "Test Report"


class TestBaseReporter:
    """Tests for BaseReporter class."""

    def test_reporter_initialization(self):
        """Test initializing a reporter."""
        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            reporter = ConcreteReporter(output_path)
            assert reporter.output_path == output_path

    def test_generate_report(self):
        """Test generating a report."""
        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            reporter = ConcreteReporter(output_path)
            result = FullAnalysisResult()
            report = reporter.generate(result)
            assert report == "Test Report"

    def test_save_report(self):
        """Test saving a report to file."""
        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            reporter = ConcreteReporter(output_path)
            reporter.save("Test Report Content")
            assert output_path.exists()
            assert output_path.read_text() == "Test Report Content"

    def test_save_report_creates_parent_directories(self):
        """Test that save creates parent directories."""
        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "subdir" / "report.md"
            reporter = ConcreteReporter(output_path)
            reporter.save("Test Report Content")
            assert output_path.exists()
            assert output_path.parent.exists()
