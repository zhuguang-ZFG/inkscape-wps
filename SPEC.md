# 写字机上位机规格说明（SPEC）

本文档描述 **inkscape-wps** 当前**设计意图**与**实现状态**的对照，便于评审、排期与验收。实现以仓库内代码为准；若与本文冲突，以代码或提交说明优先，并应回写本文。

---

## 1. 产品定位

- **目标**：类 WPS/Word 编辑体验的桌面端写字机上位机；**核心算法与 UI 分离**，便于后续移植到移动端或其它 GUI。
- **控制器**：GRBL（XYZ）；抬笔 / 落笔以 **Z 轴**为主（与 `Grbl_Esp32` 自定义机头中 `PEN_UP_Z_MM` / `PEN_DOWN_Z_MM` 及对接文档一致）。
- **字形**：屏幕使用系统 TrueType 显示；下位机使用**单线矢量**（内置 / JSON 字库），通过映射与缩放尽量对齐版面，**不等于**轮廓字完全一致。

---

## 2. 架构约束

| 层级 | 路径 | 约束 |
|------|------|------|
| 核心 | `inkscape_wps/core/` | **禁止**依赖 PyQt6/PySide；仅用标准库及可注入的串口对象。 |
| 界面 | `inkscape_wps/ui/` | 允许依赖 Qt（PyQt5/PyQt6）。当前主界面为 **PyQt5 + qfluentwidgets（Fluent）**；PyQt6 版界面保留用于回退/对照。 |

核心对外能力概览：`MachineConfig`、`config_io`（JSON/TOML 加载）、`Point` / `VectorPath`、坐标变换、`HersheyFontMapper`（含 **奎享导出 JSON** 识别与 **大字库延迟加载**）、`kuixiang_font` / `kdraw_paths`、`paths_to_gcode`、`GrblController`（含协议解析、同步发送与可选流式填满缓冲）。

---

## 3. 已实现功能（与 SPEC 对齐）

### 3.1 界面（WPS 风格）

- Fluent 主界面（PyQt5 + qfluentwidgets）：顶部 **WPS 风格菜单栏**（`CommandBar + RoundMenu`），底部 **轻量状态条**（文档名/页面/预览缩放/串口连接状态）。
- 菜单栏（贴近 WPS/Word 常见结构）：**文件 / 编辑 / 视图 / 设备 / 帮助**；支持系统标准快捷键（如 `Ctrl/Cmd+N/O/S/Q`）。
- **最近打开**：记录工程与 Office/WPS 导入文件，持久化到 `~/.config/inkscape-wps/recent_projects.json`。
- **三组件（对齐 WPS 三件套形态，互不混在同一富文本里）**：
  - **开始** 页 **「组件」**：**文字** / **表格** / **演示**，以 `QStackedWidget` 切换编辑区。
  - **文字**：`QTextEdit` 富文本；**撤销 / 重做** 仅作用于文字文档；排版 → 路径仍经 `document_bridge.text_edit_to_layout_lines`。
  - **表格**：`ui/table_editor.py` 中 `WpsTableEditor`（`QTableWidget` 独立网格，非 Word 内嵌表）；`to_layout_lines()` 输出与 `document_bridge` 一致的 `LayoutLine` 列表供 Hershey 映射。
  - **演示**：`ui/presentation_editor.py` 中 `WpsPresentationEditor`（左侧幻灯片列表 + 右侧每页 `QTextEdit`）；合并多页路径时各页沿 Y 错开；生成布局时使用**离屏** `QTextEdit` 排版，避免反复改写可见编辑器。
  - **预览与 G-code / 串口发送**：数据源随当前选中的组件切换（`MainWindow._current_paths()` 分支）。
  - **新建**：清空文字、表格、演示三端内容；非文字页的「已修改」提示与 `QTextDocument::modified` 分离（表格/演示用独立脏标记驱动标题栏星号）。
