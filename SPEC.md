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
| 界面 | `inkscape_wps/ui/` | 可使用 PyQt6；通过 `document_bridge`、`DrawingViewModel` 等与核心交互。 |

核心对外能力概览：`MachineConfig`、`config_io`（JSON/TOML 加载）、`Point` / `VectorPath`、坐标变换、`HersheyFontMapper`（含 **奎享导出 JSON** 识别与 **大字库延迟加载**）、`kuixiang_font` / `kdraw_paths`、`paths_to_gcode`、`GrblController`（含协议解析、同步发送与可选流式填满缓冲）。

---

## 3. 已实现功能（与 SPEC 对齐）

### 3.1 界面（WPS 风格）

- Ribbon 分页：**开始**、**坐标系**、**设备**、**视图**；分组与竖分隔。
- 左侧 **「文件」** 绿色入口（下拉：新建、保存配置、生成 G-code、退出）。
- 菜单栏、快速访问栏（撤销 / 重做、保存配置、生成 G-code）。
- **三组件（对齐 WPS 三件套形态，互不混在同一富文本里）**：
  - **开始** 页 **「组件」**：**文字** / **表格** / **演示**，以 `QStackedWidget` 切换编辑区。
  - **文字**：`QTextEdit` 富文本；**撤销 / 重做** 仅作用于文字文档；排版 → 路径仍经 `document_bridge.text_edit_to_layout_lines`。
  - **表格**：`ui/table_editor.py` 中 `WpsTableEditor`（`QTableWidget` 独立网格，非 Word 内嵌表）；`to_layout_lines()` 输出与 `document_bridge` 一致的 `LayoutLine` 列表供 Hershey 映射。
  - **演示**：`ui/presentation_editor.py` 中 `WpsPresentationEditor`（左侧幻灯片列表 + 右侧每页 `QTextEdit`）；合并多页路径时各页沿 Y 错开；生成布局时使用**离屏** `QTextEdit` 排版，避免反复改写可见编辑器。
  - **预览与 G-code / 串口发送**：数据源随当前选中的组件切换（`MainWindow._current_paths()` 分支）。
  - **新建**：清空文字、表格、演示三端内容；非文字页的「已修改」提示与 `QTextDocument::modified` 分离（表格/演示用独立脏标记驱动标题栏星号）。
