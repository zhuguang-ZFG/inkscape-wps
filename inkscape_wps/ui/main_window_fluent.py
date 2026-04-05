"""Fluent UI 主窗口（PyQt5 + qfluentwidgets）。

说明：
- 仅本机使用：依赖 PyQt-Fluent-Widgets（GPL-3.0）与 PyQt5。
- core/ 不受影响；这里只替换 UI 观感与控件体系。
"""

from __future__ import annotations

import html as html_module
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import QEvent, QPoint, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QShowEvent,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextListFormat,
    QWheelEvent,
)
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QUndoStack,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    CheckBox,
    ComboBox,
    CommandBar,
    FluentIcon,
    FluentWindow,
    InfoBar,
    InfoBarPosition,
    NavigationItemPosition,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SpinBox,
    SwitchButton,
    Theme,
    TitleLabel,
    setTheme,
)
from qfluentwidgets.common.config import qconfig
from qfluentwidgets.common.style_sheet import setCustomStyleSheet

from inkscape_wps.core.config_io import load_machine_config, save_machine_config
from inkscape_wps.core.coordinate_transform import transform_paths
from inkscape_wps.core.gcode import order_paths_nearest_neighbor, paths_to_gcode
from inkscape_wps.core.grbl import (
    GrblController,
    GrblSendError,
    parse_bf_field,
    verify_grbl_responsive,
)
from inkscape_wps.core.hershey import HersheyFontMapper, map_document_lines
from inkscape_wps.core.machine_monitor import MachineMonitor
from inkscape_wps.core.office_export import (
    DocParagraph,
    DocRun,
    OfficeExportError,
    export_docx,
    export_markdown,
    export_pptx,
    export_xlsx,
    has_soffice,
)
from inkscape_wps.core.office_import import (
    OfficeImportError,
    detect_office_kind,
    import_docx_to_html,
    import_markdown_file_to_slides_plain,
    import_markdown_to_plain,
    import_pptx_to_slides,
    import_xlsx_to_table_blob,
    try_convert_wps_private_to_office,
)
from inkscape_wps.core.project_io import (
    deserialize_vector_paths,
    load_project_file,
    save_project_file,
    serialize_vector_paths,
    write_text_atomic,
)
from inkscape_wps.core.kdraw_paths import suggest_gcode_fonts_dirs
from inkscape_wps.core.raster_trace import trace_image_to_svg
from inkscape_wps.core.serial_discovery import filter_ports, list_port_infos
from inkscape_wps.core.svg_import import vector_paths_from_svg_file, vector_paths_from_svg_string
from inkscape_wps.core.transport import TcpTextStream
from inkscape_wps.core.types import Point, VectorPath, paths_bounding_box
from inkscape_wps.ui.document_bridge_pyqt5 import (
    _char_format_at_doc_pos,
    apply_default_tab_stops,
    document_plain_text_skip_strike,
    stroke_editor_to_layout_lines,
)
from inkscape_wps.ui.drawing_view_model_pyqt5 import DrawingViewModelPyQt5
from inkscape_wps.ui.file_flow_text import describe_document_kind
from inkscape_wps.ui.nonword_undo_pyqt5 import NonWordEditCommandPyQt5, capture_nonword_state_pyqt5
from inkscape_wps.ui.presentation_editor_pyqt5 import WpsPresentationEditorPyQt5
from inkscape_wps.ui.stroke_text_editor import StrokeTextEditor
from inkscape_wps.ui.table_editor_pyqt5 import WpsTableEditorPyQt5
from inkscape_wps.ui.wps_theme import WPS_ACCENT

_logger = logging.getLogger(__name__)


def _count_visible_chars(text: str) -> int:
    """统一“字数”口径：忽略空格、制表符与换行。"""
    return len("".join(ch for ch in (text or "") if not ch.isspace()))


def _paragraph_align_shortcut(portable: str) -> QKeySequence:
    """段落对齐快捷键：macOS 用 Meta（Cmd）+ 键，其它平台 Ctrl+。"""
    if sys.platform == "darwin":
        return QKeySequence(portable.replace("Ctrl+", "Meta+", 1))
    return QKeySequence(portable)


