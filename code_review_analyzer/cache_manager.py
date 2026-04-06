"""缓存管理器 - 缓存已解析的 AST 和分析结果

本模块提供了一个缓存系统，用于缓存已解析的 Python 文件的 AST 和分析结果，
以提高大型项目的分析速度。

缓存策略：
- 基于文件内容的哈希值进行缓存
- 支持缓存失效检测（文件修改时自动失效）
- 支持缓存清理和统计
"""

import ast
import hashlib
from pathlib import Path
from typing import Dict, Optional, Tuple


class CacheManager:
    """缓存管理器 - 管理 AST 和分析结果的缓存"""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """初始化缓存管理器
        
        Args:
            cache_dir: 缓存目录，默认为 .cache/code_review_analyzer
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "code_review_analyzer"
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存
        self._ast_cache: Dict[str, Tuple[ast.Module, str]] = {}
        self._stats = {
            "hits": 0,
            "misses": 0,
            "invalidations": 0,
        }
    
    def get_file_hash(self, filepath: Path) -> str:
        """计算文件的哈希值
        
        Args:
            filepath: 文件路径
            
        Returns:
            文件内容的 SHA256 哈希值
        """
        try:
            with open(filepath, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except (IOError, OSError):
            return ""
    
    def get_cached_ast(self, filepath: Path) -> Optional[ast.Module]:
        """获取缓存的 AST
        
        Args:
            filepath: 文件路径
            
        Returns:
            缓存的 AST Module，如果缓存无效或不存在返回 None
        """
        filepath_str = str(filepath)
        current_hash = self.get_file_hash(filepath)
        
        # 检查内存缓存
        if filepath_str in self._ast_cache:
            cached_ast, cached_hash = self._ast_cache[filepath_str]
            if cached_hash == current_hash:
                self._stats["hits"] += 1
                return cached_ast
            else:
                # 缓存失效
                del self._ast_cache[filepath_str]
                self._stats["invalidations"] += 1
        
        self._stats["misses"] += 1
        return None
    
    def cache_ast(self, filepath: Path, tree: ast.Module) -> None:
        """缓存 AST
        
        Args:
            filepath: 文件路径
            tree: AST Module
        """
        filepath_str = str(filepath)
        file_hash = self.get_file_hash(filepath)
        self._ast_cache[filepath_str] = (tree, file_hash)
    
    def clear_cache(self) -> None:
        """清空所有缓存"""
        self._ast_cache.clear()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "invalidations": 0,
        }
    
    def get_stats(self) -> Dict[str, int]:
        """获取缓存统计信息
        
        Returns:
            包含命中数、未命中数、失效数的字典
        """
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0
        
        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "invalidations": self._stats["invalidations"],
            "total": total,
            "hit_rate": f"{hit_rate:.1f}%",
        }
    
    def print_stats(self) -> None:
        """打印缓存统计信息"""
        stats = self.get_stats()
        print("\n📊 缓存统计信息:")
        print(f"  命中数：{stats['hits']}")
        print(f"  未命中数：{stats['misses']}")
        print(f"  失效数：{stats['invalidations']}")
        print(f"  总请求数：{stats['total']}")
        print(f"  命中率：{stats['hit_rate']}")