- 文档区：灰底 + 白纸 + **简易水平 mm 标尺**；右侧任务窗格：**路径预览**、**串口日志**。
- 状态栏：在**文字**模式下为行列 / 字数；**表格**为行×列；**演示**为当前幻灯片序号；另有串口状态、预览缩放。
- **开始** 页 **单线字库**：选择 JSON（含 grblapp/奎享导出格式）、恢复包内默认、打开本机 **KDraw** `gcodeFonts` 目录（参阅 `references/third_party/docs/KDraw与单线字库参阅.txt`）。
- **文件菜单（贴近 WPS/Word 顺序）**：**新建**、**打开…**（占位禁用，提示文档存储后续提供）、**插入** 子菜单、**保存配置…**、**生成 G-code…**、**退出**；绿色 **「文件」** 按钮与菜单栏共用同一结构。**插入** 子项：**预置素材**、**来自文件…**、**从图片导入矢量…**、**清除已插入内容**；对话框标题为「导入矢量（SVG）」「导入图片…」。
- **插入矢量图**（Ribbon「图片 / 矢量」与 **文件 → 插入**）：**预置**（`data/preset_svgs/`）、**来自文件**，或 **位图 → Potrace/Autotrace → SVG**（需本机 `potrace` 或 `autotrace`，参阅 `references/third_party/docs/Potrace与位图矢量化参阅.txt`）；解析为 `VectorPath` 后与当前组件路径**合并**出 G-code，**不经 Hershey**。**导入后默认页面居中**（包围盒中心对齐纸张中心，类 WPS 插图）；**开始 → 矢量** 中可随时点 **页面居中**。**变换**：以包围盒中心为枢轴 **等比缩放**，再 **整体平移**（mm，Y 向上为正）。**比例** 滑块（10%–400%）、**偏移 X/Y**、**重置位置**；预览内拖四角缩放、框内平移。
- **文字 / 演示正文编辑（贴近 WPS 常用项）**：**字体 / 字号** 对当前选区合并字符格式（**文字**、**演示** 当前页；**表格** 仍用整表默认字体）；**加粗 / 倾斜 / 下划线**（Ctrl+B / I / U）；**段落** 左/中/右/**两端对齐**（Ctrl+L / E / R / J）。`QTextDocument` **边距** 与配置 **`document_margin_mm`**、纸宽联动（窗口缩放时重算），与 `document_bridge` 横向 mm 一致；主题中减小 QTextEdit 水平 padding，避免与页边距叠加过宽。

### 3.2 核心逻辑

- **坐标系**：镜像 X/Y（枢轴可设）、轴 ×(−1)、平移；与 G-code / 预览共用同一变换。
- **字库**：默认 `data/hershey_roman.json`；可通过配置 **`stroke_font_json_path`** 指向用户 JSON。与 **内置** 字形 **合并**（外置字覆盖同码位）。**支持 `.jhf` / `.hf`**（见 `hershey_jhf`）；可选 **`*.jhf.map.json`**，**无 map 时**按文件内行序将前 95 个 glyph 对应 ASCII 32–126。
- **随包 Hershey .jhf**：`data/fonts/` 含 11 套经校验的 `.jhf` + 映射 JSON、以及 `Hershey-COPYING.txt` 等署名文件；上游同仓库中索引为占位符 `12345` 的文件已剔除（详见该目录 `README.txt`）。
- **奎享兼容**：自动识别 grblapp 所用 **奎享提取 JSON**（`glyphs` + 点 `x,y,t`），按与 `gfont_loader` 一致的 **mm_per_unit（默认 0.01530）** 转为笔画并归一化到 em 框；**不解析 .gfont**（需用 grblapp `export_kuixiang_from_kdraw` 等导出）。
- **大字库性能**：JSON 文件 ≥ **400KB** 时 **延迟到首次排版**再 `json.load`；启动后可在后台线程 **预加载**（`HersheyFontMapper.preload_background()`），减轻首帧卡顿。
- **排版 → 路径**：`document_bridge` 使用 **`QTextBlock`/`QTextLine`** 与文档布局坐标；同一视觉行内按 **字号/字重/斜体** 拆成多段 `LayoutLine`，每段独立 **基线**（行级一致）、**字号**、**参考 ascent** 与 **per_char_advances_mm**；**Tab** 使用约 4 空格宽的默认停距。布局不可用时回退为按换行 + 字体度量。
- **纸张标定**：横向 `mm/px = page_width_mm / 视口宽`；纵向 `page_height_mm / 文档高度 * layout_vertical_scale`（`MachineConfig`，默认 1，用于与实纸长度对齐）。
- **路径**：最近邻排序笔画段；生成 G-code 采用与 **grblapp kuixiang** 一致的顺序：**每笔前 G1 抬笔 Z → G0 到起点 → G1 落笔 Z → 从第二点起 G1**；路径点去重（容差约 1e−4 mm）。
- **程序头尾**：可选 **G92 X0 Y0 Z0**（默认开）；结尾 **M5**；**M2**（默认，不换纸）或 **M30**（配置项，换纸类任务预留）。
- **串口**：打开后发送 **`\r\n\r\n`** 并短时读入；若**完全无应答**再发 **`$I`** 探测，仍无数据则**关闭端口**并提示（避免静默误认已连上）。通过探测后建立读线程；**逐行等待 `ok`**；**error:** / **alarm:** 触发失败并提示；行首 **`?`** 剥离。可选 **流式填满缓冲**（`grbl_streaming`）：在仍逐条等 ok 的前提下按 **`grbl_rx_buffer_size`**（设备页 **RX 预算**）字节预算尽量排队多行；**新建默认 256**，与 **Grbl_Esp32** ``Serial.h`` 的 ``RX_BUFFER_SIZE`` 对齐（参阅 `inkscape_wps/core/grbl_firmware_ref.py` 与本地固件树如 `Grbl_Esp32`）。已连接时可点 **Bf→RX**，用实时状态 ``Bf:`` 第二项（RX 剩余空间，**Idle** 下近似容量）写入预算。**超长单行**会先排空已排队再单独发送。

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

---

## 5. 未实现（规格中曾出现、代码中尚无）

- **中文及大字符集**：包内未带中文大字库；可通过 **奎享导出 JSON** 或自管 JSON 加载。通用 **轮廓 → 单线字**（Inkscape 中心线等）未接入；**已支持** SVG/位图矢量化路径与文字路径合并出 G-code（参阅 §3.1 插入矢量图）。
- **手绘路径**：无内置画布笔工具；**已支持**通过插入 SVG / 位图矢量化得到 `VectorPath` 并与文字等合并。
- **纯 M3/M5 抬落笔 G-code 模式**：固件支持时可用 Z 等效；**未**提供「仅发 M3/M5」的生成开关。
- **固件扩展流程**：**M800 授权**、**换纸 / `[ESPxxx]`** 等 **未**集成。
- **文档文件**：无 **打开/保存** 工程或 `.txt` 项目文件（仅有「新建」清屏与配置保存）。
- **独立撤销栈 / 版本历史**：**文字**依赖 `QTextEdit` 自带撤销；**表格 / 演示** 无统一文档级撤销栈与版本管理。

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
| `grbl_line_timeout_s` | 每行等待 **ok** 超时 |
| `mm_per_pt` | 字号与书写尺度相关约定 |
| `document_margin_mm` | 文档区左边距（mm），映射到机床 X |
| `layout_vertical_scale` | 纵向文档坐标 → 纸张 mm 的额外比例（标定用） |
| `grbl_streaming` | 是否启用流式填满缓冲 |
| `grbl_rx_buffer_size` | 流式发送时接收缓冲字节预算（约）；默认 **256**（Grbl_Esp32 ``RX_BUFFER_SIZE``） |
| `grbl_buffer_target` | 历史字段；旧 JSON 可迁移为 `grbl_rx_buffer_size` |
| `stroke_font_json_path` | 外置单线字库 JSON 路径；空则用包内 `hershey_roman.json` |
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

---

*文档版本：与仓库实现同步维护；未注明日期的修改以 Git 历史为准。*