- 文档区：灰底 + 白纸 + **简易水平 mm 标尺**；右侧任务窗格：**路径预览**、**串口日志**。
- 状态条：显示文档名、当前页面、预览缩放与串口连接状态（迁移期先实现这四项；更细粒度统计可后续补齐）。
- **设备** 页 **抬落笔方式**：**Z 轴 (G1 Z)**（默认）或 **M3 / M5**（`MachineConfig.gcode_pen_mode`，伺服笔类固件）；**M3 S** 数值可配。与 `core/gcode.py` 中 `paths_to_gcode` 一致。**程序附加 G-code**：多行 **前缀 / 后缀**（写入 `gcode_program_prefix` / `gcode_program_suffix`）、**G92 程序零点**、**结尾 M30** 勾选，以及 **+M800** / **+ESP** 快捷插入占位行（须按固件修改）。
- **开始** 页 **单线字库**：选择 JSON（含 grblapp/奎享导出格式）、恢复包内默认、打开本机 **KDraw** `gcodeFonts` 目录（参阅 `references/third_party/docs/KDraw与单线字库参阅.txt`）。**合并字库…**：第二份 JSON 在主编译结果上叠加字形（`stroke_font_merge_json_path`）；**中文小样** 指向包内 `data/fonts/cjk_stroke_sample.json`（仅演示笔画，非大字库）。
- **手绘路径**：**开始 → 矢量** 勾选 **手绘笔** 后，在右侧 **路径预览** 上左键拖动绘制折线（文档 mm，Y 向上）；与文字/表格/演示路径及插入矢量一并进入最近邻排序与 G-code。工程文件 **`sketch`** 字段持久化（`paths` 序列化）；**插入** 菜单含 **清除手绘路径**。
- **撤销 / 重做**：**文字** 仍用 `QTextDocument` 栈；**表格 / 演示 / 手绘** 共用 `QUndoStack`（`ui/nonword_undo.py`），与工具栏/编辑菜单撤销重做在切换组件时自动切换目标。
- **文件菜单（贴近 WPS/Word 顺序）**：**新建**、**打开工程…**（`*.inkwps.json` / JSON，见 `core/project_io.py`）、**插入** 子菜单、**保存工程** / **另存工程为…**（含文字 HTML、表格单元格 HTML、演示各页 HTML、**手绘 sketch.paths**、插入矢量路径与缩放/偏移；**原子写入**：先临时文件再 `replace`，降低保存中断损坏风险）、**保存配置…**（机床 JSON/TOML，与工程分离）、**生成 G-code…**、**导出 G-code 到文件…**（`project_io.write_text_atomic`，与工程保存同款原子写）、**退出**；绿色 **「文件」** 按钮与菜单栏共用同一结构。**新建 / 打开工程 / 退出** 前若文字或表格/演示/插入有未保存修改，会提示 **保存 / 不保存 / 取消**。**帮助**：**快速入门**（对话框摘要）、**查阅 SPEC.md**、**查阅 AI_PROMPTS.md**（仓库根目录，系统默认程序打开）。**插入** 子项：**预置素材**、**来自文件…**、**从图片导入矢量…**、**清除已插入内容**、**清除手绘路径**。
- **插入矢量图**（Ribbon「图片 / 矢量」与 **文件 → 插入**）：**预置**（`data/preset_svgs/`）、**来自文件**，或 **位图 → Potrace/Autotrace → SVG**（需本机 `potrace` 或 `autotrace`，参阅 `references/third_party/docs/Potrace与位图矢量化参阅.txt`）；解析为 `VectorPath` 后与当前组件路径**合并**出 G-code，**不经 Hershey**。**导入后默认页面居中**（包围盒中心对齐纸张中心，类 WPS 插图）；**开始 → 矢量** 中可随时点 **页面居中**。**变换**：以包围盒中心为枢轴 **等比缩放**，再 **整体平移**（mm，Y 向上为正）。**比例** 滑块（10%–400%）、**偏移 X/Y**、**重置位置**；预览内拖四角缩放、框内平移。
- **文字 / 演示 / 表格单元格编辑**：**字体 / 字号**、**加粗 / 倾斜 / 下划线**、**段落对齐** 在 **文字**、**演示** 当前页为选区合并；在 **表格** 为**当前选中单元格**整格应用（单元格内以 HTML 存 `UserRole`，原地键盘编辑会按纯文本刷新格式，见 `table_editor` 提示）。快捷键使用 `QKeySequence.StandardKey`：**macOS 上为 Cmd+B/I/U 与系统对齐快捷键**；**Windows 上为 Ctrl**；两端对齐在无 `AlignJustify` 的平台回退为 **Ctrl+J**。
- **屏幕格式 → G-code 的保留关系**：**对齐、字距、字号、加粗/斜体带来的 QTextLayout 位置**会进入 `LayoutLine` 并映射到笔划坐标，**会保留**。下划线、删除线等 **Qt 装饰** 与 **TrueType 轮廓** 本身**不会**生成额外笔画（仍为 **Hershey/单线字库** 的同一套字形）；**加粗**主要体现为 **更宽的字距与略大的度量缩放**，机床上**不会出现** TrueType 那种「填充实心粗字」。
- **文字 / 演示** `QTextDocument` **边距** 与 **`document_margin_mm`**、纸宽联动；主题中减小 QTextEdit 水平 padding。**演示** 每页以 **HTML** 存稿，换页保留格式。

