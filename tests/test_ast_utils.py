"""AST 工具的单元测试"""

import ast
from pathlib import Path

from code_review_analyzer.analyzers import ast_utils


class TestParseFile:
    """测试 parse_python_file 函数"""
    
    def test_parse_valid_file(self, sample_python_file):
        """测试解析有效的 Python 文件"""
        tree = ast_utils.parse_python_file(sample_python_file)
        
        assert tree is not None
        assert isinstance(tree, ast.Module)
    
    def test_parse_nonexistent_file(self):
        """测试解析不存在的文件"""
        tree = ast_utils.parse_python_file(Path("/nonexistent/file.py"))
        
        assert tree is None
    
    def test_parse_invalid_syntax(self, temp_project_dir):
        """测试解析语法错误的文件"""
        filepath = temp_project_dir / "invalid.py"
        filepath.write_text("def invalid syntax here")
        
        tree = ast_utils.parse_python_file(filepath)
        
        assert tree is None


class TestFindFunctions:
    """测试 find_function_definitions 函数"""
    
    def test_find_functions(self, sample_python_file):
        """测试查找函数定义"""
        tree = ast_utils.parse_python_file(sample_python_file)
        functions = ast_utils.find_function_definitions(tree)
        
        assert len(functions) >= 2
        assert any(name == "hello_world" for name, _, _ in functions)
    
    def test_find_functions_empty_file(self, temp_project_dir):
        """测试在空文件中查找函数"""
        filepath = temp_project_dir / "empty.py"
        filepath.write_text("")
        
        tree = ast_utils.parse_python_file(filepath)
        functions = ast_utils.find_function_definitions(tree)
        
        assert len(functions) == 0


class TestFindClasses:
    """测试 find_class_definitions 函数"""
    
    def test_find_classes(self, sample_python_file):
        """测试查找类定义"""
        tree = ast_utils.parse_python_file(sample_python_file)
        classes = ast_utils.find_class_definitions(tree)
        
        assert len(classes) >= 1
        assert any(name == "SampleClass" for name, _, _ in classes)
    
    def test_find_classes_with_methods(self, sample_python_file):
        """测试查找包含方法的类"""
        tree = ast_utils.parse_python_file(sample_python_file)
        classes = ast_utils.find_class_definitions(tree)
        
        # 验证类的行号范围
        for class_name, start_line, end_line in classes:
            assert start_line > 0
            assert end_line >= start_line


class TestCountLines:
    """测试 count_lines 函数"""
    
    def test_count_lines(self, sample_python_file):
        """测试计算文件行数"""
        lines = ast_utils.count_lines(sample_python_file)
        
        assert lines > 0
    
    def test_count_lines_empty_file(self, temp_project_dir):
        """测试计算空文件的行数"""
        filepath = temp_project_dir / "empty.py"
        filepath.write_text("")
        
        lines = ast_utils.count_lines(filepath)
        
        assert lines == 0


class TestFindDuplicateBranches:
    """测试 find_duplicate_branches 函数"""
    
    def test_find_duplicate_branches(self, temp_project_dir):
        """测试查找重复分支"""
        filepath = temp_project_dir / "duplicate_branches.py"
        
        code = '''
def test_function(x):
    if x > 0:
        return "positive"
    else:
        return "positive"
'''
        
        filepath.write_text(code)
        tree = ast_utils.parse_python_file(filepath)
        duplicates = ast_utils.find_duplicate_branches(tree)
        
        assert len(duplicates) > 0
    
    def test_no_duplicate_branches(self, temp_project_dir):
        """测试没有重复分支的代码"""
        filepath = temp_project_dir / "no_duplicates.py"
        
        code = '''
def test_function(x):
    if x > 0:
        return "positive"
    else:
        return "negative"
'''
        
        filepath.write_text(code)
        tree = ast_utils.parse_python_file(filepath)
        duplicates = ast_utils.find_duplicate_branches(tree)
        
        assert len(duplicates) == 0


class TestCountDataclassFields:
    """测试 count_dataclass_fields 函数"""
    
    def test_count_dataclass_fields(self, temp_project_dir):
        """测试计算 dataclass 字段数量"""
        filepath = temp_project_dir / "dataclass_test.py"
        
        code = '''
from dataclasses import dataclass

@dataclass
class TestClass:
    field1: str
    field2: int
    field3: float
'''
        
        filepath.write_text(code)
        tree = ast_utils.parse_python_file(filepath)
        count = ast_utils.count_dataclass_fields(tree, "TestClass")
        
        assert count == 3


class TestCountInstanceVariables:
    """测试 count_instance_variables 函数"""
    
    def test_count_instance_variables(self, temp_project_dir):
        """测试计算实例变量数量"""
        filepath = temp_project_dir / "instance_vars_test.py"
        
        code = '''
class TestClass:
    def __init__(self):
        self.var1 = 1
        self.var2 = 2
        self.var3 = 3
'''
        
        filepath.write_text(code)
        tree = ast_utils.parse_python_file(filepath)
        count = ast_utils.count_instance_variables(tree, "TestClass")
        
        assert count == 3
