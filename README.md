# inkscape-wps

类 WPS/Word 体验的 **写字机（GRBL XYZ）上位机**：文字 / 表格 / 演示三组件、单线字库、矢量导入、工程文件与 G-code 导出。

**核心特性**：

- WPS 风格界面（Ribbon + 三组件：文字/表格/演示；界面文案以中文为主）
- 支持多种字库格式（Hershey、JSON、JHF、奎享导出）
- GRBL 协议完整支持（串口通信、流式传输）
- 设备页可选 Z 抬落笔或 M3/M5（`gcode_pen_mode` / `gcode_m3_s_value`）
- 工程文件 `*.inkwps.json`（格式版本 2）与机床配置分离（`machine_config.toml` / `.json`，优先 TOML）；保存与 G-code 导出均支持**原子写入**（`project_io` 临时文件 + `replace`）

## 运行

```bash
python3 -m inkscape_wps
```

**依赖**：

- **Python 3.10+**（3.10 需额外 **tomli** 读 TOML，3.11+ 用标准库 `tomllib`）
- **PyQt5 + qfluentwidgets（PyQt-Fluent-Widgets）**（当前主界面，类 WPS 风格菜单与导航）
- **PyQt6**（保留旧版界面作为回退/对照）
- **pyserial**（串口通信）
- **tomli-w**（写 TOML）
- **Pillow**（位图导入等）
- （可选）**Office/WPS 文件导入**：`.docx/.xlsx/.pptx` 需要 `python-docx` / `openpyxl` / `python-pptx`；`.wps/.et/.dps` 可用 LibreOffice（`soffice`）自动转换后导入

**安装依赖**：

```bash
pip install -r requirements.txt
```

## 文档

| 文件 | 说明 |
|------|------|
| [SPEC.md](SPEC.md) | 规格与实现对照（验收、维护约定） |
| [AI_PROMPTS.md](AI_PROMPTS.md) | AI 协作提示词与项目现状摘要 |

## 测试

```bash
python3 -m unittest discover -s tests -v
```

## 许可

以仓库内各组件许可文件为准（如 Hershey 数据目录中的 COPYING / README）。