### 3.2 核心逻辑

- **坐标系**：镜像 X/Y（枢轴可设）、轴 ×(−1)、平移；与 G-code / 预览共用同一变换。
- **字库**：默认 `data/hershey_roman.json`；可通过配置 **`stroke_font_json_path`** 指向用户 JSON。与 **内置** 字形 **合并**（外置字覆盖同码位）。可选 **`stroke_font_merge_json_path`**：第二路 JSON（小文件立即合并，≥400KB 与主编译同为延迟加载链）在主编译结果上再合并。**支持 `.jhf` / `.hf`**（见 `hershey_jhf`）；可选 **`*.jhf.map.json`**，**无 map 时**按文件内行序将前 95 个 glyph 对应 ASCII 32–126。
- **随包 Hershey .jhf**：`data/fonts/` 含 11 套经校验的 `.jhf` + 映射 JSON、以及 `Hershey-COPYING.txt` 等署名文件；上游同仓库中索引为占位符 `12345` 的文件已剔除（详见该目录 `README.txt`）。
- **奎享兼容**：自动识别 grblapp 所用 **奎享提取 JSON**（`glyphs` + 点 `x,y,t`），按与 `gfont_loader` 一致的 **mm_per_unit（默认 0.01530）** 转为笔画并归一化到 em 框；**不解析 .gfont**（需用 grblapp `export_kuixiang_from_kdraw` 等导出）。
- **大字库性能**：JSON 文件 ≥ **400KB** 时 **延迟到首次排版**再 `json.load`；启动后可在后台线程 **预加载**（`HersheyFontMapper.preload_background()`），减轻首帧卡顿。
- **排版 → 路径**：`document_bridge` 使用 **`QTextBlock`/`QTextLine`** 与文档布局坐标；同一视觉行内按 **字号/字重/斜体** 拆成多段 `LayoutLine`，每段独立 **基线**（行级一致）、**字号**、**参考 ascent** 与 **per_char_advances_mm**；**Tab** 使用约 4 空格宽的默认停距。布局不可用时回退为按换行 + 字体度量。**表格单元格** 内 HTML 经 **`html_fragment_to_layout_lines`** 按格宽/格高映射到页坐标后再走同一 `map_document_lines`。
- **纸张标定**：横向 `mm/px = page_width_mm / 视口宽`；纵向 `page_height_mm / 文档高度 * layout_vertical_scale`（`MachineConfig`，默认 1，用于与实纸长度对齐）。
- **路径**：最近邻排序笔画段；生成 G-code 采用与 **grblapp kuixiang** 一致的顺序：**每笔前抬笔 → G0 到起点 → 落笔 → 从第二点起 G1**；抬/落笔为 **G1 Z**（默认）或 **M5 / M3 S…**（`gcode_pen_mode`）；路径点去重（容差约 1e−4 mm）。
- **程序头尾**：可选 **G92 X0 Y0 Z0**（默认开）；结尾 **M5**；**M2**（默认，不换纸）或 **M30**（配置项，换纸类任务预留）。
- **串口**：打开后发送 **`\r\n\r\n`** 并短时读入；若**完全无应答**再发 **`$I`** 探测，仍无数据则**关闭端口**并提示（避免静默误认已连上）。通过探测后建立读线程；**逐行等待 `ok`**；**error:** / **alarm:** 触发失败并提示；行首 **`?`** 剥离。可选 **流式填满缓冲**（`grbl_streaming`）：在仍逐条等 ok 的前提下按 **`grbl_rx_buffer_size`**（设备页 **RX 预算**）字节预算尽量排队多行；**新建默认 256**，与 **Grbl_Esp32** ``Serial.h`` 的 ``RX_BUFFER_SIZE`` 对齐（参阅 `inkscape_wps/core/grbl_firmware_ref.py` 与本地固件树如 `Grbl_Esp32`）。已连接时可点 **Bf→RX**，用实时状态 ``Bf:`` 第二项（RX 剩余空间，**Idle** 下近似容量）写入预算。**超长单行**会先排空已排队再单独发送。
- **换纸/M800 流程**：支持“发送（遇 M800 暂停）→ 继续（从 M800 后）”的两段式发送；以及“前缀 → M800 → 后缀”的流程按钮（到达 M800 视为**流程节点**，等待人工处理后继续，不假设固件必然自动暂停运动）。

