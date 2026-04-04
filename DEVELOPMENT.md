# inkscape-wps 开发文档

本文档面向开发者，详细介绍项目的架构设计、代码规范、开发流程和扩展方法。

## 目录

- [项目概述](#项目概述)
- [架构设计](#架构设计)
- [代码规范](#代码规范)
- [开发环境](#开发环境)
- [核心模块详解](#核心模块详解)
- [扩展开发](#扩展开发)
- [测试策略](#测试策略)
- [性能优化](#性能优化)
- [已知问题与改进方向](#已知问题与改进方向)
- [与 WPS 逐步对标计划](#与-wps-逐步对标计划)

## 项目概述

inkscape-wps 是一个类 WPS 体验的 GRBL 写字机上位机，采用分层架构设计，核心特点是**核心逻辑与界面完全分离**。

### 核心特性

- **WPS 风格界面**：Ribbon + 三组件（文字/表格/演示）
- **多格式字体支持**：Hershey、JSON、JHF、奎享导出格式
- **完整 GRBL 协议**：串口通信、流式传输、实时状态监控
- **原子文件操作**：防止保存中断导致数据损坏
- **中文优先设计**：界面和文档主要以中文为主

## 架构设计

### 分层架构

```
┌─────────────────────────────────────────┐
│                 UI层                     │
│           (inkscape_wps/ui)             │
│  • PyQt5(Fluent) / PyQt6 双界面实现      │
│  • WPS 风格交互逻辑                    │
│  • 文档桥接 (document_bridge)          │
├─────────────────────────────────────────┤
│                核心层                    │
│          (inkscape_wps/core)            │
│  • 纯 Python 业务逻辑                  │
│  • 无 GUI 依赖                         │
│  • 可移植到其他平台                    │
├─────────────────────────────────────────┤
│                数据层                    │
│  • JSON/TOML 配置持久化                │
│  • 原子文件操作                        │
│  • 字体资源管理                        │
└─────────────────────────────────────────┘
```

### 核心数据流

```
用户输入 → UI事件 → DocumentBridge → 核心逻辑 → 结果返回 → UI更新
    ↑          │           │              │           │
    │          ↓           ↓              ↓           │
    └── 字体映射 ← HersheyFontMapper ← LayoutLine ← 排版引擎
    │          │           │              │           │
    └── G-code生成 ← VectorPath ← 坐标变换 ← 配置参数
```

## 代码规范

### Python 编码规范

#### 1. 导入规范
```python
# 标准库导入
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

# 第三方库导入
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMainWindow

# 项目内部导入（相对导入优先）
from .hershey import HersheyFontMapper
from ..core.config import MachineConfig
```

#### 2. 类型注解
```python
# 必须使用类型注解
def map_text_to_paths(
    text: str,
    font_config: FontConfig,
    transform: CoordinateTransform
) -> List[VectorPath]:
    """将文本映射为矢量路径。"""
    pass

# 复杂类型使用 TypeAlias
from typing import TypeAlias
VectorPaths: TypeAlias = List[VectorPath]
```

#### 3. 数据类设计
```python
@dataclass(frozen=True)  # 配置类使用 frozen
class MachineConfig:
    z_up_mm: float = 0.0
    z_down_mm: float = 5.0

    def validate(self) -> None:
        """运行时验证逻辑。"""
        if self.z_up_mm >= self.z_down_mm:
            raise ValueError("抬笔高度必须小于落笔高度")
```

#### 4. 异常处理
```python
def load_font_safely(path: Path) -> Optional[HersheyFont]:
    """安全加载字体，返回 None 而不是抛出异常。"""
    try:
        return load_font(path)
    except (OSError, ValueError) as e:
        logger.warning(f"字体加载失败 {path}: {e}")
        return None
```

### 文档规范

#### 1. 模块文档
```python
"""字体映射系统：支持 Hershey、JSON、JHF、奎享格式。

本模块提供将文本转换为单线矢量路径的核心功能，采用延迟加载策略
优化大字库性能。支持字体合并，便于中文大字库与 ASCII 字体叠加使用。

典型用法：
    >>> mapper = HersheyFontMapper(Path("my_font.json"))
    >>> paths = mapper.map_text("Hello 世界")
    >>> len(paths) > 0
    True
"""
```

#### 2. 函数文档
```python
def map_document_lines(
    lines: List[LayoutLine],
    font_mapper: HersheyFontMapper,
    transform: CoordinateTransform
) -> List[VectorPath]:
    """将排版行映射为矢量路径。

    Args:
        lines: 排版行列表，包含文本、字体信息和位置
        font_mapper: 字体映射器实例
        transform: 坐标变换配置

    Returns:
        矢量路径列表，可直接用于 G-code 生成

    Raises:
        FontLoadError: 字体加载失败时抛出
        TransformError: 坐标变换错误时抛出
    """
```

## 开发环境

### 环境配置

```bash
# 1. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或 .venv\Scripts\activate  # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 开发依赖（可选）
pip install pytest pytest-qt black flake8 mypy

# 4. 验证安装
python -m inkscape_wps --help
```

### 开发工具推荐

- **IDE**: VS Code + Python 插件 / PyCharm
- **代码格式化**: black
- **静态检查**: flake8, mypy
- **测试**: pytest + pytest-qt
- **调试**: pdb++ 或 IDE 内置调试器

### 项目结构约定

```
inkscape_wps/
├── core/                    # 核心业务逻辑
│   ├── __init__.py         # 模块导出
│   ├── config.py           # 配置管理
│   ├── hershey.py          # 字体系统
│   ├── grbl.py             # GRBL 通信
│   └── types.py            # 基础数据类型
├── ui/                     # 用户界面
│   ├── main_window.py      # 主窗口 (PyQt6，兼容保留)
│   ├── main_window_fluent.py # 主窗口 (PyQt5 + Fluent，默认)
│   ├── ribbon.py           # Ribbon 控件
│   └── widgets/            # 自定义控件
├── data/                   # 资源文件
│   ├── fonts/              # 字体文件
│   └── preset_svgs/        # SVG 素材
├── tests/                  # 单元测试
│   ├── test_*.py           # 测试文件
│   └── data/               # 测试数据
└── docs/                   # 文档
    ├── api/                # API 文档
    └── design/             # 设计文档
```

## 核心模块详解

### 1. 字体系统 (hershey.py)

#### 架构设计

```python
class HersheyFontMapper:
    """字体映射器：文本 → 矢量路径"""

    def __init__(self, font_path=None, merge_font_path=None):
        self._builtin = {}           # 内置字体
        self._glyphs = {}            # 主字体
        self._lazy_json_path = None  # 延迟加载路径
        self._lock = threading.Lock() # 线程安全
```

#### 关键算法

**字体合并算法**：
```python
def _merge_fonts(self, base_font, merge_font):
    """合并两个字体，后者覆盖前者相同字符。"""
    merged = base_font.copy()
    for char, glyph in merge_font.items():
        merged[char] = glyph  # 覆盖重复字符
    return merged
```

**延迟加载实现**：
```python
def _ensure_lazy_loaded(self):
    """确保延迟加载的字体已载入内存。"""
    if self._lazy_json_loaded:
        return

    with self._lock:
        if self._lazy_json_loaded:  # 双重检查
            return

        if self._lazy_json_path:
            self._load_json_font(self._lazy_json_path)
            self._lazy_json_loaded = True
```

### 2. GRBL 通信 (grbl.py)

#### 协议实现

```python
class GrblController:
    """GRBL 协议控制器"""

    def __init__(self, port, baudrate=115200):
        self.port = serial.Serial(port, baudrate)
        self._buffer_usage = 0
        self._lock = threading.Lock()

    def send_line(self, line: str) -> bool:
        """发送单行 G-code，等待 ok 响应。"""
        with self._lock:
            self.port.write(f"{line}\r\n".encode())
            return self._wait_for_ok()
```

#### 流式传输算法

```python
def _stream_optimize(self, gcode_lines: List[str]) -> Iterator[str]:
    """优化 G-code 流式传输顺序。"""
    buffer_size = self.config.grbl_rx_buffer_size
    current_usage = 0

    for line in gcode_lines:
        line_size = len(line.encode()) + 2  # \r\n
        # 如果添加此行会超出缓冲区，先等待
        while current_usage + line_size > buffer_size:
            yield None  # 发送等待信号
            current_usage = self._get_buffer_usage()

        current_usage += line_size
        yield line
```

### 3. 坐标变换系统

#### 变换链设计

```python
class CoordinateTransform:
    """文档坐标 → 机床坐标的变换链"""

    def __init__(self, config: MachineConfig):
        self.config = config

    def document_to_machine(self, point: Point) -> Point:
        """完整的坐标变换流程。"""
        x, y = point.x, point.y

        # 1. 镜像变换
        if self.config.coord_mirror_x:
            x = 2 * self.config.coord_pivot_x_mm - x
        if self.config.coord_mirror_y:
            y = 2 * self.config.coord_pivot_y_mm - y

        # 2. 缩放变换
        x *= self.config.coord_scale_x
        y *= self.config.coord_scale_y

        # 3. 平移变换
        x += self.config.coord_offset_x_mm
        y += self.config.coord_offset_y_mm

        return Point(x, y)
```

## 扩展开发

### 1. 添加新字体格式

```python
# 在 hershey.py 中扩展
class HersheyFontMapper:
    def _load_custom_format(self, path: Path) -> Dict[str, Glyph]:
        """加载自定义字体格式。"""
        if path.suffix == '.myformat':
            return self._load_myformat(path)

    def _load_myformat(self, path: Path) -> Dict[str, Glyph]:
        """解析 .myformat 字体文件。"""
        # 实现格式解析逻辑
        pass
```

### 2. 开发 UI 插件

```python
# 创建自定义 Ribbon 标签页
class CustomTab(QWidget):
    """自定义功能标签页"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 添加自定义控件
        self.custom_button = QPushButton("自定义功能")
        self.custom_button.clicked.connect(self._on_custom_action)
        layout.addWidget(self.custom_button)

    def _on_custom_action(self):
        """执行自定义功能"""
        pass

# 在主窗口中注册
class MainWindow(QMainWindow):
    def _setup_ribbon(self):
        # ... 现有代码 ...

        # 添加自定义标签页
        self.custom_tab = CustomTab()
        self.ribbon.addTab(self.custom_tab, "自定义")
```

### 3. 添加新文档组件

```python
# 创建新的文档编辑器
class CustomEditor(QWidget):
    """自定义文档编辑器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dirty = False
        self._undo_stack = QUndoStack(self)

    def to_layout_lines(self) -> List[LayoutLine]:
        """转换为排版行，供字体映射使用。"""
        # 实现转换逻辑
        return []

    def clear(self):
        """清空编辑器内容。"""
        # 实现清空逻辑
        self._mark_dirty()

    def _mark_dirty(self):
        """标记文档已修改。"""
        self._dirty = True
        self.documentChanged.emit()
```

## 测试策略

### 1. 单元测试

```python
# tests/test_hershey.py
class TestHersheyFontMapper(unittest.TestCase):

    def setUp(self):
        self.test_font_path = Path("tests/data/test_font.json")

    def test_basic_mapping(self):
        """测试基本字体映射功能。"""
        mapper = HersheyFontMapper(self.test_font_path)
        paths = mapper.map_text("ABC")

        self.assertIsInstance(paths, list)
        self.assertGreater(len(paths), 0)

        # 验证第一个字符
        first_char_paths = [p for p in paths if p.char == 'A']
        self.assertGreater(len(first_char_paths), 0)

    def test_font_merge(self):
        """测试字体合并功能。"""
        base_font = Path("tests/data/base_font.json")
        merge_font = Path("tests/data/merge_font.json")

        mapper = HersheyFontMapper(
            base_font,
            merge_font_path=merge_font
        )

        # 验证合并后包含两个字体的字符
        chars = mapper.get_available_chars()
        self.assertIn('A', chars)  # 基础字体字符
        self.assertIn('中', chars)  # 合并字体字符
```

### 2. 集成测试

```python
# tests/test_integration.py
class TestGrblIntegration:

    def test_full_workflow(self, tmp_path):
        """测试完整的工作流程。"""
        # 1. 创建测试文档
        project_path = tmp_path / "test.inkwps.json"

        # 2. 保存项目文件
        save_project_file(
            project_path,
            title="测试文档",
            word_html="<p>Hello World</p>",
            table_blob={...},
            slides=["<p>测试幻灯片</p>"],
            sketch_blob={}
        )

        # 3. 加载项目文件
        data = load_project_file(project_path)
        self.assertEqual(data["title"], "测试文档")

        # 4. 生成 G-code
        config = MachineConfig()
        mapper = HersheyFontMapper()

        paths = mapper.map_document(data)
        gcode = paths_to_gcode(paths, config)

        # 5. 验证 G-code
        self.assertIn("G0", gcode)
        self.assertIn("G1", gcode)
        self.assertIn("M2", gcode)
```

### 3. UI 测试

```python
# tests/test_ui.py
class TestMainWindow:

    def test_text_editing(self, qtbot):
        """测试文本编辑功能。"""
        window = MainWindow()
        qtbot.addWidget(window)

        # 切换到文字组件
        window.ribbon.setCurrentIndex(0)  # 开始标签页

        # 获取文本编辑器
        text_edit = window.findChild(QTextEdit, "textEdit")
        self.assertIsNotNone(text_edit)

        # 输入文本
        qtbot.keyClicks(text_edit, "Hello World")

        # 验证内容
        self.assertEqual(text_edit.toPlainText(), "Hello World")

        # 验证撤销/重做
        undo_action = window.findChild(QAction, "undoAction")
        undo_action.trigger()
        self.assertEqual(text_edit.toPlainText(), "")
```

## 性能优化

### 1. 字体系统优化

```python
class OptimizedHersheyFontMapper(HersheyFontMapper):
    """优化版本的字体映射器"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = LRUCache(maxsize=1000)  # 字形缓存
        self._preload_thread = None

    def map_text(self, text: str) -> List[VectorPath]:
        """优化文本映射，使用缓存。"""
        result = []

        for char in text:
            # 检查缓存
            if char in self._cache:
                glyph = self._cache[char]
            else:
                glyph = self._load_glyph(char)
                self._cache[char] = glyph

            result.extend(self._glyph_to_paths(glyph, char))

        return result

    def preload_background(self):
        """后台预加载常用字符。"""
        def preload_task():
            common_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
            for char in common_chars:
                self._load_glyph(char)

        self._preload_thread = threading.Thread(target=preload_task)
        self._preload_thread.start()
```

### 2. 内存管理

```python
class MemoryEfficientProject:
    """内存高效的项目管理"""

    def __init__(self):
        self._vector_cache = {}
        self._cache_size_limit = 100 * 1024 * 1024  # 100MB

    def _manage_cache(self):
        """管理矢量缓存大小。"""
        current_size = sum(len(str(v)) for v in self._vector_cache.values())

        if current_size > self._cache_size_limit:
            # 清理最旧的 50% 缓存
            keys = list(self._vector_cache.keys())
            remove_count = len(keys) // 2

            for key in keys[:remove_count]:
                del self._vector_cache[key]
```

## 已知问题与改进方向

### 当前已知问题

#### 1. 性能问题
- **大字体加载慢**：400KB+ 字体首次加载有明显卡顿
- **复杂文档渲染**：大量矢量路径时预览卡顿
- **内存占用**：长时间使用内存占用持续增长

#### 2. 功能限制
- **中文支持不全**：缺少完整中文单线字体
- **富文本功能弱**：相比 WPS 功能差距较大
- **错误处理不足**：部分异常情况处理不够完善

#### 3. 兼容性问题
- **字体格式兼容**：部分第三方字体文件解析失败
- **GRBL 版本差异**：不同 GRBL 固件行为不一致
- **操作系统差异**：macOS/Windows/Linux 字体渲染差异

### 改进路线图

#### 短期目标 (v0.2.0)
- [ ] 增强测试覆盖率到 80%
- [ ] 优化字体加载性能
- [x] 添加基础查找替换功能（文字/演示基础版）
- [ ] 完善错误处理机制

#### 中期目标 (v0.3.0)
- [ ] 实现插件系统
- [ ] 添加更多字体格式支持
- [ ] 优化内存管理
- [ ] 添加英文界面支持

#### 长期目标 (v1.0.0)
- [ ] 完整的 WPS 功能对标（**迭代中**：Fluent 主窗已对齐菜单结构、三件套、格式条、查找替换、字体/选区行为、**撤销/重做**——单线文字用 `StrokeTextEditor` 栈，表格/演示/手绘快照用 `QUndoStack`，与 PyQt6 `MainWindow` 分栈策略一致；**仍属差距**的包括复杂富文本母版、对象嵌入、云字体与云存储、与 WPS 完全对等的 Office 体验，见仓库 `SPEC.md` §4–§5。）
- [ ] 云字体和云存储集成
- [ ] 移动端版本
- [ ] 完整的 API 文档

### 贡献指南

欢迎提交 Issue 和 Pull Request！请遵循以下流程：

1. **Issue 提交**：
   - 清晰描述问题或功能需求
   - 提供复现步骤（如适用）
   - 注明操作系统和 Python 版本

2. **Pull Request**：
   - 遵循代码规范
   - 添加相应的测试
   - 更新相关文档
   - 确保所有测试通过

3. **代码审查**：
   - 至少需要一位核心维护者批准
   - 确保代码质量和架构一致性
   - 验证测试覆盖率和性能影响

## 与 WPS 逐步对标计划

> **定位**：本项目是「写字机 CAM + 类 WPS 编辑体验」，不是 WPS/Office 的完整替代品。下列计划按**交互习惯 → 编辑能力 → 兼容与工程化 → 明确不做**排序，每步应可独立验收，并始终保证 **预览与 G-code 数据流一致**。

### 原则（全阶段遵守）

1. **路径一致性**：任何新模式（样式、列表、表格结构）必须先定义如何落到 `LayoutLine` / `VectorPath`，再谈 UI。
2. **Fluent / PyQt6 行为对齐**：双主窗在「三件套 + 撤销策略 + 插入矢量几何」上保持同一语义（已有中心缩放等，后续改动的验收项需双窗或文档说明）。
3. **Office 导入导出**：只承诺「可映射子集」；在 `SPEC.md` / 用户提示中列出易丢失项（复杂样式、嵌入对象等）。

### 阶段 P0：交互与信息架构（进行中 · 高优先级）

对标 WPS 的「找得到、用得顺」，不扩展笔画能力边界。

| 序号 | 事项 | 验收标准 |
|------|------|----------|
| P0-1 | 导航与子页 | 切换「文件/开始/文字/表格/演示/设备/帮助」后，预览与状态栏与当前子页数据源一致（`stackedWidget.currentChanged` 已接预览刷新）。 |
| P0-2 | 「开始」格式条 | 三件套各自格式条：剪贴板、字体、B/I/U、对齐；表格含行列快捷；演示含段落列表与缩进；与右键菜单行为一致。 |
| P0-3 | 右键与上下文 | 文字/表格网格/演示正文/幻灯片列表/预览 分区菜单齐全；表格行列、幻灯片页级操作与 WPS 缩略图区习惯接近。 |
| P0-4 | 状态栏 | 按子页显示字数 / 表格尺寸 / 幻灯片页码；串口与预览比例可读。 |
| P0-5 | 撤销分层 | 演示页：焦点在富文本内用文档栈，焦点在列表等用整页快照栈；表格/文字策略与实现文档一致。 |
| P0-6 | 快捷键策略 | **已完成**：见 `SPEC.md` **§7**（菜单绑定、剪贴板故意不设菜单快捷键、单线区按键、预览/列表/撤销语义）。 |

**P0 完成定义**：新用户能在无说明情况下完成「打字 → 看预览 → 导出 G-code」，且不在子页切换后出现预览与导出不一致。

### 阶段 P1：文字与演示（富文本子集）

在**不改变单线笔画核心**前提下，增强「像 WPS 一样改稿」的体验。

| 序号 | 事项 | 验收标准 / 备注 |
|------|------|-----------------|
| P1-1 | 演示多级列表 | **基线**：`text_edit_to_layout_lines`（`document_bridge_pyqt5`）按 `QTextLayout` / `blockBoundingRect` 取坐标，**QTextList 与块缩进会体现在行 x 上**，一般无需单独加算列表偏移。验收：演示页多级符号/编号 + 增加缩进后，**预览与 G-code 与屏幕排版一致**；若发现某 Qt 版本下列表项错位，再针对块格式补偿。**可选后续**：列表深度上限 UI 提示。 |
| P1-2 | 演示固定样式预设 | **已完成（Fluent）**：格式条「样式」**标题1 / 标题2 / 正文** + 幻灯片右键同项；`BlockUnderCursor` 整段合并字符/段落格式，**随 `slides` HTML 工程保存**。 |
| P1-3 | 文字页说明与引导 | 已完成（Fluent）：切换到「文字」页时一次性弹出边界提示（单线笔画 → 生成 G-code；富文本样式请切到「表格/演示」），避免用户误以为可在「文字」页像 WPS 一样排版。 |
| P1-4 | 查找替换增强 | 已完成（Fluent）：编辑菜单查找/替换覆盖「演示（QTextEdit）」与「表格（按行优先跨单元格，替换支持当前/全部）」。 |
| P1-5 | 打印/页边距联动 | 已完成（Fluent）：当 `document_margin_mm` 改变/窗口尺寸变化时，同步到演示页 `QTextEdit.documentMargin`，避免预览/G-code 与屏显错位。 |

**不做（P1）**：页眉页脚、目录域、脚注尾注、嵌入式图片公式（除非单独立项做「仅预览不刻」或位图描边管线）。

### 阶段 P2：表格（刻写可用性）

| 序号 | 事项 | 验收标准 / 备注 |
|------|------|-----------------|
| P2-1 | 单元格内富文本一致化 | 已完成（Fluent）：格式条 B/I/U/对齐通过 `WpsTableEditorPyQt5` 当前单元格整格应用；`QTableWidgetItem` 改动会同步存 `ROLE_HTML`，且提示“原地键盘编辑按纯文本刷新格式”作为边界说明。 |
| P2-2 | 合并单元格（可选） | 已完成（Fluent）：表格支持矩形选区合并/拆分；工程序列化记录 `spans`；渲染侧按锚点单元格放大排版区域并跳过被覆盖格，保证预览/G-code 内容唯一性。需手工验收复杂交互（如与插入行列的组合）。 |
| P2-3 | 表格导入导出回归 | 已增强（Fluent/核心）：xlsx 导出会按 `cell_w_mm/cell_h_mm` 写入列宽/行高；xlsx 导入会从工作表列宽/行高反推为统一的 `cell_w_mm/cell_h_mm`（近似取平均），以保证刻写网格间距在可接受误差内。 |
| P2-4 | 窄屏格式条 | 已完成（Fluent）：表格「行列」与演示「段落/样式」改为按钮 + `RoundMenu`（始终折叠），避免窄屏时工具条溢出。 |

**不做（P2）**：公式引擎、透视表、条件格式、数据验证（除非产品转型为通用表格软件）。

### 阶段 P3：工程、兼容与专业感

| 序号 | 事项 | 验收标准 / 备注 |
|------|------|-----------------|
| P3-1 | 导入格式清单 | 已完成（文档）：`SPEC.md` 补全 docx/xlsx/pptx 导入时的主要保留项与丢失项，并说明 wps/et/dps 依赖 LibreOffice。 |
| P3-2 | 导出矩阵 | 已完成（文档）：`SPEC.md` 新增「导出矩阵（当前实现）」表格，覆盖工程/G-code/PNG/DOCX/XLSX/PPTX/Markdown。 |
| P3-3 | 配置与机床向导 | 已完成（Fluent）：设备页分组与说明在界面内提供；发送 G-code / 发送遇 M800 / 从 M800 后继续 / 换纸流程均增加二次确认弹窗，避免误触。 |
| P3-4 | 自动化测试 | 已完成（核心回归）：新增 `test_office_xlsx_dims.py` 覆盖 xlsx 列宽/行高 ↔ `cell_w_mm/cell_h_mm` 映射；并继续依赖已有 `test_gcode.py` 等 core 黄金样例。 |

### 阶段 P4：长期（默认不作为「靠近 WPS」承诺）

以下与**写字机产品目标**弱相关，单独立项前不纳入版本里程碑。

- 协作、修订、批注、云同步  
- 宏、插件市场、模板云库  
- 演示动画/过渡/母版主题、音视频（其中：母版页眉/页脚占位符 B-3 已完成（Fluent）；“主题应用到所有幻灯片” B-2 已完成（迁移期：字体/字号/对齐/段前后距））  
- Office 像素级兼容  

### 与现有「改进路线图」的关系

- **短期 v0.2.0**：优先填 P0 未完成项 + 测试与错误处理。  
- **中期 v0.3.0**：P1～P2 中选 2～3 条可交付项；「插件系统」若做，应服务于字体/后处理而非通用 Office 插件。  
- **长期 v1.0.0**：将「完整 WPS 对标」改为 **「类 WPS 编辑体验 + 可靠刻写管线」达标**；全文 Office 对等从路线图主目标中剥离，避免误解。

---

*文档版本：1.0.0*
*最后更新：2026-04-03（P0-6：SPEC §7 快捷键；macOS 段落对齐 Cmd+）*
