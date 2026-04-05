"""命令行接口

本模块提供了命令行接口，用于运行代码审查分析工具。

支持的选项：
- --project-path: 项目根目录路径
- --output: 报告输出文件路径
- --format: 报告格式（markdown/html）
- --priority: 过滤问题优先级
- --no-cache: 禁用缓存
- --no-monitor: 禁用性能监控
- --verbose: 显示详细输出
"""

import argparse
import sys
from pathlib import Path

from .analyzer_coordinator import AnalyzerCoordinator


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="inkscape_wps 代码审查分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 分析当前目录
  python -m code_review_analyzer

  # 分析指定目录
  python -m code_review_analyzer --project-path /path/to/project

  # 保存报告到文件
  python -m code_review_analyzer --output report.md

  # 只显示严重问题
  python -m code_review_analyzer --priority critical,high
        """
    )
    
    parser.add_argument(
        "--project-path",
        type=Path,
        default=Path.cwd(),
        help="项目根目录路径（默认：当前目录）"
    )
    
    parser.add_argument(
        "--output",
        type=Path,
        help="报告输出文件路径（默认：不保存）"
    )
    
    parser.add_argument(
        "--format",
        choices=["markdown", "html"],
        default="markdown",
        help="报告格式（默认：markdown）"
    )
    
    parser.add_argument(
        "--priority",
        type=str,
        help="过滤问题优先级（逗号分隔，如：critical,high）"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示详细输出"
    )
    
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="禁用 AST 缓存"
    )
    
    parser.add_argument(
        "--no-monitor",
        action="store_true",
        help="禁用性能监控"
    )
    
    args = parser.parse_args()
    
    # 验证项目路径
    if not args.project_path.exists():
        print(f"错误：项目路径不存在：{args.project_path}", file=sys.stderr)
        return 1
    
    # 创建协调器
    coordinator = AnalyzerCoordinator(
        args.project_path,
        enable_cache=not args.no_cache,
        enable_monitoring=not args.no_monitor
    )
    
    # 运行分析
    print(f"正在分析项目：{args.project_path}")
    print()
    
    result = coordinator.run_all_analyzers()
    
    print()
    print("=" * 60)
    print("分析完成")
    print("=" * 60)
    print()
    
    # 显示摘要
    summary = result.summary()
    print(f"总问题数：{summary['total_issues']}")
    print(f"  - 严重：{summary['critical']}")
    print(f"  - 高：{summary['high']}")
    print(f"  - 中：{summary['medium']}")
    print(f"  - 低：{summary['low']}")
    print(f"分析耗时：{summary['analysis_duration_seconds']:.2f} 秒")
    print()
    
    # 过滤问题
    if args.priority:
        priorities = args.priority.split(",")
        filtered_issues = [
            issue for issue in result.issues
            if issue.severity.value in priorities
        ]
    else:
        filtered_issues = result.issues
    
    # 显示问题
    if filtered_issues:
        print("发现的问题：")
        print()
        
        for issue in filtered_issues[:20]:  # 只显示前 20 个
            print(f"[{issue.severity.value.upper()}] {issue.title}")
            print(f"  位置：{issue.file_path}:{issue.line_number}")
            if issue.suggestion:
                print(f"  建议：{issue.suggestion}")
            print()
        
        if len(filtered_issues) > 20:
            print(f"... 还有 {len(filtered_issues) - 20} 个问题")
            print()
    
    # 保存报告
    if args.output:
        coordinator.save_report(args.output)
    
    # 显示性能统计
    if not args.no_monitor or not args.no_cache:
        coordinator.print_performance_stats()
    
    # 返回状态码
    if summary['critical'] > 0:
        return 2  # 有严重问题
    elif summary['high'] > 0:
        return 1  # 有高优先级问题
    else:
        return 0  # 没有严重问题


if __name__ == "__main__":
    sys.exit(main())