- **兼容 WPS/Office 文件导入**（迁移期实现）：
  - `.docx` → 导入到「文字」（转为 `word_html`）。
  - `.xlsx` → 导入到「表格」（转为 `table_blob`，迁移期以纯文本单元格为主）。
  - `.pptx` → 导入到「演示」（每页提取文本，转为 `slides`）。
  - `.wps/.et/.dps` → 若本机存在 LibreOffice（`soffice`），自动转换为 docx/xlsx/pptx 后导入；否则提示用户安装 LibreOffice 或用 WPS 手动另存为标准格式。

### 3.3 配置持久化

- 目录：`~/.config/inkscape-wps/`。优先加载 **`machine_config.toml`**，否则 **`machine_config.json`**（兼容旧安装）；新建默认路径为 **TOML**。
- 依赖：`tomli-w` 写 TOML；Python 3.11+ 用标准库 `tomllib` 读，3.10 用 `tomli`。

### 3.4 蓝牙串口

- 枚举时按描述启发式标记 **蓝牙 SPP**；支持 **仅列出疑似蓝牙端口**。

---

## 4. 部分实现（与理想规格存在差距）

当前 **§3 已覆盖**原 §4 所列：QTextLayout 级排版桥接、JHF、字号/mm 与纵向标定、TOML、流式发送。下列在 **2026-04** 已做一轮加强；表中为**仍存差距**（非阻塞）：

| 能力 | 说明 |
|------|------|
| 复杂富文本 | **已改进**：`document_bridge` 在同一 `QTextLine` 内按 **字号/字重/斜体** 切 run，每段独立 `font_pt` / `ref_ascent` 与 per-char 字宽；**默认 Tab 停距** 为约 4 个空格宽（`apply_default_tab_stops`）。**仍未支持**：图片/对象嵌入、多字体族精细混排（仅按 `QFont` 度量键拆分）、制表位自定义 UI。 |
| JHF 映射 | **已改进**：无 `*.jhf.map.json` 时，按 **文件内行序** 将前 95 个 glyph 映射为 ASCII 32–126（与 `tools/generate_hershey_jhf_maps.py` 一致），并保留 `glyph_id∈[32,126]` 的补键。**仍注意**：与经典 rowmans 行序不一致的第三方 .jhf 可能错位，宜自备 map。 |
| 流式参数 | **已改进**：默认 RX 预算 **256**（对齐 Grbl_Esp32）；设备页 **Bf→RX** 可根据固件上报的 ``Bf:`` 第二项同步（需开启缓冲状态报告）。超长单行仍可能大于硬件 UART/协议缓冲，需调预算或缩短行。 |
| 演示页富文本 | **已改进**：**演示** 各页以 **HTML**（`QTextEdit.toHtml()`）持久化，换页保留加粗/斜体/下划线/对齐等；离屏排版路径生成时同步 `setHtml`。**仍注意**：与 WPS 相比未实现完整主题母版、动画与对象；复杂粘贴自 Office 的 HTML 可能排版略有差异。 |

---

## 5. 未实现或仅部分实现

- **中文及大字符集**：包内仍 **无** 完整中文大字库；**已支持** 主编译 JSON + **合并字库** 叠加奎享大包，以及包内 **cjk_stroke_sample.json** 演示字。通用 **轮廓 → 单线字**（Inkscape 中心线等）未接入；**已支持** SVG/位图矢量化路径与文字路径合并出 G-code（参阅 §3.1）。
- **固件扩展流程**：**已提供** G-code **前缀/后缀** 编辑及 **M800**、**[ESP800]** 占位快捷行、**结尾 M30** 勾选；**不**解析固件专有握手或自动换纸状态机，具体指令须用户按固件文档调整。
- **纯文本 .txt 文档**：无单独「另存为 .txt」；工程为 **JSON**（`format: inkscape-wps-project`）。**不含**机器配置（配置仍 **保存配置…**）。
- **版本历史**：无多版本时间轴；**表格 / 演示 / 手绘** 已有 **撤销 / 重做**（`QUndoStack`），**文字** 仍为编辑器自带撤销。

