# 快速开始指南

## 安装依赖

```bash
# 安装必要的依赖
pip install psutil

# 或使用 requirements.txt
pip install -r requirements.txt
```

## 基本使用

### 1. 分析当前项目

```bash
# 分析当前目录
python -m code_review_analyzer

# 分析指定目录
python -m code_review_analyzer --project-path /path/to/project
```

### 2. 保存报告

```bash
# 保存为 Markdown 文件
python -m code_review_analyzer --output report.md

# 保存为 HTML 文件（未来支持）
python -m code_review_analyzer --output report.html --format html
```

### 3. 过滤问题

```bash
# 只显示严重和高优先级问题
python -m code_review_analyzer --priority critical,high

# 只显示严重问题
python -m code_review_analyzer --priority critical
```

### 4. 性能优化

```bash
# 启用缓存（默认启用）
python -m code_review_analyzer

# 禁用缓存（用于调试）
python -m code_review_analyzer --no-cache

# 禁用性能监控
python -m code_review_analyzer --no-monitor

# 显示详细输出
python -m code_review_analyzer --verbose
```

## Python API 使用

### 基本分析

```python
from code_review_analyzer.analyzer_coordinator import AnalyzerCoordinator
from pathlib import Path

# 创建协调器
coordinator = AnalyzerCoordinator(Path("/path/to/project"))

# 运行分析
result = coordinator.run_all_analyzers()

# 获取结果
print(f"发现 {len(result.issues)} 个问题")

# 保存报告
coordinator.save_report(Path("report.md"))

# 显示性能统计
coordinator.print_performance_stats()
```

### 使用缓存

```python
from code_review_analyzer.cache_manager import CacheManager
from code_review_analyzer.analyzer_coordinator import AnalyzerCoordinator
from pathlib import Path

# 创建缓存管理器
cache_manager = CacheManager()

# 创建协调器（启用缓存）
coordinator = AnalyzerCoordinator(
    Path("/path/to/project"),
    enable_cache=True,
    enable_monitoring=True
)

# 运行分析
result = coordinator.run_all_analyzers()

# 显示缓存统计
coordinator.cache_manager.print_stats()
```

### 性能监控

```python
from code_review_analyzer.analyzer_coordinator import AnalyzerCoordinator
from pathlib import Path

# 创建协调器（启用性能监控）
coordinator = AnalyzerCoordinator(
    Path("/path/to/project"),
    enable_monitoring=True
)

# 运行分析
result = coordinator.run_all_analyzers()

# 显示性能指标
coordinator.print_performance_stats()
```

## 常见问题

### Q: 如何加快分析速度？

A: 启用缓存（默认启用）。对于大型项目，缓存可以提升 30-70% 的性能。

```bash
python -m code_review_analyzer --project-path /path/to/project
```

### Q: 如何了解分析的性能瓶颈？

A: 启用性能监控（默认启用）。

```bash
python -m code_review_analyzer --project-path /path/to/project
# 输出中会显示性能统计信息
```

### Q: 如何禁用缓存？

A: 使用 `--no-cache` 参数。

```bash
python -m code_review_analyzer --no-cache
```

### Q: 缓存存储在哪里？

A: 默认存储在 `~/.cache/code_review_analyzer/`。

### Q: 如何清空缓存？

A: 删除缓存目录或使用 Python API：

```python
cache_manager.clear_cache()
```

### Q: 支持哪些报告格式？

A: 目前支持 Markdown 格式。HTML 格式将在未来版本中支持。

## 输出示例

### 命令行输出

```
正在分析项目：/path/to/project

运行 P0 优先级分析器...
  ✓ 运行时崩溃检测：发现 8 个问题
运行 P1 优先级分析器...
  ✓ 脱节代码检测：发现 4 个问题
  ✓ 设计问题检测：发现 7 个问题
运行 P2 优先级分析器...
  ✓ 代码质量检测：发现 5 个问题
  ✓ 依赖关系分析：发现 2 个问题

============================================================
分析完成
============================================================

总问题数：26
  - 严重：8
  - 高：11
  - 中：5
  - 低：2
分析耗时：5.23 秒

⏱️  性能指标:
  总耗时：5.23 秒
  分析文件数：150
  发现问题数：26
  处理速度：28.7 文件/秒

💾 内存使用:
  初始内存：50.5 MB
  峰值内存：180.2 MB
  最终内存：65.3 MB
  内存增长：14.8 MB

🔍 分析器耗时:
  运行时崩溃检测：1.23 秒
  脱节代码检测：0.95 秒
  设计问题检测：1.50 秒
  代码质量检测：0.87 秒
  依赖关系分析：0.68 秒

📊 缓存统计信息:
  命中数：120
  未命中数：30
  失效数：0
  总请求数：150
  命中率：80.0%
```

## 文件结构

```
code_review_analyzer/
├── __init__.py
├── __main__.py
├── cli.py                          # 命令行接口
├── models.py                       # 数据模型
├── cache_manager.py                # 缓存管理器（新）
├── performance_monitor.py          # 性能监控器（新）
├── analyzer_coordinator.py         # 分析协调器
├── analyzers/
│   ├── __init__.py
│   ├── base_analyzer.py           # 基础分析器
│   ├── ast_utils.py               # AST 工具（已优化）
│   ├── runtime_crash_analyzer.py  # 运行时崩溃检测
│   ├── design_issue_analyzer.py   # 设计问题检测
│   ├── code_quality_analyzer.py   # 代码质量检测
│   ├── orphaned_code_analyzer.py  # 脱节代码检测
│   └── dependency_analyzer.py     # 依赖关系分析
└── reporters/
    ├── __init__.py
    ├── base_reporter.py           # 基础报告生成器
    ├── report_generator.py        # 报告生成器
    └── html_reporter.py           # HTML 报告生成器（未来）
```

## 下一步

1. 查看 `CODE_IMPROVEMENTS.md` 了解代码改进
2. 查看 `PERFORMANCE_OPTIMIZATION.md` 了解性能优化
3. 查看 `REFACTORING_CHECKLIST.md` 了解改进清单
4. 查看 `.kiro/specs/code-review-analysis/` 了解项目规范