class MainWindowFluent(FluentWindow):
    """以 FluentWindow 承载的应用主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self._apply_wps_fluent_theme()

        _cfg_dir = Path.home() / ".config" / "inkscape-wps"
        self._cfg, self._cfg_path = load_machine_config(_cfg_dir)
        self._view_model = DrawingViewModelPyQt5(self._cfg)
        self._mapper = HersheyFontMapper(
            _resolve_stroke_font_path(self._cfg),
            merge_font_path=_resolve_merge_stroke_font_path(self._cfg),
            kuixiang_mm_per_unit=self._cfg.kuixiang_mm_per_unit,
        )
        self._mapper.preload_background()

        self._doc_title = "未命名文档"
        self._project_path: Optional[Path] = None
        self._last_saved_at: Optional[str] = None
        self._last_active_mode = "文字"
        self._recent_projects: List[str] = self._load_recent_projects()
        self._preview_zoom = 1.0
        self._grbl: Optional[GrblController] = None
        self._machine_monitor = MachineMonitor()
        self._pending_bf_for_rx_spin = False
        self._job_state_text = "就绪"
        self._job_progress = (0, 0)
        self._pending_program_after_m800: Optional[List[str]] = None
        self._log_records: List[tuple[str, str]] = []
        self._log_filter = "全部"

        self._sketch_paths: List[VectorPath] = []
        self._insert_paths_base: List[VectorPath] = []
        self._insert_vector_scale: float = 1.0
        self._insert_vector_dx_mm: float = 0.0
        self._insert_vector_dy_mm: float = 0.0
        self._device_setting_groups: List[QGroupBox] = []
        self._wps_font_combos: List[QFontComboBox] = []
        self._wps_font_spins: List[SpinBox] = []
        self._top_nav_buttons: List[tuple[QPushButton, QWidget]] = []
        self._top_nav_titles: List[QLabel] = []
        self._top_nav_meta_labels: List[QLabel] = []
        self._device_page: QWidget | None = None
        self._help_page: QWidget | None = None

        self._nonword_undo_stack = QUndoStack(self)
        self._nonword_undo_stack.setUndoLimit(300)
        self._nonword_undo_anchor: tuple[str, str, str, str, str] = ("", "", "", "", "")
        self._nonword_undo_restoring = False
        self._shown_word_mode_tip = False
        # P4-C-3：演示页修订模式（删除键加删除线，不物理删除；LayoutLine/G-code 忽略删除线字符）
        self._slide_revision_mode = False

        self._build_pages()
        self._status_poll_timer = QTimer(self)
        self._status_poll_timer.setInterval(700)
        self._status_poll_timer.timeout.connect(self._poll_grbl_status)
        self._status_poll_timer.start()
        # P1-5：页边距与三边编辑区（尤其演示页 QTextEdit）同步，避免预览/G-code 与屏显偏移。
        try:
            self._sync_fluent_editor_margins()
        except Exception:
            _logger.debug("同步编辑区页边距失败", exc_info=True)

        # 切换导航页时必须刷新预览：
        # _work_paths() 按当前子页 objectName 取字/表/演示。
        # 注意：不能靠替换 _onCurrentInterfaceChanged。
        # Qt 在首个子页加入时已把槽绑到原方法，替换实例属性不会重连信号。
        try:
            self.stackedWidget.currentChanged.connect(self._on_fluent_stack_page_changed)
        except Exception:
            _logger.debug("连接 stackedWidget.currentChanged 失败", exc_info=True)

        try:
            qconfig.themeChanged.connect(lambda *_: self._restyle_device_setting_groups())
        except Exception:
            pass

        try:
            self.navigationInterface.setMinimumExpandWidth(72)
            self.navigationInterface.setMaximumExpandWidth(88)
        except Exception:
            _logger.debug("调整 Fluent 左导航宽度失败", exc_info=True)

        self._apply_window_title()
        self.resize(1280, 860)
        self._update_action_states()
        self._update_status_line()
        # FluentWindow 首个子页是「文件」。
        # 切到「开始」避免用户误以为未启动，
        # 也避免开始页再与「文字」抢同一控件。
        try:
            self.switchTo(self._home_page)
        except Exception:
            pass

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        # 勿在每次 show 里反复 activateIgnoringOtherApps_，否则 macOS Dock 会持续弹跳

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        try:
            self._sync_fluent_editor_margins()
        except Exception:
            _logger.debug("resize 同步编辑区页边距失败", exc_info=True)
        try:
            self._refresh_preview()
        except Exception:
            _logger.debug("resize 刷新预览失败", exc_info=True)

    def _sync_fluent_editor_margins(self) -> None:
        """
        Fluent 主窗：把 `cfg.document_margin_mm`
        同步到演示页 QTextEdit 的 document margin（px）。

        说明：`text_edit_to_layout_lines` 使用
        `cfg.document_margin_mm` 与 QTextEdit 的布局矩形计算行基线；
        若 QTextEdit 的 `documentMargin` 仍是旧值，会导致预览/G-code 与屏显位置偏移。
        """
        if not hasattr(self, "_presentation_editor"):
            return

        te = self._presentation_editor.slide_editor()
        try:
            vw = max(1, int(te.viewport().width()))
            pw = max(1e-6, float(getattr(self._cfg, "page_width_mm", 1.0)))
            m_mm = float(getattr(self._cfg, "document_margin_mm", 0.0))
            m_px = m_mm * float(vw) / float(pw)
        except Exception:
            return

        self._presentation_editor.set_slide_document_margin_px(m_px)

    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001, N802
        """演示页：修订模式下拦截 Backspace/Delete；获得焦点时刷新撤销/重做菜单状态。"""
        if obj is self._presentation_editor.slide_editor() and event.type() == QEvent.KeyPress:
            if self._slide_revision_mode and isinstance(event, QKeyEvent):
                try:
                    if self._slide_revision_handle_delete(event):
                        return True
                except Exception:
                    _logger.debug("演示修订模式处理按键失败", exc_info=True)
        if event.type() == QEvent.FocusIn and obj is self._presentation_editor.slide_editor():
            QTimer.singleShot(0, self._refresh_undo_redo_menu_state)
        if event.type() == QEvent.FocusIn and obj is self._presentation_editor.slide_list_widget():
            QTimer.singleShot(0, self._refresh_undo_redo_menu_state)
        try:
            return super().eventFilter(obj, event)
        except Exception:
            return False

    def _apply_wps_fluent_theme(self) -> None:
        """Fluent 默认冷白 + 青色强调；改为 WPS 系浅灰底、品牌绿与中文优先字体。"""
        setTheme(Theme.LIGHT)
        qconfig.set(qconfig.themeColor, QColor(WPS_ACCENT), save=False)
        qconfig.set(
            qconfig.fontFamilies,
            ["PingFang SC", "Microsoft YaHei", "Segoe UI"],
            save=False,
        )
        self.setCustomBackgroundColor(QColor("#e6eaef"), QColor(32, 32, 32))
        setCustomStyleSheet(
            self.stackedWidget,
            """
            QStackedWidget {
                background-color: #eef2f5;
            }
            """,
            """
            QStackedWidget {
                background-color: #2c2c2c;
            }
            """,
        )
        try:
            panel = self.navigationInterface.panel
            setCustomStyleSheet(
                panel,
                """
                NavigationPanel {
                    background-color: #edf1f4;
                    border: none;
                }
                """,
                """
                NavigationPanel {
                    background-color: #2a2a2a;
                    border: none;
                }
                """,
            )
        except Exception:
            pass

    def _register_device_setting_group(self, gb: QGroupBox) -> None:
        self._device_setting_groups.append(gb)
        self._apply_device_setting_group_style(gb)

    def _apply_device_setting_group_style(self, gb: QGroupBox) -> None:
        from qfluentwidgets.common.style_sheet import isDarkTheme

        if isDarkTheme():
            gb.setStyleSheet(
                """
                QGroupBox {
                    font-weight: 600;
                    border: 1px solid #5a5a5a;
                    border-radius: 8px;
                    margin-top: 10px;
                    padding: 12px 10px 10px 10px;
                    background-color: #323232;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 6px;
                    color: #e8e8e8;
                }
                """
            )
        else:
            gb.setStyleSheet(
                """
                QGroupBox {
                    font-weight: 600;
                    border: 1px solid #cfd6de;
                    border-radius: 8px;
                    margin-top: 10px;
                    padding: 12px 10px 10px 10px;
                    background-color: #fafbfc;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 6px;
                    color: #2d333a;
                }
                """
            )

    def _restyle_device_setting_groups(self) -> None:
        for gb in self._device_setting_groups:
            self._apply_device_setting_group_style(gb)

    def _create_backstage_metric_card(
        self, title: str, value: str, *, accent: str
    ) -> tuple[QWidget, QLabel]:
        card = QFrame()
        card.setObjectName("backstageInfoCard")
        card.setStyleSheet(
            f"""
            QFrame#backstageInfoCard {{
                border-left: 4px solid {accent};
            }}
            """
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("backstageInfoCardTitle")
        value_label = QLabel(value)
        value_label.setObjectName("backstageInfoCardValue")
        value_label.setStyleSheet(f"color:{accent};")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addStretch(1)
        return card, value_label

    def _create_device_metric_card(
        self, title: str, value: str, *, accent: str
    ) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("deviceMetricCard")
        card.setStyleSheet(
            f"""
            QFrame#deviceMetricCard {{
                background-color: #ffffff;
                border: 1px solid #d7dee6;
                border-left: 4px solid {accent};
                border-radius: 12px;
            }}
            """
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        title_label = QLabel(title)
        title_label.setStyleSheet("color:#71808f;font-size:11px;font-weight:600;")
        value_label = QLabel(value)
        value_label.setStyleSheet("font-size:18px;font-weight:700;color:#233241;")
        value_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return card, value_label

    def _create_info_panel(self, title: str, body: str, *, accent: str = "#217346") -> QFrame:
        card = QFrame()
        card.setObjectName("WpsInfoPanel")
        card.setStyleSheet(
            f"""
            QFrame#WpsInfoPanel {{
                background-color: rgba(255, 255, 255, 0.92);
                border: 1px solid #d8e0e7;
                border-left: 4px solid {accent};
                border-radius: 14px;
            }}
            """
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setStyleSheet("color:#233241;font-size:13px;font-weight:700;")
        body_label = QLabel(body)
        body_label.setWordWrap(True)
        body_label.setStyleSheet("color:#66727e;font-size:12px;line-height:1.45;")
        layout.addWidget(title_label)
        layout.addWidget(body_label)
        return card

    def _create_home_action_button(
        self, text: str, slot, *, primary: bool = False, tip: str | None = None
    ):
        btn = PrimaryPushButton(text) if primary else PushButton(text)
        btn.setFixedHeight(34)
        if tip:
            btn.setToolTip(tip)
        btn.clicked.connect(slot)
        return btn

    def _notify_info(self, title: str, content: str) -> None:
        InfoBar.info(title, content, parent=self, position=InfoBarPosition.TOP)

    def _notify_success(self, title: str, content: str) -> None:
        InfoBar.success(title, content, parent=self, position=InfoBarPosition.TOP)

    def _notify_warning(self, title: str, content: str) -> None:
        InfoBar.warning(title, content, parent=self, position=InfoBarPosition.TOP)

    def _notify_error(self, title: str, content: str) -> None:
        InfoBar.error(title, content, parent=self, position=InfoBarPosition.TOP)

    def _log_event(self, category: str, message: str, *, level: str = "INFO") -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self._log_append(f"{stamp} [{category}/{level}] {message}", category=category)

    def _recent_log_excerpt(self, limit: int = 80) -> str:
        lines = [line for _category, line in self._log_records]
        if not lines:
            return "暂无运行日志。"
        if len(lines) <= limit:
            return "\n".join(lines)
        return "\n".join(lines[-limit:])

    def _render_log_views(self) -> None:
        if self._log_filter == "全部":
            lines = [line for _category, line in self._log_records]
        else:
            lines = [line for category, line in self._log_records if category == self._log_filter]
        text = "\n".join(lines)
        if hasattr(self, "_log"):
            self._log.setPlainText(text)
        if hasattr(self, "_dev_log"):
            self._dev_log.setPlainText(text)

    def _sync_log_filter_widgets(self) -> None:
        for name in ("_log_filter_combo", "_dev_log_filter_combo"):
            combo = getattr(self, name, None)
            if combo is None:
                continue
            idx = combo.findText(self._log_filter)
            if idx >= 0 and combo.currentIndex() != idx:
                combo.blockSignals(True)
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)

    def _set_log_filter(self, value: str) -> None:
        self._log_filter = str(value or "全部")
        self._sync_log_filter_widgets()
        self._render_log_views()

    def _clear_logs(self) -> None:
        self._log_records.clear()
        self._render_log_views()
        self._notify_info("日志", "运行日志已清空。")

    def _table_grid_mode_label(self) -> str:
        try:
            mode = str(self._table_editor.grid_gcode_mode() or "none")
        except Exception:
            mode = "none"
        return {
            "none": "不导出",
            "outer": "仅外框",
            "all": "全部网格",
        }.get(mode, "不导出")

    def _preflight_report(self) -> tuple[str, List[str]]:
        pid = self._current_content_page_id()
        source = self._content_mode_label(pid)
        text = self._current_content_plain_text_for_glyph_check(pid)
        missing = self._missing_glyph_chars(pid)
        paths = self._work_paths()
        errors: List[str] = []
        warnings: List[str] = []
        infos: List[str] = []

        infos.append(f"当前来源：{source}")
        infos.append(
            "纸张尺寸："
            f"{float(getattr(self._cfg, 'page_width_mm', 0.0)):.1f} × "
            f"{float(getattr(self._cfg, 'page_height_mm', 0.0)):.1f} mm"
        )
        infos.append(f"表格网格线：{self._table_grid_mode_label()}")
        infos.append(f"设备连接：{'已连接' if self._grbl is not None else '未连接'}")

        if pid == "slides":
            infos.append(f"幻灯片数量：{self._presentation_editor.slide_count()}")
        elif pid == "table":
            rows, cols = self._table_editor.row_column_count()
            infos.append(f"表格尺寸：{rows} × {cols}")
        else:
            infos.append(f"文本长度：{len(text.strip())} 字符")

        if float(getattr(self._cfg, "page_width_mm", 0.0)) <= 0 or float(
            getattr(self._cfg, "page_height_mm", 0.0)
        ) <= 0:
            errors.append("纸张尺寸必须大于 0，否则预览与 G-code 坐标范围会异常。")
        if int(getattr(self._cfg, "draw_feed_rate", 0) or 0) <= 0:
            errors.append("绘制进给速度必须大于 0。")

        pen_mode = str(getattr(self._cfg, "gcode_pen_mode", "z") or "z").strip().lower()
        if pen_mode in ("m3m5", "m3", "spindle"):
            if int(getattr(self._cfg, "gcode_m3_s_value", 0) or 0) <= 0:
                warnings.append("当前使用 M3/M5 抬落笔，但 S 值为 0，落笔输出可能无效。")
        else:
            z_up = float(getattr(self._cfg, "z_up_mm", 0.0))
            z_down = float(getattr(self._cfg, "z_down_mm", 0.0))
            if z_up <= z_down:
                warnings.append("Z 轴抬笔高度未高于落笔高度，请核对抬落笔参数。")

        if not text.strip() and pid in ("word", "slides"):
            warnings.append(f"当前“{source}”没有文本内容。")
        if not paths:
            errors.append("当前内容还没有可导出的笔画路径。")
        else:
            point_count = sum(len(vp.points) for vp in paths)
            infos.append(f"预览/导出路径：{len(paths)} 段，{point_count} 个点")

        if missing:
            preview = " ".join(missing[:8])
            extra = " ..." if len(missing) > 8 else ""
            warnings.append(f"存在 {len(missing)} 个缺失字符：{preview}{extra}")

        if self._grbl is None:
            warnings.append("当前未连接设备；导出文件不受影响，但发送到机床前需要先连接。")
        else:
            snap = self._machine_monitor.snapshot
            infos.append(f"设备状态：{snap.state}")
            if snap.last_alarm:
                warnings.append(f"设备最近告警：{snap.last_alarm}")

        if not errors and not warnings:
            headline = "检查通过：当前可以直接导出或发送。"
        elif errors:
            headline = f"检查发现 {len(errors)} 个必须先处理的问题。"
        else:
            headline = f"检查发现 {len(warnings)} 个建议先确认的项目。"

        lines = [headline, "", "当前状态"]
        lines.extend(f"- {item}" for item in infos)
        if warnings:
            lines.append("")
            lines.append("建议确认")
            lines.extend(f"- {item}" for item in warnings)
        if errors:
            lines.append("")
            lines.append("必须处理")
            lines.extend(f"- {item}" for item in errors)
        lines.append("")
        lines.append("排查顺序：先看内容来源与缺字形，再看纸张/抬落笔，最后看设备连接与告警。")
        return headline, lines

    def _diagnostic_overview_text(self) -> str:
        headline, lines = self._preflight_report()
        if len(lines) >= 4:
            return f"{headline}\n{lines[2]}  {lines[3].lstrip('- ')}"
        return headline

    def _health_status_payload(self) -> tuple[str, str, str, List[str]]:
        pid = self._current_content_page_id()
        source = self._content_mode_label(pid)
        text = self._current_content_plain_text_for_glyph_check(pid)
        missing = self._missing_glyph_chars(pid)
        paths = self._work_paths()
        errors: List[str] = []
        warnings: List[str] = []
        checks: List[str] = []

        if paths:
            checks.append(f"内容路径正常：{len(paths)} 段可用于预览/G-code")
        else:
            errors.append("当前内容还没有生成有效路径")

        if missing:
            warnings.append(f"缺字形 {len(missing)} 个")
        else:
            checks.append("字形覆盖正常")

        if self._grbl is None:
            warnings.append("设备未连接")
        else:
            snap = self._machine_monitor.snapshot
            if snap.last_alarm:
                warnings.append(f"设备告警：{snap.last_alarm}")
            else:
                checks.append(f"设备在线：{snap.state}")

        if pid in ("word", "slides") and not text.strip():
            warnings.append(f"{source}内容为空")

        if errors:
            return "error", "#c23b32", "需先处理", (errors + warnings + checks)[:3]
        if warnings:
            return "warn", "#b06a12", "建议确认", (warnings + checks)[:3]
        return "ok", "#217346", "可以开始", checks[:3] or ["当前状态正常"]

    def _health_primary_action_spec(self) -> tuple[str, str, str]:
        pid = self._current_content_page_id()
        source = self._content_mode_label(pid)
        text = self._current_content_plain_text_for_glyph_check(pid)
        missing = self._missing_glyph_chars(pid)
        paths = self._work_paths()
        pen_mode = str(getattr(self._cfg, "gcode_pen_mode", "z") or "z").strip().lower()

        if missing:
            return "missing", "查看缺失字符", "优先补齐字形覆盖，避免预览或 G-code 缺笔画。"
        if not paths:
            return "content", f"回到{source}", "先补充当前内容，生成可导出的路径。"
        if self._grbl is None:
            return "device", "去连接设备", "先到设备页连接串口或 TCP，再发送 G-code。"
        snap = self._machine_monitor.snapshot
        if snap.last_alarm:
            return "device", "查看设备告警", "先到设备页确认告警、坐标和缓存状态。"
        if pen_mode in ("m3m5", "m3", "spindle"):
            if int(getattr(self._cfg, "gcode_m3_s_value", 0) or 0) <= 0:
                return "device", "检查抬落笔参数", "当前 M3/M5 的 S 值为 0，请先核对。"
        else:
            z_up = float(getattr(self._cfg, "z_up_mm", 0.0))
            z_down = float(getattr(self._cfg, "z_down_mm", 0.0))
            if z_up <= z_down:
                return "device", "检查抬落笔参数", "当前抬笔高度未高于落笔高度。"
        if pid in ("word", "slides") and not text.strip():
            return "content", f"回到{source}", "当前内容为空，先输入文本再导出。"
        return "preflight", "查看完整检查", "打开完整检查单，确认导出和发送前状态。"

    def _run_health_primary_action(self) -> None:
        action, _label, tip = self._health_primary_action_spec()
        if action == "missing":
            self._show_missing_glyphs_dialog()
            return
        if action == "device":
            self._open_device_page_with_hint(tip)
            return
        if action == "content":
            pid = self._current_content_page_id()
            if pid == "table" and self._table_page is not None:
                self._safe_switch_to(self._table_page, "表格")
            elif pid == "slides" and self._slides_page is not None:
                self._safe_switch_to(self._slides_page, "演示")
            elif self._word_page is not None:
                self._safe_switch_to(self._word_page, "文字")
            self._notify_info("继续处理", tip)
            return
        self._show_preflight_report()

    def _set_health_card_state(self, card: QFrame, title: QLabel, detail: QLabel) -> None:
        _level, color, badge, items = self._health_status_payload()
        title.setText(f"健康检查  ·  {badge}")
        detail.setText("\n".join(f"• {item}" for item in items))
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: #ffffff;
                border: 1px solid {color};
                border-radius: 14px;
            }}
            """
        )
        title.setStyleSheet(f"color:{color};font-size:13px;font-weight:700;")
        detail.setStyleSheet("color:#52606d;font-size:12px;line-height:1.45;")

    def _refresh_health_action_button(self, button: QPushButton) -> None:
        _action, label, tip = self._health_primary_action_spec()
        button.setText(label)
        button.setToolTip(tip)

    def _refresh_diagnostic_summary(self) -> None:
        text = self._diagnostic_overview_text()
        if hasattr(self, "_home_diag_summary"):
            self._home_diag_summary.setText(text)
        if hasattr(self, "_dev_diag_summary"):
            self._dev_diag_summary.setText(text)
        if hasattr(self, "_home_health_card"):
            self._set_health_card_state(
                self._home_health_card, self._home_health_title, self._home_health_detail
            )
        if hasattr(self, "_home_health_action_btn"):
            self._refresh_health_action_button(self._home_health_action_btn)
        if hasattr(self, "_dev_health_card"):
            self._set_health_card_state(
                self._dev_health_card, self._dev_health_title, self._dev_health_detail
            )
        if hasattr(self, "_dev_health_action_btn"):
            self._refresh_health_action_button(self._dev_health_action_btn)

    def _show_preflight_report(self) -> None:
        headline, lines = self._preflight_report()
        self._log_event("预检", headline, level="WARN" if "问题" in headline else "INFO")
        box = QMessageBox(self)
        box.setWindowTitle("开始加工前检查")
        box.setIcon(
            QMessageBox.Warning
            if "问题" in headline or "建议" in headline
            else QMessageBox.Information
        )
        box.setText(headline)
        box.setInformativeText("这份检查单按当前预览来源生成，可直接用于导出前或发送前复核。")
        box.setDetailedText("\n".join(lines))
        box.exec()

    def _show_diagnostics_report(self) -> None:
        headline, lines = self._preflight_report()
        self._log_event("诊断", "打开诊断面板", level="INFO")
        box = QMessageBox(self)
        box.setWindowTitle("诊断报告")
        box.setIcon(QMessageBox.Information)
        box.setText(headline)
        box.setInformativeText("详细内容包含当前检查结果和最近运行日志。")
        box.setDetailedText(
            "\n".join(lines)
            + "\n\nSVG / 位图导入诊断\n"
            + "\n".join(self._svg_diagnostic_lines())
            + "\n\n奎享 / 字库诊断\n"
            + "\n".join(self._font_diagnostic_lines())
            + "\n\n最近运行日志\n"
            + self._recent_log_excerpt()
        )
        box.exec()

    def _svg_diagnostic_lines(self) -> List[str]:
        out: List[str] = []
        inserted = len(self._insert_paths_base)
        total_points = sum(len(vp.points) for vp in self._insert_paths_base)
        out.append(f"- 当前插入矢量段数：{inserted}")
        out.append(f"- 当前插入矢量点数：{total_points}")
        out.append(f"- 当前插图缩放：{self._insert_vector_scale:.3f}")
        out.append(
            f"- 当前插图偏移：X {self._insert_vector_dx_mm:.2f} mm / Y {self._insert_vector_dy_mm:.2f} mm"
        )
        if not self._insert_paths_base:
            out.append("- 未检测到插入矢量。若 SVG 导入后无图形，请先确认文件内是否真的含 path/polyline/line/rect 等可转折线元素。")
            out.append("- 若是位图描摹失败，请先提高原图黑白对比度，再重试描摹。")
            return out
        bb = paths_bounding_box(self._insert_paths_base)
        out.append(
            f"- 插入矢量包围盒：X {bb[0]:.2f}..{bb[2]:.2f} / Y {bb[1]:.2f}..{bb[3]:.2f} mm"
        )
        out.append("- 若预览有图但 G-code 没有线，请继续检查：页面尺寸、镜像/偏移、以及最终工作路径是否为空。")
        return out

    def _font_diagnostic_lines(self) -> List[str]:
        out: List[str] = []
        base_font = _resolve_stroke_font_path(self._cfg)
        merge_font = _resolve_merge_stroke_font_path(self._cfg)
        out.append(f"- 主字库：{base_font if base_font is not None else '未找到'}")
        out.append(f"- 合并字库：{merge_font if merge_font is not None else '未设置'}")
        out.append(f"- 奎享 mm/unit：{float(getattr(self._cfg, 'kuixiang_mm_per_unit', 0.01530)):.5f}")
        pid = self._current_content_page_id()
        missing = self._missing_glyph_chars(pid)
        out.append(f"- 当前内容缺字形数量：{len(missing)}")
        if missing:
            preview = " ".join(missing[:12])
            if len(missing) > 12:
                preview += " ..."
            out.append(f"- 缺失字符预览：{preview}")
            out.append("- 若使用奎享 JSON，请先确认该 JSON 是已导出的文本字库，而不是原始 .gfont 二进制。")
            out.append("- 若已修改 mm/unit，已载入的奎享字形不会自动重算；建议重新加载字库后再检查。")
        else:
            out.append("- 当前内容字形覆盖正常。若仍有缺笔画，更可能是路径过小、参数过细或字库本身笔画定义不完整。")
        return out

    def _show_svg_diagnostics(self) -> None:
        self._log_event("诊断", "打开 SVG / 位图导入诊断", level="INFO")
        box = QMessageBox(self)
        box.setWindowTitle("SVG / 位图导入诊断")
        box.setIcon(QMessageBox.Information)
        box.setText("已生成 SVG / 位图导入诊断。")
        box.setDetailedText("\n".join(self._svg_diagnostic_lines()))
        btn_svg = box.addButton("重新导入 SVG", QMessageBox.ActionRole)
        btn_trace = box.addButton("重新描摹图片", QMessageBox.ActionRole)
        btn_clear = box.addButton("清除插图", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_svg:
            self._insert_svg_from_dialog()
        elif clicked is btn_trace:
            self._insert_bitmap_traced()
        elif clicked is btn_clear:
            self._clear_inserted_vectors()

    def _show_font_diagnostics(self) -> None:
        self._log_event("诊断", "打开奎享 / 字库诊断", level="INFO")
        box = QMessageBox(self)
        box.setWindowTitle("奎享 / 字库诊断")
        box.setIcon(QMessageBox.Information)
        box.setText("已生成奎享 / 字库诊断。")
        box.setDetailedText("\n".join(self._font_diagnostic_lines()))
        btn_missing = box.addButton("查看缺失字符", QMessageBox.ActionRole)
        btn_reset = box.addButton("恢复默认字库", QMessageBox.ActionRole)
        btn_clear_merge = box.addButton("清除合并字库", QMessageBox.ActionRole)
        btn_kdraw = box.addButton("打开 KDraw 字库目录", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_missing:
            self._show_missing_glyphs_dialog()
        elif clicked is btn_reset:
            self._reset_stroke_font_to_bundled()
        elif clicked is btn_clear_merge:
            self._clear_stroke_merge_json()
        elif clicked is btn_kdraw:
            self._open_kdraw_gcode_fonts_dir()

    def _remap_stroke_font(self) -> None:
        self._mapper = HersheyFontMapper(
            _resolve_stroke_font_path(self._cfg),
            merge_font_path=_resolve_merge_stroke_font_path(self._cfg),
            kuixiang_mm_per_unit=self._cfg.kuixiang_mm_per_unit,
        )
        self._mapper.preload_background()
        if hasattr(self, "_word_editor"):
            self._word_editor.set_mapper(self._mapper)
        self._refresh_preview()
        self._update_status_line()

    def _clear_stroke_merge_json(self) -> None:
        self._cfg.stroke_font_merge_json_path = ""
        self._remap_stroke_font()
        self._log_event("字库", "已清除合并字库", level="INFO")
        self._notify_success("字库", "已清除合并字库。")

    def _reset_stroke_font_to_bundled(self) -> None:
        self._cfg.stroke_font_json_path = ""
        self._remap_stroke_font()
        self._log_event("字库", "已恢复包内默认字库", level="INFO")
        self._notify_success("字库", "已恢复包内默认字库。")

    def _open_kdraw_gcode_fonts_dir(self) -> None:
        dirs = suggest_gcode_fonts_dirs()
        if not dirs:
            QMessageBox.information(
                self,
                "KDraw 字库",
                "未检测到常见安装路径下的 gcodeFonts。\n"
                "若已安装奎享 KDraw，可将 .gfont 用 grblapp 的导出工具转为 JSON 后再导入本应用。",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(dirs[0].resolve())))

    def _set_backstage_detail_empty(
        self, message: str, *, action_text: str = "打开选中文件"
    ) -> None:
        self._backstage_detail_name.setText("未选择文件")
        self._backstage_detail_type.setText(message)
        self._backstage_detail_path.setText(
            "提示：双击左侧项目可直接打开；也可以先在「打开」页导入 Office/WPS/Markdown。"
        )
        self._backstage_btn_open.setEnabled(False)
        self._backstage_btn_open.setText(action_text)

    # ---------- UI ----------
    def _build_pages(self) -> None:
        # File Backstage（类 WPS 文件后台视图：左导航 + 右内容）
        self._file_page = QWidget()
        self._file_page.setObjectName("file")
        fv = QVBoxLayout(self._file_page)
        fv.setContentsMargins(16, 16, 16, 16)
        fv.setSpacing(10)
        fv.addWidget(self._build_wps_top_nav())
        fv.addWidget(TitleLabel("文件"))
        fsplit = QSplitter()
        fsplit.setChildrenCollapsible(False)
        self._backstage_nav = QListWidget()
        self._backstage_nav.setObjectName("backstageNav")

        def _fluent_icon(name: str, fallback: str = "FOLDER") -> QIcon:
            ico = getattr(FluentIcon, name, None)
            if ico is None:
                ico = getattr(FluentIcon, fallback, None)
            if ico is None:
                return QIcon()
            try:
                return ico.icon()
            except Exception:
                return QIcon()

        def _add_group(title: str) -> None:
            it = QListWidgetItem(title)
            it.setFlags(Qt.NoItemFlags)
            it.setData(Qt.UserRole, -1)
            f = QFont()
            f.setPointSize(10)
            f.setBold(True)
            it.setFont(f)
            it.setForeground(QBrush(QColor("#7a7f87")))
            self._backstage_nav.addItem(it)

        def _add_nav_item(
            text: str, stack_idx: int, icon_name: str, fallback: str = "FOLDER"
        ) -> None:
            it = QListWidgetItem(_fluent_icon(icon_name, fallback), text)
            it.setData(Qt.UserRole, int(stack_idx))
            self._backstage_nav.addItem(it)

        _add_group("文件")
        _add_nav_item("信息", 0, "DOCUMENT", "FOLDER")
        _add_nav_item("新建", 1, "ADD", "FOLDER")
        _add_nav_item("打开", 2, "FOLDER", "FOLDER")
        _add_nav_item("最近", 3, "HISTORY", "FOLDER")
        _add_group("导出")
        _add_nav_item("导出", 4, "SHARE", "FOLDER")
        _add_group("设置")
        _add_nav_item("选项", 5, "SETTING", "DEVELOPER_TOOLS")
        self._backstage_nav.currentItemChanged.connect(self._on_backstage_nav_item_changed)
        if self._backstage_nav.count() > 1:
            self._backstage_nav.setCurrentRow(1)
        fsplit.addWidget(self._backstage_nav)

        self._backstage_stack = QStackedWidget()

        # 信息
        pg_info = QWidget()
        iv = QVBoxLayout(pg_info)
        iv.setContentsMargins(8, 0, 0, 0)
        iv.setSpacing(12)
        iv.addWidget(TitleLabel("文档信息"))
        self._backstage_info_doc = QLabel("")
        self._backstage_info_doc.setObjectName("backstageInfoLine")
        self._backstage_info_proj = QLabel("")
        self._backstage_info_proj.setObjectName("backstageInfoLine")
        self._backstage_info_soffice = QLabel("")
        self._backstage_info_soffice.setObjectName("backstageInfoLine")
        cards = QWidget()
        cards.setObjectName("backstageCardsHost")
        cards_grid = QGridLayout(cards)
        cards_grid.setContentsMargins(0, 0, 0, 0)
        cards_grid.setHorizontalSpacing(10)
        cards_grid.setVerticalSpacing(10)
        card1, self._backstage_card_words = self._create_backstage_metric_card(
            "字数", "0", accent="#217346"
        )
        card2, self._backstage_card_pages = self._create_backstage_metric_card(
            "页数", "1", accent="#2f6fed"
        )
        card3, self._backstage_card_saved = self._create_backstage_metric_card(
            "最近保存", "未保存", accent="#b06a12"
        )
        card4, self._backstage_card_mode = self._create_backstage_metric_card(
            "当前模式", "文字", accent="#8754d6"
        )
        cards_grid.addWidget(card1, 0, 0)
        cards_grid.addWidget(card2, 0, 1)
        cards_grid.addWidget(card3, 1, 0)
        cards_grid.addWidget(card4, 1, 1)
        self._backstage_info_doc.setWordWrap(True)
        self._backstage_info_proj.setWordWrap(True)
        self._backstage_info_soffice.setWordWrap(True)
        iv.addWidget(cards)
        iv.addWidget(self._backstage_info_doc)
        iv.addWidget(self._backstage_info_proj)
        iv.addWidget(self._backstage_info_soffice)
        iv.addStretch(1)
        self._backstage_stack.addWidget(pg_info)

        # 新建
        pg_new = QWidget()
        nv = QVBoxLayout(pg_new)
        nv.setContentsMargins(8, 0, 0, 0)
        nv.setSpacing(8)
        nv.addWidget(TitleLabel("新建"))
        n1 = PrimaryPushButton("新建空白文档")
        n1.clicked.connect(self._new_project)
        n2 = PushButton("新建并打开文件…")
        n2.clicked.connect(self._open_project)
        nv.addWidget(n1)
        nv.addWidget(n2)
        nv.addStretch(1)
        self._backstage_stack.addWidget(pg_new)

        # 打开
        pg_open = QWidget()
        ov = QVBoxLayout(pg_open)
        ov.setContentsMargins(8, 0, 0, 0)
        ov.setSpacing(8)
        ov.addWidget(TitleLabel("打开与保存"))
        o1 = PrimaryPushButton("打开文件…")
        o1.clicked.connect(self._open_project)
        o2 = PushButton("保存")
        o2.clicked.connect(self._save_project)
        o3 = PushButton("另存为…")
        o3.clicked.connect(self._save_project_as)
        o4 = PushButton("导入 Markdown…")
        o4.setToolTip("将 .md / .markdown 解析为纯文本并载入「文字」页（需已安装 markdown 包）")
        o4.clicked.connect(self._import_markdown_dialog)
        ov.addWidget(o1)
        ov.addWidget(o2)
        ov.addWidget(o3)
        ov.addWidget(o4)
        ov.addStretch(1)
        self._backstage_stack.addWidget(pg_open)

        # 最近
        pg_recent = QWidget()
        rwrap = QSplitter()
        rwrap.setChildrenCollapsible(False)
        rgv = QVBoxLayout(pg_recent)
        rgv.setContentsMargins(0, 0, 0, 0)
        rgv.setSpacing(0)

        left_recent = QWidget()
        lrv = QVBoxLayout(left_recent)
        lrv.setContentsMargins(8, 0, 0, 0)
        lrv.setSpacing(8)
        lrv.addWidget(TitleLabel("最近打开"))
        self._backstage_recent = QListWidget()
        self._backstage_recent.setObjectName("backstageRecentList")
        self._backstage_recent.itemDoubleClicked.connect(self._open_backstage_recent_item)
        self._backstage_recent.currentItemChanged.connect(
            self._on_backstage_recent_selection_changed
        )
        lrv.addWidget(self._backstage_recent, 1)
        rwrap.addWidget(left_recent)

        right_detail = QWidget()
        rdv = QVBoxLayout(right_detail)
        rdv.setContentsMargins(8, 0, 0, 0)
        rdv.setSpacing(8)
        rdv.addWidget(TitleLabel("文件详情"))
        self._backstage_detail_name = QLabel("未选择文件")
        self._backstage_detail_name.setObjectName("backstageDetailName")
        self._backstage_detail_name.setWordWrap(True)
        self._backstage_detail_path = QLabel("")
        self._backstage_detail_path.setObjectName("backstageDetailMeta")
        self._backstage_detail_path.setWordWrap(True)
        self._backstage_detail_type = QLabel("")
        self._backstage_detail_type.setObjectName("backstageDetailMeta")
        self._backstage_btn_open = PrimaryPushButton("打开选中文件")
        self._backstage_btn_open.setEnabled(False)
        self._backstage_btn_open.clicked.connect(self._open_backstage_current)
        rdv.addWidget(self._backstage_detail_name)
        rdv.addWidget(self._backstage_detail_type)
        rdv.addWidget(self._backstage_detail_path)
        rdv.addWidget(self._backstage_btn_open)
        rdv.addStretch(1)
        rwrap.addWidget(right_detail)
        rwrap.setStretchFactor(0, 3)
        rwrap.setStretchFactor(1, 2)
        rgv.addWidget(rwrap, 1)
        self._backstage_stack.addWidget(pg_recent)

        # 导出
        pg_export = QWidget()
        ev = QVBoxLayout(pg_export)
        ev.setContentsMargins(8, 0, 0, 0)
        ev.setSpacing(8)
        ev.addWidget(TitleLabel("导出"))
        self._btn_export_docx = PrimaryPushButton("导出 DOCX")
        self._btn_export_docx.clicked.connect(self._export_docx)
        self._btn_export_xlsx = PushButton("导出 XLSX")
        self._btn_export_xlsx.clicked.connect(self._export_xlsx)
        self._btn_export_pptx = PushButton("导出 PPTX")
        self._btn_export_pptx.clicked.connect(self._export_pptx)
        self._btn_export_md = PushButton("导出 Markdown")
        self._btn_export_md.setToolTip("文字页导出正文；演示页导出为多页（以 --- 分隔）")
        self._btn_export_md.clicked.connect(self._export_markdown)
        self._btn_export_gcode = PushButton("导出 G-code")
        self._btn_export_gcode.clicked.connect(self._export_gcode_to_file_stub)
        self._export_hint = QLabel(
            "会根据当前工作页导出对应内容。建议先保存工程，再执行 Office 或 G-code 导出。"
        )
        self._export_hint.setWordWrap(True)
        self._export_hint.setStyleSheet(
            "color:#66727e;font-size:12px;background:rgba(255,255,255,0.72);"
            "border:1px solid #d9e1e8;border-radius:10px;padding:10px 12px;"
        )
        ev.addWidget(self._btn_export_docx)
        ev.addWidget(self._btn_export_xlsx)
        ev.addWidget(self._btn_export_pptx)
        ev.addWidget(self._btn_export_md)
        ev.addWidget(self._btn_export_gcode)
        ev.addWidget(self._export_hint)
        ev.addStretch(1)
        self._backstage_stack.addWidget(pg_export)

        # 选项
        pg_opt = QWidget()
        pv = QVBoxLayout(pg_opt)
        pv.setContentsMargins(8, 0, 0, 0)
        pv.setSpacing(8)
        pv.addWidget(TitleLabel("选项"))
        self._backstage_cfg_path = QLabel("")
        self._backstage_cfg_path.setWordWrap(True)
        p1 = PrimaryPushButton("保存当前配置")
        p1.clicked.connect(self._save_config)
        pv.addWidget(self._backstage_cfg_path)
        pv.addWidget(p1)
        pv.addStretch(1)
        self._backstage_stack.addWidget(pg_opt)

        fsplit.addWidget(self._backstage_stack)
        fsplit.setStretchFactor(0, 1)
        fsplit.setStretchFactor(1, 4)
        fv.addWidget(fsplit, 1)
        self._apply_backstage_style()
        self._refresh_backstage_info()
        self.addSubInterface(
            self._file_page,
            icon=FluentIcon.FOLDER,
            text="文件",
            position=NavigationItemPosition.TOP,
        )

        # Start page: 先把“文字/表格/演示”三个工作区的骨架搭起来，后续再迁移预览/拖拽/串口等复杂逻辑
        home = QWidget()
        home.setObjectName("home")
        self._home_page = home
        lay = QVBoxLayout(home)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        lay.addWidget(self._build_wps_top_nav())

        # 顶部菜单栏（WPS 风格：文件/编辑/视图/设备/帮助）
        self._menu_bar = CommandBar()
        self._menu_bar.setToolTip("WPS 风格菜单栏（Fluent）")
        self._install_wps_menus()
        lay.addWidget(self._menu_bar)

        # 查找/替换条（基础版，先覆盖文字/演示编辑区）
        fr = QWidget()
        fr_l = QHBoxLayout(fr)
        fr_l.setContentsMargins(0, 0, 0, 0)
        fr_l.setSpacing(6)
        fr_l.addWidget(QLabel("查找"))
        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText("输入关键字")
        self._find_edit.returnPressed.connect(self._find_next_from_box)
        fr_l.addWidget(self._find_edit)
        fr_l.addWidget(QLabel("替换"))
        self._replace_edit = QLineEdit()
        self._replace_edit.setPlaceholderText("输入替换文本")
        fr_l.addWidget(self._replace_edit)
        self._btn_find_next = PushButton("查找下一处")
        self._btn_find_next.clicked.connect(self._find_next_from_box)
        self._btn_replace_one = PushButton("替换当前")
        self._btn_replace_one.clicked.connect(self._replace_current_from_box)
        self._btn_replace_all = PushButton("全部替换")
        self._btn_replace_all.clicked.connect(self._replace_all_from_box)
        fr_l.addWidget(self._btn_find_next)
        fr_l.addWidget(self._btn_replace_one)
        fr_l.addWidget(self._btn_replace_all)
        self._btn_symbols = PushButton("符号")
        self._btn_symbols.setToolTip("插入数学、单位等 Unicode 符号（在「文字」或「演示」页）")
        self._btn_symbols.clicked.connect(self._on_symbol_button_clicked)
        fr_l.addWidget(self._btn_symbols)
        fr_l.addStretch(1)
        lay.addWidget(fr)

        # 顶部：WPS 式快速动作（先用 Fluent 按钮承载）
        bar_l = QSplitter()
        bar_l.setChildrenCollapsible(False)
        # 左侧动作
        left = QWidget()
        left.setObjectName("homeActionPanel")
        left.setStyleSheet(
            """
            QWidget#homeActionPanel {
                background-color: #ffffff;
                border: 1px solid #d8dee6;
                border-radius: 14px;
            }
            """
        )
        left_v = QVBoxLayout(left)
        left_v.setContentsMargins(14, 14, 14, 14)
        left_v.setSpacing(8)
        quick_title = QLabel("常用操作")
        quick_title.setStyleSheet("color:#233241;font-size:13px;font-weight:700;")
        left_v.addWidget(quick_title)
        quick_hint = QLabel(
            "把最常用的打开、保存、导入和导出收在一起，方便像办公软件一样快速起步。"
        )
        quick_hint.setWordWrap(True)
        quick_hint.setStyleSheet("color:#6c7a88;font-size:12px;")
        left_v.addWidget(quick_hint)
        self._btn_open = self._create_home_action_button("打开工程…", self._open_project)
        self._btn_new = self._create_home_action_button("新建空白", self._new_project, primary=True)
        self._btn_save = self._create_home_action_button(
            "保存工程", self._save_project, primary=True
        )
        self._btn_export_g = self._create_home_action_button(
            "导出 G-code…", self._export_gcode_to_file_stub
        )
        self._btn_import_md = self._create_home_action_button(
            "导入 Markdown…", self._import_markdown_dialog
        )
        self._btn_recent = self._create_home_action_button(
            "最近文件",
            self._show_backstage,
            tip="打开类似 WPS 的文件后台视图，查看最近文档与导出入口。",
        )
        left_v.addWidget(self._btn_new)
        left_v.addWidget(self._btn_open)
        left_v.addWidget(self._btn_save)
        left_v.addWidget(self._btn_import_md)
        left_v.addWidget(self._btn_export_g)
        left_v.addWidget(self._btn_recent)
        left_v.addStretch(1)
        bar_l.addWidget(left)

        # 右侧：简要指引（优先可读性，减少「未完工」观感）
        right = QFrame()
        right.setObjectName("homeQuickCard")
        right.setStyleSheet(
            """
            QFrame#homeQuickCard {
                background-color: #f9fbfc;
                border: 1px solid #d8dee6;
                border-radius: 14px;
            }
            """
        )
        rv = QVBoxLayout(right)
        rv.setContentsMargins(18, 18, 18, 18)
        rv.setSpacing(10)
        rv.addWidget(TitleLabel("快速上手"))
        badge = QLabel("WPS 风格工作台")
        badge.setObjectName("homeQuickBadge")
        badge.setStyleSheet(
            """
            QLabel#homeQuickBadge {
                color: #0f5a34;
                background: #e7f4eb;
                border: 1px solid #cce7d5;
                border-radius: 999px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            """
        )
        rv.addWidget(badge, 0, Qt.AlignLeft)
        desc = QLabel(
            "1. 对标 WPS 三件套："
            "「文字」单线书写、「表格」网格、「演示」左列表+多页富文本；"
            "预览随当前页切换。\n"
            "2. 「开始」条：剪贴板 + 字体 + B/I/U + 对齐；"
            "表格页「行列」快捷；演示页「段落」列表/缩进 + "
            "「样式」标题1/标题2/正文预设（随工程保存）；"
            "表格/演示右键亦可用。预览：缩放、复制/导出 PNG；"
            "幻灯片列表：页管理。状态栏：字数/表格尺寸/页码。"
            "「视图」：预览缩放与导出。\n"
            "3. 「插入」可导入 Markdown 与符号；"
            "「页面布局」进入纸张/页边距/坐标设置；"
            "「审阅」用于演示页修订。\n"
            "4. 「设备」页核对 Z/进给/坐标/纸张；先导出 G-code 再小范围试写。"
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        desc.setStyleSheet("color:#3d444d;font-size:13px;")
        rv.addWidget(desc)
        rv.addStretch(1)
        bar_l.addWidget(right)
        bar_l.setStretchFactor(1, 1)
        lay.addWidget(bar_l)

        # 主体：开始页仅放说明 + 预览/日志；单线编辑区只在「文字」页。
        # 同一 QWidget 不能挂到两个父级；
        # 此前 home 与「文字」共用 _workspace 会导致 home 侧被掏空。
        split = QSplitter()
        split.setChildrenCollapsible(False)
        home_left = QWidget()
        hl = QVBoxLayout(home_left)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(10)
        start_card = self._create_info_panel(
            "开始",
            "先从“文字”“表格”或“演示”进入对应工作区。右侧会跟随当前工作区刷新预览和日志，设备连接与发送集中放在“设备”页。",
            accent="#217346",
        )
        hl.addWidget(start_card)
        _home_hint = QLabel(
            "推荐流程：新建或打开工程 → 编辑内容 → 检查右侧预览 → "
            "进入设备页核对参数 → 导出或发送 G-code。"
        )
        _home_hint.setWordWrap(True)
        _home_hint.setStyleSheet("color:#52606d;font-size:12px;")
        hl.addWidget(_home_hint)
        self._home_health_card = QFrame()
        home_health_layout = QVBoxLayout(self._home_health_card)
        home_health_layout.setContentsMargins(14, 14, 14, 14)
        home_health_layout.setSpacing(6)
        self._home_health_title = QLabel("健康检查")
        self._home_health_detail = QLabel()
        self._home_health_detail.setWordWrap(True)
        home_health_layout.addWidget(self._home_health_title)
        home_health_layout.addWidget(self._home_health_detail)
        self._home_health_action_btn = PrimaryPushButton("查看完整检查")
        self._home_health_action_btn.clicked.connect(self._run_health_primary_action)
        home_health_layout.addWidget(self._home_health_action_btn)
        hl.addWidget(self._home_health_card)
        self._home_diag_summary = QLabel()
        self._home_diag_summary.setWordWrap(True)
        self._home_diag_summary.setStyleSheet("color:#52606d;font-size:12px;")
        hl.addWidget(
            self._create_info_panel(
                "开始前检查",
                "导出或发送前，先看这一条摘要；如果出现缺字形、空路径或设备未连接，会直接在这里暴露。",
                accent="#b06a12",
            )
        )
        hl.addWidget(self._home_diag_summary)
        home_diag_row = QHBoxLayout()
        home_diag_row.setSpacing(8)
        btn_home_preflight = PushButton("开始加工前检查")
        btn_home_preflight.clicked.connect(self._show_preflight_report)
        btn_home_diag = PushButton("查看诊断")
        btn_home_diag.clicked.connect(self._show_diagnostics_report)
        home_diag_row.addWidget(btn_home_preflight)
        home_diag_row.addWidget(btn_home_diag)
        home_diag_row.addStretch(1)
        hl.addLayout(home_diag_row)
        hl.addWidget(
            self._create_info_panel(
                "当前工作台",
                "首页负责快速进入和总览；文件页适合打开、导入和导出；帮助页放说明文档入口。这样不会把常用动作藏得太深。",
                accent="#2f6fed",
            )
        )
        hl.addStretch(1)

        task_wrap = QWidget()
        tv = QVBoxLayout(task_wrap)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(10)
        self._preview = _PreviewView()
        self._preview.zoomChanged.connect(self._on_preview_zoom_changed)
        self._preview.setContextMenuPolicy(Qt.CustomContextMenu)
        self._preview.customContextMenuRequested.connect(
            lambda pos: self._open_preview_context_menu(self._preview.mapToGlobal(pos))
        )
        log_tools = QWidget()
        log_tools_l = QHBoxLayout(log_tools)
        log_tools_l.setContentsMargins(0, 0, 0, 0)
        log_tools_l.setSpacing(8)
        log_tools_l.addWidget(QLabel("日志筛选"))
        self._log_filter_combo = ComboBox()
        for item in ("全部", "导出", "发送", "设备", "预检", "诊断", "运行"):
            self._log_filter_combo.addItem(item)
        self._log_filter_combo.currentTextChanged.connect(self._set_log_filter)
        log_tools_l.addWidget(self._log_filter_combo)
        btn_clear_logs = PushButton("清空日志")
        btn_clear_logs.clicked.connect(self._clear_logs)
        log_tools_l.addWidget(btn_clear_logs)
        log_tools_l.addStretch(1)
        self._log = PlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("日志：预览刷新与部分状态；串口收发详情见「设备」页右侧。")
        tv.addWidget(self._build_task_pane_card("路径预览", self._preview), 3)
        tv.addWidget(self._build_task_pane_card("日志筛选", log_tools), 0)
        tv.addWidget(self._build_task_pane_card("运行日志", self._log), 2)
        split.addWidget(home_left)
        split.addWidget(task_wrap)
        split.setStretchFactor(0, 7)
        split.setStretchFactor(1, 3)
        lay.addWidget(split, 1)

        self._workspace = QWidget()
        self._workspace.setObjectName("WordWorkspace")
        self._workspace.setStyleSheet("QWidget#WordWorkspace{background:transparent;}")
        wv = QVBoxLayout(self._workspace)
        wv.setContentsMargins(0, 0, 0, 0)
        wv.setSpacing(8)
        title_row = QWidget()
        title_row.setObjectName("WordWorkspaceHeader")
        title_row.setStyleSheet(
            """
            QWidget#WordWorkspaceHeader {
                background-color: #f2f6f9;
                border: 1px solid #d6dee6;
                border-radius: 12px;
            }
            """
        )
        tr = QHBoxLayout(title_row)
        tr.setContentsMargins(12, 8, 12, 8)
        tr.setSpacing(10)
        self._workspace_title = TitleLabel("文字")
        tr.addWidget(self._workspace_title)
        tr.addStretch(1)
        line_space_lab = QLabel("单线行距")
        line_space_lab.setStyleSheet("color:#44505c;font-size:12px;font-weight:600;")
        tr.addWidget(line_space_lab)
        self._stroke_line_spacing_spin = QDoubleSpinBox()
        self._stroke_line_spacing_spin.setFixedHeight(30)
        self._stroke_line_spacing_spin.setMinimumWidth(84)
        self._stroke_line_spacing_spin.setRange(1.0, 3.0)
        self._stroke_line_spacing_spin.setSingleStep(0.05)
        self._stroke_line_spacing_spin.setDecimals(2)
        self._stroke_line_spacing_spin.setValue(
            float(getattr(self._cfg, "stroke_editor_line_spacing", 1.45))
        )
        tr.addWidget(self._stroke_line_spacing_spin)
        wv.addWidget(title_row)

        self._workspace_stack = QWidget()
        self._workspace_stack.setObjectName("WordWorkspacePaper")
        self._workspace_stack.setStyleSheet(
            """
            QWidget#WordWorkspacePaper {
                background-color: #ffffff;
                border: 1px solid #e1e7ee;
                border-radius: 12px;
            }
            """
        )
        wsv = QVBoxLayout(self._workspace_stack)
        wsv.setContentsMargins(16, 16, 16, 16)
        wsv.setSpacing(0)

        self._word_editor = StrokeTextEditor(self._cfg, self._mapper)
        self._word_editor.textChanged.connect(self._refresh_preview)
        self._word_editor.textChanged.connect(self._refresh_undo_redo_menu_state)
        self._word_editor.textChanged.connect(self._update_status_line)
        self._stroke_line_spacing_spin.valueChanged.connect(self._on_stroke_line_spacing_changed)
        wsv.addWidget(self._word_editor)

        _word_surface_host, self._word_surface_shell = self._build_document_surface(
            self._workspace_stack,
            max_width=self._page_mm_to_surface_width(
                float(getattr(self._cfg, "page_width_mm", 210.0))
            ),
            margins=16,
        )
        wv.addWidget(_word_surface_host, 1)

        # 底部状态条（轻量，模仿 WPS 底部状态栏）
        self._status_line = QLabel()
        self._status_line.setObjectName("WpsStatusLine")
        self._status_line.setTextFormat(Qt.RichText)
        self._status_line.setOpenExternalLinks(False)
        self._status_line.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self._status_line.linkActivated.connect(self._on_status_line_link_activated)
        self._status_line.setStyleSheet(
            """
            QLabel#WpsStatusLine {
                padding: 8px 12px;
                color: #32404d;
                background: #f3f6f8;
                border: 1px solid #d5dde5;
                border-radius: 10px;
                font-size: 12px;
            }
            """
        )
        lay.addWidget(self._status_line)

        # 添加为 FluentWindow 的子页面
        self.addSubInterface(
            home, icon=FluentIcon.HOME, text="开始", position=NavigationItemPosition.TOP
        )

        self._word_page = QWidget()
        self._word_page.setObjectName("word")
        word_l = QVBoxLayout(self._word_page)
        word_l.setContentsMargins(12, 12, 12, 12)
        word_l.setSpacing(10)
        word_l.addWidget(self._build_wps_top_nav())
        word_l.addWidget(self._build_mode_ribbon("word"))
        word_l.addWidget(self._make_wps_ruler_bar())
        word_l.addWidget(self._workspace, 1)
        self.addSubInterface(
            self._word_page, icon=FluentIcon.EDIT, text="文字", position=NavigationItemPosition.TOP
        )

        self._table_page = QWidget()
        self._table_page.setObjectName("table")
        table_l = QVBoxLayout(self._table_page)
        table_l.setContentsMargins(12, 12, 12, 12)
        table_l.setSpacing(10)
        table_l.addWidget(self._build_wps_top_nav())
        self._table_editor = WpsTableEditorPyQt5(self._cfg)
        self._table_editor.set_font_point_size_resolver(
            lambda: float(
                self._word_editor.font().pointSizeF() or self._word_editor.font().pointSize() or 12
            )
        )
        self._table_editor.contentChanged.connect(self._refresh_preview)
        self._table_editor.contentChanged.connect(self._on_nonword_content_changed)
        self._table_editor.contentChanged.connect(self._update_status_line)
        self._table_editor.connect_toolbar_context_refresh(self._wps_refresh_font_toolbar_context)
        table_l.addWidget(self._build_mode_ribbon("table"))
        _table_surface_host, self._table_surface_shell = self._build_document_surface(
            self._table_editor,
            max_width=min(
                1180,
                self._page_mm_to_surface_width(float(getattr(self._cfg, "page_width_mm", 210.0)))
                + 140,
            ),
            margins=16,
        )
        table_l.addWidget(_table_surface_host, 1)
        self.addSubInterface(
            self._table_page,
            icon=FluentIcon.LAYOUT,
            text="表格",
            position=NavigationItemPosition.TOP,
        )

        self._slides_page = QWidget()
        self._slides_page.setObjectName("slides")
        ppt_l = QVBoxLayout(self._slides_page)
        ppt_l.setContentsMargins(12, 12, 12, 12)
        ppt_l.setSpacing(10)
        ppt_l.addWidget(self._build_wps_top_nav())
        self._presentation_editor = WpsPresentationEditorPyQt5(self._cfg)
        try:
            self._presentation_editor.slide_editor().setObjectName("PresentationSlideEditor")
        except Exception:
            _logger.debug("设置演示编辑器 objectName 失败", exc_info=True)
        self._presentation_editor.contentChanged.connect(self._refresh_preview)
        self._presentation_editor.contentChanged.connect(self._on_nonword_content_changed)
        self._presentation_editor.contentChanged.connect(self._update_status_line)
        self._presentation_editor.currentSlideChanged.connect(lambda *_: self._update_status_line())
        _slide_te = self._presentation_editor.slide_editor()
        _slide_te.cursorPositionChanged.connect(self._wps_refresh_font_toolbar_context)
        _slide_te.selectionChanged.connect(self._wps_refresh_font_toolbar_context)
        ppt_l.addWidget(self._build_mode_ribbon("slides"))
        ppt_l.addWidget(self._make_wps_ruler_bar())
        _slides_surface_host, self._slides_surface_shell = self._build_document_surface(
            self._presentation_editor,
            max_width=min(
                1220,
                self._page_mm_to_surface_width(float(getattr(self._cfg, "page_width_mm", 210.0)))
                + 180,
            ),
            margins=16,
        )
        ppt_l.addWidget(_slides_surface_host, 1)
        self.addSubInterface(
            self._slides_page,
            icon=FluentIcon.VIEW,
            text="演示",
            position=NavigationItemPosition.TOP,
        )

        self._install_editor_context_menus()

        self._device_page = QWidget()
        self._device_page.setObjectName("device")
        dv = QVBoxLayout(self._device_page)
        dv.setContentsMargins(12, 12, 12, 12)
        dv.setSpacing(10)
        dv.addWidget(self._build_wps_top_nav())
        dv.addWidget(TitleLabel("设备与机床"))
        dv.addWidget(
            self._create_info_panel(
                "上机前建议",
                "先确认纸张尺寸、页边距、抬落笔和坐标映射，再连接设备做小范围试写。发送中断后可根据右侧作业状态决定是否断点续发。",
                accent="#b06a12",
            )
        )

        row = QSplitter()
        row.setChildrenCollapsible(False)

        left_scroll = QScrollArea()
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setWidgetResizable(True)
        left_scroll.setStyleSheet(
            """
            QScrollArea {
                background: transparent;
                border: none;
            }
            """
        )
        left_inner = QWidget()
        lv = QVBoxLayout(left_inner)
        lv.setContentsMargins(0, 0, 8, 0)
        lv.setSpacing(8)

        gb_motion = QGroupBox("上机前检查 · 笔行程与进给")
        self._register_device_setting_group(gb_motion)
        gmv = QGridLayout(gb_motion)
        gmv.setHorizontalSpacing(10)
        gmv.setVerticalSpacing(8)
        ri = 0
        gmv.addWidget(QLabel("抬笔 Z (mm)"), ri, 0)
        self._z_up = QDoubleSpinBox()
        self._z_up.setRange(-50, 50)
        self._z_up.setDecimals(3)
        self._z_up.setToolTip("与固件抬笔高度一致；抬不够会擦纸。")
        gmv.addWidget(self._z_up, ri, 1)
        ri += 1
        gmv.addWidget(QLabel("落笔 Z (mm)"), ri, 0)
        self._z_down = QDoubleSpinBox()
        self._z_down.setRange(-50, 50)
        self._z_down.setDecimals(3)
        self._z_down.setToolTip("与固件落笔深度一致；过深可能压坏纸面。")
        gmv.addWidget(self._z_down, ri, 1)
        ri += 1
        gmv.addWidget(QLabel("XY 进给"), ri, 0)
        xy_l = QLabel("mm/min")
        xy_l.setStyleSheet("color:#6b7280;font-size:12px;")
        xy_h = QHBoxLayout()
        self._draw_feed_spin = SpinBox()
        self._draw_feed_spin.setRange(100, 20000)
        self._draw_feed_spin.setToolTip("G1 书写进给。")
        xy_h.addWidget(self._draw_feed_spin)
        xy_h.addWidget(xy_l)
        xy_h.addStretch(1)
        gmv.addLayout(xy_h, ri, 1)
        ri += 1
        gmv.addWidget(QLabel("Z 进给"), ri, 0)
        zz_l = QLabel("mm/min")
        zz_l.setStyleSheet("color:#6b7280;font-size:12px;")
        zz_h = QHBoxLayout()
        self._z_feed_spin = SpinBox()
        self._z_feed_spin.setRange(10, 6000)
        zz_h.addWidget(self._z_feed_spin)
        zz_h.addWidget(zz_l)
        zz_h.addStretch(1)
        gmv.addLayout(zz_h, ri, 1)
        ri += 1
        gmv.addWidget(QLabel("抬落笔方式"), ri, 0)
        self._pen_mode_combo = QComboBox()
        self._pen_mode_combo.addItem("Z 轴 (G1 Z)", "z")
        self._pen_mode_combo.addItem("M3 / M5（伺服笔）", "m3m5")
        self._pen_mode_combo.setToolTip("默认 Z 抬落；伺服笔类固件选 M3/M5。")
        gmv.addWidget(self._pen_mode_combo, ri, 1)
        ri += 1
        gmv.addWidget(QLabel("M3 S（落笔）"), ri, 0)
        self._m3_s_spin = SpinBox()
        self._m3_s_spin.setRange(0, 10000)
        self._m3_s_spin.setToolTip("仅 M3/M5 模式时用于 M3 S。")
        gmv.addWidget(self._m3_s_spin, ri, 1)
        ri += 1
        self._cb_rapid_after_up = CheckBox("抬笔后空移用 G0")
        self._cb_rapid_after_up.setToolTip("关闭则抬笔后仍用 G1 到下一笔起点（部分机台更稳）。")
        gmv.addWidget(self._cb_rapid_after_up, ri, 0, 1, 2)
        lv.addWidget(gb_motion)

        gb_cal = QGroupBox("版式标定（屏幕 → 机床）")
        self._register_device_setting_group(gb_cal)
        gcal = QGridLayout(gb_cal)
        gcal.setHorizontalSpacing(10)
        gcal.setVerticalSpacing(8)
        ri = 0
        gcal.addWidget(QLabel("mm / pt"), ri, 0)
        self._mm_per_pt_spin = QDoubleSpinBox()
        self._mm_per_pt_spin.setRange(0.05, 5.0)
        self._mm_per_pt_spin.setSingleStep(0.05)
        self._mm_per_pt_spin.setDecimals(3)
        self._mm_per_pt_spin.setToolTip("字号换算到毫米；字太大或太小优先调此项。")
        gcal.addWidget(self._mm_per_pt_spin, ri, 1)
        ri += 1
        gcal.addWidget(QLabel("左边距 (mm)"), ri, 0)
        self._doc_margin_spin = QDoubleSpinBox()
        self._doc_margin_spin.setRange(0, 120)
        self._doc_margin_spin.setDecimals(2)
        gcal.addWidget(self._doc_margin_spin, ri, 1)
        ri += 1
        gcal.addWidget(QLabel("纵向比例"), ri, 0)
        self._layout_v_scale_spin = QDoubleSpinBox()
        self._layout_v_scale_spin.setRange(0.25, 4.0)
        self._layout_v_scale_spin.setSingleStep(0.05)
        self._layout_v_scale_spin.setDecimals(3)
        self._layout_v_scale_spin.setToolTip("文档纵向 → 纸长；用于与实纸长度对齐。")
        gcal.addWidget(self._layout_v_scale_spin, ri, 1)
        ri += 1
        gcal.addWidget(QLabel("纸张宽 (mm)"), ri, 0)
        self._page_w_spin = QDoubleSpinBox()
        self._page_w_spin.setRange(10.0, 2000.0)
        self._page_w_spin.setDecimals(2)
        self._page_w_spin.setToolTip("与编辑区纸张宽度一致；影响预览与坐标范围。")
        gcal.addWidget(self._page_w_spin, ri, 1)
        ri += 1
        gcal.addWidget(QLabel("纸张高 (mm)"), ri, 0)
        self._page_h_spin = QDoubleSpinBox()
        self._page_h_spin.setRange(10.0, 2000.0)
        self._page_h_spin.setDecimals(2)
        gcal.addWidget(self._page_h_spin, ri, 1)
        lv.addWidget(gb_cal)

        gb_kxi = QGroupBox("奎享导出 JSON（可选）")
        self._register_device_setting_group(gb_kxi)
        vk = QVBoxLayout(gb_kxi)
        vk.setSpacing(6)
        k_top = QHBoxLayout()
        k_top.addWidget(QLabel("mm / 字体单位"))
        self._kuixiang_unit_spin = QDoubleSpinBox()
        self._kuixiang_unit_spin.setRange(0.0001, 0.2)
        self._kuixiang_unit_spin.setDecimals(5)
        self._kuixiang_unit_spin.setSingleStep(0.0001)
        self._kuixiang_unit_spin.setToolTip(
            "解析奎享提取的 JSON（gfont 格式）时，坐标单位→毫米的系数；默认与 grblapp 一致。"
            "已载入内存的奎享字形不会随此项自动重算，需更换字库或重启应用后再加载。"
        )
        k_top.addWidget(self._kuixiang_unit_spin)
        k_top.addStretch(1)
        vk.addLayout(k_top)
        _kxi_hint = QLabel(
            "使用 Hershey / 非奎享 JSON 时可忽略；奎享大包建议在首次排版前设好再加载字库。"
        )
        _kxi_hint.setWordWrap(True)
        _kxi_hint.setStyleSheet("color:#6b7280;font-size:12px;")
        vk.addWidget(_kxi_hint)
        lv.addWidget(gb_kxi)

        gb_coord = QGroupBox("坐标系（文档 mm → 机床）")
        self._register_device_setting_group(gb_coord)
        gcord = QVBoxLayout(gb_coord)
        gcord.setSpacing(8)
        h_mir = QHBoxLayout()
        self._cb_coord_mirror_x = CheckBox("镜像 X")
        self._cb_coord_mirror_y = CheckBox("镜像 Y")
        h_mir.addWidget(self._cb_coord_mirror_x)
        h_mir.addWidget(self._cb_coord_mirror_y)
        h_mir.addStretch(1)
        gcord.addLayout(h_mir)
        gpv = QGridLayout()
        gpv.setHorizontalSpacing(10)
        gpv.setVerticalSpacing(8)
        gpv.addWidget(QLabel("枢轴 X (mm)"), 0, 0)
        self._pivot_x_spin = QDoubleSpinBox()
        self._pivot_x_spin.setRange(-10000, 10000)
        self._pivot_x_spin.setDecimals(3)
        gpv.addWidget(self._pivot_x_spin, 0, 1)
        gpv.addWidget(QLabel("枢轴 Y (mm)"), 1, 0)
        self._pivot_y_spin = QDoubleSpinBox()
        self._pivot_y_spin.setRange(-10000, 10000)
        self._pivot_y_spin.setDecimals(3)
        gpv.addWidget(self._pivot_y_spin, 1, 1)
        gcord.addLayout(gpv)
        self._btn_pivot_center = PushButton("枢轴 = 纸张中心")
        self._btn_pivot_center.setToolTip("按上方纸张宽/高的一半设置枢轴（镜像绕此点）。")
        self._btn_pivot_center.clicked.connect(self._fluent_pivot_page_center)
        gcord.addWidget(self._btn_pivot_center)
        h_inv = QHBoxLayout()
        self._cb_invert_x = CheckBox("X ×(−1)")
        self._cb_invert_y = CheckBox("Y ×(−1)")
        h_inv.addWidget(self._cb_invert_x)
        h_inv.addWidget(self._cb_invert_y)
        h_inv.addStretch(1)
        gcord.addLayout(h_inv)
        gof = QGridLayout()
        gof.setHorizontalSpacing(10)
        gof.setVerticalSpacing(8)
        gof.addWidget(QLabel("偏移 ΔX (mm)"), 0, 0)
        self._off_x_spin = QDoubleSpinBox()
        self._off_x_spin.setRange(-10000, 10000)
        self._off_x_spin.setDecimals(3)
        gof.addWidget(self._off_x_spin, 0, 1)
        gof.addWidget(QLabel("偏移 ΔY (mm)"), 1, 0)
        self._off_y_spin = QDoubleSpinBox()
        self._off_y_spin.setRange(-10000, 10000)
        self._off_y_spin.setDecimals(3)
        gof.addWidget(self._off_y_spin, 1, 1)
        gcord.addLayout(gof)
        _coord_hint = QLabel(
            "变换顺序：镜像 X→Y → 绕枢轴缩放（轴反向）→ 平移；与固件对零方式需一致。"
        )
        _coord_hint.setWordWrap(True)
        _coord_hint.setStyleSheet("color:#6b7280;font-size:12px;")
        gcord.addWidget(_coord_hint)
        lv.addWidget(gb_coord)

        gb_serial = QGroupBox("连接与发送")
        self._register_device_setting_group(gb_serial)
        sv = QVBoxLayout(gb_serial)
        sv.setSpacing(8)
        sv.addWidget(QLabel("连接方式"))
        self._conn_mode_combo = ComboBox()
        self._conn_mode_combo.addItem("串口 / 蓝牙 SPP", "serial")
        self._conn_mode_combo.addItem("Wi-Fi / Telnet (TCP)", "tcp")
        self._conn_mode_combo.currentIndexChanged.connect(self._on_connection_mode_changed)
        sv.addWidget(self._conn_mode_combo)
        self._cb_bt_only = CheckBox("仅列出疑似蓝牙串口")
        self._cb_bt_only.setChecked(bool(getattr(self._cfg, "serial_show_bluetooth_only", False)))
        self._cb_bt_only.stateChanged.connect(lambda _: self._on_fluent_bluetooth_filter_changed())
        sv.addWidget(self._cb_bt_only)
        self._port_combo = ComboBox()
        self._btn_ports = PushButton("刷新端口")
        self._btn_ports.clicked.connect(self._refresh_ports)
        self._baud_spin = SpinBox()
        self._baud_spin.setRange(9600, 921600)
        self._baud_spin.setValue(115200)
        self._tcp_host_edit = QLineEdit()
        self._tcp_host_edit.setPlaceholderText("192.168.4.1")
        self._tcp_port_spin = SpinBox()
        self._tcp_port_spin.setRange(1, 65535)
        self._tcp_port_spin.setValue(23)
        self._cb_stream = SwitchButton()
        self._cb_stream.setChecked(bool(getattr(self._cfg, "grbl_streaming", False)))
        self._cb_stream.checkedChanged.connect(
            lambda c: setattr(self._cfg, "grbl_streaming", bool(c))
        )
        self._rx_buf_spin = SpinBox()
        self._rx_buf_spin.setRange(32, 16384)
        self._rx_buf_spin.setValue(int(getattr(self._cfg, "grbl_rx_buffer_size", 128)))
        self._rx_buf_spin.valueChanged.connect(
            lambda v: setattr(self._cfg, "grbl_rx_buffer_size", int(v))
        )

        self._btn_connect = PrimaryPushButton("连接")
        self._btn_connect.clicked.connect(self._toggle_serial)
        self._btn_send = PushButton("发送当前 G-code")
        self._btn_send.setEnabled(False)
        self._btn_send.clicked.connect(self._send_gcode)
        self._btn_send_pause_m800 = PushButton("发送（遇 M800 暂停）")
        self._btn_send_pause_m800.setEnabled(False)
        self._btn_send_pause_m800.clicked.connect(self._send_gcode_pause_at_m800)
        self._btn_send_checkpoint = PushButton("断点续发")
        self._btn_send_checkpoint.setEnabled(False)
        self._btn_send_checkpoint.clicked.connect(self._resume_from_checkpoint)
        self._btn_send_resume = PrimaryPushButton("继续（从 M800 后）")
        self._btn_send_resume.setEnabled(False)
        self._btn_send_resume.clicked.connect(self._resume_after_m800)
        self._btn_bf_rx = PushButton("Bf→RX 同步")
        self._btn_bf_rx.clicked.connect(self._sync_rx_from_grbl_bf)
        self._btn_m800 = PushButton("插入 M800（换纸）")
        self._btn_m800.clicked.connect(self._send_m800_only)
        self._btn_paper_flow = PrimaryPushButton("换纸流程（前缀→M800→后缀）")
        self._btn_paper_flow.setEnabled(False)
        self._btn_paper_flow.clicked.connect(self._paper_change_flow)
        self._btn_hold = PushButton("暂停(Hold)")
        self._btn_hold.clicked.connect(lambda: self._grbl.feed_hold() if self._grbl else None)
        self._btn_start = PushButton("继续(Start)")
        self._btn_start.clicked.connect(lambda: self._grbl.cycle_start() if self._grbl else None)
        self._btn_reset = PushButton("软复位(Ctrl+X)")
        self._btn_reset.setEnabled(False)
        self._btn_reset.clicked.connect(self._soft_reset_machine)

        sv.addWidget(QLabel("端口"))
        sv.addWidget(self._port_combo)
        sv.addWidget(self._btn_ports)
        sv.addWidget(QLabel("波特率"))
        sv.addWidget(self._baud_spin)
        sv.addWidget(QLabel("TCP 主机 / IP"))
        sv.addWidget(self._tcp_host_edit)
        sv.addWidget(QLabel("TCP 端口"))
        sv.addWidget(self._tcp_port_spin)
        sv.addWidget(QLabel("Streaming"))
        sv.addWidget(self._cb_stream)
        sv.addWidget(QLabel("RX 缓冲预算（字节估算）"))
        sv.addWidget(self._rx_buf_spin)
        sv.addWidget(self._btn_connect)
        sv.addWidget(self._btn_send)
        sv.addWidget(self._btn_send_pause_m800)
        sv.addWidget(self._btn_send_checkpoint)
        sv.addWidget(self._btn_send_resume)
        sv.addWidget(self._btn_bf_rx)
        sv.addWidget(self._btn_m800)
        sv.addWidget(self._btn_paper_flow)
        h_run = QHBoxLayout()
        h_run.addWidget(self._btn_hold)
        h_run.addWidget(self._btn_start)
        h_run.addWidget(self._btn_reset)
        sv.addLayout(h_run)
        lv.addWidget(gb_serial)

        gb_gc = QGroupBox("程序头尾与附加 G-code")
        self._register_device_setting_group(gb_gc)
        gv = QVBoxLayout(gb_gc)
        gv.setSpacing(8)
        self._cb_g92 = CheckBox("使用 G92（程序头对零）")
        self._cb_g92.setChecked(bool(getattr(self._cfg, "gcode_use_g92", True)))
        self._cb_g92.stateChanged.connect(
            lambda _: setattr(self._cfg, "gcode_use_g92", self._cb_g92.isChecked())
        )
        self._cb_m30 = CheckBox("结尾用 M30（否则 M2）")
        self._cb_m30.setChecked(bool(getattr(self._cfg, "gcode_end_m30", False)))
        self._cb_m30.stateChanged.connect(
            lambda _: setattr(self._cfg, "gcode_end_m30", self._cb_m30.isChecked())
        )
        self._prefix_edit = PlainTextEdit()
        self._prefix_edit.setPlaceholderText("程序前缀（每行一条，可含 M800 / [ESP800] 等）")
        self._prefix_edit.setPlainText(str(getattr(self._cfg, "gcode_program_prefix", "")))
        self._prefix_edit.setFixedHeight(72)
        self._prefix_edit.textChanged.connect(
            lambda: setattr(self._cfg, "gcode_program_prefix", self._prefix_edit.toPlainText())
        )
        self._suffix_edit = PlainTextEdit()
        self._suffix_edit.setPlaceholderText("程序后缀（每行一条）")
        self._suffix_edit.setPlainText(str(getattr(self._cfg, "gcode_program_suffix", "")))
        self._suffix_edit.setFixedHeight(72)
        self._suffix_edit.textChanged.connect(
            lambda: setattr(self._cfg, "gcode_program_suffix", self._suffix_edit.toPlainText())
        )
        gv.addWidget(self._cb_g92)
        gv.addWidget(self._cb_m30)
        gv.addWidget(QLabel("程序前缀"))
        gv.addWidget(self._prefix_edit)
        gv.addWidget(QLabel("程序后缀"))
        gv.addWidget(self._suffix_edit)
        self._btn_save_cfg = PrimaryPushButton("保存配置到本机")
        self._btn_save_cfg.setToolTip("写入 ~/.config/inkscape-wps/ 下 machine_config.toml/json")
        self._btn_save_cfg.clicked.connect(self._save_config)
        gv.addWidget(self._btn_save_cfg)
        lv.addWidget(gb_gc)

        lv.addStretch(1)
        left_scroll.setWidget(left_inner)
        row.addWidget(left_scroll)

        self._apply_device_machine_widgets_from_cfg()
        self._pen_mode_combo.currentIndexChanged.connect(self._on_fluent_pen_mode_changed)
        for _w in (
            self._z_up,
            self._z_down,
            self._draw_feed_spin,
            self._z_feed_spin,
            self._m3_s_spin,
            self._mm_per_pt_spin,
            self._doc_margin_spin,
            self._layout_v_scale_spin,
            self._page_w_spin,
            self._page_h_spin,
            self._pivot_x_spin,
            self._pivot_y_spin,
            self._off_x_spin,
            self._off_y_spin,
            self._kuixiang_unit_spin,
        ):
            _w.valueChanged.connect(self._on_device_machine_value_changed)
        self._cb_rapid_after_up.stateChanged.connect(
            lambda _: self._on_device_machine_value_changed()
        )
        for _cb in (
            self._cb_coord_mirror_x,
            self._cb_coord_mirror_y,
            self._cb_invert_x,
            self._cb_invert_y,
        ):
            _cb.stateChanged.connect(lambda _: self._on_device_machine_value_changed())

        right_panel = QWidget()
        right_panel.setObjectName("deviceSummaryPanel")
        right_panel.setStyleSheet(
            """
            QWidget#deviceSummaryPanel {
                background-color: transparent;
            }
            """
        )
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        hero = QFrame()
        hero.setObjectName("deviceHeroCard")
        hero.setStyleSheet(
            """
            QFrame#deviceHeroCard {
                background-color: #f8fbfd;
                border: 1px solid #d8e0e7;
                border-radius: 14px;
            }
            """
        )
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 16, 16, 16)
        hero_layout.setSpacing(6)
        hero_title = QLabel("机床摘要")
        hero_title.setStyleSheet("color:#233241;font-size:14px;font-weight:700;")
        hero_layout.addWidget(hero_title)
        self._dev_connection_hint = QLabel(
            "连接后可在这里快速查看状态、坐标和缓存，不用来回扫日志。"
        )
        self._dev_connection_hint.setWordWrap(True)
        self._dev_connection_hint.setStyleSheet("color:#66727e;font-size:12px;")
        hero_layout.addWidget(self._dev_connection_hint)
        self._dev_health_card = QFrame()
        dev_health_layout = QVBoxLayout(self._dev_health_card)
        dev_health_layout.setContentsMargins(14, 14, 14, 14)
        dev_health_layout.setSpacing(6)
        self._dev_health_title = QLabel("健康检查")
        self._dev_health_detail = QLabel()
        self._dev_health_detail.setWordWrap(True)
        dev_health_layout.addWidget(self._dev_health_title)
        dev_health_layout.addWidget(self._dev_health_detail)
        self._dev_health_action_btn = PrimaryPushButton("查看完整检查")
        self._dev_health_action_btn.clicked.connect(self._run_health_primary_action)
        dev_health_layout.addWidget(self._dev_health_action_btn)
        hero_layout.addWidget(self._dev_health_card)
        self._dev_diag_summary = QLabel()
        self._dev_diag_summary.setWordWrap(True)
        self._dev_diag_summary.setStyleSheet("color:#52606d;font-size:12px;")
        hero_layout.addWidget(self._dev_diag_summary)
        hero_actions = QHBoxLayout()
        hero_actions.setSpacing(8)
        btn_preflight = PushButton("开始加工前检查")
        btn_preflight.clicked.connect(self._show_preflight_report)
        btn_diag = PushButton("查看诊断")
        btn_diag.clicked.connect(self._show_diagnostics_report)
        hero_actions.addWidget(btn_preflight)
        hero_actions.addWidget(btn_diag)
        hero_actions.addStretch(1)
        hero_layout.addLayout(hero_actions)
        right_layout.addWidget(hero)

        summary_grid = QGridLayout()
        summary_grid.setHorizontalSpacing(10)
        summary_grid.setVerticalSpacing(10)
        state_card, self._dev_state = self._create_device_metric_card(
            "设备状态", "未连接", accent="#217346"
        )
        job_card, self._dev_job = self._create_device_metric_card(
            "作业状态", "就绪", accent="#2f6fed"
        )
        progress_card, self._dev_progress = self._create_device_metric_card(
            "作业进度", "0/0", accent="#b06a12"
        )
        pos_card, self._dev_pos = self._create_device_metric_card(
            "机械坐标", "X0.000 Y0.000 Z0.000", accent="#8754d6"
        )
        buf_card, self._dev_buf = self._create_device_metric_card(
            "缓冲", "Planner - / RX -", accent="#5b6b7f"
        )
        alarm_card, self._dev_alarm = self._create_device_metric_card("告警", "-", accent="#c23b32")
        summary_grid.addWidget(state_card, 0, 0)
        summary_grid.addWidget(job_card, 0, 1)
        summary_grid.addWidget(progress_card, 1, 0)
        summary_grid.addWidget(pos_card, 1, 1)
        summary_grid.addWidget(buf_card, 2, 0)
        summary_grid.addWidget(alarm_card, 2, 1)
        right_layout.addLayout(summary_grid)

        dev_log_tools = QWidget()
        dev_log_tools_l = QHBoxLayout(dev_log_tools)
        dev_log_tools_l.setContentsMargins(0, 0, 0, 0)
        dev_log_tools_l.setSpacing(8)
        dev_log_tools_l.addWidget(QLabel("日志筛选"))
        self._dev_log_filter_combo = ComboBox()
        for item in ("全部", "导出", "发送", "设备", "预检", "诊断", "运行"):
            self._dev_log_filter_combo.addItem(item)
        self._dev_log_filter_combo.currentTextChanged.connect(self._set_log_filter)
        dev_log_tools_l.addWidget(self._dev_log_filter_combo)
        btn_clear_dev_logs = PushButton("清空日志")
        btn_clear_dev_logs.clicked.connect(self._clear_logs)
        dev_log_tools_l.addWidget(btn_clear_dev_logs)
        dev_log_tools_l.addStretch(1)
        right_layout.addWidget(dev_log_tools)
        self._dev_log = PlainTextEdit()
        self._dev_log.setReadOnly(True)
        self._dev_log.setPlaceholderText("设备日志…")
        self._dev_log.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #ffffff;
                border: 1px solid #d7dee6;
                border-radius: 14px;
                padding: 6px;
            }
            """
        )
        right_layout.addWidget(self._dev_log, 1)
        row.addWidget(right_panel)
        row.setStretchFactor(1, 1)
        dv.addWidget(row, 1)

        self.addSubInterface(
            self._device_page,
            icon=FluentIcon.DEVELOPER_TOOLS,
            text="设备",
            position=NavigationItemPosition.BOTTOM,
        )
        self._refresh_ports()
        self._update_status_line()

        self._help_page = QWidget()
        self._help_page.setObjectName("help")
        hv = QVBoxLayout(self._help_page)
        hv.setContentsMargins(16, 16, 16, 16)
        hv.setSpacing(10)
        hv.addWidget(self._build_wps_top_nav())
        hv.addWidget(TitleLabel("帮助"))
        help_intro = self._create_info_panel(
            "文档入口",
            "这里收纳快速入门、规格说明和提示词指南入口。"
            "遇到功能不明确时，先看 SPEC；"
            "需要联动 AI 协作时，再看 AI_PROMPTS。",
            accent="#2f6fed",
        )
        hv.addWidget(help_intro)
        help_actions = QFrame()
        help_actions.setObjectName("helpActionCard")
        help_actions.setStyleSheet(
            """
            QFrame#helpActionCard {
                background-color: #ffffff;
                border: 1px solid #d8e0e7;
                border-radius: 14px;
            }
            """
        )
        help_layout = QVBoxLayout(help_actions)
        help_layout.setContentsMargins(16, 16, 16, 16)
        help_layout.setSpacing(10)
        hl = QLabel("菜单栏“帮助”也提供同样入口；下面几个按钮更适合首次上手时直接跳转。")
        hl.setWordWrap(True)
        hl.setStyleSheet("color:#52606d;font-size:12px;")
        help_layout.addWidget(hl)
        btn_quick = PrimaryPushButton("打开快速入门")
        btn_quick.clicked.connect(self._show_quick_start)
        btn_spec = PushButton("查看 SPEC.md")
        btn_spec.clicked.connect(self._open_spec_document)
        btn_ai = PushButton("查看 AI_PROMPTS.md")
        btn_ai.clicked.connect(self._open_ai_prompts_document)
        btn_missing = PushButton("查看缺失字符")
        btn_missing.clicked.connect(self._show_missing_glyphs_dialog)
        btn_svg_diag = PushButton("SVG 导入诊断")
        btn_svg_diag.clicked.connect(self._show_svg_diagnostics)
        btn_font_diag = PushButton("奎享/字库诊断")
        btn_font_diag.clicked.connect(self._show_font_diagnostics)
        btn_preflight_help = PushButton("开始加工前检查")
        btn_preflight_help.clicked.connect(self._show_preflight_report)
        btn_diag_help = PushButton("查看诊断")
        btn_diag_help.clicked.connect(self._show_diagnostics_report)
        help_layout.addWidget(btn_quick)
        help_layout.addWidget(btn_spec)
        help_layout.addWidget(btn_ai)
        help_layout.addWidget(btn_missing)
        help_layout.addWidget(btn_svg_diag)
        help_layout.addWidget(btn_font_diag)
        help_layout.addWidget(btn_preflight_help)
        help_layout.addWidget(btn_diag_help)
        hv.addWidget(help_actions)
        hv.addWidget(
            self._create_info_panel(
                "排查建议",
                "如果界面看起来正常但结果不对，"
                "先检查当前工作页、页面尺寸、字体参数和坐标映射；"
                "如果连接失败，再回到设备页确认串口或 TCP 设置。",
                accent="#8754d6",
            )
        )
        hv.addStretch(1)
        self.addSubInterface(
            self._help_page,
            icon=FluentIcon.HELP,
            text="帮助",
            position=NavigationItemPosition.BOTTOM,
        )

        try:
            self._sync_document_surface_widths()
        except Exception:
            _logger.debug("初始化同步文档画布宽度失败", exc_info=True)
        self._setup_symbol_panel()
        try:
            self._wps_refresh_font_toolbar_context()
        except Exception:
            pass
        self._sync_top_nav_buttons()
        self._nonword_undo_stack.canUndoChanged.connect(self._refresh_undo_redo_menu_state)

    def _build_wps_top_nav(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 2, 0, 4)
        row.setSpacing(8)

        file_btn = PrimaryPushButton("文件")
        file_btn.setObjectName("WpsFileButton")
        file_btn.setFixedHeight(34)
        file_btn.setMinimumWidth(74)
        file_btn.setStyleSheet(
            """
            QPushButton#WpsFileButton {
                background-color: #217346;
                border: 1px solid #1b613a;
                border-radius: 10px;
                padding: 0 16px;
                color: #ffffff;
                font-weight: 700;
            }
            QPushButton#WpsFileButton:hover {
                background-color: #2b8855;
            }
            QPushButton#WpsFileButton:pressed {
                background-color: #185634;
            }
            """
        )
        file_btn.clicked.connect(lambda: self._safe_switch_to(self._file_page, "文件"))
        row.addWidget(file_btn)

        info_box = QFrame()
        info_box.setObjectName("WpsTopNavInfo")
        info_box.setStyleSheet(
            """
            QFrame#WpsTopNavInfo {
                background-color: rgba(255, 255, 255, 0.96);
                border: 1px solid #dfe6ec;
                border-radius: 10px;
            }
            """
        )
        info_row = QVBoxLayout(info_box)
        info_row.setContentsMargins(12, 6, 12, 6)
        info_row.setSpacing(0)
        title = QLabel(self.windowTitle())
        title.setStyleSheet("color:#2c333a;font-size:13px;font-weight:700;")
        info_row.addWidget(title)
        meta = QLabel()
        meta.setStyleSheet("color:#7a858f;font-size:11px;")
        info_row.addWidget(meta)
        row.addWidget(info_box)
        self._top_nav_titles.append(title)
        self._top_nav_meta_labels.append(meta)

        sep = QLabel("│")
        sep.setStyleSheet("color:#c4ccd4;")
        row.addWidget(sep)

        for label, widget in (
            ("开始", self._home_page),
            ("文字", self._word_page),
            ("表格", self._table_page),
            ("演示", self._slides_page),
            ("设备", self._device_page),
            ("帮助", self._help_page),
        ):
            if widget is not None:
                self._register_top_nav_button(row, label, widget)

        return self._finalize_wps_top_nav(bar, row)

    def _register_top_nav_button(self, row: QHBoxLayout, label: str, widget: QWidget) -> None:
        btn = QPushButton(label)
        btn.setObjectName("WpsModeTabButton")
        btn.setCheckable(True)
        btn.setFixedHeight(34)
        btn.setMinimumWidth(70)
        btn.clicked.connect(
            lambda _checked=False, w=widget, lab=label: self._safe_switch_to(w, lab)
        )
        btn.setStyleSheet(
            """
            QPushButton#WpsModeTabButton {
                background-color: rgba(255, 255, 255, 0.58);
                border: 1px solid transparent;
                border-radius: 10px;
                padding: 0px 14px;
                color: #4a545e;
                font-weight: 700;
            }
            QPushButton#WpsModeTabButton:hover {
                background-color: #eef4f0;
                border-color: #dce6de;
                color: #0f3d26;
            }
            QPushButton#WpsModeTabButton:checked {
                background-color: #f7fff9;
                border: 1px solid #cfe2d6;
                color: #0f3d26;
            }
            """
        )
        row.addWidget(btn)
        self._top_nav_buttons.append((btn, widget))

    def _finalize_wps_top_nav(self, bar: QWidget, row: QHBoxLayout) -> QWidget:
        row.addStretch(1)
        bar.setStyleSheet(
            """
            QWidget {
                background-color: transparent;
            }
            """
        )
        self._sync_top_nav_meta()
        return bar

    def _ribbon_tab_button_stylesheet(self) -> str:
        return """
            QPushButton#WpsModeTabButton {
                background-color: #fbfcfd;
                border: 1px solid #dfe6ec;
                border-bottom: none;
                border-radius: 6px 6px 0 0;
                padding: 0px 12px;
                color: #4a545e;
                font-weight: 700;
            }
            QPushButton#WpsModeTabButton:hover {
                border-color: #2d8f5c;
                background-color: #eef8f1;
                color: #0f3d26;
            }
            QPushButton#WpsModeTabButton:checked {
                background-color: #f3f5f7;
                border: 1px solid #dfe6ec;
                border-bottom: 1px solid #f3f5f7;
                color: #0f3d26;
            }
        """

    def _make_wps_ruler_bar(self) -> QLabel:
        max_mm = max(20, int(round(float(getattr(self._cfg, "page_width_mm", 210.0)))))
        ticks = list(range(0, max_mm + 1, 20))
        if ticks[-1] != max_mm:
            ticks.append(max_mm)
        lb = QLabel(" ".join(f"{t:>3}" for t in ticks) + "   (mm)")
        lb.setObjectName("RulerBar")
        lb.setStyleSheet(
            "background-color:#e4e4e4;border-bottom:1px solid #c8c8c8;color:#555555;"
            'font-family:"Menlo","Consolas",monospace;padding:3px 8px;'
        )
        return lb

    def _sync_top_nav_buttons(self) -> None:
        cur = None
        try:
            cur = self.stackedWidget.currentWidget()
        except Exception:
            _logger.debug("读取当前页面失败", exc_info=True)
        for btn, widget in self._top_nav_buttons:
            btn.blockSignals(True)
            btn.setChecked(widget is cur)
            btn.blockSignals(False)

    def _apply_window_title(self) -> None:
        title = f"{self._doc_title} - 写字机上位机"
        self.setWindowTitle(title)
        for label in self._top_nav_titles:
            label.setText(title)
        self._sync_top_nav_meta()

    def _sync_top_nav_meta(self) -> None:
        saved = self._last_saved_at or "未保存"
        proj = self._project_path.name if self._project_path is not None else "临时文档"
        text = f"工程 {proj}   ·   最近保存 {saved}"
        for label in self._top_nav_meta_labels:
            label.setText(text)

    def _build_mode_ribbon(self, mode: str) -> QWidget:
        shell = QWidget()
        outer = QVBoxLayout(shell)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        tab_bar = QWidget()
        tab_row = QHBoxLayout(tab_bar)
        tab_row.setContentsMargins(0, 0, 0, 0)
        tab_row.setSpacing(4)

        stack = QStackedWidget()
        stack.setStyleSheet(
            "QStackedWidget{background-color:#f3f5f7;"
            "border:1px solid #dfe6ec;border-top:none;"
            "border-radius:0 0 6px 6px;}"
        )
        button_group = QButtonGroup(shell)
        button_group.setExclusive(True)

        pages: list[tuple[str, QWidget]] = [
            ("开始", self._build_ribbon_start_page(mode)),
            ("插入", self._build_ribbon_insert_page(mode)),
            ("页面布局", self._build_ribbon_layout_page()),
            ("审阅", self._build_ribbon_review_page(mode)),
            ("视图", self._build_ribbon_view_page()),
        ]
        for idx, (label, page) in enumerate(pages):
            btn = QPushButton(label)
            btn.setObjectName("WpsModeTabButton")
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.setMinimumWidth(78)
            btn.setStyleSheet(self._ribbon_tab_button_stylesheet())
            button_group.addButton(btn, idx)
            btn.clicked.connect(lambda _checked=False, i=idx: stack.setCurrentIndex(i))
            tab_row.addWidget(btn)
            stack.addWidget(page)
            if idx == 0:
                btn.setChecked(True)
        tab_row.addStretch(1)

        outer.addWidget(tab_bar)
        outer.addWidget(stack)
        return shell

    def _build_ribbon_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background-color:#f3f5f7;")
        return panel

    def _page_mm_to_surface_width(
        self, page_width_mm: float, *, base_mm: float = 210.0, base_px: int = 900
    ) -> int:
        try:
            mm = float(page_width_mm)
        except (TypeError, ValueError):
            mm = base_mm
        px = int(round(base_px * max(0.45, min(2.4, mm / base_mm))))
        return max(560, min(1320, px))

    def _build_task_pane_card(self, title: str, content: QWidget) -> QWidget:
        card = QFrame()
        card.setObjectName("WpsTaskPaneCard")
        card.setStyleSheet(
            """
            QFrame#WpsTaskPaneCard {
                background-color: #fbfcfd;
                border: 1px solid #d7dee6;
                border-radius: 12px;
            }
            """
        )
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(31, 35, 40, 18))
        card.setGraphicsEffect(shadow)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        header = QLabel(title)
        header.setStyleSheet("color:#314252;font-size:12px;font-weight:700;")
        layout.addWidget(header)
        layout.addWidget(content, 1)
        return card

    def _build_document_surface(
        self, content: QWidget, *, max_width: int = 1020, margins: int = 18
    ) -> tuple[QWidget, QFrame]:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)

        shell = QFrame()
        shell.setObjectName("WpsDocumentSurface")
        shell.setMaximumWidth(max_width)
        shell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        shell.setStyleSheet(
            """
            QFrame#WpsDocumentSurface {
                background-color: #ffffff;
                border: 1px solid #d7dee6;
                border-radius: 14px;
            }
            """
        )
        shadow = QGraphicsDropShadowEffect(shell)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(31, 35, 40, 30))
        shell.setGraphicsEffect(shadow)

        shell_l = QVBoxLayout(shell)
        shell_l.setContentsMargins(margins, margins, margins, margins)
        shell_l.setSpacing(10)
        shell_l.addWidget(content)

        row.addWidget(shell, 1)
        row.addStretch(1)
        return host, shell

    def _sync_document_surface_widths(self) -> None:
        width_px = self._page_mm_to_surface_width(float(getattr(self._cfg, "page_width_mm", 210.0)))
        for attr, cap in (
            ("_word_surface_shell", width_px),
            ("_table_surface_shell", min(1180, width_px + 140)),
            ("_slides_surface_shell", min(1220, width_px + 180)),
        ):
            shell = getattr(self, attr, None)
            if shell is not None:
                shell.setMaximumWidth(int(cap))

    def _build_ribbon_group(self, title: str) -> tuple[QWidget, QHBoxLayout]:
        box = QFrame()
        box.setObjectName("WpsRibbonGroup")
        box.setStyleSheet(
            """
            QFrame#WpsRibbonGroup {
                background-color: #f3f5f7;
                border-right: 1px solid #d8dee5;
            }
            """
        )
        outer = QVBoxLayout(box)
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(2)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)
        outer.addLayout(body, 1)
        caption = QLabel(title)
        caption.setAlignment(Qt.AlignCenter)
        caption.setStyleSheet("color:#7a858f;font-size:11px;padding-top:1px;")
        outer.addWidget(caption)
        return box, body

    def _create_ribbon_big_button(
        self, text: str, tip: str, slot, *, width: int = 82
    ) -> PushButton:
        btn = PushButton(text)
        btn.setFixedSize(width, 58)
        btn.setToolTip(tip)
        btn.setStyleSheet(
            """
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #d9e1e8;
                border-radius: 6px;
                padding: 6px 8px;
                text-align: center;
                font-weight: 700;
            }
            QPushButton:hover {
                border-color: #2d8f5c;
                background-color: #f4fbf6;
            }
            """
        )
        btn.clicked.connect(slot)
        return btn

    def _create_ribbon_small_button(
        self, text: str, tip: str, slot, *, width: int = 98
    ) -> PushButton:
        btn = PushButton(text)
        btn.setFixedSize(width, 28)
        btn.setToolTip(tip)
        btn.clicked.connect(slot)
        return btn

    def _add_ribbon_button_stack(
        self, layout: QHBoxLayout, items: list[tuple[str, str, object]], *, width: int = 98
    ) -> None:
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        for text, tip, slot in items:
            col.addWidget(self._create_ribbon_small_button(text, tip, slot, width=width))
        layout.addLayout(col)

    def _preset_svg_glyph(self, name: str) -> str:
        return {
            "arrow": "➜",
            "check": "✓",
            "frame": "▣",
            "heart": "♥",
            "house": "⌂",
            "smile": "☺",
            "star": "★",
            "triangle": "▲",
        }.get(name.lower(), "◻")

    def _build_preset_svg_card(self, path: Path) -> QWidget:
        btn = PushButton()
        btn.setObjectName("WpsPresetGalleryButton")
        btn.setFixedSize(74, 70)
        btn.setToolTip(f"插入预置素材：{path.stem}")
        btn.setStyleSheet(
            """
            QPushButton#WpsPresetGalleryButton {
                background-color: #ffffff;
                border: 1px solid #d9e1e8;
                border-radius: 6px;
                padding: 0;
            }
            QPushButton#WpsPresetGalleryButton:hover {
                border-color: #2d8f5c;
                background-color: #f4fbf6;
            }
            QPushButton#WpsPresetGalleryButton:pressed {
                background-color: #eaf6ee;
            }
            """
        )
        col = QVBoxLayout(btn)
        col.setContentsMargins(4, 6, 4, 6)
        col.setSpacing(2)
        icon = QLabel(self._preset_svg_glyph(path.stem))
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("color:#1c6b42;font-size:24px;font-weight:700;")
        col.addWidget(icon, 1)
        name = QLabel(path.stem.title())
        name.setAlignment(Qt.AlignCenter)
        name.setStyleSheet("color:#4a545e;font-size:11px;")
        col.addWidget(name)
        btn.clicked.connect(lambda _checked=False, p=path: self._insert_svg_paths_from_file(p))
        return btn

    def _add_ribbon_labeled_spin(
        self,
        layout: QHBoxLayout,
        label: str,
        spin: QDoubleSpinBox,
        suffix: str | None = None,
        width: int = 76,
    ) -> None:
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        lb = QLabel(label)
        lb.setStyleSheet("color:#3d444d;font-size:12px;")
        col.addWidget(lb)
        spin.setFixedWidth(width)
        if suffix:
            spin.setSuffix(suffix)
        col.addWidget(spin)
        layout.addLayout(col)

    def _match_wps_page_preset(self, width_mm: float, height_mm: float) -> str:
        presets = {
            "A4 纵向": (210.0, 297.0),
            "A5 纵向": (148.0, 210.0),
            "B5 纵向": (176.0, 250.0),
            "16:9 演示": (297.0, 167.0),
        }
        for label, (pw, ph) in presets.items():
            if abs(width_mm - pw) <= 0.5 and abs(height_mm - ph) <= 0.5:
                return label
        return "自定义"

    def _sync_ribbon_layout_widgets_from_cfg(self) -> None:
        if not hasattr(self, "_ribbon_page_preset_combo"):
            return
        pairs = (
            (self._ribbon_doc_margin_spin, float(self._cfg.document_margin_mm)),
            (self._ribbon_layout_v_scale_spin, float(self._cfg.layout_vertical_scale)),
            (self._ribbon_page_w_spin, float(self._cfg.page_width_mm)),
            (self._ribbon_page_h_spin, float(self._cfg.page_height_mm)),
            (self._ribbon_pivot_x_spin, float(self._cfg.coord_pivot_x_mm)),
            (self._ribbon_pivot_y_spin, float(self._cfg.coord_pivot_y_mm)),
            (self._ribbon_off_x_spin, float(self._cfg.coord_offset_x_mm)),
            (self._ribbon_off_y_spin, float(self._cfg.coord_offset_y_mm)),
        )
        for widget, value in pairs:
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        for widget, value in (
            (self._ribbon_mirror_x_cb, bool(self._cfg.coord_mirror_x)),
            (self._ribbon_mirror_y_cb, bool(self._cfg.coord_mirror_y)),
            (self._ribbon_invert_x_cb, float(self._cfg.coord_scale_x) < 0),
            (self._ribbon_invert_y_cb, float(self._cfg.coord_scale_y) < 0),
        ):
            widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(False)
        preset = self._match_wps_page_preset(
            float(self._cfg.page_width_mm), float(self._cfg.page_height_mm)
        )
        self._ribbon_page_preset_combo.blockSignals(True)
        idx = self._ribbon_page_preset_combo.findText(preset)
        self._ribbon_page_preset_combo.setCurrentIndex(max(0, idx))
        self._ribbon_page_preset_combo.blockSignals(False)

    def _copy_ribbon_layout_widgets_to_device(self) -> None:
        if not hasattr(self, "_doc_margin_spin"):
            return
        pairs = (
            (self._doc_margin_spin, self._ribbon_doc_margin_spin.value()),
            (self._layout_v_scale_spin, self._ribbon_layout_v_scale_spin.value()),
            (self._page_w_spin, self._ribbon_page_w_spin.value()),
            (self._page_h_spin, self._ribbon_page_h_spin.value()),
            (self._pivot_x_spin, self._ribbon_pivot_x_spin.value()),
            (self._pivot_y_spin, self._ribbon_pivot_y_spin.value()),
            (self._off_x_spin, self._ribbon_off_x_spin.value()),
            (self._off_y_spin, self._ribbon_off_y_spin.value()),
        )
        for widget, value in pairs:
            widget.blockSignals(True)
            widget.setValue(float(value))
            widget.blockSignals(False)
        for widget, value in (
            (self._cb_coord_mirror_x, self._ribbon_mirror_x_cb.isChecked()),
            (self._cb_coord_mirror_y, self._ribbon_mirror_y_cb.isChecked()),
            (self._cb_invert_x, self._ribbon_invert_x_cb.isChecked()),
            (self._cb_invert_y, self._ribbon_invert_y_cb.isChecked()),
        ):
            widget.blockSignals(True)
            widget.setChecked(bool(value))
            widget.blockSignals(False)

    def _on_ribbon_layout_value_changed(self, *_args) -> None:
        self._copy_ribbon_layout_widgets_to_device()
        self._on_device_machine_value_changed()

    def _on_ribbon_page_preset_changed(self, _index: int = 0) -> None:
        data = self._ribbon_page_preset_combo.currentData()
        if not isinstance(data, tuple) or len(data) != 2:
            return
        width_mm, height_mm = data
        for widget, value in (
            (self._ribbon_page_w_spin, float(width_mm)),
            (self._ribbon_page_h_spin, float(height_mm)),
        ):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        self._on_ribbon_layout_value_changed()

    def _on_ribbon_pivot_page_center(self) -> None:
        self._ribbon_pivot_x_spin.setValue(float(self._ribbon_page_w_spin.value()) / 2.0)
        self._ribbon_pivot_y_spin.setValue(float(self._ribbon_page_h_spin.value()) / 2.0)
        self._on_ribbon_layout_value_changed()

    def _build_ribbon_start_page(self, mode: str) -> QWidget:
        panel = self._build_ribbon_panel()
        row = QHBoxLayout(panel)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)

        clipboard_group, clipboard_row = self._build_ribbon_group("剪贴板")
        self._append_wps_clipboard_buttons(clipboard_row)
        row.addWidget(clipboard_group)

        font_group, font_row = self._build_ribbon_group("字体")
        self._append_wps_font_controls(font_row)
        row.addWidget(font_group)

        char_group, char_row = self._build_ribbon_group("字符")
        self._append_wps_character_format_buttons(char_row)
        row.addWidget(char_group)

        para_group, para_row = self._build_ribbon_group("段落")
        self._append_wps_alignment_buttons(para_row)
        if mode == "table":
            self._append_wps_table_rowcol_buttons(para_row)
        elif mode == "slides":
            self._append_wps_slide_paragraph_buttons(para_row)
        row.addWidget(para_group)

        if mode == "slides":
            style_group, style_row = self._build_ribbon_group("样式")
            self._append_wps_slide_style_presets(style_row)
            row.addWidget(style_group)
        row.addStretch(1)
        return panel

    def _build_ribbon_insert_page(self, mode: str) -> QWidget:
        panel = self._build_ribbon_panel()
        row = QHBoxLayout(panel)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)

        doc_group, doc_row = self._build_ribbon_group("文档")
        doc_row.addWidget(
            self._create_ribbon_big_button(
                "打开文件",
                "导入工程、Office/WPS 或 Markdown 文件。",
                self._open_project,
            )
        )
        self._add_ribbon_button_stack(
            doc_row,
            [
                (
                    "导入 Markdown…",
                    "将 Markdown 导入为文字或演示内容。",
                    self._import_markdown_dialog,
                ),
                ("符号", "插入数学、单位等常用 Unicode 符号。", self._on_symbol_button_clicked),
            ],
        )
        row.addWidget(doc_group)

        art_group, art_row = self._build_ribbon_group("插图与路径")
        preset_col = QVBoxLayout()
        preset_col.setContentsMargins(0, 0, 0, 0)
        preset_col.setSpacing(4)
        preset_lb = QLabel("预置素材")
        preset_lb.setStyleSheet("color:#3d444d;font-size:12px;")
        preset_col.addWidget(preset_lb)
        preset_paths = list(_preset_svg_dir().glob("*.svg"))
        if preset_paths:
            preset_gallery = QWidget()
            preset_grid = QGridLayout(preset_gallery)
            preset_grid.setContentsMargins(0, 0, 0, 0)
            preset_grid.setHorizontalSpacing(6)
            preset_grid.setVerticalSpacing(6)
            for idx, path in enumerate(sorted(preset_paths)[:8]):
                preset_grid.addWidget(self._build_preset_svg_card(path), idx // 4, idx % 4)
            preset_col.addWidget(preset_gallery)
        else:
            preset_empty = QLabel("未找到预置 SVG 素材。")
            preset_empty.setStyleSheet("color:#7a858f;font-size:12px;")
            preset_col.addWidget(preset_empty)
        art_row.addLayout(preset_col)
        art_row.addWidget(
            self._create_ribbon_big_button(
                "SVG",
                "导入 SVG 矢量并叠加到当前文档预览。",
                self._insert_svg_from_dialog,
            )
        )
        self._add_ribbon_button_stack(
            art_row,
            [
                ("图片描摹…", "把位图转成折线路径后插入。", self._insert_bitmap_traced),
                ("清除插图", "移除已插入的矢量素材。", self._clear_inserted_vectors),
            ],
        )
        row.addWidget(art_group)

        if mode == "table":
            table_group, table_row = self._build_ribbon_group("表格")
            table_row.addWidget(
                self._create_ribbon_big_button(
                    "上方插入行",
                    "在当前单元格上方插入一行。",
                    self._table_editor.insert_row_above,
                )
            )
            self._add_ribbon_button_stack(
                table_row,
                [
                    (
                        "左侧插入列",
                        "在当前单元格左侧插入一列。",
                        self._table_editor.insert_column_left,
                    ),
                    (
                        "删除当前行",
                        "删除当前行，至少保留一行。",
                        self._table_editor.delete_current_row,
                    ),
                    (
                        "删除当前列",
                        "删除当前列，至少保留一列。",
                        self._table_editor.delete_current_column,
                    ),
                ],
            )
            row.addWidget(table_group)
        elif mode == "slides":
            slide_group, slide_row = self._build_ribbon_group("幻灯片")
            slide_row.addWidget(
                self._create_ribbon_big_button(
                    "新建页",
                    "新增一张幻灯片。",
                    self._presentation_editor.add_slide,
                )
            )
            self._add_ribbon_button_stack(
                slide_row,
                [
                    (
                        "创建副本",
                        "复制当前幻灯片。",
                        self._presentation_editor.duplicate_current_slide,
                    ),
                    (
                        "母版页眉",
                        "编辑所有幻灯片共用的页眉文本。",
                        lambda: self._edit_slide_master_from_ribbon("header"),
                    ),
                    (
                        "母版页脚",
                        "编辑所有幻灯片共用的页脚文本。",
                        lambda: self._edit_slide_master_from_ribbon("footer"),
                    ),
                    ("清空母版", "移除页眉和页脚。", self._presentation_editor.clear_master),
                ],
                width=104,
            )
            row.addWidget(slide_group)
        else:
            word_group, word_row = self._build_ribbon_group("文稿")
            note = QLabel("文字页以笔画字形和版式为主，插入页主要承担符号、Markdown 和素材导入。")
            note.setWordWrap(True)
            note.setFixedWidth(240)
            note.setStyleSheet("color:#6b7280;font-size:12px;")
            word_row.addWidget(note)
            row.addWidget(word_group)
        row.addStretch(1)
        return panel

    def _build_ribbon_layout_page(self) -> QWidget:
        panel = self._build_ribbon_panel()
        row = QHBoxLayout(panel)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)
        page_group, page_row = self._build_ribbon_group("页面设置")
        self._ribbon_page_preset_combo = ComboBox()
        self._ribbon_page_preset_combo.setMinimumWidth(124)
        for label, data in (
            ("A4 纵向", (210.0, 297.0)),
            ("A5 纵向", (148.0, 210.0)),
            ("B5 纵向", (176.0, 250.0)),
            ("16:9 演示", (297.0, 167.0)),
            ("自定义", None),
        ):
            self._ribbon_page_preset_combo.addItem(label, data)
        page_col = QVBoxLayout()
        page_col.setContentsMargins(0, 0, 0, 0)
        page_col.setSpacing(2)
        page_lb = QLabel("纸张")
        page_lb.setStyleSheet("color:#3d444d;font-size:12px;")
        page_col.addWidget(page_lb)
        page_col.addWidget(self._ribbon_page_preset_combo)
        page_row.addLayout(page_col)
        self._ribbon_doc_margin_spin = QDoubleSpinBox()
        self._ribbon_doc_margin_spin.setRange(0, 120)
        self._ribbon_doc_margin_spin.setDecimals(2)
        self._add_ribbon_labeled_spin(page_row, "左边距", self._ribbon_doc_margin_spin, " mm")
        self._ribbon_page_w_spin = QDoubleSpinBox()
        self._ribbon_page_w_spin.setRange(10.0, 2000.0)
        self._ribbon_page_w_spin.setDecimals(2)
        self._add_ribbon_labeled_spin(page_row, "宽", self._ribbon_page_w_spin, " mm")
        self._ribbon_page_h_spin = QDoubleSpinBox()
        self._ribbon_page_h_spin.setRange(10.0, 2000.0)
        self._ribbon_page_h_spin.setDecimals(2)
        self._add_ribbon_labeled_spin(page_row, "高", self._ribbon_page_h_spin, " mm")
        self._ribbon_layout_v_scale_spin = QDoubleSpinBox()
        self._ribbon_layout_v_scale_spin.setRange(0.25, 4.0)
        self._ribbon_layout_v_scale_spin.setSingleStep(0.05)
        self._ribbon_layout_v_scale_spin.setDecimals(3)
        self._add_ribbon_labeled_spin(page_row, "纵向比例", self._ribbon_layout_v_scale_spin)
        row.addWidget(page_group)

        coord_group, coord_row = self._build_ribbon_group("坐标与镜像")
        mirror_col = QVBoxLayout()
        mirror_col.setContentsMargins(0, 0, 0, 0)
        mirror_col.setSpacing(4)
        self._ribbon_mirror_x_cb = CheckBox("镜像 X")
        self._ribbon_mirror_y_cb = CheckBox("镜像 Y")
        self._ribbon_invert_x_cb = CheckBox("X ×(−1)")
        self._ribbon_invert_y_cb = CheckBox("Y ×(−1)")
        for cb in (
            self._ribbon_mirror_x_cb,
            self._ribbon_mirror_y_cb,
            self._ribbon_invert_x_cb,
            self._ribbon_invert_y_cb,
        ):
            mirror_col.addWidget(cb)
        coord_row.addLayout(mirror_col)
        self._ribbon_pivot_x_spin = QDoubleSpinBox()
        self._ribbon_pivot_x_spin.setRange(-10000, 10000)
        self._ribbon_pivot_x_spin.setDecimals(3)
        self._add_ribbon_labeled_spin(coord_row, "枢轴 X", self._ribbon_pivot_x_spin, " mm")
        self._ribbon_pivot_y_spin = QDoubleSpinBox()
        self._ribbon_pivot_y_spin.setRange(-10000, 10000)
        self._ribbon_pivot_y_spin.setDecimals(3)
        self._add_ribbon_labeled_spin(coord_row, "枢轴 Y", self._ribbon_pivot_y_spin, " mm")
        self._ribbon_off_x_spin = QDoubleSpinBox()
        self._ribbon_off_x_spin.setRange(-10000, 10000)
        self._ribbon_off_x_spin.setDecimals(3)
        self._add_ribbon_labeled_spin(coord_row, "偏移 X", self._ribbon_off_x_spin, " mm")
        self._ribbon_off_y_spin = QDoubleSpinBox()
        self._ribbon_off_y_spin.setRange(-10000, 10000)
        self._ribbon_off_y_spin.setDecimals(3)
        self._add_ribbon_labeled_spin(coord_row, "偏移 Y", self._ribbon_off_y_spin, " mm")
        center_btn = self._create_ribbon_small_button(
            "枢轴=纸张中心", "把枢轴设置为页面中心。", self._on_ribbon_pivot_page_center, width=112
        )
        coord_row.addWidget(center_btn)
        row.addWidget(coord_group)

        machine_group, machine_row = self._build_ribbon_group("机床校准")
        machine_row.addWidget(
            self._create_ribbon_big_button(
                "设备页",
                "进入设备页调整抬笔、落笔、进给与串口发送。",
                lambda: self._open_device_page_with_hint(
                    "机床运动参数仍放在「设备」页，顶部功能区负责版式与页面。"
                ),
            )
        )
        tip = QLabel("像 WPS 一样把纸张和页面放在上方，机床连接留在设备页。")
        tip.setWordWrap(True)
        tip.setFixedWidth(220)
        tip.setStyleSheet("color:#6b7280;font-size:12px;")
        machine_row.addWidget(tip)
        row.addWidget(machine_group)

        self._ribbon_page_preset_combo.currentIndexChanged.connect(
            self._on_ribbon_page_preset_changed
        )
        for widget in (
            self._ribbon_doc_margin_spin,
            self._ribbon_layout_v_scale_spin,
            self._ribbon_page_w_spin,
            self._ribbon_page_h_spin,
            self._ribbon_pivot_x_spin,
            self._ribbon_pivot_y_spin,
            self._ribbon_off_x_spin,
            self._ribbon_off_y_spin,
        ):
            widget.valueChanged.connect(self._on_ribbon_layout_value_changed)
        for cb in (
            self._ribbon_mirror_x_cb,
            self._ribbon_mirror_y_cb,
            self._ribbon_invert_x_cb,
            self._ribbon_invert_y_cb,
        ):
            cb.stateChanged.connect(lambda _: self._on_ribbon_layout_value_changed())
        self._sync_ribbon_layout_widgets_from_cfg()
        row.addStretch(1)
        return panel

    def _build_ribbon_review_page(self, mode: str) -> QWidget:
        panel = self._build_ribbon_panel()
        row = QHBoxLayout(panel)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)
        if mode == "slides":
            review_group, review_row = self._build_ribbon_group("修订")
            review_toggle = self._create_ribbon_big_button(
                "修订模式", "打开删除线修订模式。", lambda checked=False: None
            )
            review_toggle.setCheckable(True)
            review_toggle.setChecked(self._slide_revision_mode)
            review_toggle.clicked.connect(
                lambda checked=False: self._set_slide_revision_mode(bool(checked))
            )
            review_row.addWidget(review_toggle)
            self._add_ribbon_button_stack(
                review_row,
                [
                    (
                        "接受修订",
                        "接受当前删除线修订。",
                        lambda: self._review_accept_or_reject(True),
                    ),
                    (
                        "拒绝修订",
                        "撤销当前删除线修订。",
                        lambda: self._review_accept_or_reject(False),
                    ),
                ],
            )
            row.addWidget(review_group)
        else:
            note_group, note_row = self._build_ribbon_group("审阅")
            note = QLabel("当前模式暂无审阅命令；演示页提供修订、接受与拒绝修订。")
            note.setStyleSheet("color:#6b7280;padding:4px 2px;")
            note.setWordWrap(True)
            note.setFixedWidth(280)
            note_row.addWidget(note)
            row.addWidget(note_group)
        row.addStretch(1)
        return panel

    def _build_ribbon_view_page(self) -> QWidget:
        panel = self._build_ribbon_panel()
        row = QHBoxLayout(panel)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)
        zoom_group, zoom_row = self._build_ribbon_group("缩放")
        zoom_row.addWidget(
            self._create_ribbon_big_button(
                "100%", "将预览缩放恢复到 100%。", self._preview_zoom_reset_100
            )
        )
        self._add_ribbon_button_stack(
            zoom_row,
            [
                ("放大预览", "将右侧路径预览逐步放大。", lambda: self._preview_zoom_step(1.15)),
                (
                    "缩小预览",
                    "将右侧路径预览逐步缩小。",
                    lambda: self._preview_zoom_step(1.0 / 1.15),
                ),
            ],
        )
        row.addWidget(zoom_group)

        export_group, export_row = self._build_ribbon_group("导出")
        export_row.addWidget(
            self._create_ribbon_big_button(
                "复制预览图",
                "将当前预览视口复制到剪贴板。",
                self._preview_copy_visible_to_clipboard,
            )
        )
        self._add_ribbon_button_stack(
            export_row,
            [
                ("导出 PNG…", "把当前预览视口导出为 PNG。", self._preview_export_visible_png),
            ],
        )
        row.addWidget(export_group)
        row.addStretch(1)
        return panel

    def _install_wps_menus(self) -> None:
        """用 CommandBar + RoundMenu 模拟 WPS 菜单栏。"""
        try:
            from qfluentwidgets import RoundMenu
        except Exception:
            return

        def _add_top_menu(title: str, menu: "RoundMenu") -> None:
            act = Action(text=title)

            def _popup() -> None:
                # 在按钮下方弹出
                btn = self._menu_bar.widgetForAction(act)
                if btn is not None:
                    gp = btn.mapToGlobal(btn.rect().bottomLeft())
                    menu.exec_(gp)
                else:
                    menu.exec_()

            act.triggered.connect(_popup)
            self._menu_bar.addAction(act)

        # 文件
        m_file = RoundMenu("文件", self)
        self._act_backstage = Action(text="文件页（Backstage）")
        self._act_backstage.triggered.connect(self._show_backstage)
        m_file.addAction(self._act_backstage)
        m_file.addSeparator()
        self._act_new = Action(text="新建")
        self._act_new.setShortcut(QKeySequence.New)
        self._act_new.triggered.connect(self._new_project)
        m_file.addAction(self._act_new)

        self._act_open = Action(text="打开工程…")
        self._act_open.setShortcut(QKeySequence.Open)
        self._act_open.triggered.connect(self._open_project)
        m_file.addAction(self._act_open)

        self._recent_menu = RoundMenu("最近打开", self)
        m_file.addMenu(self._recent_menu)

        self._act_save = Action(text="保存工程")
        self._act_save.setShortcut(QKeySequence.Save)
        self._act_save.triggered.connect(self._save_project)
        m_file.addAction(self._act_save)

        self._act_save_as = Action(text="另存为…")
        try:
            self._act_save_as.setShortcut(QKeySequence.SaveAs)
        except Exception:
            pass
        self._act_save_as.triggered.connect(self._save_project_as)
        m_file.addAction(self._act_save_as)

        m_file.addSeparator()
        self._act_export = Action(text="导出 G-code…")
        self._act_export.triggered.connect(self._export_gcode_to_file_stub)
        m_file.addAction(self._act_export)

        self._act_export_docx = Action(text="导出为 DOCX…")
        self._act_export_docx.triggered.connect(self._export_docx)
        m_file.addAction(self._act_export_docx)
        self._act_export_xlsx = Action(text="导出为 XLSX…")
        self._act_export_xlsx.triggered.connect(self._export_xlsx)
        m_file.addAction(self._act_export_xlsx)
        self._act_export_pptx = Action(text="导出为 PPTX…")
        self._act_export_pptx.triggered.connect(self._export_pptx)
        m_file.addAction(self._act_export_pptx)

        self._act_export_md = Action(text="导出为 Markdown…")
        self._act_export_md.triggered.connect(self._export_markdown)
        m_file.addAction(self._act_export_md)

        m_file.addSeparator()
        self._act_exit = Action(text="退出")
        self._act_exit.setShortcut(QKeySequence.Quit)
        self._act_exit.triggered.connect(self.close)
        m_file.addAction(self._act_exit)
        _add_top_menu("文件", m_file)

        # 开始（对标 WPS/Word 常用字符格式）
        m_edit = RoundMenu("开始", self)
        self._act_undo = Action(text="撤销")
        self._act_undo.setShortcut(QKeySequence.Undo)
        self._act_undo.triggered.connect(self._perform_undo)
        m_edit.addAction(self._act_undo)
        self._act_redo = Action(text="重做")
        self._act_redo.setShortcut(QKeySequence.Redo)
        self._act_redo.triggered.connect(self._perform_redo)
        m_edit.addAction(self._act_redo)
        m_edit.addSeparator()
        self._act_cut = Action(text="剪切")
        self._act_cut.setToolTip(
            "剪切（编辑区内 Ctrl+X）；表格为当前单元格整格。"
            "不设菜单快捷键以免与单线编辑区重复触发。"
        )
        self._act_cut.triggered.connect(self._edit_cut)
        m_edit.addAction(self._act_cut)
        self._act_copy = Action(text="复制")
        self._act_copy.setToolTip("复制（编辑区内 Ctrl+C）。")
        self._act_copy.triggered.connect(self._edit_copy)
        m_edit.addAction(self._act_copy)
        self._act_paste = Action(text="粘贴")
        self._act_paste.setToolTip("粘贴（编辑区内 Ctrl+V）；表格为粘贴到当前单元格。")
        self._act_paste.triggered.connect(self._edit_paste)
        m_edit.addAction(self._act_paste)
        m_edit.addSeparator()
        self._act_bold = Action(text="加粗")
        self._act_bold.setShortcut(QKeySequence.Bold)
        self._act_bold.triggered.connect(self._toggle_fluent_bold)
        m_edit.addAction(self._act_bold)
        self._act_italic = Action(text="倾斜")
        self._act_italic.setShortcut(QKeySequence.Italic)
        self._act_italic.triggered.connect(self._toggle_fluent_italic)
        m_edit.addAction(self._act_italic)
        self._act_underline = Action(text="下划线")
        self._act_underline.setShortcut(QKeySequence.Underline)
        self._act_underline.triggered.connect(self._toggle_fluent_underline)
        m_edit.addAction(self._act_underline)
        m_edit.addSeparator()

        self._act_al_left = Action(text="左对齐")
        self._act_al_left.setShortcut(_paragraph_align_shortcut("Ctrl+L"))
        self._act_al_left.triggered.connect(
            lambda: self._set_fluent_alignment(Qt.AlignLeft | Qt.AlignAbsolute)
        )
        m_edit.addAction(self._act_al_left)
        self._act_al_center = Action(text="居中")
        self._act_al_center.setShortcut(_paragraph_align_shortcut("Ctrl+E"))
        self._act_al_center.triggered.connect(lambda: self._set_fluent_alignment(Qt.AlignHCenter))
        m_edit.addAction(self._act_al_center)
        self._act_al_right = Action(text="右对齐")
        self._act_al_right.setShortcut(_paragraph_align_shortcut("Ctrl+R"))
        self._act_al_right.triggered.connect(
            lambda: self._set_fluent_alignment(Qt.AlignRight | Qt.AlignAbsolute)
        )
        m_edit.addAction(self._act_al_right)
        self._act_al_justify = Action(text="两端对齐")
        self._act_al_justify.setShortcut(_paragraph_align_shortcut("Ctrl+J"))
        self._act_al_justify.triggered.connect(lambda: self._set_fluent_alignment(Qt.AlignJustify))
        m_edit.addAction(self._act_al_justify)
        m_edit.addSeparator()

        self._act_find = Action(text="查找下一处")
        self._act_find.setShortcut(QKeySequence.Find)
        self._act_find.triggered.connect(self._find_next_from_box)
        m_edit.addAction(self._act_find)

        self._act_replace = Action(text="替换当前")
        try:
            self._act_replace.setShortcut(QKeySequence.Replace)
        except Exception:
            pass
        self._act_replace.triggered.connect(self._replace_current_from_box)
        m_edit.addAction(self._act_replace)

        self._act_replace_all = Action(text="全部替换")
        self._act_replace_all.triggered.connect(self._replace_all_from_box)
        m_edit.addAction(self._act_replace_all)
        m_edit.addSeparator()
        a_sel_all = Action(text="全选")
        a_sel_all.setShortcut(QKeySequence.SelectAll)
        a_sel_all.triggered.connect(self._edit_select_all)
        m_edit.addAction(a_sel_all)
        self._m_edit_menu = m_edit
        _add_top_menu("开始", m_edit)

        # 插入
        m_insert = RoundMenu("插入", self)
        a_insert_symbol = Action(text="符号")
        a_insert_symbol.triggered.connect(self._show_symbol_menu_from_menu)
        m_insert.addAction(a_insert_symbol)
        a_insert_md = Action(text="导入 Markdown…")
        a_insert_md.triggered.connect(self._import_markdown_dialog)
        m_insert.addAction(a_insert_md)
        a_insert_file = Action(text="打开文件…")
        a_insert_file.triggered.connect(self._open_project)
        m_insert.addAction(a_insert_file)
        _add_top_menu("插入", m_insert)

        # 页面布局
        m_layout = RoundMenu("页面布局", self)
        a_layout_page = Action(text="纸张与页边距…")
        a_layout_page.triggered.connect(
            lambda: self._open_device_page_with_hint(
                "已切换到「设备」页，请在纸张与页边距区域调整。"
            )
        )
        m_layout.addAction(a_layout_page)
        a_layout_coord = Action(text="坐标与镜像…")
        a_layout_coord.triggered.connect(
            lambda: self._open_device_page_with_hint("已切换到「设备」页，请在坐标与镜像区域调整。")
        )
        m_layout.addAction(a_layout_coord)
        _add_top_menu("页面布局", m_layout)

        # 审阅
        m_review = RoundMenu("审阅", self)
        a_review_toggle = Action(text="修订模式")
        a_review_toggle.setCheckable(True)
        a_review_toggle.setChecked(self._slide_revision_mode)
        a_review_toggle.triggered.connect(
            lambda checked=False: self._set_slide_revision_mode(bool(checked))
        )
        m_review.addAction(a_review_toggle)
        a_review_accept = Action(text="接受修订")
        a_review_accept.triggered.connect(lambda: self._review_accept_or_reject(True))
        m_review.addAction(a_review_accept)
        a_review_reject = Action(text="拒绝修订")
        a_review_reject.triggered.connect(lambda: self._review_accept_or_reject(False))
        m_review.addAction(a_review_reject)
        _add_top_menu("审阅", m_review)

        # 视图（预览缩放快捷）
        m_view = RoundMenu("视图", self)
        self._act_preview_zoom_in = Action(text="放大预览")
        try:
            self._act_preview_zoom_in.setIcon(FluentIcon.ZOOM_IN.icon())
        except Exception:
            _logger.debug("视图菜单图标 ZOOM_IN 不可用", exc_info=True)
        self._act_preview_zoom_in.setToolTip("路径预览逐步放大（与预览区滚轮方向一致）。")
        self._act_preview_zoom_in.triggered.connect(lambda: self._preview_zoom_step(1.15))
        m_view.addAction(self._act_preview_zoom_in)
        self._act_preview_zoom_out = Action(text="缩小预览")
        try:
            self._act_preview_zoom_out.setIcon(FluentIcon.ZOOM_OUT.icon())
        except Exception:
            _logger.debug("视图菜单图标 ZOOM_OUT 不可用", exc_info=True)
        self._act_preview_zoom_out.setToolTip("路径预览逐步缩小。")
        self._act_preview_zoom_out.triggered.connect(lambda: self._preview_zoom_step(1.0 / 1.15))
        m_view.addAction(self._act_preview_zoom_out)
        self._act_preview_zoom_reset = Action(text="预览缩放到 100%")
        try:
            self._act_preview_zoom_reset.setIcon(FluentIcon.ZOOM.icon())
        except Exception:
            _logger.debug("视图菜单图标 ZOOM 不可用", exc_info=True)
        self._act_preview_zoom_reset.triggered.connect(self._preview_zoom_reset_100)
        m_view.addAction(self._act_preview_zoom_reset)
        m_view.addSeparator()
        self._act_preview_copy_image = Action(text="复制预览图为图像")
        try:
            self._act_preview_copy_image.setIcon(FluentIcon.COPY.icon())
        except Exception:
            _logger.debug("视图菜单图标 COPY 不可用", exc_info=True)
        self._act_preview_copy_image.setToolTip(
            "将当前路径预览视口可见内容复制到系统剪贴板（位图）。"
        )
        self._act_preview_copy_image.triggered.connect(self._preview_copy_visible_to_clipboard)
        m_view.addAction(self._act_preview_copy_image)
        self._act_preview_export_png = Action(text="导出可见预览为 PNG…")
        try:
            self._act_preview_export_png.setIcon(FluentIcon.FOLDER.icon())
        except Exception:
            _logger.debug("视图菜单图标 FOLDER 不可用", exc_info=True)
        self._act_preview_export_png.setToolTip(
            "将当前视口内的预览保存为 PNG 文件（与缩放/平移后的画面一致）。"
        )
        self._act_preview_export_png.triggered.connect(self._preview_export_visible_png)
        m_view.addAction(self._act_preview_export_png)
        m_view.addSeparator()
        for z in (50, 75, 100, 125, 150, 200):
            act = Action(text=f"预览缩放 {z}%")

            def _mk(z=z) -> None:
                self._preview_zoom = float(z) / 100.0
                self._refresh_preview()

            act.triggered.connect(_mk)
            m_view.addAction(act)
        _add_top_menu("视图", m_view)

        # 设备
        m_dev = RoundMenu("设备", self)
        self._act_refresh_ports = Action(text="刷新端口")
        self._act_refresh_ports.triggered.connect(self._refresh_ports)
        m_dev.addAction(self._act_refresh_ports)

        self._act_toggle_serial = Action(text="连接/断开")
        self._act_toggle_serial.triggered.connect(self._toggle_serial)
        m_dev.addAction(self._act_toggle_serial)

        m_dev.addSeparator()

        self._act_send = Action(text="发送当前 G-code")
        self._act_send.triggered.connect(self._send_gcode)
        m_dev.addAction(self._act_send)

        self._act_send_pause = Action(text="发送（遇 M800 暂停）")
        self._act_send_pause.triggered.connect(self._send_gcode_pause_at_m800)
        m_dev.addAction(self._act_send_pause)

        self._act_paper_flow = Action(text="换纸流程（前缀→M800→后缀）")
        self._act_paper_flow.triggered.connect(self._paper_change_flow)
        m_dev.addAction(self._act_paper_flow)
        _add_top_menu("设备", m_dev)

        # 帮助
        m_help = RoundMenu("帮助", self)
        a_spec = Action(text="打开 SPEC.md")
        a_spec.triggered.connect(self._open_spec_document)
        m_help.addAction(a_spec)
        a_ai = Action(text="打开 AI_PROMPTS.md")
        a_ai.triggered.connect(self._open_ai_prompts_document)
        m_help.addAction(a_ai)
        a_missing = Action(text="查看缺失字符")
        a_missing.triggered.connect(self._show_missing_glyphs_dialog)
        m_help.addAction(a_missing)
        _add_top_menu("帮助", m_help)

    def _safe_switch_to(self, widget: QWidget, label: str) -> None:
        try:
            self.switchTo(widget)
        except Exception:
            _logger.debug("Fluent switchTo 失败（%s）", label, exc_info=True)

    def _current_page_id(self) -> str:
        try:
            cur = self.stackedWidget.currentWidget()
            return str(cur.objectName() if cur is not None else "")
        except Exception:
            _logger.debug("读取当前子界面失败", exc_info=True)
            return ""

    def _current_content_page_id(self) -> str:
        """当前预览实际取数的内容页：文字 / 表格 / 演示。"""
        pid = self._current_page_id()
        if pid in ("word", "table", "slides"):
            return pid
        return {
            "文字": "word",
            "表格": "table",
            "演示": "slides",
        }.get(self._last_active_mode, "word")

    def _content_mode_label(self, pid: str) -> str:
        return {
            "word": "文字",
            "table": "表格",
            "slides": "演示",
        }.get(pid, "文字")

    def _status_line_content_extra(self, pid: str) -> str:
        if pid == "table":
            try:
                tr, tc = self._table_editor.row_column_count()
                extra = f"表格：{tr}×{tc}"
                grid_mode = str(getattr(self._table_editor, "grid_gcode_mode", lambda: "none")())
                if grid_mode == "outer":
                    extra += "   网格：仅外框"
                elif grid_mode == "all":
                    extra += "   网格：全部"
                return extra
            except Exception:
                return ""
        if pid == "slides":
            try:
                return self._presentation_editor.status_line()
            except Exception:
                return ""
        try:
            return f"字数：{_count_visible_chars(self._word_editor.toPlainText())}"
        except Exception:
            return ""

    def _current_content_source_label(self) -> str:
        return self._content_mode_label(self._current_content_page_id())

    def _current_content_plain_text_for_glyph_check(self, pid: str) -> str:
        if pid == "table":
            try:
                blob = self._capture_table_blob()
            except Exception:
                return ""
            rows = blob.get("cells") or []
            parts: list[str] = []
            for row in rows:
                for cell in row:
                    text = str((cell or {}).get("text", "") or "").strip()
                    if text:
                        parts.append(text)
            return "\n".join(parts)
        if pid == "slides":
            try:
                return "\n".join(self._capture_slides_storage_for_export())
            except Exception:
                return ""
        try:
            return self._word_editor.toPlainText()
        except Exception:
            return ""

    def _glyph_status_hint(self, pid: str) -> str:
        text = self._current_content_plain_text_for_glyph_check(pid)
        if not text.strip():
            return ""
        try:
            missing = self._mapper.missing_text_chars(text)
        except Exception:
            return ""
        if not missing:
            return "字形：完整"
        preview = " ".join(repr(ch)[1:-1] for ch in missing[:4])
        if len(missing) > 4:
            preview += " ..."
        return f"缺字形：{len(missing)}（{preview}）"

    def _glyph_warning_summary(self, pid: str) -> str:
        hint = self._glyph_status_hint(pid)
        if hint.startswith("缺字形："):
            return hint
        return ""

    def _missing_glyph_chars(self, pid: str) -> List[str]:
        text = self._current_content_plain_text_for_glyph_check(pid)
        if not text.strip():
            return []
        try:
            return self._mapper.missing_text_chars(text)
        except Exception:
            return []

    def _show_missing_glyphs_dialog(self) -> None:
        pid = self._current_content_page_id()
        source = self._content_mode_label(pid)
        text = self._current_content_plain_text_for_glyph_check(pid)
        if not text.strip():
            QMessageBox.information(self, "缺失字符检查", f"当前“{source}”没有可检查的文本内容。")
            return
        missing = self._missing_glyph_chars(pid)
        if not missing:
            QMessageBox.information(
                self,
                "缺失字符检查",
                f"当前“{source}”内容的字形覆盖完整，可以继续生成预览或 G-code。",
            )
            return
        chars = " ".join(missing)
        QMessageBox.warning(
            self,
            "缺失字符检查",
            f"当前“{source}”存在 {len(missing)} 个未覆盖字符：\n\n{chars}\n\n"
            "这些字符可能不会出现在预览或 G-code 中。"
            "如需完整输出，请更换/合并单线字库，或调整文档内容。",
        )

    def _on_status_line_link_activated(self, link: str) -> None:
        target = str(link or "").strip()
        if target == "missing-glyphs":
            self._show_missing_glyphs_dialog()
        elif target == "preflight-report":
            self._show_preflight_report()

    def _current_work_paths_checked(self) -> List[VectorPath]:
        paths = self._work_paths()
        if paths:
            return paths
        source = self._current_content_source_label()
        glyph_hint = self._glyph_status_hint(self._current_content_page_id())
        glyph_extra = f" {glyph_hint}。" if glyph_hint.startswith("缺字形：") else ""
        raise ValueError(
            f"当前“{source}”没有可导出的笔画路径。请先输入内容，或检查字库/表格/演示内容是否为空。{glyph_extra}"
        )

    def _build_job_summary(self, paths: List[VectorPath]) -> str:
        pid = self._current_content_page_id()
        source = self._content_mode_label(pid)
        path_count = len(paths)
        point_count = sum(len(vp.points) for vp in paths)
        pm = str(getattr(self._cfg, "gcode_pen_mode", "z") or "z").strip().lower()
        if pm in ("m3m5", "m3", "spindle"):
            pen = f"M3/M5（S{int(getattr(self._cfg, 'gcode_m3_s_value', 0) or 0)}）"
        else:
            pen = (
                f"Z 轴（抬笔 {float(getattr(self._cfg, 'z_up_mm', 0.0)):.1f} / "
                f"落笔 {float(getattr(self._cfg, 'z_down_mm', 0.0)):.1f} mm）"
            )
        summary = (
            f"来源：{source}\n"
            f"路径段：{path_count}，点数：{point_count}\n"
            f"纸张：{float(getattr(self._cfg, 'page_width_mm', 0.0)):.1f} × "
            f"{float(getattr(self._cfg, 'page_height_mm', 0.0)):.1f} mm\n"
            f"抬落笔：{pen}"
        )
        glyph_warning = self._glyph_warning_summary(pid)
        if glyph_warning:
            summary += f"\n注意：{glyph_warning}"
        return summary

    def _show_symbol_menu_from_menu(self) -> None:
        m = getattr(self, "_symbol_menu", None)
        if m is None:
            InfoBar.warning("符号", "符号菜单未初始化。", parent=self, position=InfoBarPosition.TOP)
            return
        try:
            gp = self._menu_bar.mapToGlobal(self._menu_bar.rect().bottomLeft())
            m.exec_(gp)
        except Exception:
            _logger.debug("从菜单栏打开符号菜单失败", exc_info=True)

    def _open_device_page_with_hint(self, hint: str) -> None:
        if self._device_page is None:
            return
        self._safe_switch_to(self._device_page, "设备")
        InfoBar.info("页面布局", hint, parent=self, position=InfoBarPosition.TOP)

    def _set_slide_revision_mode(self, enabled: bool) -> None:
        self._slide_revision_mode = bool(enabled)
        if self._current_page_id() != "slides":
            InfoBar.info(
                "审阅",
                "修订模式主要用于「演示」页文本审阅。",
                parent=self,
                position=InfoBarPosition.TOP,
            )

    def _review_accept_or_reject(self, accept: bool) -> None:
        if self._current_page_id() != "slides":
            InfoBar.info(
                "审阅",
                "请先切换到「演示」页，再执行修订接受或拒绝。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        cur = self._presentation_editor.slide_editor().textCursor()
        if accept:
            self._slide_revision_accept(selection_only=cur.hasSelection())
        else:
            self._slide_revision_reject(selection_only=cur.hasSelection())

    def _on_fluent_stack_page_changed(self, _index: int = 0) -> None:
        """
        导航切换子页后刷新预览与状态，
        使 _work_paths() 与画面一致，
        不依赖替换 _onCurrentInterfaceChanged。
        """
        try:
            self._refresh_preview()
        except Exception:
            _logger.debug("切换子页后刷新预览失败", exc_info=True)
        try:
            self._update_status_line()
        except Exception:
            pass
        try:
            self._wps_refresh_font_toolbar_context()
        except Exception:
            pass
        try:
            self._refresh_undo_redo_menu_state()
        except Exception:
            pass
        try:
            self._refresh_export_action_states()
        except Exception:
            pass
        # 文字模式边界提示（一次性、避免打扰；对齐 P1-3「文字页说明与引导」）。
        try:
            if not self._shown_word_mode_tip and self._current_page_id() == "word":
                self._shown_word_mode_tip = True
                InfoBar.info(
                    "文字模式",
                    "「文字」为单线笔画编辑：输入会映射为 Hershey/奎享字形并生成 G-code。\n"
                    "富文本样式（如加粗/斜体/段落对齐）请切到「表格」或「演示」设置。",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
        except Exception:
            _logger.debug("文字模式提示失败", exc_info=True)

    def _capture_nonword_tuple(self) -> tuple[str, str, str, str, str]:
        return capture_nonword_state_pyqt5(
            self._table_editor.to_project_blob(),
            self._presentation_editor.slides_storage(),
            self._presentation_editor.master_storage(),
            serialize_vector_paths(self._sketch_paths),
            self._capture_insert_vector_blob(),
        )

    def _restore_nonword_state(self, state: tuple[str, str, str, str, str]) -> None:
        self._nonword_undo_restoring = True
        try:
            tb_s, sl_s, sm_s, sk_s, iv_s = state
            self._table_editor.from_project_blob(json.loads(tb_s))
            slides = json.loads(sl_s)
            master = json.loads(sm_s) if sm_s else {}
            self._presentation_editor.load_slides(slides if isinstance(slides, list) else [""])
            self._presentation_editor.load_master_storage(
                master if isinstance(master, dict) else {}
            )
            self._sketch_paths = deserialize_vector_paths(json.loads(sk_s))
            iv = json.loads(iv_s) if iv_s else {}
            self._insert_paths_base.clear()
            self._insert_vector_scale = 1.0
            self._insert_vector_dx_mm = 0.0
            self._insert_vector_dy_mm = 0.0
            if isinstance(iv, dict) and iv.get("paths"):
                self._insert_paths_base.extend(deserialize_vector_paths(iv["paths"]))
                self._insert_vector_scale = float(iv.get("scale", 1.0))
                self._insert_vector_dx_mm = float(iv.get("dx_mm", 0.0))
                self._insert_vector_dy_mm = float(iv.get("dy_mm", 0.0))
        finally:
            self._nonword_undo_restoring = False
        self._nonword_undo_anchor = state
        self._refresh_preview()
        self._refresh_undo_redo_menu_state()

    def _push_nonword_undo_snapshot(self) -> None:
        if self._nonword_undo_restoring:
            return
        cur = self._capture_nonword_tuple()
        if cur == self._nonword_undo_anchor:
            return
        self._nonword_undo_stack.push(
            NonWordEditCommandPyQt5(self, self._nonword_undo_anchor, cur, text="表格 / 演示 / 手绘")
        )
        self._nonword_undo_anchor = cur

    def _reset_nonword_undo_anchor(self) -> None:
        self._nonword_undo_stack.clear()
        self._nonword_undo_anchor = self._capture_nonword_tuple()

    def _on_nonword_content_changed(self) -> None:
        self._push_nonword_undo_snapshot()

    def _edit_slide_master_from_ribbon(self, which: str) -> None:
        master = self._presentation_editor.master_storage()
        self._edit_presentation_master_text(which, master.get(which, ""))

    def _insert_svg_paths_from_file(self, path: Path) -> None:
        try:
            vps = vector_paths_from_svg_file(
                path,
                page_width_mm=self._cfg.page_width_mm,
                page_height_mm=self._cfg.page_height_mm,
            )
        except Exception as e:
            InfoBar.error("插入 SVG", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        if not vps:
            InfoBar.warning(
                "插入 SVG", "SVG 中未解析到可绘制路径。", parent=self, position=InfoBarPosition.TOP
            )
            return
        self._insert_paths_base.extend(vps)
        self._insert_vector_scale = 1.0
        self._insert_vector_dx_mm = 0.0
        self._insert_vector_dy_mm = 0.0
        self._center_insert_vector_on_page()
        self._on_nonword_content_changed()
        self._refresh_preview()
        self._update_status_line()
        InfoBar.success(
            "插入素材",
            f"已导入 {path.name}，共 {len(vps)} 段路径，已居中到页面。",
            parent=self,
            position=InfoBarPosition.TOP,
        )

    def _insert_svg_from_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入矢量（SVG）",
            str(Path.home()),
            "SVG (*.svg);;所有文件 (*)",
        )
        if path:
            self._insert_svg_paths_from_file(Path(path))

    def _insert_bitmap_traced(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入图片并描摹为路径",
            str(Path.home()),
            "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;所有文件 (*)",
        )
        if not path:
            return
        try:
            xml = trace_image_to_svg(Path(path))
            vps = vector_paths_from_svg_string(
                xml,
                page_width_mm=self._cfg.page_width_mm,
                page_height_mm=self._cfg.page_height_mm,
            )
        except Exception as e:
            InfoBar.error("图片描摹", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        if not vps:
            InfoBar.warning(
                "图片描摹",
                "矢量化结果中未解析到路径，可尝试提高图片对比度后重试。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        self._insert_paths_base.extend(vps)
        self._insert_vector_scale = 1.0
        self._insert_vector_dx_mm = 0.0
        self._insert_vector_dy_mm = 0.0
        self._center_insert_vector_on_page()
        self._on_nonword_content_changed()
        self._refresh_preview()
        self._update_status_line()
        InfoBar.success(
            "图片描摹",
            f"已把图片转为 {len(vps)} 段路径并插入页面中心。",
            parent=self,
            position=InfoBarPosition.TOP,
        )

    def _clear_inserted_vectors(self) -> None:
        if not self._insert_paths_base:
            InfoBar.info(
                "插图", "当前没有已插入的矢量素材。", parent=self, position=InfoBarPosition.TOP
            )
            return
        self._insert_paths_base.clear()
        self._insert_vector_scale = 1.0
        self._insert_vector_dx_mm = 0.0
        self._insert_vector_dy_mm = 0.0
        self._on_nonword_content_changed()
        self._refresh_preview()
        self._update_status_line()
        InfoBar.success("插图", "已清除插入的矢量素材。", parent=self, position=InfoBarPosition.TOP)

    def _center_insert_vector_on_page(self) -> None:
        if not self._insert_paths_base:
            return
        bb = paths_bounding_box(self._insert_paths_base)
        if bb[0] >= bb[2] or bb[1] >= bb[3]:
            return
        cx = (bb[0] + bb[2]) / 2.0
        cy = (bb[1] + bb[3]) / 2.0
        self._insert_vector_dx_mm = float(self._cfg.page_width_mm) / 2.0 - cx
        self._insert_vector_dy_mm = float(self._cfg.page_height_mm) / 2.0 - cy

    def _focus_in_slide_editor(self) -> bool:
        """焦点在演示页右侧富文本区内（含其 viewport），用于区分「改字」与「整页级」撤销栈。"""
        te = self._presentation_editor.slide_editor()
        w = QApplication.focusWidget()
        while w is not None:
            if w is te:
                return True
            w = w.parentWidget()
        return False

    def _refresh_undo_redo_menu_state(self) -> None:
        if not hasattr(self, "_act_undo"):
            return
        pid = self._current_page_id()
        if pid == "slides" and self._focus_in_slide_editor():
            doc = self._presentation_editor.slide_editor().document()
            self._act_undo.setEnabled(doc.isUndoAvailable())
            self._act_redo.setEnabled(doc.isRedoAvailable())
        elif pid in ("table", "slides"):
            self._act_undo.setEnabled(self._nonword_undo_stack.canUndo())
            self._act_redo.setEnabled(self._nonword_undo_stack.canRedo())
        elif pid == "word":
            self._act_undo.setEnabled(self._word_editor.canUndo())
            self._act_redo.setEnabled(self._word_editor.canRedo())
        else:
            self._act_undo.setEnabled(False)
            self._act_redo.setEnabled(False)

    def _perform_undo(self) -> None:
        pid = self._current_page_id()
        if pid == "slides" and self._focus_in_slide_editor():
            self._presentation_editor.slide_editor().undo()
        elif pid in ("table", "slides"):
            self._nonword_undo_stack.undo()
        elif pid == "word":
            self._word_editor.undo()
        else:
            return
        self._refresh_undo_redo_menu_state()

    def _perform_redo(self) -> None:
        pid = self._current_page_id()
        if pid == "slides" and self._focus_in_slide_editor():
            self._presentation_editor.slide_editor().redo()
        elif pid in ("table", "slides"):
            self._nonword_undo_stack.redo()
        elif pid == "word":
            self._word_editor.redo()
        else:
            return
        self._refresh_undo_redo_menu_state()

    def _inner_clipboard_text_widget(self):
        """表格单元格内嵌编辑器、演示/设备多行框等（不含单线编辑区）。"""
        w = QApplication.focusWidget()
        while w is not None and w is not self._word_editor:
            if isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit)):
                return w
            w = w.parentWidget()
        return None

    def _edit_cut(self) -> None:
        if QApplication.focusWidget() is self._word_editor:
            self._word_editor.edit_cut()
            return
        inner = self._inner_clipboard_text_widget()
        if inner is not None and callable(getattr(inner, "cut", None)):
            inner.cut()
            return
        pid = self._current_page_id()
        if pid == "table":
            self._table_editor.clipboard_cut_cell()
        elif pid == "slides":
            self._presentation_editor.slide_editor().cut()

    def _edit_copy(self) -> None:
        if QApplication.focusWidget() is self._word_editor:
            self._word_editor.edit_copy()
            return
        inner = self._inner_clipboard_text_widget()
        if inner is not None and callable(getattr(inner, "copy", None)):
            inner.copy()
            return
        pid = self._current_page_id()
        if pid == "table":
            self._table_editor.clipboard_copy_cell()
        elif pid == "slides":
            self._presentation_editor.slide_editor().copy()

    def _edit_paste(self) -> None:
        if QApplication.focusWidget() is self._word_editor:
            self._word_editor.edit_paste()
            return
        inner = self._inner_clipboard_text_widget()
        if inner is not None and callable(getattr(inner, "paste", None)):
            inner.paste()
            return
        pid = self._current_page_id()
        if pid == "table":
            self._table_editor.clipboard_paste_cell()
        elif pid == "slides":
            self._presentation_editor.slide_editor().paste()

    def _active_text_edit(self):
        name = self._current_page_id()
        if name == "slides":
            return self._presentation_editor.slide_editor()
        if name == "word" or not name:
            return self._word_editor
        return None

    def _edit_select_all(self) -> None:
        if self._current_page_id() == "table":
            self._table_editor.select_all()
            return
        te = self._active_text_edit()
        if te is not None:
            te.selectAll()

    def _toggle_fluent_bold(self) -> None:
        pid = self._current_page_id()
        if pid == "table":
            self._table_editor.apply_bold_current_cell()
        elif pid == "slides":
            te = self._presentation_editor.slide_editor()
            cur = te.textCursor()
            bold_on = cur.charFormat().fontWeight() >= QFont.DemiBold
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Normal if bold_on else QFont.Bold)
            cur.mergeCharFormat(fmt)
            te.mergeCurrentCharFormat(fmt)
        elif pid in ("word", "home", "file", ""):
            InfoBar.info(
                "加粗",
                "「文字」为单线笔画模式，不支持富文本加粗。请切到「表格」或「演示」使用加粗。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        else:
            return
        self._refresh_preview()

    def _toggle_fluent_italic(self) -> None:
        pid = self._current_page_id()
        if pid == "table":
            self._table_editor.apply_italic_current_cell()
        elif pid == "slides":
            te = self._presentation_editor.slide_editor()
            cur = te.textCursor()
            fmt = QTextCharFormat()
            fmt.setFontItalic(not cur.charFormat().fontItalic())
            cur.mergeCharFormat(fmt)
            te.mergeCurrentCharFormat(fmt)
        elif pid in ("word", "home", "file", ""):
            InfoBar.info(
                "倾斜",
                "「文字」为单线笔画模式，不支持富文本倾斜。请切到「表格」或「演示」。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        else:
            return
        self._refresh_preview()

    def _toggle_fluent_underline(self) -> None:
        pid = self._current_page_id()
        if pid == "table":
            self._table_editor.apply_underline_current_cell()
        elif pid == "slides":
            te = self._presentation_editor.slide_editor()
            cur = te.textCursor()
            u = cur.charFormat().underlineStyle()
            fmt = QTextCharFormat()
            if u != QTextCharFormat.NoUnderline:
                fmt.setUnderlineStyle(QTextCharFormat.NoUnderline)
            else:
                fmt.setUnderlineStyle(QTextCharFormat.SingleUnderline)
            cur.mergeCharFormat(fmt)
            te.mergeCurrentCharFormat(fmt)
        elif pid in ("word", "home", "file", ""):
            InfoBar.info(
                "下划线",
                "「文字」为单线笔画模式，不支持富文本下划线。请切到「表格」或「演示」。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        else:
            return
        self._refresh_preview()

    def _set_fluent_alignment(self, alignment: int) -> None:
        """段落对齐：表格当前单元格 / 演示当前页 QTextEdit（对标 WPS/Word）。"""
        pid = self._current_page_id()
        if pid == "table":
            self._table_editor.set_alignment_current_cell(Qt.Alignment(alignment))
        elif pid == "slides":
            self._presentation_editor.slide_editor().setAlignment(Qt.Alignment(alignment))
        elif pid in ("word", "home", "file", ""):
            InfoBar.info(
                "段落对齐",
                "「文字」为单线笔画模式，请在「表格」或「演示」中设置段落对齐。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        else:
            return
        self._refresh_preview()

    def _append_wps_character_format_buttons(self, row: QHBoxLayout) -> None:
        def _fmt_btn(text: str, tip: str, slot) -> None:
            b = PushButton(text)
            b.setFixedSize(32, 28)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b)

        _fmt_btn("B", "加粗 (Ctrl+B)", self._toggle_fluent_bold)
        _fmt_btn("I", "倾斜 (Ctrl+I)", self._toggle_fluent_italic)
        _fmt_btn("U", "下划线 (Ctrl+U)", self._toggle_fluent_underline)

    def _append_wps_alignment_buttons(self, row: QHBoxLayout) -> None:
        def _fmt_btn(text: str, tip: str, slot) -> None:
            b = PushButton(text)
            b.setFixedSize(42, 28)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b)

        _fmt_btn(
            "左",
            "左对齐 (Ctrl+L)",
            lambda: self._set_fluent_alignment(int(Qt.AlignLeft | Qt.AlignAbsolute)),
        )
        _fmt_btn("中", "居中 (Ctrl+E)", lambda: self._set_fluent_alignment(int(Qt.AlignHCenter)))
        _fmt_btn(
            "右",
            "右对齐 (Ctrl+R)",
            lambda: self._set_fluent_alignment(int(Qt.AlignRight | Qt.AlignAbsolute)),
        )
        _fmt_btn(
            "两端", "两端对齐 (Ctrl+J)", lambda: self._set_fluent_alignment(int(Qt.AlignJustify))
        )

    def _append_wps_table_rowcol_buttons(self, row: QHBoxLayout) -> None:
        """表格页格式条：插入/删除行列快捷（与网格右键一致）。"""
        btn = PushButton("插入/删除…")
        btn.setFixedHeight(28)
        btn.setMinimumWidth(92)
        btn.setToolTip("打开行/列插入与删除菜单（对齐网格右键菜单；窄屏不挤占格式条宽度）。")

        def _open() -> None:
            try:
                from qfluentwidgets import RoundMenu
            except Exception:
                return
            m = RoundMenu("行列", self)
            a_ra = Action(text="在上方插入行")
            a_ra.setToolTip("在当前行之上插入一行")
            a_ra.triggered.connect(self._table_editor.insert_row_above)
            m.addAction(a_ra)
            a_rb = Action(text="在下方插入行")
            a_rb.setToolTip("在当前行之下插入一行")
            a_rb.triggered.connect(self._table_editor.insert_row_below)
            m.addAction(a_rb)
            m.addSeparator()
            a_cl = Action(text="在左侧插入列")
            a_cl.triggered.connect(self._table_editor.insert_column_left)
            m.addAction(a_cl)
            a_cr = Action(text="在右侧插入列")
            a_cr.triggered.connect(self._table_editor.insert_column_right)
            m.addAction(a_cr)
            m.addSeparator()
            tr, tc = self._table_editor.row_column_count()
            a_dr = Action(text="删除当前行")
            a_dr.setToolTip("至少保留一行")
            a_dr.triggered.connect(self._table_editor.delete_current_row)
            a_dr.setEnabled(tr > 1)
            m.addAction(a_dr)
            a_dc = Action(text="删除当前列")
            a_dc.setToolTip("至少保留一列")
            a_dc.triggered.connect(self._table_editor.delete_current_column)
            a_dc.setEnabled(tc > 1)
            m.addAction(a_dc)
            m.exec_(btn.mapToGlobal(btn.rect().bottomLeft()))

        btn.clicked.connect(_open)
        row.addWidget(btn)

    def _append_wps_slide_paragraph_buttons(self, row: QHBoxLayout) -> None:
        """演示页格式条：项目符号、编号、缩进（与幻灯片右键一致）。"""
        btn = PushButton("段落…")
        btn.setFixedHeight(28)
        btn.setMinimumWidth(60)
        btn.setToolTip("打开项目符号/编号/缩进菜单（与幻灯片右键一致）。")

        def _open() -> None:
            try:
                from qfluentwidgets import RoundMenu
            except Exception:
                return
            m = RoundMenu("段落", self)
            a_bul = Action(text="项目符号")
            a_bul.setToolTip("将当前段落设为符号列表")
            a_bul.triggered.connect(lambda: self._slide_apply_list_style(QTextListFormat.ListDisc))
            m.addAction(a_bul)
            a_num = Action(text="编号")
            a_num.setToolTip("将当前段落设为编号列表")
            a_num.triggered.connect(
                lambda: self._slide_apply_list_style(QTextListFormat.ListDecimal)
            )
            m.addAction(a_num)
            m.addSeparator()
            a_in = Action(text="增加缩进")
            a_in.triggered.connect(lambda: self._slide_change_block_indent(1))
            m.addAction(a_in)
            a_out = Action(text="减少缩进")
            a_out.triggered.connect(lambda: self._slide_change_block_indent(-1))
            m.addAction(a_out)
            m.exec_(btn.mapToGlobal(btn.rect().bottomLeft()))

        btn.clicked.connect(_open)
        row.addWidget(btn)

    def _append_wps_slide_style_presets(self, row: QHBoxLayout) -> None:
        """演示页：固定样式预设（P1-2），写入 HTML 随工程保存。"""
        btn = PushButton("标题/正文…")
        btn.setFixedHeight(28)
        btn.setMinimumWidth(92)
        btn.setToolTip("打开标题1/标题2/正文样式预设菜单（与右键样式一致）。")

        def _open() -> None:
            try:
                from qfluentwidgets import RoundMenu
            except Exception:
                return
            m = RoundMenu("样式", self)
            a_h1 = Action(text="标题 1")
            a_h1.setToolTip("20pt 加粗，段前后留白")
            a_h1.triggered.connect(lambda: self._slide_apply_style_preset("h1"))
            m.addAction(a_h1)
            a_h2 = Action(text="标题 2")
            a_h2.setToolTip("16pt 加粗")
            a_h2.triggered.connect(lambda: self._slide_apply_style_preset("h2"))
            m.addAction(a_h2)
            a_body = Action(text="正文")
            a_body.setToolTip("12pt 常规，段后留白")
            a_body.triggered.connect(lambda: self._slide_apply_style_preset("body"))
            m.addAction(a_body)
            m.exec_(btn.mapToGlobal(btn.rect().bottomLeft()))

        btn.clicked.connect(_open)
        row.addWidget(btn)

        theme_btn = PushButton("主题…")
        theme_btn.setFixedHeight(28)
        theme_btn.setMinimumWidth(64)
        theme_btn.setToolTip("把当前字体/字号/对齐/段前后距套用到所有幻灯片正文。")

        def _apply_theme() -> None:
            if self._current_page_id() != "slides":
                return
            te = self._presentation_editor.slide_editor()
            cur = te.textCursor()

            # 字体/字号：从光标字符格式提取；若未显式设置则回退到编辑器当前字体
            cf = cur.charFormat()
            fam = (cf.fontFamily() or "").strip()
            if not fam:
                fam = te.currentFont().family()

            pts = float(cf.fontPointSizeF() or 0.0)
            if pts <= 0:
                pts = float(cf.fontPointSize() or 0.0)
            if pts <= 0:
                pts = float(te.currentFont().pointSizeF() or te.currentFont().pointSize() or 12.0)

            theme_char = QTextCharFormat()
            theme_char.setFontFamily(fam)
            theme_char.setFontPointSize(pts)

            # 段落对齐/段距：从当前块提取
            bf = cur.blockFormat()
            theme_block = QTextBlockFormat()
            theme_block.setAlignment(bf.alignment())
            theme_block.setTopMargin(bf.topMargin())
            theme_block.setBottomMargin(bf.bottomMargin())

            self._presentation_editor.apply_theme_to_all_slides(theme_char, theme_block)
            self._refresh_preview()

        theme_btn.clicked.connect(_apply_theme)
        row.addWidget(theme_btn)

    def _append_wps_clipboard_buttons(self, row: QHBoxLayout) -> None:
        """剪贴板组：与「编辑」菜单共用槽；图标贴近 Fluent/WPS 工具栏。"""

        def _icon_btn(ico: FluentIcon, tip: str, slot) -> None:
            b = PushButton()
            try:
                b.setIcon(ico.icon())
            except Exception:
                _logger.debug("剪贴板按钮图标加载失败：%s", ico, exc_info=True)
            b.setFixedSize(32, 28)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b)

        _icon_btn(FluentIcon.CUT, "剪切（与编辑菜单相同；文字区亦可用 Ctrl+X）", self._edit_cut)
        _icon_btn(FluentIcon.COPY, "复制（Ctrl+C）", self._edit_copy)
        _icon_btn(FluentIcon.PASTE, "粘贴（Ctrl+V）", self._edit_paste)

    def _append_wps_font_controls(self, row: QHBoxLayout) -> None:
        font_lab = QLabel("字体")
        font_lab.setStyleSheet("color:#3d444d;font-size:12px;")
        row.addWidget(font_lab)
        cb = QFontComboBox()
        cb.setMaxVisibleItems(14)
        cb.setMinimumWidth(148)
        cb.setToolTip(
            "表格/演示：系统字体。文字（单线）：笔画轮廓来自当前字库 JSON，"
            "与预览、G-code、写字机一致；此处字体名不替换字库。"
        )
        cb.currentFontChanged.connect(self._on_wps_fontcombo_changed)
        self._wps_font_combos.append(cb)
        row.addWidget(cb)
        size_lab = QLabel("字号")
        size_lab.setStyleSheet("color:#3d444d;font-size:12px;")
        row.addWidget(size_lab)
        sp = SpinBox()
        sp.setRange(6, 200)
        sp.setValue(12)
        sp.setToolTip(
            "文字：单线编辑区字号；笔画按「设备」页 mm/pt 与字库缩放，与预览/机床一致。"
            "表格=当前单元格；演示=光标/选区。"
        )
        sp.valueChanged.connect(self._on_wps_fontsize_changed)
        self._wps_font_spins.append(sp)
        row.addWidget(sp)

    def _on_wps_fontcombo_changed(self, font: QFont) -> None:
        snd = self.sender()
        fam = font.family()
        for c in self._wps_font_combos:
            if c is snd:
                continue
            c.blockSignals(True)
            c.setCurrentFont(QFont(fam))
            c.blockSignals(False)
        self._wps_apply_font_family(fam)

    def _on_wps_fontsize_changed(self, value: int) -> None:
        snd = self.sender()
        v = max(6, min(200, int(value)))
        for s in self._wps_font_spins:
            if s is snd:
                continue
            s.blockSignals(True)
            s.setValue(v)
            s.blockSignals(False)
        self._wps_apply_font_size(v)

    def _wps_apply_font_family(self, family: str) -> None:
        fam = (family or "").strip()
        if not fam:
            return
        pid = self._current_page_id()
        if pid == "table":
            self._table_editor.merge_font_family_current_cell(fam)
        elif pid == "slides":
            te = self._presentation_editor.slide_editor()
            cur = te.textCursor()
            fmt = QTextCharFormat()
            fmt.setFontFamily(fam)
            cur.mergeCharFormat(fmt)
            te.mergeCurrentCharFormat(fmt)
            te.setTextCursor(cur)
        elif pid in ("word", "home", "file", ""):
            self._word_editor.set_stroke_font_family(fam)
        sz = self._wps_font_spins[0].value() if self._wps_font_spins else 12
        f = QFont(fam)
        f.setPointSize(int(sz))
        self._table_editor.apply_document_font(f)
        self._presentation_editor.apply_document_font(f)
        apply_default_tab_stops(self._presentation_editor.slide_editor())
        self._refresh_preview()

    def _wps_apply_font_size(self, sz: int) -> None:
        sz = max(6, min(200, int(sz)))
        pid = self._current_page_id()
        if pid == "table":
            self._table_editor.merge_font_point_size_current_cell(float(sz))
        elif pid == "slides":
            te = self._presentation_editor.slide_editor()
            cur = te.textCursor()
            fmt = QTextCharFormat()
            fmt.setFontPointSize(float(sz))
            cur.mergeCharFormat(fmt)
            te.mergeCurrentCharFormat(fmt)
            te.setTextCursor(cur)
        elif pid in ("word", "home", "file", ""):
            self._word_editor.set_stroke_font_point_size(float(sz))
        fam = (
            self._wps_font_combos[0].currentFont().family()
            if self._wps_font_combos
            else self._word_editor.font().family()
        )
        f = QFont(fam)
        f.setPointSize(sz)
        self._table_editor.apply_document_font(f)
        self._presentation_editor.apply_document_font(f)
        apply_default_tab_stops(self._presentation_editor.slide_editor())
        self._refresh_preview()

    def _wps_refresh_font_toolbar_context(self) -> None:
        """切换导航页时刷新各「开始」条中的字体/字号显示。"""
        if not self._wps_font_combos or not self._wps_font_spins:
            return
        pid = self._current_page_id()
        if pid == "slides":
            f = self._presentation_editor.slide_editor().currentFont()
            pt = int(round(f.pointSizeF() if f.pointSizeF() > 0 else f.pointSize() or 12))
        elif pid == "table":
            f = self._table_editor.toolbar_context_font()
            pt = int(round(f.pointSizeF() if f.pointSizeF() > 0 else f.pointSize() or 12))
        else:
            f = self._word_editor.font()
            pt = int(round(self._word_editor.stroke_font_point_size()))
        pt = max(6, min(200, pt))
        for c in self._wps_font_combos:
            c.blockSignals(True)
            if pid == "slides":
                c.setCurrentFont(self._presentation_editor.slide_editor().currentFont())
            elif pid == "table":
                c.setCurrentFont(self._table_editor.toolbar_context_font())
            else:
                c.setCurrentFont(f)
            c.blockSignals(False)
        for s in self._wps_font_spins:
            s.blockSignals(True)
            s.setValue(pt)
            s.blockSignals(False)

    def _setup_symbol_panel(self) -> None:
        """分组符号菜单：编辑菜单 + 查找条「符号」按钮。"""
        self._symbol_menu = None
        try:
            from qfluentwidgets import Action, RoundMenu
        except Exception:
            if hasattr(self, "_btn_symbols"):
                self._btn_symbols.setEnabled(False)
            return

        from inkscape_wps.ui.math_symbols import SYMBOL_GROUPS

        root = RoundMenu("插入符号", self)
        for group_title, entries in SYMBOL_GROUPS:
            sub = RoundMenu(group_title, self)
            for label, ch in entries:
                act = Action(text=f"{label}\t{ch}")
                act.triggered.connect(lambda _=False, c=ch: self._insert_symbol_char(c))
                sub.addAction(act)
            root.addMenu(sub)
        self._symbol_menu = root
        if getattr(self, "_m_edit_menu", None) is not None:
            self._m_edit_menu.addSeparator()
            self._m_edit_menu.addMenu(root)

    def _on_symbol_button_clicked(self) -> None:
        m = getattr(self, "_symbol_menu", None)
        if m is None:
            InfoBar.warning("符号", "符号菜单未初始化。", parent=self, position=InfoBarPosition.TOP)
            return
        btn = self._btn_symbols
        gp = btn.mapToGlobal(btn.rect().bottomLeft())
        m.exec_(gp)

    def _insert_symbol_char(self, ch: str) -> None:
        from inkscape_wps.ui.math_symbols import insert_unicode_at_caret

        e = self._active_text_edit()
        if e is None:
            InfoBar.warning(
                "符号",
                "请切换到「文字」或「演示」页后再插入。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        if not insert_unicode_at_caret(e, ch):
            InfoBar.warning(
                "符号",
                "当前编辑器不支持插入。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        self._refresh_preview()

    def _find_next(self, needle: str) -> bool:
        if self._current_page_id() == "table":
            return self._table_editor.find_next_in_table(needle, include_current=False)
        e = self._active_text_edit()
        if e is None:
            InfoBar.warning(
                "查找",
                "当前页面不支持查找。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return False
        if not needle:
            InfoBar.warning(
                "查找",
                "请输入要查找的文本。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return False
        if hasattr(e, "find") and e.find(needle):
            return True
        if hasattr(e, "move_caret"):
            e.move_caret(0, keep_selection=False)
            return bool(e.find(needle))
        c = e.textCursor()
        c.movePosition(QTextCursor.Start)
        e.setTextCursor(c)
        return bool(e.find(needle))

    def _find_next_from_box(self) -> None:
        q = self._find_edit.text().strip() if hasattr(self, "_find_edit") else ""
        ok = self._find_next(q)
        if not ok and q:
            if self._current_page_id() == "table":
                InfoBar.info(
                    "查找",
                    "已到表格末尾，未找到更多匹配。",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
            else:
                InfoBar.info(
                    "查找",
                    "已到文档末尾，未找到更多匹配。",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )

    def _replace_current_from_box(self) -> None:
        if self._current_page_id() == "table":
            q = self._find_edit.text().strip() if hasattr(self, "_find_edit") else ""
            rep = self._replace_edit.text() if hasattr(self, "_replace_edit") else ""
            if not q:
                InfoBar.warning(
                    "替换",
                    "请输入要查找的文本。",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
                return
            ok = self._table_editor.replace_first_in_current_cell(q, rep)
            if not ok:
                found = self._table_editor.find_next_in_table(q, include_current=False)
                if found:
                    ok = self._table_editor.replace_first_in_current_cell(q, rep)
            if not ok:
                InfoBar.info("替换", "未找到匹配项。", parent=self, position=InfoBarPosition.TOP)
                return
            InfoBar.success("替换", "已替换当前匹配。", parent=self, position=InfoBarPosition.TOP)
            return

        e = self._active_text_edit()
        if e is None:
            InfoBar.warning(
                "替换",
                "当前页面不支持替换。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        q = self._find_edit.text().strip() if hasattr(self, "_find_edit") else ""
        rep = self._replace_edit.text() if hasattr(self, "_replace_edit") else ""
        if not q:
            InfoBar.warning(
                "替换",
                "请输入要查找的文本。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        if hasattr(e, "selected_text"):
            selected = e.selected_text()
        else:
            c = e.textCursor()
            selected = c.selectedText() if c.hasSelection() else ""
        if selected != q and not self._find_next(q):
            InfoBar.info("替换", "未找到匹配项。", parent=self, position=InfoBarPosition.TOP)
            return
        if hasattr(e, "replace_selection"):
            e.replace_selection(rep)
        else:
            c = e.textCursor()
            c.insertText(rep)
        InfoBar.success("替换", "已替换当前匹配。", parent=self, position=InfoBarPosition.TOP)

    def _replace_all_from_box(self) -> None:
        if self._current_page_id() == "table":
            q = self._find_edit.text().strip() if hasattr(self, "_find_edit") else ""
            rep = self._replace_edit.text() if hasattr(self, "_replace_edit") else ""
            if not q:
                InfoBar.warning(
                    "全部替换",
                    "请输入要查找的文本。",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
                return
            n = self._table_editor.replace_all_in_table(q, rep)
            InfoBar.success(
                "全部替换",
                f"已替换 {n} 处。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return

        e = self._active_text_edit()
        if e is None:
            InfoBar.warning(
                "全部替换",
                "当前页面不支持替换。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        q = self._find_edit.text().strip() if hasattr(self, "_find_edit") else ""
        rep = self._replace_edit.text() if hasattr(self, "_replace_edit") else ""
        if not q:
            InfoBar.warning(
                "全部替换",
                "请输入要查找的文本。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        if hasattr(e, "move_caret"):
            e.move_caret(0, keep_selection=False)
        else:
            c = e.textCursor()
            c.movePosition(QTextCursor.Start)
            e.setTextCursor(c)
        n = 0
        while e.find(q):
            if hasattr(e, "replace_selection"):
                e.replace_selection(rep)
            else:
                c = e.textCursor()
                c.insertText(rep)
            n += 1
        InfoBar.success("全部替换", f"已替换 {n} 处。", parent=self, position=InfoBarPosition.TOP)

    def _update_action_states(self) -> None:
        # 文件类动作
        if hasattr(self, "_act_save"):
            self._act_save.setEnabled(self._project_path is not None)
        if hasattr(self, "_act_save_as"):
            self._act_save_as.setEnabled(True)
        if hasattr(self, "_act_export"):
            self._act_export.setEnabled(True)
        self._refresh_export_action_states()

        # 设备类动作
        connected = self._grbl is not None
        if hasattr(self, "_act_send"):
            self._act_send.setEnabled(connected)
        if hasattr(self, "_act_send_pause"):
            self._act_send_pause.setEnabled(connected)
        if hasattr(self, "_act_paper_flow"):
            self._act_paper_flow.setEnabled(connected)

        # 最近文件菜单 / Backstage 列表
        if hasattr(self, "_recent_menu"):
            self._rebuild_recent_menu()
        if hasattr(self, "_backstage_recent"):
            self._refresh_backstage_recent_list()

    def _refresh_export_action_states(self) -> None:
        pid = self._current_content_page_id()
        content_label = self._content_mode_label(pid)
        can_docx = pid in ("word", "slides", "table")
        can_xlsx = pid == "table"
        can_pptx = pid == "slides"
        can_md = pid in ("word", "slides", "table")

        if hasattr(self, "_act_export_docx"):
            self._act_export_docx.setEnabled(can_docx)
        if hasattr(self, "_act_export_xlsx"):
            self._act_export_xlsx.setEnabled(can_xlsx)
            self._act_export_xlsx.setToolTip(
                "当前来源为表格，可导出 XLSX。" if can_xlsx else f"XLSX 仅支持表格；当前来源：{content_label}。"
            )
        if hasattr(self, "_act_export_pptx"):
            self._act_export_pptx.setEnabled(can_pptx)
            self._act_export_pptx.setToolTip(
                "当前来源为演示，可导出 PPTX。"
                if can_pptx
                else f"PPTX 仅支持演示；当前来源：{content_label}。"
            )
        if hasattr(self, "_act_export_md"):
            self._act_export_md.setEnabled(can_md)

        if hasattr(self, "_btn_export_docx"):
            self._btn_export_docx.setEnabled(can_docx)
        if hasattr(self, "_btn_export_xlsx"):
            self._btn_export_xlsx.setEnabled(can_xlsx)
            self._btn_export_xlsx.setToolTip(
                "当前来源为表格，可导出 XLSX。" if can_xlsx else f"请先切到表格；当前来源：{content_label}。"
            )
        if hasattr(self, "_btn_export_pptx"):
            self._btn_export_pptx.setEnabled(can_pptx)
            self._btn_export_pptx.setToolTip(
                "当前来源为演示，可导出 PPTX。" if can_pptx else f"请先切到演示；当前来源：{content_label}。"
            )
        if hasattr(self, "_btn_export_md"):
            self._btn_export_md.setEnabled(can_md)
        if hasattr(self, "_btn_export_gcode"):
            self._btn_export_gcode.setEnabled(True)
        if hasattr(self, "_export_hint"):
            self._export_hint.setText(
                "会根据当前内容来源导出对应格式。"
                f" 当前来源：{content_label}；"
                f" DOCX：可用；XLSX：{'可用' if can_xlsx else '仅表格'}；"
                f" PPTX：{'可用' if can_pptx else '仅演示'}。"
            )
        self._refresh_undo_redo_menu_state()

    def _update_status_line(self) -> None:
        try:
            cur = self.stackedWidget.currentWidget()
            cur_name = cur.objectName() if cur is not None else ""
        except Exception:
            cur_name = ""
        page = {
            "file": "文件",
            "home": "开始",
            "word": "文字",
            "table": "表格",
            "slides": "演示",
            "device": "设备",
            "help": "帮助",
        }.get(cur_name, "开始")
        if page in ("文字", "表格", "演示"):
            self._last_active_mode = page
        content_pid = self._current_content_page_id()
        content_label = self._content_mode_label(content_pid)
        snap = self._machine_monitor.snapshot
        if self._grbl is not None:
            is_tcp = str(getattr(self._cfg, "connection_mode", "serial")) == "tcp"
            conn_mode = "Wi-Fi" if is_tcp else "串口"
            conn = f"{conn_mode}已连接/{snap.state}"
        else:
            conn = "未连接"
        proj = self._project_path.name if self._project_path is not None else "未保存"
        extra = ""
        content_extra = self._status_line_content_extra(content_pid)
        glyph_hint = self._glyph_status_hint(content_pid)
        if cur_name in ("word", "table", "slides"):
            if content_extra:
                extra = f"   {content_extra}"
            if glyph_hint:
                extra += f"   {glyph_hint}"
        else:
            extra = f"   预览来源：{content_label}"
            if content_extra:
                extra += f"   {content_extra}"
            if glyph_hint:
                extra += f"   {glyph_hint}"
        runtime = ""
        if self._grbl is not None:
            if snap.rx_free >= 0:
                runtime += f"   RX：{snap.rx_free}"
            if snap.mpos != (0.0, 0.0, 0.0):
                runtime += f"   MPos：X{snap.mpos[0]:.2f} Y{snap.mpos[1]:.2f} Z{snap.mpos[2]:.2f}"
            if snap.last_alarm:
                runtime += f"   告警：{snap.last_alarm}"
        status_text = (
            f"文档：{self._doc_title}（{proj}）   页面：{page}   "
            f"预览：{int(self._preview_zoom * 100)}%   连接：{conn}{extra}{runtime}"
        )
        health_level, _health_color, _health_badge, _health_items = self._health_status_payload()
        links: list[str] = []
        tooltip_parts: list[str] = []
        if glyph_hint.startswith("缺字形："):
            links.append(
                '<a href="missing-glyphs" style="color:#217346;text-decoration:none;">查看缺失字符</a>'
            )
            tooltip_parts.append("当前内容存在未覆盖字符，可先查看缺失字符。")
        if health_level in ("warn", "error"):
            links.append(
                '<a href="preflight-report" style="color:#b06a12;text-decoration:none;">开始检查</a>'
            )
            tooltip_parts.append("当前状态建议先做导出/发送前检查。")
        if links:
            self._status_line.setText(f"{html_module.escape(status_text)}   " + "   ".join(links))
            self._status_line.setToolTip(" ".join(tooltip_parts))
        else:
            self._status_line.setText(html_module.escape(status_text))
            self._status_line.setToolTip("")
        self._refresh_device_summary()
        self._refresh_diagnostic_summary()
        self._refresh_backstage_info()

    def _refresh_device_summary(self) -> None:
        snap = self._machine_monitor.snapshot
        if hasattr(self, "_dev_state"):
            self._dev_state.setText(str(snap.state))
            self._dev_job.setText(str(self._job_state_text))
            self._dev_progress.setText(f"{self._job_progress[0]}/{self._job_progress[1]}")
            self._dev_pos.setText(f"X{snap.mpos[0]:.3f} Y{snap.mpos[1]:.3f} Z{snap.mpos[2]:.3f}")
            planner = "-" if snap.planner_free < 0 else str(snap.planner_free)
            rx = "-" if snap.rx_free < 0 else str(snap.rx_free)
            self._dev_buf.setText(f"Planner {planner} / RX {rx}")
            self._dev_alarm.setText(str(snap.last_alarm or "-"))
            if hasattr(self, "_dev_connection_hint"):
                if self._grbl is None:
                    self._dev_connection_hint.setText(
                        "当前未连接设备。先在左侧选择串口或 TCP，再执行连接和小范围试写。"
                    )
                else:
                    is_tcp = str(getattr(self._cfg, "connection_mode", "serial")) == "tcp"
                    mode = "Wi-Fi / TCP" if is_tcp else "串口 / 蓝牙"
                    self._dev_connection_hint.setText(
                        f"当前通过 {mode} 连接，设备返回状态为 {snap.state}。"
                        "发送程序前建议先确认坐标、抬落笔和 RX 预算。"
                    )

    def _set_job_status(
        self,
        text: str,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        self._job_state_text = text
        if current is not None and total is not None:
            self._job_progress = (int(current), int(total))
        self._update_status_line()

    def _job_progress_callback(self, current: int, total: int) -> None:
        self._set_job_status("运行中", current, total)
        QApplication.processEvents()

    def _poll_grbl_status(self) -> None:
        if self._grbl is None:
            return
        try:
            self._grbl.send_realtime_status_request()
        except Exception:
            return

    def _recent_store_path(self) -> Path:
        return Path.home() / ".config" / "inkscape-wps" / "recent_projects.json"

    def _load_recent_projects(self) -> List[str]:
        p = self._recent_store_path()
        try:
            if p.is_file():
                d = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(d, list):
                    return [str(x) for x in d if isinstance(x, (str,))]
        except Exception:
            pass
        return []

    def _save_recent_projects(self) -> None:
        p = self._recent_store_path()
        try:
            payload = json.dumps(
                self._recent_projects[:15],
                ensure_ascii=False,
                indent=2,
            )
            write_text_atomic(p, payload)
        except Exception:
            pass

    def _push_recent(self, path: Path) -> None:
        s = str(path.expanduser().resolve())
        self._recent_projects = [x for x in self._recent_projects if x != s]
        self._recent_projects.insert(0, s)
        self._recent_projects = self._recent_projects[:15]
        self._save_recent_projects()
        self._update_action_states()

    def _rebuild_recent_menu(self) -> None:
        # 重新生成“最近打开”菜单项
        try:
            self._recent_menu.clear()
        except Exception:
            return
        if not self._recent_projects:
            a = Action(text="（暂无）")
            a.setEnabled(False)
            self._recent_menu.addAction(a)
            return
        for s in self._recent_projects[:10]:
            p = Path(s)
            label = p.name if p.name else s
            act = Action(text=label)

            def _mk(s=s) -> None:
                if Path(s).is_file():
                    self._open_project_path(Path(s))
                else:
                    InfoBar.warning(
                        "最近打开",
                        "文件不存在，已从列表移除。",
                        parent=self,
                        position=InfoBarPosition.TOP,
                    )
                    self._recent_projects = [x for x in self._recent_projects if x != s]
                    self._save_recent_projects()
                    self._update_action_states()

            act.triggered.connect(_mk)
            self._recent_menu.addAction(act)

        self._recent_menu.addSeparator()
        clr = Action(text="清空最近打开")
        clr.triggered.connect(self._clear_recent_projects)
        self._recent_menu.addAction(clr)

    def _clear_recent_projects(self) -> None:
        self._recent_projects = []
        self._save_recent_projects()
        self._update_action_states()

    def _show_backstage(self) -> None:
        try:
            self.switchTo(self._file_page)
            if self._backstage_nav.count() > 1:
                self._backstage_nav.setCurrentRow(1)
            self._refresh_backstage_info()
        except Exception:
            pass

    def _apply_backstage_style(self) -> None:
        if not hasattr(self, "_file_page"):
            return
        self._file_page.setStyleSheet(
            """
            QWidget#file {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f7fafc, stop:1 #eef3f7);
            }
            QListWidget#backstageNav {
                background: rgba(255, 255, 255, 0.72);
                border: 1px solid #d6dee6;
                border-radius: 14px;
                padding: 8px;
                outline: none;
            }
            QListWidget#backstageNav::item {
                color: #1f2328;
                padding: 10px 12px;
                border-radius: 9px;
                margin: 2px 0;
            }
            QListWidget#backstageNav::item:selected {
                background: #e8f5ec;
                color: #0f3d26;
                font-weight: 700;
            }
            QListWidget#backstageNav::item:hover {
                background: rgba(237, 243, 247, 0.92);
            }
            QWidget#backstageCardsHost {
                background: transparent;
            }
            QWidget#backstageInfoCard {
                background: rgba(255, 255, 255, 0.92);
                border: 1px solid #d8e0e7;
                border-radius: 14px;
            }
            QLabel#backstageInfoCardTitle {
                color: #71808f;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#backstageInfoCardValue {
                color: #1f2f3d;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#backstageInfoLine {
                color: #44505c;
                background: rgba(255, 255, 255, 0.74);
                border: 1px solid #d9e1e8;
                border-radius: 10px;
                padding: 10px 12px;
            }
            QListWidget#backstageRecentList {
                background: rgba(255, 255, 255, 0.78);
                border: 1px solid #d6dee6;
                border-radius: 14px;
                outline: none;
            }
            QListWidget#backstageRecentList::item {
                border-radius: 10px;
                padding: 10px 12px;
                margin: 4px 5px;
                color: #1f2328;
            }
            QListWidget#backstageRecentList::item:selected {
                background: #eaf4ff;
                color: #123a62;
            }
            QListWidget#backstageRecentList::item:hover {
                background: #f3f8fd;
            }
            QLabel#backstageDetailName {
                color: #1f2f3d;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#backstageDetailMeta {
                color: #66727e;
                font-size: 12px;
            }
            QLabel#homeQuickBadge {
                color: #0f5a34;
                background: #e7f4eb;
                border: 1px solid #cce7d5;
                border-radius: 999px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            """
        )

    def _on_backstage_nav_item_changed(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem],
    ) -> None:
        del previous
        if current is None:
            return
        idx = current.data(Qt.UserRole)
        if not isinstance(idx, int):
            return
        if hasattr(self, "_backstage_stack"):
            self._backstage_stack.setCurrentIndex(max(0, min(5, int(idx))))
        self._refresh_backstage_info()

    def _current_mode_label(self) -> str:
        try:
            cur = self.stackedWidget.currentWidget()
            cur_name = cur.objectName() if cur is not None else ""
        except Exception:
            cur_name = ""
        mode = {
            "file": "文件后台",
            "home": "开始",
            "word": "文字",
            "table": "表格",
            "slides": "演示",
            "device": "设备",
            "help": "帮助",
        }.get(cur_name, "开始")
        if mode == "文件后台":
            return self._last_active_mode
        return mode

    def _estimate_doc_stats(self) -> tuple[int, int]:
        if not hasattr(self, "_word_editor"):
            return 0, 1
        mode = self._current_mode_label()
        if mode in ("文字", "开始", "文件后台"):
            text = self._word_editor.toPlainText()
            words = _count_visible_chars(text)
            pages = max(1, (words + 799) // 800)
            return words, pages
        if mode == "演示":
            words = 0
            for s in self._presentation_editor.slides_storage():
                if (s or "").lstrip().startswith("<"):
                    d = QTextDocument()
                    d.setHtml(s or "")
                    t = document_plain_text_skip_strike(d)
                else:
                    t = s or ""
                words += _count_visible_chars(t)
            pages = max(1, self._presentation_editor.slide_count())
            return words, pages
        if mode == "表格":
            blob = self._table_editor.to_project_blob()
            words = 0
            filled = 0
            for row in blob.get("cells") or []:
                for cell in row:
                    t = str(cell.get("text", "")).strip()
                    if t:
                        filled += 1
                        words += _count_visible_chars(t)
            pages = max(1, (filled + 39) // 40)
            return words, pages
        return 0, 1

    def _refresh_backstage_info(self) -> None:
        if not hasattr(self, "_backstage_info_doc"):
            return
        words, pages = self._estimate_doc_stats()
        mode = self._current_mode_label()
        proj = str(self._project_path) if self._project_path is not None else "未保存为工程文件"
        self._backstage_info_doc.setText(f"文档：{self._doc_title}")
        self._backstage_info_proj.setText(f"工程：{proj}")
        self._backstage_info_soffice.setText(f"导出增强：{self._soffice_ready_hint()}")
        if hasattr(self, "_backstage_card_words"):
            self._backstage_card_words.setText(str(words))
        if hasattr(self, "_backstage_card_pages"):
            self._backstage_card_pages.setText(str(pages))
        if hasattr(self, "_backstage_card_saved"):
            self._backstage_card_saved.setText(self._last_saved_at or "未保存")
        if hasattr(self, "_backstage_card_mode"):
            self._backstage_card_mode.setText(mode)
        if hasattr(self, "_backstage_cfg_path"):
            self._backstage_cfg_path.setText(f"配置文件：{self._cfg_path}")

    def _refresh_backstage_recent_list(self) -> None:
        self._backstage_recent.clear()
        if not self._recent_projects:
            it = QListWidgetItem("还没有最近文件\n打开或导入文档后，这里会显示最近使用记录。")
            it.setData(Qt.UserRole, "")
            it.setSizeHint(QSize(it.sizeHint().width(), 64))
            self._backstage_recent.addItem(it)
            self._on_backstage_recent_selection_changed(it, None)
            return
        for s in self._recent_projects[:20]:
            p = Path(s)
            ts = "未知时间"
            try:
                ts = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
            title = p.name if p.name else str(p)
            subtitle = f"{s}\n最近修改：{ts}"
            it = QListWidgetItem(f"{title}\n{subtitle}")
            it.setData(Qt.UserRole, s)
            sz = it.sizeHint()
            it.setSizeHint(QSize(sz.width(), max(sz.height(), 54)))
            self._backstage_recent.addItem(it)
        if self._backstage_recent.count() > 0:
            self._backstage_recent.setCurrentRow(0)

    def _open_backstage_recent_item(self, item: QListWidgetItem) -> None:
        s = item.data(Qt.UserRole)
        if not isinstance(s, str) or not s:
            return
        p = Path(s)
        if not p.is_file():
            self._notify_warning("最近打开", "文件不存在，已从最近列表移除。")
            self._recent_projects = [x for x in self._recent_projects if x != s]
            self._save_recent_projects()
            self._update_action_states()
            self._set_backstage_detail_empty("该记录对应的文件已不存在。")
            return
        kind = detect_office_kind(p)
        if kind in ("docx", "xlsx", "pptx", "md", "wps", "et", "dps"):
            self._open_office_or_wps_file(p)
        else:
            self._open_project_path(p)

    def _on_backstage_recent_selection_changed(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem],
    ) -> None:
        del previous
        s = current.data(Qt.UserRole) if current is not None else ""
        if not isinstance(s, str) or not s:
            self._set_backstage_detail_empty("从左侧列表选择一个文件查看详情。")
            return
        p = Path(s)
        kind = detect_office_kind(p)
        k = describe_document_kind(kind)
        exists = p.is_file()
        self._backstage_detail_name.setText(p.name)
        status = "可打开" if exists else "文件缺失"
        self._backstage_detail_type.setText(f"类型：{k}   |   状态：{status}")
        self._backstage_detail_path.setText(f"路径：{s}")
        self._backstage_btn_open.setEnabled(exists)
        self._backstage_btn_open.setText("打开选中文件" if exists else "文件不存在")

    def _open_backstage_current(self) -> None:
        it = self._backstage_recent.currentItem()
        if it is not None:
            self._open_backstage_recent_item(it)

    # FluentWindow 没有 QMainWindow 的 addToolBar/statusBar，这里把动作放在页面内按钮栏，
    # 并用 InfoBar 替代状态栏提示。

    # ---------- 文件 ----------
    def _repo_root_file(self, name: str) -> Path:
        return Path(__file__).resolve().parents[2] / name

    def _open_spec_document(self) -> None:
        p = self._repo_root_file("SPEC.md")
        if p.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.resolve())))

    def _open_ai_prompts_document(self) -> None:
        p = self._repo_root_file("AI_PROMPTS.md")
        if p.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.resolve())))

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开文件（工程/Office/WPS/Markdown）",
            str(Path.home()),
            "工程 (*.inkwps.json *.json);;WPS/Office (*.docx *.xlsx *.pptx *.wps *.et *.dps);;"
            "Markdown (*.md *.markdown);;所有文件 (*)",
        )
        if not path:
            return
        p = Path(path)
        kind = detect_office_kind(p)
        if kind in ("docx", "xlsx", "pptx", "md", "wps", "et", "dps"):
            self._open_office_or_wps_file(p)
            return
        self._open_project_path(p)

    def _save_project(self) -> None:
        if self._project_path is None:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "另存工程为",
                str(Path.home()),
                "inkscape-wps 工程 (*.inkwps.json);;JSON (*.json);;所有文件 (*)",
            )
            if not path:
                return
            self._project_path = Path(path)
            self._doc_title = self._project_path.stem
        try:
            save_project_file(
                self._project_path,
                title=self._doc_title,
                word_html=self._word_editor.toHtml(),
                word_plain_text=self._word_editor.toPlainText(),
                table_blob=self._capture_table_blob(),
                slides=self._capture_slides_storage(),
                slides_master=self._presentation_editor.master_storage(),
                sketch_blob=self._capture_sketch_blob(),
                insert_vector=self._capture_insert_vector_blob(),
            )
        except Exception as e:
            self._notify_error("保存失败", f"{self._project_path.name} 未能写入：{e}")
            return
        self._last_saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._apply_window_title()
        self._notify_success("已保存", f"{self._project_path.name} 已保存，可放心继续编辑。")
        self._update_action_states()
        self._update_status_line()

    def _save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "另存工程为",
            str(Path.home()),
            "inkscape-wps 工程 (*.inkwps.json);;JSON (*.json);;所有文件 (*)",
        )
        if not path:
            return
        self._project_path = Path(path)
        self._doc_title = self._project_path.stem
        self._save_project()

    def _new_project(self) -> None:
        self._project_path = None
        self._doc_title = "未命名文档"
        self._last_saved_at = None
        self._nonword_undo_restoring = True
        try:
            self._word_editor.clear()
            self._table_editor.clear_all()
            self._presentation_editor.clear_all()
            self._sketch_paths.clear()
            self._insert_paths_base.clear()
            self._insert_vector_scale = 1.0
            self._insert_vector_dx_mm = 0.0
            self._insert_vector_dy_mm = 0.0
        finally:
            self._nonword_undo_restoring = False
        self._reset_nonword_undo_anchor()
        self._refresh_preview()
        self._apply_window_title()
        self._update_action_states()
        self._update_status_line()

    def _open_project_path(self, path: Path) -> None:
        try:
            d = load_project_file(path)
        except Exception as e:
            self._notify_error("打开失败", f"{path.name} 无法打开：{e}")
            return
        self._project_path = path
        self._doc_title = str(d.get("title") or self._project_path.stem)
        try:
            self._last_saved_at = datetime.fromtimestamp(path.stat().st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except OSError:
            _logger.debug("读取工程文件 mtime 失败：%s", path, exc_info=True)
            self._last_saved_at = None
        self._nonword_undo_restoring = True
        try:
            if "word_plain_text" in d:
                self._word_editor.setPlainText(str(d.get("word_plain_text", "")))
            else:
                self._word_editor.setHtml(str(d.get("word_html", "")))
            self._apply_table_blob(d.get("table") if isinstance(d.get("table"), dict) else {})
            self._apply_slides_storage(d.get("slides") if isinstance(d.get("slides"), list) else [])
            # 母版页眉/页脚（P4-B-3），旧工程无该字段时保持空
            try:
                self._presentation_editor.load_master_storage(d.get("slides_master"))
            except Exception:
                pass
            self._apply_loaded_paths(d)
        finally:
            self._nonword_undo_restoring = False
        self._reset_nonword_undo_anchor()
        self._refresh_preview()
        self._apply_window_title()
        self._push_recent(self._project_path)
        self._update_action_states()
        self._update_status_line()
        self._notify_success(
            "已打开工程",
            f"{self._project_path.name} 已载入，可继续编辑、预览或导出。",
        )

    def _open_office_or_wps_file(self, path: Path) -> None:
        p = path
        target_mode = "文字"
        try:
            p = try_convert_wps_private_to_office(p)
            kind = detect_office_kind(p)
            if kind == "docx":
                self._new_project()
                self._doc_title = p.stem
                self._word_editor.setHtml(import_docx_to_html(p))
                self._safe_switch_to(self._word_page, "文字")
                target_mode = "文字"
            elif kind == "xlsx":
                self._new_project()
                self._doc_title = p.stem
                self._apply_table_blob(import_xlsx_to_table_blob(p))
                self._safe_switch_to(self._table_page, "表格")
                target_mode = "表格"
            elif kind == "pptx":
                self._new_project()
                self._doc_title = p.stem
                slides = import_pptx_to_slides(p)
                self._apply_slides_storage(slides)
                self._safe_switch_to(self._slides_page, "演示")
                target_mode = "演示"
            elif kind == "md":
                self._new_project()
                self._doc_title = p.stem
                slides_md = import_markdown_file_to_slides_plain(p)
                if slides_md is not None:
                    self._apply_slides_storage(slides_md)
                    self._safe_switch_to(self._slides_page, "演示")
                    target_mode = "演示"
                else:
                    self._word_editor.setPlainText(import_markdown_to_plain(p))
                    self._safe_switch_to(self._word_page, "文字")
                    target_mode = "文字"
            else:
                raise OfficeImportError("不支持的文件类型。")
        except OfficeImportError as e:
            self._notify_error("导入失败", f"{p.name} 无法导入：{e}")
            return
        except Exception as e:
            self._notify_error("导入失败", f"{p.name} 导入时发生异常：{e}")
            return

        # 作为“未保存工程”的临时内容导入
        self._project_path = None
        try:
            self._last_saved_at = datetime.fromtimestamp(p.stat().st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except OSError:
            _logger.debug("读取导入文件 mtime 失败：%s", p, exc_info=True)
            self._last_saved_at = None
        self._apply_window_title()
        self._reset_nonword_undo_anchor()
        self._refresh_preview()
        self._push_recent(p)
        self._update_action_states()
        self._update_status_line()
        self._notify_success(
            "已导入",
            f"{describe_document_kind(kind)} {p.name} 已载入到“{target_mode}”页。",
        )

    def _apply_loaded_paths(self, d: dict) -> None:
        self._sketch_paths.clear()
        sk = d.get("sketch")
        if isinstance(sk, dict) and sk.get("paths"):
            try:
                self._sketch_paths.extend(deserialize_vector_paths(sk["paths"]))
            except (TypeError, ValueError, KeyError) as e:
                _logger.warning("工程内 sketch.paths 反序列化失败，已跳过：%s", e)
        self._insert_paths_base.clear()
        self._insert_vector_scale = 1.0
        self._insert_vector_dx_mm = 0.0
        self._insert_vector_dy_mm = 0.0
        iv = d.get("insert_vector")
        if isinstance(iv, dict) and iv.get("paths"):
            try:
                self._insert_paths_base.extend(deserialize_vector_paths(iv["paths"]))
                self._insert_vector_scale = float(iv.get("scale", 1.0))
                self._insert_vector_dx_mm = float(iv.get("dx_mm", 0.0))
                self._insert_vector_dy_mm = float(iv.get("dy_mm", 0.0))
            except Exception:
                pass

    def _scaled_insert_paths(self) -> List[VectorPath]:
        """与 PyQt6 主窗一致：绕插入矢量包围盒中心缩放/平移，工程文件可互换。"""
        if not self._insert_paths_base:
            return []
        s = float(self._insert_vector_scale)
        dx = float(self._insert_vector_dx_mm)
        dy = float(self._insert_vector_dy_mm)
        bb = paths_bounding_box(self._insert_paths_base)
        if bb[0] >= bb[2] or bb[1] >= bb[3]:
            cx, cy = 0.0, 0.0
        else:
            cx = (bb[0] + bb[2]) / 2.0
            cy = (bb[1] + bb[3]) / 2.0
        out: List[VectorPath] = []
        for vp in self._insert_paths_base:
            pts = tuple(
                Point(
                    cx + (p.x - cx) * s + dx,
                    cy + (p.y - cy) * s + dy,
                )
                for p in vp.points
            )
            out.append(VectorPath(pts, pen_down=vp.pen_down))
        return out

    def _preview_paths(self) -> List[VectorPath]:
        # 非编辑页沿用最近一次编辑中的内容页，避免预览悄悄退回到「文字」。
        content_pid = self._current_content_page_id()
        mm_per_pt = float(self._cfg.mm_per_pt)
        if content_pid == "table":
            base = self._table_paths()
        elif content_pid == "slides":
            base = self._slides_paths()
        else:
            text_lines = stroke_editor_to_layout_lines(self._word_editor, self._cfg)
            base = map_document_lines(self._mapper, text_lines, mm_per_pt=mm_per_pt)

        return list(base) + list(self._sketch_paths) + list(self._scaled_insert_paths())

    def _work_paths(self) -> List[VectorPath]:
        """文档坐标路径 → 最近邻排序 → 机床/work 坐标（镜像/缩放/平移），与 PyQt6 主窗一致。"""
        combined = list(self._preview_paths())
        ordered = order_paths_nearest_neighbor(combined)
        return transform_paths(ordered, self._cfg)

    def _table_paths(self) -> List[VectorPath]:
        """表格：单元格 HTML → LayoutLine → Hershey（与 PyQt6 WpsTableEditor 一致）。"""
        mm_per_px = max(
            0.05,
            self._cfg.page_width_mm / max(1, int(self._preview.viewport().width())),
        )
        lines = self._table_editor.to_layout_lines(mm_per_px)
        text_paths = map_document_lines(self._mapper, lines, mm_per_pt=float(self._cfg.mm_per_pt))
        return list(text_paths) + list(self._table_editor.to_grid_paths())

    def _slides_paths(self) -> List[VectorPath]:
        """演示：多页离屏 QTextEdit 排版，与 PyQt6 WpsPresentationEditor 一致。"""
        mm_per_pt = float(self._cfg.mm_per_pt)

        def _mm_px(ed) -> float:
            return max(0.05, self._cfg.page_width_mm / max(1, ed.viewport().width()))

        lines = self._presentation_editor.to_layout_lines_all_slides(mm_per_px_resolver=_mm_px)
        return map_document_lines(self._mapper, lines, mm_per_pt=mm_per_pt)

    def _on_stroke_line_spacing_changed(self, value: float) -> None:
        if hasattr(self, "_word_editor"):
            self._word_editor.set_line_spacing(float(value))

    def _preview_zoom_step(self, factor: float) -> None:
        self._preview_zoom = max(0.1, min(5.0, float(self._preview_zoom) * float(factor)))
        self._refresh_preview()
        self._update_status_line()

    def _preview_zoom_reset_100(self) -> None:
        self._preview_zoom = 1.0
        self._refresh_preview()
        self._update_status_line()

    def _on_preview_zoom_changed(self, zoom: float) -> None:
        """把预览视图内部缩放同步回状态栏显示。"""
        self._preview_zoom = max(0.1, min(5.0, float(zoom)))
        self._update_status_line()

    def _install_editor_context_menus(self) -> None:
        """文字 / 演示：编辑右键；表格：见 _open_table_context_menu。"""
        self._word_editor.setContextMenuPolicy(Qt.CustomContextMenu)
        self._word_editor.customContextMenuRequested.connect(
            lambda pos: self._open_wps_edit_context_menu(self._word_editor.mapToGlobal(pos))
        )
        tw = self._table_editor.table_widget()
        tw.setContextMenuPolicy(Qt.CustomContextMenu)
        tw.customContextMenuRequested.connect(
            lambda pos: self._open_table_context_menu(tw.mapToGlobal(pos))
        )
        te = self._presentation_editor.slide_editor()
        te.setContextMenuPolicy(Qt.CustomContextMenu)
        te.customContextMenuRequested.connect(
            lambda pos: self._open_slide_rich_context_menu(te.mapToGlobal(pos))
        )
        te.installEventFilter(self)
        sl = self._presentation_editor.slide_list_widget()
        sl.setContextMenuPolicy(Qt.CustomContextMenu)
        sl.customContextMenuRequested.connect(
            lambda pos: self._open_slides_list_context_menu(sl.mapToGlobal(pos))
        )
        sl.installEventFilter(self)

    def _clipboard_has_text(self) -> bool:
        try:
            md = QApplication.clipboard().mimeData()
            return bool(md is not None and md.hasText() and (md.text() or ""))
        except Exception:
            return False

    def _has_selection_for_current_edit_context(self) -> bool:
        if QApplication.focusWidget() is self._word_editor:
            return bool(self._word_editor.selected_text())
        inner = self._inner_clipboard_text_widget()
        if inner is not None:
            if hasattr(inner, "hasSelectedText"):
                try:
                    return bool(inner.hasSelectedText())
                except Exception:
                    return False
            if hasattr(inner, "textCursor"):
                try:
                    return bool(inner.textCursor().hasSelection())
                except Exception:
                    return False
        pid = self._current_page_id()
        if pid == "table":
            item = self._table_editor._current_cell_item()  # noqa: SLF001
            return bool(item is not None and (item.text() or "").strip())
        if pid == "slides":
            try:
                return bool(self._presentation_editor.slide_editor().textCursor().hasSelection())
            except Exception:
                return False
        return False

    def _can_paste_in_current_edit_context(self) -> bool:
        if not self._clipboard_has_text():
            return False
        if QApplication.focusWidget() is self._word_editor:
            return True
        inner = self._inner_clipboard_text_widget()
        if inner is not None and hasattr(inner, "canPaste"):
            try:
                return bool(inner.canPaste())
            except Exception:
                return True
        return self._current_page_id() in ("table", "slides", "word")

    def _open_slides_list_context_menu(self, global_pos: QPoint) -> None:
        """左侧幻灯片列表：新建/删除（对标 PPT 缩略图区右键）。"""
        try:
            from qfluentwidgets import RoundMenu
        except Exception:
            return
        m = RoundMenu("幻灯片", self)
        a_new = Action(text="新建幻灯片")
        a_new.triggered.connect(self._presentation_editor.add_slide)
        m.addAction(a_new)
        a_dup = Action(text="创建副本")
        a_dup.setToolTip("在当前页后插入一页相同内容")
        a_dup.triggered.connect(self._presentation_editor.duplicate_current_slide)
        m.addAction(a_dup)
        m.addSeparator()
        row = self._presentation_editor.slide_list_widget().currentRow()
        n_slides = self._presentation_editor.slide_count()
        if row < 0:
            row = 0
        a_up = Action(text="上移")
        a_up.setToolTip("与上一张幻灯片交换位置（列表聚焦时 Alt+↑）")
        a_up.triggered.connect(self._presentation_editor.move_current_slide_up)
        a_up.setEnabled(n_slides > 1 and row > 0)
        m.addAction(a_up)
        a_dn = Action(text="下移")
        a_dn.setToolTip("与下一张幻灯片交换位置（列表聚焦时 Alt+↓）")
        a_dn.triggered.connect(self._presentation_editor.move_current_slide_down)
        a_dn.setEnabled(n_slides > 1 and row < n_slides - 1)
        m.addAction(a_dn)
        m.addSeparator()
        a_copy = Action(text="复制幻灯片")
        a_copy.setToolTip("整页复制到应用内剪贴板（与系统 Ctrl+C 无关）")
        a_copy.triggered.connect(self._presentation_editor.copy_slide_to_internal_clipboard)
        m.addAction(a_copy)
        a_paste = Action(text="粘贴幻灯片")
        a_paste.setToolTip("在当前页后插入剪贴板中的整页")
        a_paste.triggered.connect(self._presentation_editor.paste_slide_from_internal_clipboard)
        a_paste.setEnabled(bool(getattr(self._presentation_editor, "_internal_slide_clipboard", None)))
        m.addAction(a_paste)
        m.addSeparator()
        a_del = Action(text="删除当前页")
        a_del.triggered.connect(self._presentation_editor.delete_slide_interactive)
        a_del.setEnabled(n_slides > 1)
        m.addAction(a_del)
        m.exec_(global_pos)

    def _open_preview_context_menu(self, global_pos: QPoint) -> None:
        """路径预览区：缩放与刷新（对标常见 CAD/预览右键）。"""
        try:
            from qfluentwidgets import RoundMenu
        except Exception:
            return
        m = RoundMenu("预览", self)
        a100 = Action(text="缩放到 100%")
        a100.triggered.connect(self._preview_zoom_reset_100)
        m.addAction(a100)
        a_in = Action(text="放大")
        a_in.triggered.connect(lambda: self._preview_zoom_step(1.15))
        m.addAction(a_in)
        a_out = Action(text="缩小")
        a_out.triggered.connect(lambda: self._preview_zoom_step(1.0 / 1.15))
        m.addAction(a_out)
        m.addSeparator()
        a_copy_img = Action(text="复制可见预览为图像")
        a_copy_img.setToolTip("将当前视口内的预览复制到系统剪贴板（与缩放/平移后的画面一致）")
        a_copy_img.triggered.connect(self._preview_copy_visible_to_clipboard)
        m.addAction(a_copy_img)
        a_png = Action(text="导出可见预览为 PNG…")
        a_png.setToolTip("保存当前视口内的预览为 PNG 文件")
        a_png.triggered.connect(self._preview_export_visible_png)
        m.addAction(a_png)
        m.addSeparator()
        a_sync = Action(text="同步滚轮缩放并重新适应")
        a_sync.setToolTip("把滚轮调节的缩放写回状态栏比例，并重新 fit（可消除拖偏后的视图）。")
        a_sync.triggered.connect(self._preview_sync_zoom_and_refit)
        m.addAction(a_sync)
        a_rf = Action(text="刷新预览")
        a_rf.triggered.connect(self._refresh_preview)
        m.addAction(a_rf)
        m.exec_(global_pos)

    def _preview_sync_zoom_and_refit(self) -> None:
        try:
            z = float(getattr(self._preview, "_zoom", self._preview_zoom))
        except (TypeError, ValueError):
            z = self._preview_zoom
        self._preview_zoom = max(0.1, min(5.0, z))
        self._refresh_preview()
        self._update_status_line()

    def _preview_viewport_pixmap(self):
        """抓取预览视口位图；失败返回 (None, 错误说明)。"""
        try:
            pm = self._preview.viewport().grab()
        except Exception as e:
            _logger.warning("预览视口 grab 失败", exc_info=True)
            return None, str(e)
        if pm.isNull():
            return None, "无法抓取预览图像。"
        return pm, None

    def _preview_copy_visible_to_clipboard(self) -> None:
        """将预览视口当前可见画面复制为位图到系统剪贴板。"""
        pm, err = self._preview_viewport_pixmap()
        if pm is None:
            InfoBar.warning("预览", f"复制失败：{err}", parent=self, position=InfoBarPosition.TOP)
            return
        QApplication.clipboard().setPixmap(pm)
        InfoBar.success(
            "预览",
            f"已复制图像到剪贴板（{pm.width()}×{pm.height()} 像素）。",
            parent=self,
            position=InfoBarPosition.TOP,
        )

    def _preview_export_visible_png(self) -> None:
        """将预览视口当前可见画面保存为 PNG 文件。"""
        pm, err = self._preview_viewport_pixmap()
        if pm is None:
            InfoBar.warning("预览", f"导出失败：{err}", parent=self, position=InfoBarPosition.TOP)
            return
        stem = "".join(
            c if c not in '<>:"/\\|?*' else "_" for c in (self._doc_title or "preview").strip()
        )[:120]
        if not stem:
            stem = "preview"
        default_path = str(Path.home() / f"{stem}_preview.png")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出可见预览为 PNG",
            default_path,
            "PNG 图像 (*.png);;所有文件 (*)",
        )
        if not path:
            return
        p = Path(path)
        if p.suffix.lower() != ".png":
            p = p.with_suffix(".png")
        try:
            if not pm.save(str(p), "PNG"):
                raise OSError("QPixmap.save 返回 False")
        except Exception as e:
            _logger.warning("预览 PNG 保存失败", exc_info=True)
            InfoBar.error("导出失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        InfoBar.success(
            "预览",
            f"已导出 {p.name}（{pm.width()}×{pm.height()} 像素）。",
            parent=self,
            position=InfoBarPosition.TOP,
        )

    def _open_wps_edit_context_menu(self, global_pos: QPoint) -> None:
        try:
            from qfluentwidgets import RoundMenu
        except Exception:
            return
        m = RoundMenu("编辑", self)
        self._populate_wps_edit_round_menu(m)
        m.exec_(global_pos)

    def _slide_document_undo(self) -> None:
        self._presentation_editor.slide_editor().undo()
        self._refresh_undo_redo_menu_state()

    def _slide_document_redo(self) -> None:
        self._presentation_editor.slide_editor().redo()
        self._refresh_undo_redo_menu_state()

    def _slide_apply_list_style(self, style: int) -> None:
        """项目符号 / 编号列表（QTextListFormat）。"""
        te = self._presentation_editor.slide_editor()
        cur = te.textCursor()
        cur.beginEditBlock()
        fmt = QTextListFormat()
        fmt.setStyle(style)
        cur.createList(fmt)
        cur.endEditBlock()
        te.setTextCursor(cur)

    def _slide_change_block_indent(self, delta: int) -> None:
        te = self._presentation_editor.slide_editor()
        doc = te.document()
        cur = te.textCursor()
        cur.beginEditBlock()
        if cur.hasSelection():
            start = min(cur.selectionStart(), cur.selectionEnd())
            end = max(cur.selectionStart(), cur.selectionEnd())
            block = doc.findBlock(start)
            while block.isValid() and block.position() <= end:
                bf = block.blockFormat()
                bf.setIndent(max(0, min(32, bf.indent() + delta)))
                c2 = QTextCursor(block)
                c2.setBlockFormat(bf)
                block = block.next()
        else:
            bf = cur.blockFormat()
            bf.setIndent(max(0, min(32, bf.indent() + delta)))
            cur.setBlockFormat(bf)
        cur.endEditBlock()
        te.setTextCursor(cur)

    def _slide_apply_style_preset(self, preset: str) -> None:
        """当前段落应用固定样式（整段字符格式 + 段前后距），写入 HTML，随工程保存。"""
        if self._current_page_id() != "slides":
            return
        te = self._presentation_editor.slide_editor()
        cur = te.textCursor()
        pos = cur.position()
        cur.beginEditBlock()
        cur.select(QTextCursor.BlockUnderCursor)
        cf = QTextCharFormat()
        bf = QTextBlockFormat()
        if preset == "h1":
            cf.setFontPointSize(20.0)
            cf.setFontWeight(QFont.Bold)
            bf.setTopMargin(10.0)
            bf.setBottomMargin(10.0)
        elif preset == "h2":
            cf.setFontPointSize(16.0)
            cf.setFontWeight(QFont.Bold)
            bf.setTopMargin(6.0)
            bf.setBottomMargin(8.0)
        else:
            cf.setFontPointSize(12.0)
            cf.setFontWeight(QFont.Normal)
            bf.setTopMargin(0.0)
            bf.setBottomMargin(6.0)
        cur.mergeCharFormat(cf)
        cur.mergeBlockFormat(bf)
        cur.setPosition(pos)
        cur.endEditBlock()
        te.setTextCursor(cur)
        self._refresh_preview()

    def _slide_revision_handle_delete(self, ke: QKeyEvent) -> bool:
        """修订开启时：Backspace/Delete 改为给字符加删除线。返回 True 表示已消费事件。"""
        if int(ke.modifiers()) & (
            int(Qt.ControlModifier) | int(Qt.AltModifier) | int(Qt.MetaModifier)
        ):
            return False
        key = int(ke.key())
        if key not in (int(Qt.Key_Backspace), int(Qt.Key_Delete)):
            return False
        te = self._presentation_editor.slide_editor()
        cur = te.textCursor()
        strike = QTextCharFormat()
        strike.setFontStrikeOut(True)

        if cur.hasSelection():
            cur.mergeCharFormat(strike)
            cur.clearSelection()
            te.setTextCursor(cur)
            self._refresh_preview()
            return True

        if key == int(Qt.Key_Backspace):
            p = cur.position()
            if p <= cur.block().position():
                return False
            cur.setPosition(p - 1)
            cur.setPosition(p, QTextCursor.KeepAnchor)
        else:
            p = cur.position()
            if cur.atBlockEnd():
                return False
            cur.setPosition(p)
            cur.setPosition(p + 1, QTextCursor.KeepAnchor)

        cur.mergeCharFormat(strike)
        cur.clearSelection()
        if key == int(Qt.Key_Backspace):
            cur.setPosition(p)
        else:
            cur.setPosition(p + 1)
        te.setTextCursor(cur)
        self._refresh_preview()
        return True

    def _slide_revision_accept(self, *, selection_only: bool) -> None:
        """接受修订：移除带删除线的字符（从文档中删除）。"""
        te = self._presentation_editor.slide_editor()
        doc = te.document()
        cur0 = te.textCursor()
        if selection_only and cur0.hasSelection():
            a = min(cur0.anchor(), cur0.position())
            b = max(cur0.anchor(), cur0.position())
        else:
            a, b = 0, doc.characterCount()
        to_del: List[int] = []
        for pos in range(a, b):
            if doc.characterAt(pos) == "\u0000":
                break
            if _char_format_at_doc_pos(doc, pos).fontStrikeOut():
                to_del.append(pos)
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        for pos in reversed(to_del):
            cur.setPosition(pos)
            cur.setPosition(pos + 1, QTextCursor.KeepAnchor)
            cur.removeSelectedText()
        cur.endEditBlock()
        te.setTextCursor(cur0)
        self._refresh_preview()

    def _slide_revision_reject(self, *, selection_only: bool) -> None:
        """拒绝修订：去掉选区或全文内的删除线，保留字符。"""
        te = self._presentation_editor.slide_editor()
        doc = te.document()
        cur0 = te.textCursor()
        if selection_only and cur0.hasSelection():
            a = min(cur0.anchor(), cur0.position())
            b = max(cur0.anchor(), cur0.position())
        else:
            a, b = 0, doc.characterCount()
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        for pos in range(a, b):
            if doc.characterAt(pos) == "\u0000":
                break
            if not _char_format_at_doc_pos(doc, pos).fontStrikeOut():
                continue
            cur.setPosition(pos)
            cur.setPosition(pos + 1, QTextCursor.KeepAnchor)
            plain = QTextCharFormat()
            plain.setFontStrikeOut(False)
            cur.mergeCharFormat(plain)
        cur.endEditBlock()
        te.setTextCursor(cur0)
        self._refresh_preview()

    def _edit_presentation_master_text(self, which: str, current: str) -> None:
        """P4-B-3：编辑母版页眉/页脚文本（参与预览/G-code）。"""
        if which not in ("header", "footer"):
            return
        title = "母版页眉" if which == "header" else "母版页脚"
        text, ok = QInputDialog.getText(
            self,
            "演示母版",
            f"{title}（将套用到所有幻灯片；参与预览/G-code）：",
            QLineEdit.Normal,
            str(current or ""),
        )
        if not ok:
            return
        if which == "header":
            self._presentation_editor.set_master_header(text)
        else:
            self._presentation_editor.set_master_footer(text)

    def _populate_wps_edit_round_menu(self, m) -> None:  # noqa: ANN001
        """填充「编辑」类 RoundMenu 项（供文字/演示与表格菜单复用）。"""
        a_u = Action(text="撤销")
        a_u.setEnabled(bool(self._act_undo.isEnabled()))
        a_u.triggered.connect(self._perform_undo)
        m.addAction(a_u)
        a_r = Action(text="重做")
        a_r.setEnabled(bool(self._act_redo.isEnabled()))
        a_r.triggered.connect(self._perform_redo)
        m.addAction(a_r)
        m.addSeparator()
        a_cut = Action(text="剪切")
        a_cut.setEnabled(self._has_selection_for_current_edit_context())
        a_cut.triggered.connect(self._edit_cut)
        m.addAction(a_cut)
        a_copy = Action(text="复制")
        a_copy.setEnabled(self._has_selection_for_current_edit_context())
        a_copy.triggered.connect(self._edit_copy)
        m.addAction(a_copy)
        a_paste = Action(text="粘贴")
        a_paste.setEnabled(self._can_paste_in_current_edit_context())
        a_paste.triggered.connect(self._edit_paste)
        m.addAction(a_paste)
        m.addSeparator()
        a_all = Action(text="全选")
        a_all.triggered.connect(self._edit_select_all)
        m.addAction(a_all)

    def _open_slide_rich_context_menu(self, global_pos: QPoint) -> None:
        """演示页富文本：编辑 + 段落/列表（对标 WPS/ PowerPoint）。"""
        try:
            from qfluentwidgets import RoundMenu
        except Exception:
            return
        te = self._presentation_editor.slide_editor()
        doc = te.document()
        m = RoundMenu("演示", self)
        a_u = Action(text="撤销")
        a_u.setEnabled(doc.isUndoAvailable())
        a_u.triggered.connect(self._slide_document_undo)
        m.addAction(a_u)
        a_r = Action(text="重做")
        a_r.setEnabled(doc.isRedoAvailable())
        a_r.triggered.connect(self._slide_document_redo)
        m.addAction(a_r)
        m.addSeparator()
        a_cut = Action(text="剪切")
        a_cut.triggered.connect(self._edit_cut)
        m.addAction(a_cut)
        a_copy = Action(text="复制")
        a_copy.triggered.connect(self._edit_copy)
        m.addAction(a_copy)
        a_paste = Action(text="粘贴")
        a_paste.triggered.connect(self._edit_paste)
        m.addAction(a_paste)
        m.addSeparator()
        a_all = Action(text="全选")
        a_all.triggered.connect(self._edit_select_all)
        m.addAction(a_all)
        m.addSeparator()
        s1 = Action(text="样式：标题 1")
        s1.triggered.connect(lambda: self._slide_apply_style_preset("h1"))
        m.addAction(s1)
        s2 = Action(text="样式：标题 2")
        s2.triggered.connect(lambda: self._slide_apply_style_preset("h2"))
        m.addAction(s2)
        sb = Action(text="样式：正文")
        sb.triggered.connect(lambda: self._slide_apply_style_preset("body"))
        m.addAction(sb)
        m.addSeparator()
        a_rev = Action(text="修订模式")
        a_rev.setCheckable(True)
        a_rev.setChecked(self._slide_revision_mode)
        a_rev.setToolTip(
            "开启后 Backspace/Delete 为「标记删除」（删除线），不物理删除；"
            "预览与 G-code 不刻写删除线字符。"
        )

        def _on_rev_toggled(checked: bool) -> None:
            self._slide_revision_mode = bool(checked)

        a_rev.toggled.connect(_on_rev_toggled)
        m.addAction(a_rev)
        a_acc = Action(text="接受修订（删除线内容）")
        a_acc.setToolTip("有选区时仅处理选区，否则处理当前幻灯片全文。")

        def _do_slide_accept_revision() -> None:
            c = te.textCursor()
            self._slide_revision_accept(selection_only=c.hasSelection())

        a_acc.triggered.connect(_do_slide_accept_revision)
        m.addAction(a_acc)
        a_rej = Action(text="拒绝修订（去掉删除线）")
        a_rej.setToolTip("有选区时仅处理选区，否则处理当前幻灯片全文。")

        def _do_slide_reject_revision() -> None:
            c = te.textCursor()
            self._slide_revision_reject(selection_only=c.hasSelection())

        a_rej.triggered.connect(_do_slide_reject_revision)
        m.addAction(a_rej)
        m.addSeparator()
        ms = self._presentation_editor.master_storage()
        a_h = Action(text="母版：设置页眉")
        a_h.setToolTip("为所有幻灯片套用页眉文本（参与预览/G-code）。")
        a_h.triggered.connect(
            lambda: self._edit_presentation_master_text(
                "header",
                ms.get("header", ""),
            )
        )
        m.addAction(a_h)
        a_f = Action(text="母版：设置页脚")
        a_f.setToolTip("为所有幻灯片套用页脚文本（参与预览/G-code）。")
        a_f.triggered.connect(
            lambda: self._edit_presentation_master_text(
                "footer",
                ms.get("footer", ""),
            )
        )
        m.addAction(a_f)
        a_clear = Action(text="母版：清空页眉/页脚")
        a_clear.setToolTip("清除所有幻灯片的页眉/页脚占位文本。")
        a_clear.triggered.connect(self._presentation_editor.clear_master)
        m.addAction(a_clear)
        m.addSeparator()
        a_bul = Action(text="项目符号")
        a_bul.setToolTip("将当前段落设为符号列表")
        a_bul.triggered.connect(lambda: self._slide_apply_list_style(QTextListFormat.ListDisc))
        m.addAction(a_bul)
        a_num = Action(text="编号")
        a_num.setToolTip("将当前段落设为编号列表")
        a_num.triggered.connect(lambda: self._slide_apply_list_style(QTextListFormat.ListDecimal))
        m.addAction(a_num)
        m.addSeparator()
        a_in = Action(text="增加缩进")
        a_in.triggered.connect(lambda: self._slide_change_block_indent(1))
        m.addAction(a_in)
        a_out = Action(text="减少缩进")
        a_out.triggered.connect(lambda: self._slide_change_block_indent(-1))
        m.addAction(a_out)
        m.exec_(global_pos)

    def _open_table_context_menu(self, global_pos: QPoint) -> None:
        """表格网格右键：编辑 + WPS 式插入/删除行列。"""
        try:
            from qfluentwidgets import RoundMenu
        except Exception:
            return
        m = RoundMenu("表格", self)
        self._populate_wps_edit_round_menu(m)
        m.addSeparator()
        a_ra = Action(text="在上方插入行")
        a_ra.setToolTip("在当前行之上插入一行")
        a_ra.triggered.connect(self._table_editor.insert_row_above)
        m.addAction(a_ra)
        a_rb = Action(text="在下方插入行")
        a_rb.setToolTip("在当前行之下插入一行")
        a_rb.triggered.connect(self._table_editor.insert_row_below)
        m.addAction(a_rb)
        a_cl = Action(text="在左侧插入列")
        a_cl.triggered.connect(self._table_editor.insert_column_left)
        m.addAction(a_cl)
        a_cr = Action(text="在右侧插入列")
        a_cr.triggered.connect(self._table_editor.insert_column_right)
        m.addAction(a_cr)
        m.addSeparator()
        tr, tc = self._table_editor.row_column_count()
        a_dr = Action(text="删除当前行")
        a_dr.setToolTip("至少保留一行")
        a_dr.triggered.connect(self._table_editor.delete_current_row)
        a_dr.setEnabled(tr > 1)
        m.addAction(a_dr)
        a_dc = Action(text="删除当前列")
        a_dc.setToolTip("至少保留一列")
        a_dc.triggered.connect(self._table_editor.delete_current_column)
        a_dc.setEnabled(tc > 1)
        m.addAction(a_dc)

        m.addSeparator()
        tw = self._table_editor.table_widget()
        ranges = tw.selectedRanges()
        merge_enable = False
        if ranges:
            rng = ranges[0]
            rs = int(rng.bottomRow() - rng.topRow() + 1)
            cs = int(rng.rightColumn() - rng.leftColumn() + 1)
            merge_enable = rs > 1 or cs > 1
        a_merge = Action(text="合并选区单元格")
        a_merge.setToolTip("将矩形选区合并为一个单元格（保留左上角内容）。")
        a_merge.triggered.connect(self._table_editor.merge_selected_cells)
        a_merge.setEnabled(merge_enable)
        m.addAction(a_merge)

        ar, ac = self._table_editor.current_grid_indices()
        a_split = Action(text="拆分当前合并")
        a_split.setToolTip("将当前合并单元格拆分回普通格。")
        a_split.triggered.connect(self._table_editor.split_current_merged_cell)
        a_split.setEnabled(int(tw.rowSpan(ar, ac) or 1) > 1 or int(tw.columnSpan(ar, ac) or 1) > 1)
        m.addAction(a_split)
        m.exec_(global_pos)

    def _refresh_preview(self) -> None:
        paths = self._work_paths()
        mm_per_px = max(0.05, self._cfg.page_width_mm / max(1, self._preview.viewport().width()))
        scene, _items = self._view_model.paths_to_scene_items(paths, mm_per_px=mm_per_px)
        self._preview.setScene(scene)
        self._preview.apply_fit_and_zoom(self._preview_zoom)

    def _capture_sketch_blob(self) -> dict:
        return {"paths": serialize_vector_paths(self._sketch_paths)} if self._sketch_paths else {}

    def _capture_insert_vector_blob(self) -> Optional[dict]:
        if not self._insert_paths_base:
            return None
        return {
            "paths": serialize_vector_paths(self._insert_paths_base),
            "scale": float(self._insert_vector_scale),
            "dx_mm": float(self._insert_vector_dx_mm),
            "dy_mm": float(self._insert_vector_dy_mm),
        }

    def _apply_table_blob(self, blob: dict) -> None:
        try:
            self._table_editor.from_project_blob(blob if isinstance(blob, dict) else {})
        except Exception:
            pass

    def _capture_table_blob(self) -> dict:
        return self._table_editor.to_project_blob()

    def _apply_slides_storage(self, slides: list[str]) -> None:
        self._presentation_editor.load_slides(slides if slides else [""])

    def _capture_slides_storage(self) -> list[str]:
        return self._presentation_editor.slides_storage()

    def _capture_slides_storage_for_export(self) -> list[str]:
        return self._presentation_editor.slides_storage_for_export()

    # ---------- 导出（占位） ----------
    def _export_gcode_to_file_stub(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 G-code",
            str(Path.home() / "output.nc"),
            "G-code (*.nc *.gcode *.tap *.txt);;所有文件 (*)",
        )
        if not path:
            return
        self._sync_device_machine_widgets_to_cfg()
        self._log_event("导出", "开始导出 G-code", level="INFO")
        try:
            paths = self._current_work_paths_checked()
        except ValueError as e:
            self._log_event("导出", f"G-code 导出前检查失败：{e}", level="ERROR")
            self._notify_error("导出失败", str(e))
            return
        # 与右侧预览一致：输出当前 work paths
        g = paths_to_gcode(paths, self._cfg, order=False)
        try:
            write_text_atomic(Path(path), g)
        except Exception as e:
            self._log_event("导出", f"{Path(path).name} 写入失败：{e}", level="ERROR")
            self._notify_error("导出失败", f"{Path(path).name} 写入失败：{e}")
            return
        summary = self._build_job_summary(paths).replace("\n", "；")
        self._log_event("导出", f"G-code 已导出到 {Path(path).name}")
        self._notify_success(
            "已导出",
            f"G-code 已写入 {Path(path).name}。{summary}。建议先做小范围试写。",
        )
        glyph_warning = self._glyph_warning_summary(self._current_content_page_id())
        if glyph_warning:
            self._notify_warning(
                "字形提醒",
                f"当前内容存在未覆盖字符，导出结果可能缺少部分笔画。{glyph_warning}",
            )

    def _export_docx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出为 DOCX",
            str(Path.home() / f"{self._doc_title}.docx"),
            "Word 文档 (*.docx);;所有文件 (*)",
        )
        if not path:
            return
        try:
            paragraphs, src_html = self._docx_export_payload()
            export_docx(Path(path), paragraphs=paragraphs, html_text=src_html, prefer_soffice=True)
        except OfficeExportError as e:
            self._log_event("导出", f"DOCX 导出失败：{e}", level="ERROR")
            self._notify_error("导出失败", f"{Path(path).name} 导出失败：{e}")
            return
        except Exception as e:
            self._log_event("导出", f"DOCX 导出异常：{e}", level="ERROR")
            self._notify_error("导出失败", f"{Path(path).name} 导出失败：{e}")
            return
        self._log_event("导出", f"DOCX 已导出到 {Path(path).name}")
        self._notify_success("已导出", f"DOCX 已生成：{Path(path).name}")

    def _export_xlsx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出为 XLSX",
            str(Path.home() / f"{self._doc_title}.xlsx"),
            "Excel 表格 (*.xlsx);;所有文件 (*)",
        )
        if not path:
            return
        try:
            self._require_export_source("table", "XLSX")
            export_xlsx(Path(path), table_blob=self._capture_table_blob(), prefer_soffice=True)
        except ValueError as e:
            self._log_event("导出", f"XLSX 导出前检查失败：{e}", level="ERROR")
            self._notify_error("导出失败", str(e))
            return
        except OfficeExportError as e:
            self._log_event("导出", f"XLSX 导出失败：{e}", level="ERROR")
            self._notify_error("导出失败", f"{Path(path).name} 导出失败：{e}")
            return
        except Exception as e:
            self._log_event("导出", f"XLSX 导出异常：{e}", level="ERROR")
            self._notify_error("导出失败", f"{Path(path).name} 导出失败：{e}")
            return
        self._log_event("导出", f"XLSX 已导出到 {Path(path).name}")
        self._notify_success("已导出", f"XLSX 已生成：{Path(path).name}")

    def _export_pptx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出为 PPTX",
            str(Path.home() / f"{self._doc_title}.pptx"),
            "PowerPoint 演示 (*.pptx);;所有文件 (*)",
        )
        if not path:
            return
        try:
            self._require_export_source("slides", "PPTX")
            # PPTX 导出：使用“套用母版页眉/页脚后的纯文本版本”
            export_pptx(
                Path(path),
                slides=self._capture_slides_storage_for_export(),
                prefer_soffice=True,
            )
        except ValueError as e:
            self._log_event("导出", f"PPTX 导出前检查失败：{e}", level="ERROR")
            self._notify_error("导出失败", str(e))
            return
        except OfficeExportError as e:
            self._log_event("导出", f"PPTX 导出失败：{e}", level="ERROR")
            self._notify_error("导出失败", f"{Path(path).name} 导出失败：{e}")
            return
        except Exception as e:
            self._log_event("导出", f"PPTX 导出异常：{e}", level="ERROR")
            self._notify_error("导出失败", f"{Path(path).name} 导出失败：{e}")
            return
        self._log_event("导出", f"PPTX 已导出到 {Path(path).name}")
        self._notify_success("已导出", f"PPTX 已生成：{Path(path).name}")

    def _slides_plain_to_markdown(self) -> str:
        parts: list[str] = []
        for s in self._capture_slides_storage_for_export():
            st = (s or "").strip()
            if not st:
                continue
            parts.append(st)
        if not parts:
            return ""
        return "\n\n---\n\n".join(parts)

    def _table_plain_to_markdown(self) -> str:
        blob = self._capture_table_blob()
        rows = blob.get("cells") or []
        lines: list[str] = []
        for row in rows:
            texts: list[str] = []
            for cell in row:
                text = str((cell or {}).get("text", "")).strip()
                texts.append(text)
            if any(texts):
                lines.append("\t".join(texts).rstrip())
        return "\n".join(lines)

    def _docx_export_payload(self) -> tuple[List[DocParagraph], str | None]:
        """按当前内容来源生成 DOCX 导出内容，避免误导出隐藏页。"""
        name = self._current_content_page_id()
        if name == "table":
            body = self._table_plain_to_markdown()
            raw = body.split("\n") if body else [""]
            return [DocParagraph(runs=[DocRun(text=ln)]) for ln in raw], None
        if name == "slides":
            ed = self._presentation_editor.slide_editor()
            return self._docx_paragraphs_from_editor_widget(ed), ed.toHtml()
        return self._docx_paragraphs_from_editor_widget(self._word_editor), self._word_editor.toHtml()

    def _require_export_source(self, expected_pid: str, target_name: str) -> None:
        """限制格式专属导出入口只作用于对应内容源。"""
        current_pid = self._current_content_page_id()
        if current_pid == expected_pid:
            return
        current_label = self._content_mode_label(current_pid)
        expected_label = self._content_mode_label(expected_pid)
        raise ValueError(
            f"{target_name} 导出仅适用于“{expected_label}”内容；当前预览来源是“{current_label}”。"
        )

    def _import_markdown_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入 Markdown",
            str(Path.home()),
            "Markdown (*.md *.markdown);;所有文件 (*)",
        )
        if not path:
            return
        self._open_office_or_wps_file(Path(path))

    def _export_markdown(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出为 Markdown",
            str(Path.home() / f"{self._doc_title}.md"),
            "Markdown (*.md *.markdown);;所有文件 (*)",
        )
        if not path:
            return
        name = self._current_content_page_id()
        if name == "slides":
            body = self._slides_plain_to_markdown()
        elif name == "table":
            body = self._table_plain_to_markdown()
        else:
            body = self._word_editor.toPlainText()
        try:
            export_markdown(Path(path), body=body)
        except Exception as e:
            self._log_event("导出", f"Markdown 导出失败：{e}", level="ERROR")
            self._notify_error("导出失败", f"{Path(path).name} 导出失败：{e}")
            return
        self._log_event("导出", f"Markdown 已导出到 {Path(path).name}")
        self._notify_success("已导出", f"Markdown 已生成：{Path(path).name}")

    def _docx_paragraphs_from_editor_widget(self, ed) -> List[DocParagraph]:  # noqa: ANN001
        """高保真（基础）：从 QTextDocument 抽取段落与字符级样式。"""
        if not hasattr(ed, "document"):
            raw = ed.toPlainText().split("\n") if hasattr(ed, "toPlainText") else [""]
            if not raw:
                raw = [""]
            return [DocParagraph(runs=[DocRun(text=ln)]) for ln in raw]
        doc = ed.document()
        paras: List[DocParagraph] = []
        block = doc.firstBlock()
        while block.isValid():
            bf = block.blockFormat()
            al = "left"
            try:
                from PyQt5.QtCore import Qt as _Qt

                a = int(bf.alignment())
                if a & int(_Qt.AlignHCenter):
                    al = "center"
                elif a & int(_Qt.AlignRight):
                    al = "right"
                elif a & int(_Qt.AlignJustify):
                    al = "justify"
            except Exception:
                pass

            runs: List[DocRun] = []
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    text = frag.text()
                    if text:
                        cf = frag.charFormat()
                        f = cf.font()
                        runs.append(
                            DocRun(
                                text=text,
                                bold=bool(f.bold()),
                                italic=bool(f.italic()),
                                underline=bool(f.underline()),
                                font_family=str(f.family() or "") or None,
                                font_pt=float(
                                    f.pointSizeF() if f.pointSizeF() > 0 else f.pointSize() or 0
                                )
                                or None,
                            )
                        )
                it += 1
            # 空段落也要保留
            if not runs:
                runs = [DocRun(text="")]
            paras.append(DocParagraph(runs=runs, align=al))
            block = block.next()
        return paras

    def _docx_paragraphs_from_editor(self) -> List[DocParagraph]:
        return self._docx_paragraphs_from_editor_widget(self._active_text_edit() or self._word_editor)

    def _soffice_ready_hint(self) -> str:
        if has_soffice():
            return "已检测到 soffice（高保真导出已启用）"
        return "未检测到 soffice（使用纯 Python 导出）"

    # ---------- 串口 / GRBL ----------
    def _log_append(self, s: str, *, category: str = "运行") -> None:
        self._log_records.append((str(category or "运行"), str(s)))
        self._render_log_views()

    def _refresh_ports(self) -> None:
        if not hasattr(self, "_port_combo"):
            return
        if (
            hasattr(self, "_conn_mode_combo")
            and str(self._conn_mode_combo.currentData() or "serial") != "serial"
        ):
            self._port_combo.clear()
            self._port_combo.addItem("TCP 模式无需扫描串口", "")
            return
        self._port_combo.clear()
        ports = filter_ports(
            list_port_infos(),
            bool(getattr(self._cfg, "serial_show_bluetooth_only", False)),
        )
        for info in ports:
            self._port_combo.addItem(info.label(), info.device)
        if self._port_combo.count() == 0:
            self._port_combo.addItem("（无端口，请手输设备名）", "")
            for dev in ("/dev/rfcomm0", "/dev/tty.Bluetooth-Incoming-Port", "COM5"):
                self._port_combo.addItem(dev, dev)

    def _toggle_serial(self) -> None:
        if self._grbl is not None:
            try:
                self._grbl.close()
            except Exception:
                pass
            self._grbl = None
            self._machine_monitor.on_disconnected()
            self._btn_connect.setText("连接")
            self._btn_send.setEnabled(False)
            self._btn_send_pause_m800.setEnabled(False)
            self._btn_send_checkpoint.setEnabled(False)
            self._btn_send_resume.setEnabled(False)
            self._btn_paper_flow.setEnabled(False)
            self._btn_reset.setEnabled(False)
            self._pending_program_after_m800 = None
            self._set_job_status("就绪", 0, 0)
            self._log_event("设备", "已断开设备连接")
            self._update_action_states()
            self._update_status_line()
            return
        try:
            mode = str(self._conn_mode_combo.currentData() or "serial").strip().lower()
            if mode == "tcp":
                host = self._tcp_host_edit.text().strip()
                port_num = int(self._tcp_port_spin.value())
                if not host:
                    raise ValueError("请输入 TCP 主机/IP")
                stream = TcpTextStream(host, port_num, timeout_s=0.2)
                stream.connect()
                target_desc = f"{host}:{port_num}"
                connect_title = "TCP"
            else:
                import serial

                data = self._port_combo.currentData()
                port = (
                    data if isinstance(data, str) and data.strip() else ""
                ) or self._port_combo.currentText().strip()
                if "—" in port:
                    port = port.split("—", 1)[0].strip()
                if not port or port.startswith("（"):
                    raise ValueError("请选择或输入串口设备路径")
                stream = serial.Serial(port, int(self._baud_spin.value()), timeout=0.1)
                target_desc = port
                connect_title = "串口"
            ok_probe, probe_msg = verify_grbl_responsive(stream, on_line=self._log_append)
            if not ok_probe:
                stream.close()
                InfoBar.error(
                    f"{connect_title}无应答",
                    probe_msg,
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
                return
            self._log_append(probe_msg)
            self._grbl = GrblController(
                stream,
                default_line_timeout_s=float(getattr(self._cfg, "grbl_line_timeout_s", 30.0)),
                on_status=self._on_grbl_status,
                on_log_line=self._log_append,
                on_protocol_error=self._on_grbl_protocol_error,
            )
            self._machine_monitor.on_connected()
            self._grbl.start_reader()
            time.sleep(0.05)
            self._btn_connect.setText("断开")
            self._btn_send.setEnabled(True)
            self._btn_send_pause_m800.setEnabled(True)
            self._btn_send_checkpoint.setEnabled(False)
            self._btn_paper_flow.setEnabled(True)
            self._btn_reset.setEnabled(True)
            self._set_job_status("就绪", 0, 0)
            self._log_event("设备", f"已连接 {target_desc}")
            self._update_action_states()
            self._update_status_line()
        except Exception as e:
            self._log_event("设备", f"连接失败：{e}", level="ERROR")
            InfoBar.error("连接", str(e), parent=self, position=InfoBarPosition.TOP)

    def _on_grbl_status(self, d: dict) -> None:
        self._machine_monitor.apply_status_fields(d)
        self._update_status_line()
        if not self._pending_bf_for_rx_spin:
            return
        _, rx_free = parse_bf_field(d)
        self._pending_bf_for_rx_spin = False
        if rx_free is not None and rx_free > 0:
            v = max(32, min(16384, int(rx_free)))
            self._rx_buf_spin.blockSignals(True)
            self._rx_buf_spin.setValue(v)
            self._rx_buf_spin.blockSignals(False)
            setattr(self._cfg, "grbl_rx_buffer_size", int(v))
            self._log_append(f"Bf→RX：已将 RX 预算设为 {v}")

    def _on_grbl_protocol_error(self, s: str) -> None:
        self._machine_monitor.apply_alarm_or_error(s)
        self._log_append(f"[协议] {s}")
        self._update_status_line()

    def _sync_rx_from_grbl_bf(self) -> None:
        if not self._grbl:
            InfoBar.warning("Bf→RX", "请先连接串口。", parent=self, position=InfoBarPosition.TOP)
            return
        self._pending_bf_for_rx_spin = True

        def _timeout() -> None:
            if self._pending_bf_for_rx_spin:
                self._pending_bf_for_rx_spin = False
                self._log_append("Bf→RX：超时未收到含 Bf 的状态报告。")

        QTimer.singleShot(1500, _timeout)
        self._grbl.send_realtime_status_request()

    def _send_m800_only(self) -> None:
        if not self._grbl:
            InfoBar.warning("M800", "请先连接串口。", parent=self, position=InfoBarPosition.TOP)
            return
        if not self._confirm_dangerous_action(
            "发送 M800",
            "即将向机床发送单条 M800。\n\n"
            "请确认 M800 在你的固件中确实作为“暂停/换纸节点”。继续吗？",
        ):
            return
        try:
            self._grbl.send_line_sync("M800")
            self._log_append("已发送 M800（换纸/暂停点）")
            InfoBar.success("M800", "已发送", parent=self, position=InfoBarPosition.TOP)
        except Exception as e:
            self._log_append(f"[错误] M800: {e}")
            InfoBar.error("M800", str(e), parent=self, position=InfoBarPosition.TOP)

    def _paper_change_flow(self) -> None:
        """换纸流程：发送配置前缀 → M800 → 等待继续 → 发送配置后缀。"""
        if not self._grbl:
            return
        if not self._confirm_dangerous_action(
            "换纸流程（前缀→M800→后缀）",
            "即将发送“前缀 → M800 → 后缀”。\n\n"
            "到达 M800 后将停下等待你完成换纸/人工处理。\n继续吗？",
        ):
            return
        from inkscape_wps.core.grbl import executable_gcode_lines

        pre = str(getattr(self._cfg, "gcode_program_prefix", "") or "")
        suf = str(getattr(self._cfg, "gcode_program_suffix", "") or "")
        pre_lines = executable_gcode_lines(pre)
        suf_lines = executable_gcode_lines(suf)
        try:
            for ln in pre_lines:
                self._grbl.send_line_sync(ln)
            self._grbl.send_line_sync("M800")
            self._pending_program_after_m800 = list(suf_lines)
            self._btn_send_resume.setEnabled(bool(suf_lines))
            InfoBar.warning(
                "换纸流程",
                "已发送前缀与 M800（到达流程节点）。"
                "完成换纸/人工处理后，点“继续（从 M800 后）”发送后缀。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except Exception as e:
            self._pending_program_after_m800 = None
            self._btn_send_resume.setEnabled(False)
            self._log_append(f"[错误] 换纸流程失败: {e}")
            InfoBar.error("换纸流程失败", str(e), parent=self, position=InfoBarPosition.TOP)

    def _sync_device_machine_widgets_to_cfg(self) -> None:
        """设备页机床相关控件写回配置（发送 / 导出 G-code 前即生效）。"""
        if not hasattr(self, "_z_up"):
            return
        self._cfg.z_up_mm = float(self._z_up.value())
        self._cfg.z_down_mm = float(self._z_down.value())
        self._cfg.draw_feed_rate = int(self._draw_feed_spin.value())
        self._cfg.z_feed_rate = int(self._z_feed_spin.value())
        data = self._pen_mode_combo.currentData()
        self._cfg.gcode_pen_mode = str(data) if data is not None else "z"
        self._cfg.gcode_m3_s_value = int(self._m3_s_spin.value())
        self._cfg.rapid_after_pen_up = bool(self._cb_rapid_after_up.isChecked())
        self._cfg.mm_per_pt = float(self._mm_per_pt_spin.value())
        self._cfg.document_margin_mm = float(self._doc_margin_spin.value())
        self._cfg.layout_vertical_scale = float(self._layout_v_scale_spin.value())
        self._cfg.page_width_mm = float(self._page_w_spin.value())
        self._cfg.page_height_mm = float(self._page_h_spin.value())
        self._cfg.coord_mirror_x = bool(self._cb_coord_mirror_x.isChecked())
        self._cfg.coord_mirror_y = bool(self._cb_coord_mirror_y.isChecked())
        self._cfg.coord_pivot_x_mm = float(self._pivot_x_spin.value())
        self._cfg.coord_pivot_y_mm = float(self._pivot_y_spin.value())
        self._cfg.coord_scale_x = -1.0 if self._cb_invert_x.isChecked() else 1.0
        self._cfg.coord_scale_y = -1.0 if self._cb_invert_y.isChecked() else 1.0
        self._cfg.coord_offset_x_mm = float(self._off_x_spin.value())
        self._cfg.coord_offset_y_mm = float(self._off_y_spin.value())
        self._cfg.connection_mode = str(self._conn_mode_combo.currentData() or "serial")
        self._cfg.tcp_host = self._tcp_host_edit.text().strip()
        self._cfg.tcp_port = int(self._tcp_port_spin.value())
        self._cfg.kuixiang_mm_per_unit = float(self._kuixiang_unit_spin.value())
        self._mapper.set_kuixiang_mm_per_unit(self._cfg.kuixiang_mm_per_unit)

    def _update_pen_mode_dependent_widgets(self) -> None:
        if not hasattr(self, "_pen_mode_combo"):
            return
        raw = self._pen_mode_combo.currentData()
        pm = str(raw if raw is not None else "z").strip().lower()
        use_z = pm not in ("m3m5", "m3", "spindle")
        self._z_up.setEnabled(use_z)
        self._z_down.setEnabled(use_z)

    def _apply_device_machine_widgets_from_cfg(self) -> None:
        if not hasattr(self, "_z_up"):
            return
        spin_widgets = (
            self._z_up,
            self._z_down,
            self._draw_feed_spin,
            self._z_feed_spin,
            self._m3_s_spin,
            self._mm_per_pt_spin,
            self._doc_margin_spin,
            self._layout_v_scale_spin,
            self._page_w_spin,
            self._page_h_spin,
            self._pivot_x_spin,
            self._pivot_y_spin,
            self._off_x_spin,
            self._off_y_spin,
            self._kuixiang_unit_spin,
        )
        for w in spin_widgets:
            w.blockSignals(True)
        self._z_up.setValue(float(self._cfg.z_up_mm))
        self._z_down.setValue(float(self._cfg.z_down_mm))
        self._draw_feed_spin.setValue(int(self._cfg.draw_feed_rate))
        self._z_feed_spin.setValue(int(self._cfg.z_feed_rate))
        self._m3_s_spin.setValue(max(0, int(self._cfg.gcode_m3_s_value)))
        self._mm_per_pt_spin.setValue(float(self._cfg.mm_per_pt))
        self._doc_margin_spin.setValue(float(self._cfg.document_margin_mm))
        self._layout_v_scale_spin.setValue(float(self._cfg.layout_vertical_scale))
        self._page_w_spin.setValue(float(self._cfg.page_width_mm))
        self._page_h_spin.setValue(float(self._cfg.page_height_mm))
        self._pivot_x_spin.setValue(float(self._cfg.coord_pivot_x_mm))
        self._pivot_y_spin.setValue(float(self._cfg.coord_pivot_y_mm))
        self._off_x_spin.setValue(float(self._cfg.coord_offset_x_mm))
        self._off_y_spin.setValue(float(self._cfg.coord_offset_y_mm))
        self._kuixiang_unit_spin.setValue(float(self._cfg.kuixiang_mm_per_unit))
        for w in spin_widgets:
            w.blockSignals(False)
        self._pen_mode_combo.blockSignals(True)
        pm = (self._cfg.gcode_pen_mode or "z").strip().lower()
        use_m3 = pm in ("m3m5", "m3", "spindle")
        self._pen_mode_combo.setCurrentIndex(1 if use_m3 else 0)
        self._pen_mode_combo.blockSignals(False)
        self._cb_rapid_after_up.blockSignals(True)
        self._cb_rapid_after_up.setChecked(bool(getattr(self._cfg, "rapid_after_pen_up", True)))
        self._cb_rapid_after_up.blockSignals(False)
        for _cb, val in (
            (self._cb_coord_mirror_x, bool(self._cfg.coord_mirror_x)),
            (self._cb_coord_mirror_y, bool(self._cfg.coord_mirror_y)),
            (self._cb_invert_x, float(self._cfg.coord_scale_x) < 0),
            (self._cb_invert_y, float(self._cfg.coord_scale_y) < 0),
        ):
            _cb.blockSignals(True)
            _cb.setChecked(val)
            _cb.blockSignals(False)
        self._cb_bt_only.blockSignals(True)
        self._cb_bt_only.setChecked(bool(getattr(self._cfg, "serial_show_bluetooth_only", False)))
        self._cb_bt_only.blockSignals(False)
        self._conn_mode_combo.blockSignals(True)
        mode = str(getattr(self._cfg, "connection_mode", "serial") or "serial").strip().lower()
        self._conn_mode_combo.setCurrentIndex(1 if mode == "tcp" else 0)
        self._conn_mode_combo.blockSignals(False)
        self._tcp_host_edit.setText(str(getattr(self._cfg, "tcp_host", "") or ""))
        self._tcp_port_spin.setValue(max(1, int(getattr(self._cfg, "tcp_port", 23) or 23)))
        self._update_connection_mode_widgets()
        self._update_pen_mode_dependent_widgets()
        try:
            self._sync_ribbon_layout_widgets_from_cfg()
        except Exception:
            _logger.debug("同步顶部页面布局功能区失败", exc_info=True)

    def _on_fluent_pen_mode_changed(self, _index: int = 0) -> None:
        self._sync_device_machine_widgets_to_cfg()
        self._update_pen_mode_dependent_widgets()

    def _on_device_machine_value_changed(self, *_args) -> None:
        self._sync_device_machine_widgets_to_cfg()
        try:
            self._sync_ribbon_layout_widgets_from_cfg()
        except Exception:
            _logger.debug("设备页变更后同步顶部页面布局功能区失败", exc_info=True)
        try:
            self._sync_document_surface_widths()
        except Exception:
            _logger.debug("设备页变更后同步文档画布宽度失败", exc_info=True)
        try:
            self._sync_fluent_editor_margins()
        except Exception:
            _logger.debug("设备页变更后同步编辑区页边距失败", exc_info=True)
        if hasattr(self, "_word_editor"):
            self._word_editor.update()
        try:
            self._update_status_line()
        except Exception:
            _logger.debug("设备页变更后刷新状态栏失败", exc_info=True)
        self._refresh_preview()

    def _fluent_pivot_page_center(self) -> None:
        """将镜像枢轴设为当前纸张宽、高的一半（与 PyQt6 Ribbon「纸张中心」一致）。"""
        if not hasattr(self, "_page_w_spin"):
            return
        pw = float(self._page_w_spin.value())
        ph = float(self._page_h_spin.value())
        self._pivot_x_spin.setValue(pw / 2.0)
        self._pivot_y_spin.setValue(ph / 2.0)
        self._on_device_machine_value_changed()

    def _on_fluent_bluetooth_filter_changed(self) -> None:
        self._cfg.serial_show_bluetooth_only = bool(self._cb_bt_only.isChecked())
        self._refresh_ports()

    def _on_connection_mode_changed(self, _index: int = 0) -> None:
        self._cfg.connection_mode = str(self._conn_mode_combo.currentData() or "serial")
        self._update_connection_mode_widgets()
        self._refresh_ports()

    def _update_connection_mode_widgets(self) -> None:
        mode = str(getattr(self._cfg, "connection_mode", "serial") or "serial").strip().lower()
        is_serial = mode != "tcp"
        self._cb_bt_only.setEnabled(is_serial)
        self._port_combo.setEnabled(is_serial)
        self._btn_ports.setEnabled(is_serial)
        self._baud_spin.setEnabled(is_serial)
        self._tcp_host_edit.setEnabled(not is_serial)
        self._tcp_port_spin.setEnabled(not is_serial)

    def _save_config(self) -> None:
        self._sync_device_machine_widgets_to_cfg()
        try:
            save_machine_config(self._cfg, self._cfg_path)
        except Exception as e:
            self._log_append(f"[错误] 保存配置: {e}")
            InfoBar.error("保存配置失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        self._log_append(f"已保存配置 {self._cfg_path}")
        InfoBar.success(
            "已保存配置",
            str(self._cfg_path),
            parent=self,
            position=InfoBarPosition.TOP,
        )

    def _confirm_dangerous_action(self, title: str, text: str) -> bool:
        """危险操作二次确认（如发送 G-code / 换纸流程继续）。"""
        try:
            r = QMessageBox.question(
                self,
                title,
                text,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            return bool(r == QMessageBox.Yes)
        except Exception:
            # 若弹窗失败（极端环境），保持默认继续，避免阻塞核心功能。
            return True

    def _send_gcode(self) -> None:
        if not self._grbl:
            self._notify_error("发送失败", "请先连接设备，再发送当前 G-code。")
            return
        self._sync_device_machine_widgets_to_cfg()
        self._log_event("发送", "开始发送当前 G-code", level="INFO")
        try:
            paths = self._current_work_paths_checked()
        except ValueError as e:
            self._log_event("发送", f"发送前检查失败：{e}", level="ERROR")
            self._notify_error("发送失败", str(e))
            return
        if not self._confirm_dangerous_action(
            "发送 G-code",
            "即将向机床发送当前文档生成的 G-code。\n\n"
            f"{self._build_job_summary(paths)}\n\n"
            "请再次确认：坐标零点、抬落笔模式、纸张/工作区是否正确。\n继续吗？",
        ):
            return
        g = paths_to_gcode(paths, self._cfg, order=False)
        try:
            total_lines = len([ln for ln in g.splitlines() if ln.strip()])
            self._set_job_status("发送中", 0, total_lines)
            n_ok, n_tot = self._grbl.send_program(
                g,
                streaming=bool(getattr(self._cfg, "grbl_streaming", False)),
                rx_buffer_size=int(getattr(self._cfg, "grbl_rx_buffer_size", 128)),
                on_progress=self._job_progress_callback,
            )
            self._btn_send_checkpoint.setEnabled(False)
            self._set_job_status("已完成", n_ok, n_tot)
            self._log_event("发送", f"已发送 {n_ok}/{n_tot} 行")
            InfoBar.success(
                "发送完成",
                f"{n_ok}/{n_tot} 行",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except GrblSendError as e:
            self._log_event("发送", str(e), level="ERROR")
            self._set_job_status("失败", e.acked_count or 0, e.total_count or 0)
            remaining = len(self._grbl.remaining_program_lines_from_checkpoint())
            self._btn_send_checkpoint.setEnabled(self._grbl.can_resume_from_checkpoint)
            if self._grbl.can_resume_from_checkpoint:
                self._log_event("发送", f"已确认 {e.acked_count or 0} 行，剩余 {remaining} 行可续发")
            InfoBar.error("GRBL 发送失败", str(e), parent=self, position=InfoBarPosition.TOP)
        except Exception as e:
            self._log_event("发送", f"发送异常：{e}", level="ERROR")
            InfoBar.error("发送失败", str(e), parent=self, position=InfoBarPosition.TOP)

    def _resume_from_checkpoint(self) -> None:
        if not self._grbl or not self._grbl.can_resume_from_checkpoint:
            self._btn_send_checkpoint.setEnabled(False)
            if not self._grbl:
                self._notify_error("断点续发失败", "当前未连接设备。")
            return
        remaining = self._grbl.remaining_program_lines_from_checkpoint()
        if not self._confirm_dangerous_action(
            "断点续发",
            f"准备从上次确认断点继续发送，剩余 {len(remaining)} 行。\n\n"
            "请确认机床位置、纸张和夹具状态没有变化。继续吗？",
        ):
            return
        try:
            self._set_job_status("断点续发", 0, len(remaining))
            n_ok, n_tot = self._grbl.resume_from_checkpoint(
                streaming=bool(getattr(self._cfg, "grbl_streaming", False)),
                rx_buffer_size=int(getattr(self._cfg, "grbl_rx_buffer_size", 128)),
                on_progress=self._job_progress_callback,
            )
            self._btn_send_checkpoint.setEnabled(False)
            self._set_job_status("已完成", n_ok, n_tot)
            self._log_append(f"断点续发完成 {n_ok}/{n_tot} 行")
            InfoBar.success(
                "断点续发完成",
                f"{n_ok}/{n_tot} 行",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except GrblSendError as e:
            self._set_job_status("失败", e.acked_count or 0, e.total_count or 0)
            self._btn_send_checkpoint.setEnabled(self._grbl.can_resume_from_checkpoint)
            self._log_append(f"[错误] 断点续发失败: {e}")
            InfoBar.error("断点续发失败", str(e), parent=self, position=InfoBarPosition.TOP)

    def _soft_reset_machine(self) -> None:
        if not self._grbl:
            self._notify_error("软复位失败", "请先连接设备。")
            return
        if not self._confirm_dangerous_action(
            "软复位",
            "即将发送 Ctrl+X 软复位，当前作业会被中断。继续吗？",
        ):
            return
        try:
            self._grbl.soft_reset()
            self._set_job_status("已复位", 0, 0)
            self._log_append("已发送软复位 Ctrl+X")
            InfoBar.success("软复位", "已发送 Ctrl+X", parent=self, position=InfoBarPosition.TOP)
        except Exception as e:
            InfoBar.error("软复位失败", str(e), parent=self, position=InfoBarPosition.TOP)

    def _send_gcode_pause_at_m800(self) -> None:
        """发送程序，遇到第一条 M800 时停下，等待用户点击继续。"""
        if not self._grbl:
            self._notify_error("发送失败", "请先连接设备，再发送当前 G-code。")
            return
        self._sync_device_machine_widgets_to_cfg()
        try:
            paths = self._current_work_paths_checked()
        except ValueError as e:
            self._notify_error("发送失败", str(e))
            return
        if not self._confirm_dangerous_action(
            "发送（遇 M800 暂停）",
            "将发送当前文档的 G-code，并在遇到第一条 M800 时停下等待。\n\n"
            f"{self._build_job_summary(paths)}\n\n"
            "请确认：M800 定义与固件流程一致，"
            "且你已准备好“换纸/人工处理”。\n继续吗？",
        ):
            return
        self._pending_program_after_m800 = None
        g = paths_to_gcode(paths, self._cfg, order=False)
        from inkscape_wps.core.grbl import executable_gcode_lines

        lines = executable_gcode_lines(g)
        idx = None
        for i, ln in enumerate(lines):
            s = ln.strip().upper()
            if s.startswith("M800") or (" M800" in f" {s} "):
                idx = i
                break
        if idx is None:
            # 没有 M800：就正常发送
            self._send_gcode()
            return
        before = lines[: idx + 1]
        after = lines[idx + 1 :]
        try:
            for ln in before:
                self._grbl.send_line_sync(ln)
            self._pending_program_after_m800 = list(after)
            self._btn_send_resume.setEnabled(bool(after))
            InfoBar.warning(
                "已到 M800 节点",
                "已发送到 M800（到达流程节点）。完成换纸/人工处理后点“继续（从 M800 后）”。",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except Exception as e:
            self._pending_program_after_m800 = None
            self._btn_send_resume.setEnabled(False)
            self._log_append(f"[错误] 发送到 M800 失败: {e}")
            InfoBar.error("发送失败", str(e), parent=self, position=InfoBarPosition.TOP)

    def _resume_after_m800(self) -> None:
        if not self._grbl:
            return
        after = self._pending_program_after_m800 or []
        if not after:
            self._btn_send_resume.setEnabled(False)
            return
        if not self._confirm_dangerous_action(
            "继续发送（从 M800 后）",
            f"当前已在 M800 暂停，准备继续发送剩余 {len(after)} 行。\n\n"
            "确认换纸/人工处理已完成且机床状态正确。继续吗？",
        ):
            return
        try:
            for ln in after:
                self._grbl.send_line_sync(ln)
            self._log_append(f"已继续发送 {len(after)} 行")
            InfoBar.success(
                "继续完成",
                f"{len(after)} 行",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        except Exception as e:
            self._log_append(f"[错误] 继续发送失败: {e}")
            InfoBar.error("继续失败", str(e), parent=self, position=InfoBarPosition.TOP)
        finally:
            self._pending_program_after_m800 = None
            self._btn_send_resume.setEnabled(False)


class _PreviewView(QGraphicsView):
    """PyQt5 预览视图：滚轮缩放 + 拖拽平移（macOS 下强制抓取鼠标）。"""

    zoomChanged = pyqtSignal(float)

    def __init__(self) -> None:
        super().__init__()
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setRenderHints(
            self.renderHints() | QPainter.Antialiasing | QPainter.SmoothPixmapTransform
        )
        self._zoom = 1.0

    def apply_fit_and_zoom(self, zoom: float) -> None:
        self._zoom = max(0.1, min(5.0, float(zoom)))
        sc = self.scene()
        if sc is None:
            return
        self.resetTransform()
        self.fitInView(sc.sceneRect(), Qt.KeepAspectRatio)
        if abs(self._zoom - 1.0) > 1e-6:
            self.scale(self._zoom, self._zoom)
        self.zoomChanged.emit(self._zoom)

    def wheelEvent(self, event: QWheelEvent) -> None:
        # 以鼠标位置为中心缩放
        delta = event.angleDelta().y()
        if delta == 0:
            return super().wheelEvent(event)
        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        self._zoom = max(0.1, min(5.0, self._zoom * factor))
        self.scale(factor, factor)
        self.zoomChanged.emit(self._zoom)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            try:
                self.viewport().grabMouse()
            except Exception:
                pass
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        try:
            self.viewport().releaseMouse()
        except Exception:
            pass
        super().mouseReleaseEvent(event)


def _package_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def _preset_svg_dir() -> Path:
    return _package_data_dir() / "preset_svgs"


def _resolve_stroke_font_path(cfg) -> Path | None:
    raw = (getattr(cfg, "stroke_font_json_path", "") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if p.is_file():
            return p
    bundled = _package_data_dir() / "hershey_roman.json"
    return bundled if bundled.is_file() else None


def _resolve_merge_stroke_font_path(cfg) -> Path | None:
    raw = (getattr(cfg, "stroke_font_merge_json_path", "") or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.is_file() else None
