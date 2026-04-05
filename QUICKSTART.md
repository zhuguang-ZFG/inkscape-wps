# 快速启动指南

## 项目概述

这是一个针对 inkscape_wps 项目的代码审查分析工具，用于系统性地识别和报告代码问题。

## 文件结构

```
.
├── code_review_analyzer/          # 分析工具主包
│   ├── __init__.py
│   ├── __main__.py
│   ├── models.py                  # 数据模型
│   ├── README.md                  # 工具文档
│   ├── analyzers/                 # 分析器模块
│   │   ├── base_analyzer.py
│   │   ├── ast_utils.py           # AST 解析工具
│   │   └── runtime_crash_analyzer.py
│   └── reporters/                 # 报告生成模块
│       └── base_reporter.py
│
├── tests/                         # 测试模块
│   ├── conftest.py
│   ├── test_ast_utils.py
│   └── test_runtime_crash_analyzer.py
│
├── .kiro/specs/code-review-analysis/  # 规格文档
│   ├── design.md                  # 设计文档
│   ├── requirements.md            # 需求文档
│   ├── tasks.md                   # 任务列表
│   ├── FIXES_APPLIED.md           # 修复记录
│   ├── IMPLEMENTATION_PROGRESS.md # 实现进度
│   └── PHASE_1_SUMMARY.md         # 第一阶段总结
│
└── pytest.ini                     # pytest 配置
```

## 快速开始

### 1. 查看规格文档

```bash
# 查看设计文档
cat .kiro/specs/code-review-analysis/design.md

# 查看需求文档
cat .kiro/specs/code-review-analysis/requirements.md

# 查看任务列表
cat .kiro/specs/code-review-analysis/tasks.md
```

### 2. 查看实现进度

```bash
# 查看第一阶段总结
cat .kiro/specs/code-review-analysis/PHASE_1_SUMMARY.md

# 查看实现进度
cat .kiro/specs/code-review-analysis/IMPLEMENTATION_PROGRESS.md

# 查看已修复的 bug
cat .kiro/specs/code-review-analysis/FIXES_APPLIED.md
```

### 3. 运行分析工具

```bash
# 运行分析工具
python -m code_review_analyzer

# 运行测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_ast_utils.py -v
```

### 4. 使用分析工具

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

# 查看问题
for issue in result.issues:
    print(f"[{issue.severity.value}] {issue.title}")
    print(f"  位置: {issue.file_path}:{issue.line_number}")
    print(f"  建议: {issue.suggestion}")
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

## 已完成的工作

### ✅ P0 优先级（已完成）

- [x] 项目框架建立
- [x] AST 解析工具库
- [x] 运行时崩溃检测器
- [x] 测试框架

### ⏳ P1 优先级（待完成）

- [ ] 脱节代码检测器
- [ ] 设计问题检测器

### ⏳ P2 优先级（待完成）

- [ ] 代码质量检测器
- [ ] 依赖关系分析器

### ⏳ P3 优先级（待完成）

- [ ] 报告生成器
- [ ] 命令行接口
- [ ] 文档和示例

## 已修正的 Bug

1. **gcode.py - M5 命令条件发送** ✅
   - 修正：Z 轴模式下不再发送 M5 命令

2. **qt_compat.py - QShowEvent 导入缺失** ✅
   - 修正：添加了 QShowEvent 导入

## 下一步

1. **继续实现 P1 优先级的分析器**
   - 脱节代码检测器
   - 设计问题检测器

2. **实现 P2 优先级的分析器**
   - 代码质量检测器
   - 依赖关系分析器

3. **实现报告生成和命令行接口**
   - Markdown/HTML 报告生成
   - 命令行参数解析

4. **完成端到端测试和文档**

## 文档

- `code_review_analyzer/README.md` - 工具使用指南
- `.kiro/specs/code-review-analysis/design.md` - 设计文档
- `.kiro/specs/code-review-analysis/requirements.md` - 需求文档
- `.kiro/specs/code-review-analysis/tasks.md` - 任务列表

## 技术栈

- Python 3.8+
- AST 解析（标准库）
- pytest 测试框架
- dataclass 数据模型

## 联系方式

如有问题或建议，请提交 Issue 或 Pull Request。

