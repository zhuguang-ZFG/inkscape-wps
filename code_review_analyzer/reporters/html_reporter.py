"""HTML 报告生成器"""


from ..models import IssueCategory, IssueSeverity
from .base_reporter import BaseReporter


class HTMLReporter(BaseReporter):
    """HTML 格式报告生成器"""
    
    def generate(self) -> str:
        """生成 HTML 报告"""
        html = self._generate_header()
        html += self._generate_summary()
        html += self._generate_issues_by_severity()
        html += self._generate_issues_by_category()
        html += self._generate_statistics()
        html += self._generate_footer()
        
        return html
    
    def _generate_header(self) -> str:
        """生成 HTML 头"""
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>inkscape_wps 代码审查分析报告</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: white;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        
        header {
            border-bottom: 3px solid #007bff;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        
        h1 {
            color: #007bff;
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        h2 {
            color: #0056b3;
            font-size: 1.8em;
            margin-top: 30px;
            margin-bottom: 15px;
            border-left: 4px solid #007bff;
            padding-left: 15px;
        }
        
        h3 {
            color: #333;
            font-size: 1.3em;
            margin-top: 20px;
            margin-bottom: 10px;
        }
        
        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .summary-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        .summary-card.critical {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        
        .summary-card.high {
            background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
        }
        
        .summary-card.medium {
            background: linear-gradient(135deg, #30cfd0 0%, #330867 100%);
        }
        
        .summary-card.low {
            background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
            color: #333;
        }
        
        .summary-card h3 {
            margin: 0 0 10px 0;
            font-size: 1.1em;
        }
        
        .summary-card .number {
            font-size: 2.5em;
            font-weight: bold;
        }
        
        .issue {
            background: #f9f9f9;
            border-left: 4px solid #007bff;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 4px;
        }
        
        .issue.critical {
            border-left-color: #f5576c;
            background: #fff5f5;
        }
        
        .issue.high {
            border-left-color: #fa709a;
            background: #fffaf5;
        }
        
        .issue.medium {
            border-left-color: #30cfd0;
            background: #f5fffe;
        }
        
        .issue.low {
            border-left-color: #a8edea;
            background: #fafffe;
        }
        
        .issue-title {
            font-weight: bold;
            font-size: 1.1em;
            margin-bottom: 8px;
            color: #333;
        }
        
        .issue-meta {
            display: flex;
            gap: 20px;
            margin-bottom: 8px;
            font-size: 0.9em;
            color: #666;
        }
        
        .issue-meta span {
            display: flex;
            align-items: center;
        }
        
        .issue-meta strong {
            margin-right: 5px;
        }
        
        .issue-description {
            margin-bottom: 8px;
            color: #555;
        }
        
        .issue-suggestion {
            background: #e7f3ff;
            border-left: 3px solid #007bff;
            padding: 10px;
            margin-top: 8px;
            border-radius: 3px;
            font-size: 0.95em;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }
        
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        
        th {
            background: #f0f0f0;
            font-weight: bold;
            color: #333;
        }
        
        tr:hover {
            background: #f9f9f9;
        }
        
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: bold;
        }
        
        .badge.critical {
            background: #f5576c;
            color: white;
        }
        
        .badge.high {
            background: #fa709a;
            color: white;
        }
        
        .badge.medium {
            background: #30cfd0;
            color: white;
        }
        
        .badge.low {
            background: #a8edea;
            color: #333;
        }
        
        footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #999;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 inkscape_wps 代码审查分析报告</h1>
            <p>本报告由代码审查分析工具自动生成</p>
        </header>
"""
    
    def _generate_summary(self) -> str:
        """生成摘要"""
        summary = self.result.summary()
        
        html = "<h2>📈 摘要</h2>\n"
        html += '<div class="summary">\n'
        
        # 总问题数
        html += f'''    <div class="summary-card">
        <h3>总问题数</h3>
        <div class="number">{summary['total_issues']}</div>
    </div>\n'''
        
        # 严重问题
        html += f'''    <div class="summary-card critical">
        <h3>严重问题</h3>
        <div class="number">{summary['critical']}</div>
    </div>\n'''
        
        # 高优先级
        html += f'''    <div class="summary-card high">
        <h3>高优先级</h3>
        <div class="number">{summary['high']}</div>
    </div>\n'''
        
        # 中优先级
        html += f'''    <div class="summary-card medium">
        <h3>中优先级</h3>
        <div class="number">{summary['medium']}</div>
    </div>\n'''
        
        # 低优先级
        html += f'''    <div class="summary-card low">
        <h3>低优先级</h3>
        <div class="number">{summary['low']}</div>
    </div>\n'''
        
        html += "</div>\n"
        
        return html
    
    def _generate_issues_by_severity(self) -> str:
        """按严重程度生成问题列表"""
        html = "<h2>🔴 按严重程度分类</h2>\n"
        
        for severity in (
            IssueSeverity.CRITICAL,
            IssueSeverity.HIGH,
            IssueSeverity.MEDIUM,
            IssueSeverity.LOW,
        ):
            issues = self.result.get_issues_by_severity(severity)
            
            if not issues:
                continue
            
            html += f"<h3>{severity.value.upper()} - {len(issues)} 个问题</h3>\n"
            
            for issue in issues:
                html += f'<div class="issue {severity.value}">\n'
                html += f'    <div class="issue-title">{issue.title}</div>\n'
                html += '    <div class="issue-meta">\n'
                html += f'        <span><strong>位置：</strong>{issue.file_path}'
                if issue.line_number:
                    html += f':{issue.line_number}'
                html += '</span>\n'
                if issue.error_type:
                    html += f'        <span><strong>错误类型：</strong>{issue.error_type}</span>\n'
                html += '    </div>\n'
                html += f'    <div class="issue-description">{issue.description}</div>\n'
                if issue.suggestion:
                    html += (
                        '    <div class="issue-suggestion"><strong>建议：</strong> '
                        f"{issue.suggestion}</div>\n"
                    )
                html += '</div>\n'
        
        return html
    
    def _generate_issues_by_category(self) -> str:
        """按分类生成问题列表"""
        html = "<h2>📂 按分类统计</h2>\n"
        
        html += "<table>\n"
        html += "    <thead>\n"
        html += "        <tr>\n"
        html += "            <th>分类</th>\n"
        html += "            <th>问题数</th>\n"
        html += "            <th>问题列表</th>\n"
        html += "        </tr>\n"
        html += "    </thead>\n"
        html += "    <tbody>\n"
        
        for category in IssueCategory:
            issues = self.result.get_issues_by_category(category)
            
            if not issues:
                continue
            
            html += "        <tr>\n"
            html += f"            <td><strong>{category.value}</strong></td>\n"
            html += f"            <td>{len(issues)}</td>\n"
            html += "            <td>\n"
            for issue in issues[:5]:
                html += f"                • {issue.title}<br>\n"
            if len(issues) > 5:
                html += f"                ... 还有 {len(issues) - 5} 个问题\n"
            html += "            </td>\n"
            html += "        </tr>\n"
        
        html += "    </tbody>\n"
        html += "</table>\n"
        
        return html
    
    def _generate_statistics(self) -> str:
        """生成统计信息"""
        html = "<h2>📊 统计信息</h2>\n"
        
        # 按文件统计
        file_issues = {}
        for issue in self.result.issues:
            if issue.file_path not in file_issues:
                file_issues[issue.file_path] = 0
            file_issues[issue.file_path] += 1
        
        html += "<h3>问题最多的文件</h3>\n"
        html += "<table>\n"
        html += "    <thead>\n"
        html += "        <tr>\n"
        html += "            <th>文件</th>\n"
        html += "            <th>问题数</th>\n"
        html += "        </tr>\n"
        html += "    </thead>\n"
        html += "    <tbody>\n"
        
        sorted_files = sorted(file_issues.items(), key=lambda x: x[1], reverse=True)[:10]
        for filepath, count in sorted_files:
            html += "        <tr>\n"
            html += f"            <td>{filepath}</td>\n"
            html += f"            <td><span class='badge high'>{count}</span></td>\n"
            html += "        </tr>\n"
        
        html += "    </tbody>\n"
        html += "</table>\n"
        
        return html
    
    def _generate_footer(self) -> str:
        """生成 HTML 尾"""
        summary = self.result.summary()
        
        return f"""        <footer>
            <p>分析耗时：{summary['analysis_duration_seconds']:.2f} 秒</p>
            <p>生成时间：<span id="timestamp"></span></p>
            <p>© 2024 inkscape_wps 代码审查分析工具</p>
        </footer>
    </div>
    
    <script>
        document.getElementById('timestamp').textContent = new Date().toLocaleString('zh-CN');
    </script>
</body>
</html>
"""
