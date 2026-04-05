"""报告生成器 - 生成结构化的代码审查报告"""

from pathlib import Path
from typing import Dict, List

from ..models import AnalysisResult, IssueSeverity, IssueCategory


class ReportGenerator:
    """生成 Markdown 格式的代码审查报告"""
    
    def __init__(self, result: AnalysisResult):
        """初始化报告生成器
        
        Args:
            result: 分析结果
        """
        self.result = result
    
    def generate(self) -> str:
        """生成完整报告
        
        Returns:
            报告内容（Markdown 格式）
        """
        report = self._generate_header()
        report += self._generate_summary()
        report += self._generate_issues_by_severity()
        report += self._generate_issues_by_category()
        report += self._generate_statistics()
        
        return report
    
    def save(self, output_path: Path) -> None:
        """保存报告到文件
        
        Args:
            output_path: 输出文件路径
        """
        report = self.generate()
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        
        print(f"报告已保存到：{output_path}")
    
    def _generate_header(self) -> str:
        """生成报告头"""
        return """# inkscape_wps 代码审查分析报告

本报告由代码审查分析工具自动生成。

---

"""
    
    def _generate_summary(self) -> str:
        """生成摘要"""
        summary = self.result.summary()
        
        report = "## 摘要\n\n"
        report += f"- **总问题数**：{summary['total_issues']}\n"
        report += f"- **严重问题**：{summary['critical']}\n"
        report += f"- **高优先级**：{summary['high']}\n"
        report += f"- **中优先级**：{summary['medium']}\n"
        report += f"- **低优先级**：{summary['low']}\n"
        report += f"- **分析耗时**：{summary['analysis_duration_seconds']:.2f} 秒\n\n"
        
        return report
    
    def _generate_issues_by_severity(self) -> str:
        """按严重程度生成问题列表"""
        report = "## 按严重程度分类\n\n"
        
        for severity in [IssueSeverity.CRITICAL, IssueSeverity.HIGH, IssueSeverity.MEDIUM, IssueSeverity.LOW]:
            issues = self.result.get_issues_by_severity(severity)
            
            if not issues:
                continue
            
            report += f"### {severity.value.upper()} - {len(issues)} 个问题\n\n"
            
            for issue in issues:
                report += f"#### {issue.title}\n\n"
                report += f"- **位置**：{issue.file_path}"
                if issue.line_number:
                    report += f":{issue.line_number}"
                report += "\n"
                report += f"- **描述**：{issue.description}\n"
                if issue.error_type:
                    report += f"- **错误类型**：{issue.error_type}\n"
                if issue.suggestion:
                    report += f"- **建议**：{issue.suggestion}\n"
                report += "\n"
        
        return report
    
    def _generate_issues_by_category(self) -> str:
        """按分类生成问题列表"""
        report = "## 按分类统计\n\n"
        
        for category in IssueCategory:
            issues = self.result.get_issues_by_category(category)
            
            if not issues:
                continue
            
            report += f"### {category.value} - {len(issues)} 个问题\n\n"
            
            for issue in issues:
                report += f"- {issue.title} ({issue.file_path}"
                if issue.line_number:
                    report += f":{issue.line_number}"
                report += ")\n"
            
            report += "\n"
        
        return report
    
    def _generate_statistics(self) -> str:
        """生成统计信息"""
        report = "## 统计信息\n\n"
        
        # 按文件统计
        file_issues = {}
        for issue in self.result.issues:
            if issue.file_path not in file_issues:
                file_issues[issue.file_path] = 0
            file_issues[issue.file_path] += 1
        
        report += "### 问题最多的文件\n\n"
        sorted_files = sorted(file_issues.items(), key=lambda x: x[1], reverse=True)[:10]
        for filepath, count in sorted_files:
            report += f"- {filepath}：{count} 个问题\n"
        
        report += "\n"
        
        return report
