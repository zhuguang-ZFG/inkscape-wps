# inkscape_wps 代码审查分析工具

一个系统性的代码审查分析工具，用于识别 inkscape_wps 项目中的运行时崩溃问题、设计问题、代码质量问题等。

## 功能

- ✅ **运行时崩溃检测**：识别会导致程序崩溃的代码问题
- ⏳ **脱节代码识别**：找出与实际运行路径无关的代码
- ⏳ **设计问题检测**：识别架构和设计层面的问题
- ⏳ **代码质量分析**：检查代码风格和质量问题
- ⏳ **依赖关系分析**：验证项目依赖的正确性
- ⏳ **结构化报告生成**：生成详细的分析报告

## 快速开始

### 安装

```bash
# 克隆项目
git clone <repository>
cd inkscape_wps

# 安装依赖
pip install pytest
```

### 使用

```bash
# 运行分析
python -m code_review_analyzer

# 运行测试
pytest tests/ -v
```

## 项目结构

```
code_review_analyzer/
├── models.py              # 数据模型定义
├── analyzers/             # 分析器模块
│   ├── base_analyzer.py   # 基础分析器类
│   ├── ast_utils.py       # AST 解析工具
│   └── runtime_crash_analyzer.py  # 运行时崩溃检测器
└── reporters/             # 报告生成模块
    └── base_reporter.py   # 基础报告生成器类

tests/                      # 测试模块
├── conftest.py            # pytest 配置
├── test_ast_utils.py      # AST 工具测试
└── test_runtime_crash_analyzer.py  # 分析器测试
```

## 核心概念

### 问题严重程度

- **CRITICAL**：运行时必崩的问题
- **HIGH**：设计层面的问题
- **MEDIUM**：代码质量问题
- **LOW**：建议改进

### 问题分类

- **RUNTIME_CRASH**：运行时崩溃
- **DESIGN**：设计问题
- **CODE_QUALITY**：代码质量
- **DEPENDENCY**：依赖关系
- **ORPHANED_CODE**：脱节代码

## API 示例

### 基本使用

```python
from pathlib import Path
from code_review_analyzer.analyzers.runtime_crash_analyzer import RuntimeCrashAnalyzer

# 创建分析器
analyzer = RuntimeCrashAnalyzer(Path.cwd())

# 执行分析
result = analyzer.analyze()

# 获取摘要
summary = result.summary()
print(f"发现 {summary['total_issues']} 个问题")
print(f"  - 严重: {summary['critical']}")
print(f"  - 高: {summary['high']}")
print(f"  - 中: {summary['medium']}")
print(f"  - 低: {summary['low']}")

# 按严重程度获取问题
from code_review_analyzer.models import IssueSeverity
critical_issues = result.get_issues_by_severity(IssueSeverity.CRITICAL)
for issue in critical_issues:
    print(f"[{issue.severity.value}] {issue.title}")
    print(f"  位置: {issue.file_path}:{issue.line_number}")
    print(f"  建议: {issue.suggestion}")
```

### 使用 AST 工具

```python
from pathlib import Path
from code_review_analyzer.analyzers.ast_utils import (
    parse_python_file,
    find_method_calls,
    find_function_definitions,
)

# 解析 Python 文件
tree = parse_python_file(Path("example.py"))

# 查找方法调用
calls = find_method_calls(tree, "get")
for line_no, call_expr in calls:
    print(f"Line {line_no}: {call_expr}")

# 查找函数定义
functions = find_function_definitions(tree)
for func_name, start_line, end_line in functions:
    size = end_line - start_line + 1
    print(f"{func_name}: {size} 行")
```

## 开发指南

### 添加新的分析器

1. 创建新的分析器类，继承自 `BaseAnalyzer`
2. 实现 `analyze()` 方法
3. 使用 `add_issue()` 方法添加发现的问题
4. 编写单元测试

```python
from code_review_analyzer.analyzers.base_analyzer import BaseAnalyzer
from code_review_analyzer.models import Issue, IssueSeverity, IssueCategory

class MyAnalyzer(BaseAnalyzer):
    def analyze(self):
        # 执行分析
        issue = Issue(
            id="my_001",
            title="问题标题",
            description="问题描述",
            category=IssueCategory.CODE_QUALITY,
            severity=IssueSeverity.MEDIUM,
            file_path="path/to/file.py",
            line_number=10,
            suggestion="改进建议",
        )
        self.add_issue(issue)
        return self.result
```

### 添加新的报告生成器

1. 创建新的报告生成器类，继承自 `BaseReporter`
2. 实现 `generate()` 方法
3. 返回格式化的报告内容

```python
from code_review_analyzer.reporters.base_reporter import BaseReporter

class MyReporter(BaseReporter):
    def generate(self) -> str:
        # 生成报告
        report = "# 代码审查报告\n\n"
        for issue in self.result.issues:
            report += f"## {issue.title}\n"
            report += f"- 位置: {issue.file_path}:{issue.line_number}\n"
            report += f"- 建议: {issue.suggestion}\n\n"
        return report
```

## 测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_ast_utils.py -v

# 运行特定测试
pytest tests/test_ast_utils.py::test_parse_python_file -v

# 显示覆盖率
pytest tests/ --cov=code_review_analyzer
```

## 许可证

MIT

## 贡献

欢迎提交 Issue 和 Pull Request！

