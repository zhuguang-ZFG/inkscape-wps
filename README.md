# inkscape-wps

类 WPS/Word 体验的 **写字机（GRBL XYZ）上位机**：文字 / 表格 / 演示三组件、单线字库、矢量导入、工程文件与 G-code 导出。

项目的**核心中的核心**是“输入内容稳定落到路径并生成正确 `G-code`”；类 WPS 交互主要用于降低学习成本，而不是 1:1 复刻 WPS/Office。

**核心特性**：

- 以 `LayoutLine -> VectorPath -> G-code` 为核心链路，优先保证预览、导出与发送一致
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

开发验证建议安装：

```bash
pip install -r requirements-dev.txt
```

或直接使用项目命令：

```bash
make install-dev
make install
```

## 文档

| 文件 | 说明 |
|------|------|
| [SPEC.md](SPEC.md) | 规格与实现对照（验收、维护约定） |
| [AI_PROMPTS.md](AI_PROMPTS.md) | AI 协作提示词与项目现状摘要 |

## 构建验证

```bash
make verify
# 或
python3 tools/verify.py
```

默认会统一执行：

- `compileall`
- 已安装 `pytest` 时执行 `pytest -q`，否则回退到 `unittest discover`
- 已安装时自动执行 `ruff check`
- 已安装时自动执行 `mypy`

如果希望把缺少 `ruff` / `mypy` 也视为失败，可用：

```bash
make verify-strict
```

也可以单独执行：

```bash
make test
make lint
make typecheck
```

## 打包分发

运行依赖已声明在 `pyproject.toml` 的 `project.dependencies` 中，因此使用：

```bash
pip install .
# 或
pip install -e .
```

时会自动安装运行所需依赖。

如果后续需要生成可直接分发的桌面包，而不是要求目标机器再单独安装 Python 依赖，可使用：

```bash
make bundle
```

该命令会调用 `PyInstaller`，读取 `packaging/inkscape_wps.spec`，把 Qt、Fluent 资源和项目数据文件一起打入分发产物。

`make verify` 和 `make verify-strict` 会额外写出结构化结果到 `logs/verify-report.json`，方便本地排错或在 CI 中作为构建产物保存。

Qt 相关测试若需固定绑定，可设置 `INKSCAPE_WPS_QT_BINDING=pyqt5` 或 `pyqt6`，避免同进程混用两套 Qt。

## 许可

以仓库内各组件许可文件为准（如 Hershey 数据目录中的 COPYING / README）。
