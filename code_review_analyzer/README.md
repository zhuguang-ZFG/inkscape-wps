# Code Review Analyzer

A comprehensive code analysis tool for the inkscape_wps project that identifies runtime crashes, design problems, code quality issues, and provides improvement suggestions.

## Project Structure

```
code_review_analyzer/
├── __init__.py              # Package initialization
├── __main__.py              # CLI entry point
├── models.py                # Data models (Issue, IssueSeverity, etc.)
├── analyzers/
│   ├── __init__.py
│   ├── base_analyzer.py     # Base class for all analyzers
│   ├── runtime_crash_analyzer.py      # P0: Runtime crash detection
│   ├── orphaned_code_analyzer.py      # P1: Orphaned code detection
│   ├── design_issue_analyzer.py       # P1: Design problem detection
│   ├── code_quality_analyzer.py       # P2: Code quality issues
│   ├── dependency_analyzer.py         # P2: Dependency analysis
│   └── ast_utils.py                   # AST parsing utilities
├── reporters/
│   ├── __init__.py
│   ├── base_reporter.py     # Base class for all reporters
│   ├── report_generator.py  # P3: Report generation
│   └── testing_strategy_generator.py  # P3: Testing strategy
├── analyzer_coordinator.py  # Main analysis orchestrator
├── cli.py                   # Command-line interface
└── README.md                # This file
```

## Data Models

### Issue
Represents a single issue found during analysis with:
- `id`: Unique identifier
- `title`: Issue title
- `description`: Detailed description
- `severity`: IssueSeverity (CRITICAL, HIGH, MEDIUM, LOW)
- `category`: IssueCategory (RUNTIME_CRASH, ORPHANED_CODE, DESIGN_PROBLEM, CODE_QUALITY, DEPENDENCY)
- `location`: File path and line number
- `impact`: Description of the impact
- `suggestion`: Improvement suggestion
- `details`: Additional details (optional)
- `tags`: List of tags (optional)

### IssueSeverity
Enum with levels:
- `CRITICAL`: Runtime crashes (P0)
- `HIGH`: Design problems (P1)
- `MEDIUM`: Code quality issues (P2)
- `LOW`: Minor issues

### IssueCategory
Enum with categories:
- `RUNTIME_CRASH`: Runtime crash issues
- `ORPHANED_CODE`: Orphaned/unused code
- `DESIGN_PROBLEM`: Design and architecture issues
- `CODE_QUALITY`: Code quality issues
- `DEPENDENCY`: Dependency-related issues

### AnalysisResult
Result from a single analyzer containing:
- `analyzer_name`: Name of the analyzer
- `issues`: List of Issue objects
- `errors`: List of error messages
- `warnings`: List of warning messages

### FullAnalysisResult
Complete analysis result from all analyzers with:
- `results`: List of AnalysisResult objects
- `total_issues`: Total number of issues
- `critical_issues`: Count of critical issues
- `high_issues`: Count of high issues
- `medium_issues`: Count of medium issues
- `low_issues`: Count of low issues

## Base Classes

### BaseAnalyzer
Abstract base class for all analyzers. Provides:
- `analyze()`: Abstract method to run analysis
- `_get_file_path()`: Get full path to a project file
- `_read_file()`: Read file content
- `get_result()`: Get the analysis result

### BaseReporter
Abstract base class for all reporters. Provides:
- `generate()`: Abstract method to generate report
- `save()`: Save report to file

## Testing

Run tests with pytest:

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test file
python3 -m pytest tests/test_models.py -v

# Run with coverage
python3 -m pytest tests/ --cov=code_review_analyzer
```

## Implementation Phases

### P0: Runtime Crash Detection (Priority 0)
- Task 1: Project structure and framework (✓ COMPLETED)
- Task 2: Runtime crash analyzer
- Task 3: AST parsing utilities
- Task 4: P0 checkpoint

### P1: Orphaned Code & Design Issues (Priority 1)
- Task 5: Orphaned code analyzer
- Task 6: Design issue analyzer
- Task 7: P1 checkpoint

### P2: Code Quality & Dependencies (Priority 2)
- Task 8: Code quality analyzer
- Task 9: Dependency analyzer
- Task 10: P2 checkpoint

### P3: Reports & Testing Strategy (Priority 3)
- Task 11: Report generator
- Task 12: Testing strategy generator
- Task 13: Analyzer coordinator
- Task 14: CLI interface
- Task 15: P3 checkpoint

### Integration & Validation
- Task 16: End-to-end integration tests
- Task 17: Documentation and examples
- Task 18: Final checkpoint

## Usage

```bash
# Run analysis on a project
python3 -m code_review_analyzer --project-path /path/to/project --output report.md

# Run with specific priority filter
python3 -m code_review_analyzer --project-path /path/to/project --priority critical

# Generate HTML report
python3 -m code_review_analyzer --project-path /path/to/project --format html
```

## Development

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Format code:

```bash
black code_review_analyzer tests
isort code_review_analyzer tests
```

Run linting:

```bash
flake8 code_review_analyzer tests
mypy code_review_analyzer
```