---

## 6. 配置项摘要（`MachineConfig`）

以下为常用项；完整字段见 `inkscape_wps/core/config.py`。

| 字段 | 含义 |
|------|------|
| `z_up_mm` / `z_down_mm` | 抬笔 / 落笔 Z（mm），默认与 `CLOUD_WRITER_INTEGRATION` 一致时多为 **0 / 5** |
| `draw_feed_rate` / `z_feed_rate` | XY / Z 进给 |
| `dwell_after_pen_*_s` | G4 停顿（**秒**） |
| `coord_*` | 镜像、枢轴、缩放、偏移 |
| `gcode_use_g92` | 是否生成 **G92** |
| `gcode_end_m30` | 结尾 **M30** 与 **M2** 切换 |
| `gcode_pen_mode` | 抬落笔：`z`（**G1 Z**）或 `m3m5`（**M5** 抬、**M3 S** 落） |
| `gcode_m3_s_value` | **M3** 落笔时的 **S** 参数（整数） |
| `grbl_line_timeout_s` | 每行等待 **ok** 超时 |
| `mm_per_pt` | 字号与书写尺度相关约定 |
| `document_margin_mm` | 文档区左边距（mm），映射到机床 X |
| `layout_vertical_scale` | 纵向文档坐标 → 纸张 mm 的额外比例（标定用） |
| `grbl_streaming` | 是否启用流式填满缓冲 |
| `grbl_rx_buffer_size` | 流式发送时接收缓冲字节预算（约）；默认 **256**（Grbl_Esp32 ``RX_BUFFER_SIZE``） |
| `grbl_buffer_target` | 历史字段；旧 JSON 可迁移为 `grbl_rx_buffer_size` |
| `stroke_font_json_path` | 外置单线字库 JSON 路径；空则用包内 `hershey_roman.json` |
| `stroke_font_merge_json_path` | 可选第二路 JSON，在主编译上合并字形（覆盖同码位） |
| `gcode_program_prefix` / `gcode_program_suffix` | 笔画前 / 抬笔后附加行（每行一条，设备页可编辑） |
| `kuixiang_mm_per_unit` | 解析奎享 JSON 时的 font 单位→毫米系数（与 grblapp 默认一致） |

---

## 7. 外部参考（仓库内）

- `references/third_party/docs/README-参阅说明.txt`：PyQt-Fluent-Widgets、qt-material 等**参阅用**说明（主程序不依赖其 GPL 组件）。
- `references/third_party/docs/KDraw与单线字库参阅.txt`：本机 KDraw 路径、奎享 JSON 工作流、Hershey 许可提示、Inkscape 矢量管线说明。
- G-code 序列与 **grblapp** `src/grbl_writer/core/gcode.py` 中 **kuixiang** 思路对齐；串口行为参考同仓库 `grbl_protocol`、连接唤醒逻辑。
- 固件 Z 与 M3/M5 约定以 **Grbl_Esp32** 机头文件及根目录 **CLOUD_WRITER_INTEGRATION.md**（若你本地有该仓库）为准。

---

## 8. 维护约定

- 新增或删减**用户可见能力**时，应同步更新本 SPEC 的 **§3～§5**。
- **破坏性变更**（G-code 头尾、默认 Z、协议行为）须在变更说明中写明，并考虑旧配置兼容。
- **`AI_PROMPTS.md`**：面向 AI 助手的提示词与「项目现状」摘要，宜与 SPEC、代码同步修订（避免仍写「无文档保存」等过时描述）。
- **`README.md`**：运行命令、文档索引、测试入口；与 SPEC 互补，非能力细则来源。
- **测试覆盖**：新增核心功能应考虑补充单元测试（现有 `test_project_io.py`、`test_gcode.py`、`test_hershey_merge.py`、`test_coordinate_transform.py`、`test_config_io.py`）。
- **项目配置**：根目录 `pyproject.toml` 和 `requirements.txt` 应保持依赖同步。

---

*文档版本：与仓库实现同步维护；未注明日期的修改以 Git 历史为准。*
