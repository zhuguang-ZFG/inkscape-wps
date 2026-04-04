"""Base class for all analyzers."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from ..models import AnalysisResult


class BaseAnalyzer(ABC):
    """Base class for all code analyzers."""

    def __init__(self, project_path: Path):
        """Initialize the analyzer.

        Args:
            project_path: Path to the project root directory
        """
        self.project_path = Path(project_path)
        self.result = AnalysisResult(analyzer_name=self.__class__.__name__)

    @abstractmethod
    def analyze(self) -> AnalysisResult:
        """Run the analysis.

        Returns:
            AnalysisResult containing all issues found
        """
        pass

    def get_result(self) -> AnalysisResult:
        """Get the analysis result.

        Returns:
            The AnalysisResult object
        """
        return self.result

    def _get_file_path(self, relative_path: str) -> Optional[Path]:
        """Get the full path to a file in the project.

        Args:
            relative_path: Relative path from project root

        Returns:
            Full Path object if file exists, None otherwise
        """
        full_path = self.project_path / relative_path
        if full_path.exists():
            return full_path
        return None

    def _read_file(self, relative_path: str) -> Optional[str]:
        """Read a file from the project.

        Args:
            relative_path: Relative path from project root

        Returns:
            File content as string, or None if file doesn't exist
        """
        file_path = self._get_file_path(relative_path)
        if file_path is None:
            return None
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            self.result.add_error(f"Failed to read {relative_path}: {e}")
            return None
