"""Base class for all reporters."""

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import FullAnalysisResult


class BaseReporter(ABC):
    """Base class for all report generators."""

    def __init__(self, output_path: Path):
        """Initialize the reporter.

        Args:
            output_path: Path where the report will be saved
        """
        self.output_path = Path(output_path)

    @abstractmethod
    def generate(self, analysis_result: FullAnalysisResult) -> str:
        """Generate a report from analysis results.

        Args:
            analysis_result: The complete analysis result

        Returns:
            Report content as string
        """
        pass

    def save(self, content: str) -> None:
        """Save the report to file.

        Args:
            content: Report content to save
        """
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(content, encoding="utf-8")
