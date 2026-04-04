"""Fluent UI 主窗口（PyQt5 + qfluentwidgets）。

说明：
- 仅本机使用：依赖 PyQt-Fluent-Widgets（GPL-3.0）与 PyQt5。
- core/ 不受影响；这里只替换 UI 观感与控件体系。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import time

from PyQt5.QtCore import QEvent, QPoint, QSize, QTimer, QUrl, Qt
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
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
    QComboBox,
    QMessageBox,
    QInputDialog,
    QFileDialog,
    QFrame,
    QGraphicsView,
    QGridLayout,
    QGroupBox,
    QFontComboBox,
    QLineEdit,
    QLabel,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QStackedWidget,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
    QUndoStack,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
)

from qfluentwidgets import (
    Action,
    CommandBar,
    FluentWindow,
    FluentIcon,
    CheckBox,
    ComboBox,
    InfoBar,
    InfoBarPosition,
    NavigationItemPosition,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SpinBox,
    SwitchButton,
    TextEdit,
    Theme,
    TitleLabel,
    setTheme,
)
from qfluentwidgets.common.config import qconfig
from qfluentwidgets.common.style_sheet import setCustomStyleSheet

from inkscape_wps.core.config_io import load_machine_config
from inkscape_wps.core.config_io import save_machine_config
from inkscape_wps.core.hershey import HersheyFontMapper, map_document_lines
from inkscape_wps.core.coordinate_transform import transform_paths
from inkscape_wps.core.gcode import order_paths_nearest_neighbor, paths_to_gcode
from inkscape_wps.core.grbl import GrblController, GrblSendError, parse_bf_field, verify_serial_responsive
from inkscape_wps.core.serial_discovery import filter_ports, list_port_infos
from inkscape_wps.core.project_io import load_project_file, save_project_file, write_text_atomic
from inkscape_wps.core.project_io import deserialize_vector_paths, serialize_vector_paths
from inkscape_wps.core.types import Point, VectorPath, paths_bounding_box
from inkscape_wps.ui.document_bridge_pyqt5 import (
    apply_default_tab_stops,
    stroke_editor_to_layout_lines,
    text_edit_to_layout_lines,
)
from inkscape_wps.ui.drawing_view_model_pyqt5 import DrawingViewModelPyQt5
from inkscape_wps.ui.presentation_editor_pyqt5 import WpsPresentationEditorPyQt5
from inkscape_wps.ui.stroke_text_editor import StrokeTextEditor
from inkscape_wps.ui.nonword_undo_pyqt5 import NonWordEditCommandPyQt5, capture_nonword_state_pyqt5
from inkscape_wps.ui.table_editor_pyqt5 import WpsTableEditorPyQt5
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
from inkscape_wps.ui.wps_theme import WPS_ACCENT

_logger = logging.getLogger(__name__)


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
        self._pending_bf_for_rx_spin = False
        self._pending_program_after_m800: Optional[List[str]] = None

        self._sketch_paths: List[VectorPath] = []
        self._insert_paths_base: List[VectorPath] = []
        self._insert_vector_scale: float = 1.0
        self._insert_vector_dx_mm: float = 0.0
        self._insert_vector_dy_mm: float = 0.0
        self._device_setting_groups: List[QGroupBox] = []
        self._wps_font_combos: List[QFontComboBox] = []
        self._wps_font_spins: List[SpinBox] = []

        self._nonword_undo_stack = QUndoStack(self)
        self._nonword_undo_stack.setUndoLimit(300)
        self._nonword_undo_anchor: tuple[str, str, str, str] = ("", "", "", "")
        self._nonword_undo_restoring = False
        self._shown_word_mode_tip = False

        self._build_pages()
        # P1-5：页边距与三边编辑区（尤其演示页 QTextEdit）同步，避免预览/G-code 与屏显偏移。
        try:
            self._sync_fluent_editor_margins()
        except Exception:
            _logger.debug("同步编辑区页边距失败", exc_info=True)

        # 切换导航页时必须刷新预览：_work_paths() 按当前子页 objectName 取字/表/演示。
        # 注意：不能靠替换 _onCurrentInterfaceChanged——Qt 在首个子页加入时已把槽绑到原方法，替换实例属性不会重连信号。
        try:
            self.stackedWidget.currentChanged.connect(self._on_fluent_stack_page_changed)
        except Exception:
            _logger.debug("连接 stackedWidget.currentChanged 失败", exc_info=True)

        try:
            qconfig.themeChanged.connect(lambda *_: self._restyle_device_setting_groups())
        except Exception:
            pass

        self.setWindowTitle(f"{self._doc_title} - 写字机上位机")
        self.resize(1280, 860)
        self._update_action_states()
        self._update_status_line()
        # FluentWindow 首个子页是「文件」；切到「开始」避免用户误以为未启动（且开始页不再与「文字」抢同一控件）
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
        """Fluent 主窗：把 `cfg.document_margin_mm` 同步到演示页 QTextEdit 的 document margin（px）。

        说明：`text_edit_to_layout_lines` 使用 `cfg.document_margin_mm` 与 QTextEdit 的布局矩形计算行基线；
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
        """演示页编辑器获得焦点时刷新「撤销/重做」菜单状态（文档栈 vs 整页栈）。"""
        if event.type() == QEvent.FocusIn and obj is self._presentation_editor.slide_editor():
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
                background-color: #eef1f4;
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
                    background-color: #eceff2;
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

    # ---------- UI ----------
    def _build_pages(self) -> None:
        # File Backstage（类 WPS 文件后台视图：左导航 + 右内容）
        self._file_page = QWidget()
        self._file_page.setObjectName("file")
        fv = QVBoxLayout(self._file_page)
        fv.setContentsMargins(16, 16, 16, 16)
        fv.setSpacing(10)
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

        def _add_nav_item(text: str, stack_idx: int, icon_name: str, fallback: str = "FOLDER") -> None:
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
        iv.setSpacing(8)
        iv.addWidget(TitleLabel("文档信息"))
        self._backstage_info_doc = QLabel("")
        self._backstage_info_proj = QLabel("")
        self._backstage_info_soffice = QLabel("")
        cards = QSplitter()
        cards.setObjectName("backstageCards")
        cards.setChildrenCollapsible(False)
        card1 = QWidget()
        card1.setObjectName("backstageInfoCard")
        c1 = QVBoxLayout(card1)
        c1.setContentsMargins(8, 8, 8, 8)
        c1.setSpacing(4)
        c1.addWidget(TitleLabel("字数"))
        self._backstage_card_words = QLabel("0")
        c1.addWidget(self._backstage_card_words)
        c1.addStretch(1)
        card2 = QWidget()
        card2.setObjectName("backstageInfoCard")
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(8, 8, 8, 8)
        c2.setSpacing(4)
        c2.addWidget(TitleLabel("页数"))
        self._backstage_card_pages = QLabel("1")
        c2.addWidget(self._backstage_card_pages)
        c2.addStretch(1)
        card3 = QWidget()
        card3.setObjectName("backstageInfoCard")
        c3 = QVBoxLayout(card3)
        c3.setContentsMargins(8, 8, 8, 8)
        c3.setSpacing(4)
        c3.addWidget(TitleLabel("最近保存"))
        self._backstage_card_saved = QLabel("未保存")
        c3.addWidget(self._backstage_card_saved)
        c3.addStretch(1)
        card4 = QWidget()
        card4.setObjectName("backstageInfoCard")
        c4 = QVBoxLayout(card4)
        c4.setContentsMargins(8, 8, 8, 8)
        c4.setSpacing(4)
        c4.addWidget(TitleLabel("当前模式"))
        self._backstage_card_mode = QLabel("文字")
        c4.addWidget(self._backstage_card_mode)
        c4.addStretch(1)
        cards.addWidget(card1)
        cards.addWidget(card2)
        cards.addWidget(card3)
        cards.addWidget(card4)
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
        self._backstage_recent.currentItemChanged.connect(self._on_backstage_recent_selection_changed)
        lrv.addWidget(self._backstage_recent, 1)
        rwrap.addWidget(left_recent)

        right_detail = QWidget()
        rdv = QVBoxLayout(right_detail)
        rdv.setContentsMargins(8, 0, 0, 0)
        rdv.setSpacing(8)
        rdv.addWidget(TitleLabel("文件详情"))
        self._backstage_detail_name = QLabel("未选择文件")
        self._backstage_detail_name.setWordWrap(True)
        self._backstage_detail_path = QLabel("")
        self._backstage_detail_path.setWordWrap(True)
        self._backstage_detail_type = QLabel("")
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
        e1 = PrimaryPushButton("导出 DOCX")
        e1.clicked.connect(self._export_docx)
        e2 = PushButton("导出 XLSX")
        e2.clicked.connect(self._export_xlsx)
        e3 = PushButton("导出 PPTX")
        e3.clicked.connect(self._export_pptx)
        e3b = PushButton("导出 Markdown")
        e3b.setToolTip("文字页导出正文；演示页导出为多页（以 --- 分隔）")
        e3b.clicked.connect(self._export_markdown)
        e4 = PushButton("导出 G-code")
        e4.clicked.connect(self._export_gcode_to_file_stub)
        ev.addWidget(e1)
        ev.addWidget(e2)
        ev.addWidget(e3)
        ev.addWidget(e3b)
        ev.addWidget(e4)
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
        self.addSubInterface(self._file_page, icon=FluentIcon.FOLDER, text="文件", position=NavigationItemPosition.TOP)

        # Start page: 先把“文字/表格/演示”三个工作区的骨架搭起来，后续再迁移预览/拖拽/串口等复杂逻辑
        home = QWidget()
        home.setObjectName("home")
        self._home_page = home
        lay = QVBoxLayout(home)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

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
        left_v = QVBoxLayout(left)
        left_v.setContentsMargins(0, 0, 0, 0)
        left_v.setSpacing(6)
        self._btn_open = PushButton("打开工程…")
        self._btn_open.clicked.connect(self._open_project)
        self._btn_save = PrimaryPushButton("保存工程")
        self._btn_save.clicked.connect(self._save_project)
        self._btn_export_g = PushButton("导出 G-code…")
        self._btn_export_g.clicked.connect(self._export_gcode_to_file_stub)
        self._btn_spec = PushButton("SPEC…")
        self._btn_spec.clicked.connect(self._open_spec_document)
        self._btn_ai_prompts = PushButton("AI_PROMPTS…")
        self._btn_ai_prompts.clicked.connect(self._open_ai_prompts_document)
        left_v.addWidget(self._btn_open)
        left_v.addWidget(self._btn_save)
        left_v.addWidget(self._btn_export_g)
        left_v.addWidget(self._btn_spec)
        left_v.addWidget(self._btn_ai_prompts)
        left_v.addStretch(1)
        bar_l.addWidget(left)

        # 右侧：简要指引（优先可读性，减少「未完工」观感）
        right = QFrame()
        right.setObjectName("homeQuickCard")
        right.setStyleSheet(
            """
            QFrame#homeQuickCard {
                background-color: #f5f8fa;
                border: 1px solid #d8dee6;
                border-radius: 10px;
            }
            """
        )
        rv = QVBoxLayout(right)
        rv.setContentsMargins(14, 14, 14, 14)
        rv.setSpacing(8)
        rv.addWidget(TitleLabel("快速上手"))
        desc = QLabel(
            "1. 对标 WPS 三件套：「文字」单线书写、「表格」网格、「演示」左列表+多页富文本；预览随当前页切换。\n"
            "2. 「开始」条：剪贴板 + 字体 + B/I/U + 对齐；表格页「行列」快捷；演示页「段落」列表/缩进 + 「样式」标题1/标题2/正文预设（随工程保存）；表格/演示右键亦可用。预览：缩放、复制/导出 PNG；幻灯片列表：页管理。状态栏：字数/表格尺寸/页码。「视图」：预览缩放与导出。\n"
            "3. 「设备」页核对 Z/进给/坐标/纸张；先导出 G-code 再小范围试写。\n"
            "4. 详见菜单或 SPEC.md。"
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
        # （同一 QWidget 不能挂到两个父级；此前 home 与「文字」共用 _workspace 会导致 home 侧被掏空。）
        split = QSplitter()
        split.setChildrenCollapsible(False)
        home_left = QWidget()
        hl = QVBoxLayout(home_left)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        hl.addWidget(TitleLabel("开始"))
        _home_hint = QLabel("左侧导航进入「文字」编辑书写内容；本页右侧为路径预览与日志（串口连接后在「设备」页查看详情）。")
        _home_hint.setWordWrap(True)
        hl.addWidget(_home_hint)
        hl.addStretch(1)

        task_wrap = QWidget()
        tv = QVBoxLayout(task_wrap)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(10)
        self._preview = _PreviewView()
        self._preview.setContextMenuPolicy(Qt.CustomContextMenu)
        self._preview.customContextMenuRequested.connect(
            lambda pos: self._open_preview_context_menu(self._preview.mapToGlobal(pos))
        )
        self._log = PlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("日志：预览刷新与部分状态；串口收发详情见「设备」页右侧。")
        tv.addWidget(self._preview, 3)
        tv.addWidget(self._log, 2)
        split.addWidget(home_left)
        split.addWidget(task_wrap)
        split.setStretchFactor(0, 7)
        split.setStretchFactor(1, 3)
        lay.addWidget(split, 1)

        self._workspace = QWidget()
        wv = QVBoxLayout(self._workspace)
        wv.setContentsMargins(0, 0, 0, 0)
        wv.setSpacing(8)
        title_row = QWidget()
        tr = QHBoxLayout(title_row)
        tr.setContentsMargins(0, 0, 0, 0)
        tr.setSpacing(10)
        self._workspace_title = TitleLabel("文字")
        tr.addWidget(self._workspace_title)
        tr.addStretch(1)
        tr.addWidget(QLabel("单线行距"))
        self._stroke_line_spacing_spin = QDoubleSpinBox()
        self._stroke_line_spacing_spin.setRange(1.0, 3.0)
        self._stroke_line_spacing_spin.setSingleStep(0.05)
        self._stroke_line_spacing_spin.setDecimals(2)
        self._stroke_line_spacing_spin.setValue(float(getattr(self._cfg, "stroke_editor_line_spacing", 1.45)))
        tr.addWidget(self._stroke_line_spacing_spin)
        wv.addWidget(title_row)

        fmt_word = QWidget()
        fmt_word.setStyleSheet(
            "background-color:#f3f5f7;border:1px solid #dfe6ec;border-radius:6px;"
        )
        fwr = QHBoxLayout(fmt_word)
        fwr.setContentsMargins(6, 4, 6, 4)
        fwr.setSpacing(6)
        self._append_wps_format_bar(fwr)
        fwr.addStretch(1)
        wv.addWidget(fmt_word)

        self._workspace_stack = QWidget()
        wsv = QVBoxLayout(self._workspace_stack)
        wsv.setContentsMargins(0, 0, 0, 0)
        wsv.setSpacing(0)

        self._word_editor = StrokeTextEditor(self._cfg, self._mapper)
        self._word_editor.textChanged.connect(self._refresh_preview)
        self._word_editor.textChanged.connect(self._refresh_undo_redo_menu_state)
        self._word_editor.textChanged.connect(self._update_status_line)
        self._stroke_line_spacing_spin.valueChanged.connect(self._on_stroke_line_spacing_changed)
        wsv.addWidget(self._word_editor)

        wv.addWidget(self._workspace_stack, 1)

        # 底部状态条（轻量，模仿 WPS 底部状态栏）
        self._status_line = QLabel()
        self._status_line.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._status_line.setStyleSheet(
            "QLabel{padding:6px 10px;color:#3d444d;background:#e8ecf0;border:1px solid #cfd6de;border-radius:6px;}"
        )
        lay.addWidget(self._status_line)

        # 添加为 FluentWindow 的子页面
        self.addSubInterface(home, icon=FluentIcon.HOME, text="开始", position=NavigationItemPosition.TOP)

        self._word_page = QWidget()
        self._word_page.setObjectName("word")
        word_l = QVBoxLayout(self._word_page)
        word_l.setContentsMargins(12, 12, 12, 12)
        word_l.setSpacing(10)
        word_l.addWidget(self._workspace, 1)
        self.addSubInterface(self._word_page, icon=FluentIcon.EDIT, text="文字", position=NavigationItemPosition.TOP)

        self._table_page = QWidget()
        self._table_page.setObjectName("table")
        table_l = QVBoxLayout(self._table_page)
        table_l.setContentsMargins(12, 12, 12, 12)
        table_l.setSpacing(10)
        table_l.addWidget(TitleLabel("表格"))
        self._table_editor = WpsTableEditorPyQt5(self._cfg)
        self._table_editor.set_font_point_size_resolver(
            lambda: float(
                self._word_editor.font().pointSizeF()
                or self._word_editor.font().pointSize()
                or 12
            )
        )
        self._table_editor.contentChanged.connect(self._refresh_preview)
        self._table_editor.contentChanged.connect(self._on_nonword_content_changed)
        self._table_editor.contentChanged.connect(self._update_status_line)
        self._table_editor.connect_toolbar_context_refresh(self._wps_refresh_font_toolbar_context)
        fmt_tbl = QWidget()
        fmt_tbl.setStyleSheet(
            "background-color:#f3f5f7;border:1px solid #dfe6ec;border-radius:6px;"
        )
        ftr = QHBoxLayout(fmt_tbl)
        ftr.setContentsMargins(6, 4, 6, 4)
        ftr.setSpacing(6)
        self._append_wps_format_bar(ftr)
        self._append_wps_table_rowcol_buttons(ftr)
        ftr.addStretch(1)
        table_l.addWidget(fmt_tbl)
        table_l.addWidget(self._table_editor, 1)
        self.addSubInterface(self._table_page, icon=FluentIcon.LAYOUT, text="表格", position=NavigationItemPosition.TOP)

        self._slides_page = QWidget()
        self._slides_page.setObjectName("slides")
        ppt_l = QVBoxLayout(self._slides_page)
        ppt_l.setContentsMargins(12, 12, 12, 12)
        ppt_l.setSpacing(10)
        ppt_l.addWidget(TitleLabel("演示"))
        self._presentation_editor = WpsPresentationEditorPyQt5(self._cfg)
        self._presentation_editor.contentChanged.connect(self._refresh_preview)
        self._presentation_editor.contentChanged.connect(self._on_nonword_content_changed)
        self._presentation_editor.contentChanged.connect(self._update_status_line)
        _slide_te = self._presentation_editor.slide_editor()
        _slide_te.cursorPositionChanged.connect(self._wps_refresh_font_toolbar_context)
        _slide_te.selectionChanged.connect(self._wps_refresh_font_toolbar_context)
        fmt_ppt = QWidget()
        fmt_ppt.setStyleSheet(
            "background-color:#f3f5f7;border:1px solid #dfe6ec;border-radius:6px;"
        )
        fpr = QHBoxLayout(fmt_ppt)
        fpr.setContentsMargins(6, 4, 6, 4)
        fpr.setSpacing(6)
        self._append_wps_format_bar(fpr)
        self._append_wps_slide_paragraph_buttons(fpr)
        self._append_wps_slide_style_presets(fpr)
        fpr.addStretch(1)
        ppt_l.addWidget(fmt_ppt)
        ppt_l.addWidget(self._presentation_editor, 1)
        self.addSubInterface(self._slides_page, icon=FluentIcon.VIEW, text="演示", position=NavigationItemPosition.TOP)

        self._install_editor_context_menus()

        device_page = QWidget()
        device_page.setObjectName("device")
        dv = QVBoxLayout(device_page)
        dv.setContentsMargins(12, 12, 12, 12)
        dv.setSpacing(10)
        dv.addWidget(TitleLabel("设备与机床"))

        row = QSplitter()
        row.setChildrenCollapsible(False)

        left_scroll = QScrollArea()
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setWidgetResizable(True)
        left_inner = QWidget()
        lv = QVBoxLayout(left_inner)
        lv.setContentsMargins(0, 0, 8, 0)
        lv.setSpacing(6)

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
        _kxi_hint = QLabel("使用 Hershey / 非奎享 JSON 时可忽略；奎享大包建议在首次排版前设好再加载字库。")
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

        gb_serial = QGroupBox("串口与发送")
        self._register_device_setting_group(gb_serial)
        sv = QVBoxLayout(gb_serial)
        sv.setSpacing(8)
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
        self._cb_stream = SwitchButton()
        self._cb_stream.setChecked(bool(getattr(self._cfg, "grbl_streaming", False)))
        self._cb_stream.checkedChanged.connect(lambda c: setattr(self._cfg, "grbl_streaming", bool(c)))
        self._rx_buf_spin = SpinBox()
        self._rx_buf_spin.setRange(32, 16384)
        self._rx_buf_spin.setValue(int(getattr(self._cfg, "grbl_rx_buffer_size", 128)))
        self._rx_buf_spin.valueChanged.connect(lambda v: setattr(self._cfg, "grbl_rx_buffer_size", int(v)))

        self._btn_connect = PrimaryPushButton("连接")
        self._btn_connect.clicked.connect(self._toggle_serial)
        self._btn_send = PushButton("发送当前 G-code")
        self._btn_send.setEnabled(False)
        self._btn_send.clicked.connect(self._send_gcode)
        self._btn_send_pause_m800 = PushButton("发送（遇 M800 暂停）")
        self._btn_send_pause_m800.setEnabled(False)
        self._btn_send_pause_m800.clicked.connect(self._send_gcode_pause_at_m800)
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

        sv.addWidget(QLabel("端口"))
        sv.addWidget(self._port_combo)
        sv.addWidget(self._btn_ports)
        sv.addWidget(QLabel("波特率"))
        sv.addWidget(self._baud_spin)
        sv.addWidget(QLabel("Streaming"))
        sv.addWidget(self._cb_stream)
        sv.addWidget(QLabel("RX 缓冲预算（字节估算）"))
        sv.addWidget(self._rx_buf_spin)
        sv.addWidget(self._btn_connect)
        sv.addWidget(self._btn_send)
        sv.addWidget(self._btn_send_pause_m800)
        sv.addWidget(self._btn_send_resume)
        sv.addWidget(self._btn_bf_rx)
        sv.addWidget(self._btn_m800)
        sv.addWidget(self._btn_paper_flow)
        h_run = QHBoxLayout()
        h_run.addWidget(self._btn_hold)
        h_run.addWidget(self._btn_start)
        sv.addLayout(h_run)
        lv.addWidget(gb_serial)

        gb_gc = QGroupBox("程序头尾与附加 G-code")
        self._register_device_setting_group(gb_gc)
        gv = QVBoxLayout(gb_gc)
        gv.setSpacing(8)
        self._cb_g92 = CheckBox("使用 G92（程序头对零）")
        self._cb_g92.setChecked(bool(getattr(self._cfg, "gcode_use_g92", True)))
        self._cb_g92.stateChanged.connect(lambda _: setattr(self._cfg, "gcode_use_g92", self._cb_g92.isChecked()))
        self._cb_m30 = CheckBox("结尾用 M30（否则 M2）")
        self._cb_m30.setChecked(bool(getattr(self._cfg, "gcode_end_m30", False)))
        self._cb_m30.stateChanged.connect(lambda _: setattr(self._cfg, "gcode_end_m30", self._cb_m30.isChecked()))
        self._prefix_edit = PlainTextEdit()
        self._prefix_edit.setPlaceholderText("程序前缀（每行一条，可含 M800 / [ESP800] 等）")
        self._prefix_edit.setPlainText(str(getattr(self._cfg, "gcode_program_prefix", "")))
        self._prefix_edit.setFixedHeight(72)
        self._prefix_edit.textChanged.connect(lambda: setattr(self._cfg, "gcode_program_prefix", self._prefix_edit.toPlainText()))
        self._suffix_edit = PlainTextEdit()
        self._suffix_edit.setPlaceholderText("程序后缀（每行一条）")
        self._suffix_edit.setPlainText(str(getattr(self._cfg, "gcode_program_suffix", "")))
        self._suffix_edit.setFixedHeight(72)
        self._suffix_edit.textChanged.connect(lambda: setattr(self._cfg, "gcode_program_suffix", self._suffix_edit.toPlainText()))
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
        self._cb_rapid_after_up.stateChanged.connect(lambda _: self._on_device_machine_value_changed())
        for _cb in (
            self._cb_coord_mirror_x,
            self._cb_coord_mirror_y,
            self._cb_invert_x,
            self._cb_invert_y,
        ):
            _cb.stateChanged.connect(lambda _: self._on_device_machine_value_changed())

        self._dev_log = PlainTextEdit()
        self._dev_log.setReadOnly(True)
        self._dev_log.setPlaceholderText("设备日志…")
        row.addWidget(self._dev_log)
        row.setStretchFactor(1, 1)
        dv.addWidget(row, 1)

        self.addSubInterface(device_page, icon=FluentIcon.DEVELOPER_TOOLS, text="设备", position=NavigationItemPosition.BOTTOM)
        self._refresh_ports()
        self._update_status_line()

        help_page = QWidget()
        help_page.setObjectName("help")
        hv = QVBoxLayout(help_page)
        hv.setContentsMargins(16, 16, 16, 16)
        hv.setSpacing(10)
        hv.addWidget(TitleLabel("帮助"))
        hl = QLabel(
            "菜单栏「帮助」可打开快速入门说明；"
            "「查阅 SPEC.md」与「查阅 AI_PROMPTS.md」会用系统默认程序打开仓库内文档。"
        )
        hl.setWordWrap(True)
        hl.setStyleSheet("color:#3d444d;font-size:13px;")
        hv.addWidget(hl)
        hv.addStretch(1)
        self.addSubInterface(help_page, icon=FluentIcon.HELP, text="帮助", position=NavigationItemPosition.BOTTOM)

        self._setup_symbol_panel()
        try:
            self._wps_refresh_font_toolbar_context()
        except Exception:
            pass
        self._nonword_undo_stack.canUndoChanged.connect(self._refresh_undo_redo_menu_state)
        self._nonword_undo_stack.canRedoChanged.connect(self._refresh_undo_redo_menu_state)
        self._reset_nonword_undo_anchor()
        self._refresh_undo_redo_menu_state()

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

        # 编辑（对标 WPS/Word 常用字符格式）
        m_edit = RoundMenu("编辑", self)
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
        self._act_cut.setToolTip("剪切（编辑区内 Ctrl+X）；表格为当前单元格整格。不设菜单快捷键以免与单线编辑区重复触发。")
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
        self._act_al_left.triggered.connect(lambda: self._set_fluent_alignment(Qt.AlignLeft | Qt.AlignAbsolute))
        m_edit.addAction(self._act_al_left)
        self._act_al_center = Action(text="居中")
        self._act_al_center.setShortcut(_paragraph_align_shortcut("Ctrl+E"))
        self._act_al_center.triggered.connect(lambda: self._set_fluent_alignment(Qt.AlignHCenter))
        m_edit.addAction(self._act_al_center)
        self._act_al_right = Action(text="右对齐")
        self._act_al_right.setShortcut(_paragraph_align_shortcut("Ctrl+R"))
        self._act_al_right.triggered.connect(lambda: self._set_fluent_alignment(Qt.AlignRight | Qt.AlignAbsolute))
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
        _add_top_menu("编辑", m_edit)

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
        self._act_preview_copy_image.setToolTip("将当前路径预览视口可见内容复制到系统剪贴板（位图）。")
        self._act_preview_copy_image.triggered.connect(self._preview_copy_visible_to_clipboard)
        m_view.addAction(self._act_preview_copy_image)
        self._act_preview_export_png = Action(text="导出可见预览为 PNG…")
        try:
            self._act_preview_export_png.setIcon(FluentIcon.FOLDER.icon())
        except Exception:
            _logger.debug("视图菜单图标 FOLDER 不可用", exc_info=True)
        self._act_preview_export_png.setToolTip("将当前视口内的预览保存为 PNG 文件（与缩放/平移后的画面一致）。")
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

    def _on_fluent_stack_page_changed(self, _index: int = 0) -> None:
        """导航切换子页后刷新预览与状态，使 _work_paths() 与画面一致（不依赖替换 _onCurrentInterfaceChanged）。"""
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

    def _capture_nonword_tuple(self) -> tuple[str, str, str, str]:
        return capture_nonword_state_pyqt5(
            self._table_editor.to_project_blob(),
            self._presentation_editor.slides_storage(),
            self._presentation_editor.master_storage(),
            serialize_vector_paths(self._sketch_paths),
        )

    def _restore_nonword_state(self, state: tuple[str, str, str, str]) -> None:
        self._nonword_undo_restoring = True
        try:
            tb_s, sl_s, sm_s, sk_s = state
            self._table_editor.from_project_blob(json.loads(tb_s))
            slides = json.loads(sl_s)
            master = json.loads(sm_s) if sm_s else {}
            self._presentation_editor.load_slides(slides if isinstance(slides, list) else [""])
            self._presentation_editor.load_master_storage(master if isinstance(master, dict) else {})
            self._sketch_paths = deserialize_vector_paths(json.loads(sk_s))
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
        else:
            self._act_undo.setEnabled(self._word_editor.canUndo())
            self._act_redo.setEnabled(self._word_editor.canRedo())

    def _perform_undo(self) -> None:
        pid = self._current_page_id()
        if pid == "slides" and self._focus_in_slide_editor():
            self._presentation_editor.slide_editor().undo()
        elif pid in ("table", "slides"):
            self._nonword_undo_stack.undo()
        else:
            self._word_editor.undo()
        self._refresh_undo_redo_menu_state()

    def _perform_redo(self) -> None:
        pid = self._current_page_id()
        if pid == "slides" and self._focus_in_slide_editor():
            self._presentation_editor.slide_editor().redo()
        elif pid in ("table", "slides"):
            self._nonword_undo_stack.redo()
        else:
            self._word_editor.redo()
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
        if name == "word" or name == "home" or not name:
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

    def _append_wps_format_bar(self, row: QHBoxLayout) -> None:
        """「开始」：剪贴板 + 字体/字号 + B/I/U + 对齐（对标 WPS「开始」选项卡分组）。"""
        lab = QLabel("开始")
        lab.setStyleSheet("color:#6b7280;font-size:11px;font-weight:600;padding-right:4px;")
        row.addWidget(lab)

        self._append_wps_clipboard_buttons(row)
        self._append_wps_font_controls(row)

        def _fmt_btn(text: str, tip: str, slot) -> None:
            b = PushButton(text)
            b.setFixedSize(32, 28)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b)

        _fmt_btn("B", "加粗 (Ctrl+B)", self._toggle_fluent_bold)
        _fmt_btn("I", "倾斜 (Ctrl+I)", self._toggle_fluent_italic)
        _fmt_btn("U", "下划线 (Ctrl+U)", self._toggle_fluent_underline)

        sep = QLabel(" │ ")
        sep.setStyleSheet("color:#cfd6de;")
        row.addWidget(sep)

        _fmt_btn("左", "左对齐 (Ctrl+L)", lambda: self._set_fluent_alignment(int(Qt.AlignLeft | Qt.AlignAbsolute)))
        _fmt_btn("中", "居中 (Ctrl+E)", lambda: self._set_fluent_alignment(int(Qt.AlignHCenter)))
        _fmt_btn("右", "右对齐 (Ctrl+R)", lambda: self._set_fluent_alignment(int(Qt.AlignRight | Qt.AlignAbsolute)))
        _fmt_btn("两端", "两端对齐 (Ctrl+J)", lambda: self._set_fluent_alignment(int(Qt.AlignJustify)))

    def _append_wps_table_rowcol_buttons(self, row: QHBoxLayout) -> None:
        """表格页格式条：插入/删除行列快捷（与网格右键一致）。"""
        lab = QLabel("行列")
        lab.setStyleSheet("color:#6b7280;font-size:11px;font-weight:600;padding-left:4px;padding-right:2px;")
        row.addWidget(lab)

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
        lab = QLabel("段落")
        lab.setStyleSheet("color:#6b7280;font-size:11px;font-weight:600;padding-left:4px;padding-right:2px;")
        row.addWidget(lab)

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
            a_num.triggered.connect(lambda: self._slide_apply_list_style(QTextListFormat.ListDecimal))
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
        lab = QLabel("样式")
        lab.setStyleSheet("color:#6b7280;font-size:11px;font-weight:600;padding-left:4px;padding-right:2px;")
        row.addWidget(lab)

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
        sub = QLabel("剪贴板")
        sub.setStyleSheet("color:#6b7280;font-size:11px;font-weight:600;padding-right:2px;")
        row.addWidget(sub)

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
        sep = QLabel(" │ ")
        sep.setStyleSheet("color:#cfd6de;")
        row.addWidget(sep)

    def _append_wps_font_controls(self, row: QHBoxLayout) -> None:
        row.addWidget(QLabel("字体"))
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
        row.addWidget(QLabel("字号"))
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
        sep = QLabel(" │ ")
        sep.setStyleSheet("color:#cfd6de;")
        row.addWidget(sep)

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
            InfoBar.warning("查找", "当前页面不支持查找。", parent=self, position=InfoBarPosition.TOP)
            return False
        if not needle:
            InfoBar.warning("查找", "请输入要查找的文本。", parent=self, position=InfoBarPosition.TOP)
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
                InfoBar.info("查找", "已到文档末尾，未找到更多匹配。", parent=self, position=InfoBarPosition.TOP)

    def _replace_current_from_box(self) -> None:
        if self._current_page_id() == "table":
            q = self._find_edit.text().strip() if hasattr(self, "_find_edit") else ""
            rep = self._replace_edit.text() if hasattr(self, "_replace_edit") else ""
            if not q:
                InfoBar.warning("替换", "请输入要查找的文本。", parent=self, position=InfoBarPosition.TOP)
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
            InfoBar.warning("替换", "当前页面不支持替换。", parent=self, position=InfoBarPosition.TOP)
            return
        q = self._find_edit.text().strip() if hasattr(self, "_find_edit") else ""
        rep = self._replace_edit.text() if hasattr(self, "_replace_edit") else ""
        if not q:
            InfoBar.warning("替换", "请输入要查找的文本。", parent=self, position=InfoBarPosition.TOP)
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
                InfoBar.warning("全部替换", "请输入要查找的文本。", parent=self, position=InfoBarPosition.TOP)
                return
            n = self._table_editor.replace_all_in_table(q, rep)
            InfoBar.success("全部替换", f"已替换 {n} 处。", parent=self, position=InfoBarPosition.TOP)
            return

        e = self._active_text_edit()
        if e is None:
            InfoBar.warning("全部替换", "当前页面不支持替换。", parent=self, position=InfoBarPosition.TOP)
            return
        q = self._find_edit.text().strip() if hasattr(self, "_find_edit") else ""
        rep = self._replace_edit.text() if hasattr(self, "_replace_edit") else ""
        if not q:
            InfoBar.warning("全部替换", "请输入要查找的文本。", parent=self, position=InfoBarPosition.TOP)
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
        self._refresh_undo_redo_menu_state()

    def _update_status_line(self) -> None:
        try:
            cur = self.stackedWidget.currentWidget()
            cur_name = cur.objectName() if cur is not None else ""
        except Exception:
            cur_name = ""
        page = {"file": "文件", "home": "开始", "word": "文字", "table": "表格", "slides": "演示", "device": "设备", "help": "帮助"}.get(
            cur_name, "开始"
        )
        if page != "文件":
            self._last_active_mode = page
        conn = "已连接" if self._grbl is not None else "未连接"
        proj = self._project_path.name if self._project_path is not None else "未保存"
        extra = ""
        if cur_name == "word":
            try:
                extra = f"   字数：{len(self._word_editor.toPlainText())}"
            except Exception:
                pass
        elif cur_name == "table":
            try:
                tr, tc = self._table_editor.row_column_count()
                extra = f"   表格：{tr}×{tc}"
            except Exception:
                pass
        elif cur_name == "slides":
            try:
                extra = f"   {self._presentation_editor.status_line()}"
            except Exception:
                pass
        self._status_line.setText(
            f"文档：{self._doc_title}（{proj}）   页面：{page}   预览：{int(self._preview_zoom*100)}%   串口：{conn}{extra}"
        )
        self._refresh_backstage_info()

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
            write_text_atomic(p, json.dumps(self._recent_projects[:15], ensure_ascii=False, indent=2))
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
                    InfoBar.warning("最近打开", "文件不存在，已从列表移除。", parent=self, position=InfoBarPosition.TOP)
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
            QListWidget#backstageNav {
                background: #eef1f4;
                border: 1px solid #d0d8e0;
                border-radius: 8px;
                padding: 6px;
                outline: none;
            }
            QListWidget#backstageNav::item {
                color: #1f2328;
                padding: 8px 10px;
                border-radius: 6px;
                margin: 1px 0;
            }
            QListWidget#backstageNav::item:selected {
                background: #e6f4ea;
                color: #0f3d26;
                font-weight: 700;
            }
            QListWidget#backstageNav::item:hover {
                background: #eef3f7;
            }
            QWidget#backstageInfoCard {
                background: #f4f6f8;
                border: 1px solid #d0d8e0;
                border-radius: 8px;
            }
            QListWidget#backstageRecentList {
                background: #f4f6f8;
                border: 1px solid #d0d8e0;
                border-radius: 8px;
                outline: none;
            }
            QListWidget#backstageRecentList::item {
                border-radius: 6px;
                padding: 8px 10px;
                margin: 3px 4px;
                color: #1f2328;
            }
            QListWidget#backstageRecentList::item:selected {
                background: #eaf4ff;
                color: #123a62;
            }
            QListWidget#backstageRecentList::item:hover {
                background: #f3f8fd;
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
        mode = {"file": "文件后台", "home": "开始", "word": "文字", "table": "表格", "slides": "演示", "device": "设备", "help": "帮助"}.get(
            cur_name, "开始"
        )
        if mode == "文件后台":
            return self._last_active_mode
        return mode

    def _estimate_doc_stats(self) -> tuple[int, int]:
        if not hasattr(self, "_word_editor"):
            return 0, 1
        mode = self._current_mode_label()
        if mode in ("文字", "开始", "文件后台"):
            text = self._word_editor.toPlainText()
            words = len("".join(ch for ch in text if not ch.isspace()))
            pages = max(1, (words + 799) // 800)
            return words, pages
        if mode == "演示":
            words = 0
            for s in self._presentation_editor.slides_storage():
                if (s or "").lstrip().startswith("<"):
                    d = QTextDocument()
                    d.setHtml(s or "")
                    t = d.toPlainText()
                else:
                    t = s or ""
                words += len("".join(ch for ch in t if not ch.isspace()))
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
                        words += len("".join(ch for ch in t if not ch.isspace()))
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
            it = QListWidgetItem("（暂无）")
            it.setData(Qt.UserRole, "")
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
            InfoBar.warning("最近打开", "文件不存在。", parent=self, position=InfoBarPosition.TOP)
            self._recent_projects = [x for x in self._recent_projects if x != s]
            self._save_recent_projects()
            self._update_action_states()
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
            self._backstage_detail_name.setText("未选择文件")
            self._backstage_detail_type.setText("")
            self._backstage_detail_path.setText("")
            self._backstage_btn_open.setEnabled(False)
            return
        p = Path(s)
        kind = detect_office_kind(p)
        k = {
            "docx": "Word 文档（DOCX）",
            "xlsx": "Excel 表格（XLSX）",
            "pptx": "PowerPoint 演示（PPTX）",
            "wps": "WPS 文字（WPS）",
            "et": "WPS 表格（ET）",
            "dps": "WPS 演示（DPS）",
            "md": "Markdown（MD）",
            "unknown": "工程文件/其他",
        }.get(kind, "文件")
        self._backstage_detail_name.setText(p.name)
        self._backstage_detail_type.setText(f"类型：{k}")
        self._backstage_detail_path.setText(f"路径：{s}")
        self._backstage_btn_open.setEnabled(p.is_file())

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
            InfoBar.error("保存失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        self.setWindowTitle(f"{self._doc_title} - 写字机上位机")
        self._last_saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        InfoBar.success("已保存", self._project_path.name, parent=self, position=InfoBarPosition.TOP)
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
        self.setWindowTitle(f"{self._doc_title} - 写字机上位机")
        self._update_action_states()
        self._update_status_line()

    def _open_project_path(self, path: Path) -> None:
        try:
            d = load_project_file(path)
        except Exception as e:
            InfoBar.error("打开失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        self._project_path = path
        self._doc_title = str(d.get("title") or self._project_path.stem)
        try:
            self._last_saved_at = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
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
        self.setWindowTitle(f"{self._doc_title} - 写字机上位机")
        self._push_recent(self._project_path)
        self._update_action_states()
        self._update_status_line()
        InfoBar.success("已打开工程", self._project_path.name, parent=self, position=InfoBarPosition.TOP)

    def _open_office_or_wps_file(self, path: Path) -> None:
        p = path
        try:
            p = try_convert_wps_private_to_office(p)
            kind = detect_office_kind(p)
            if kind == "docx":
                self._new_project()
                self._doc_title = p.stem
                self._word_editor.setHtml(import_docx_to_html(p))
                self._safe_switch_to(self._word_page, "文字")
            elif kind == "xlsx":
                self._new_project()
                self._doc_title = p.stem
                self._apply_table_blob(import_xlsx_to_table_blob(p))
                self._safe_switch_to(self._table_page, "表格")
            elif kind == "pptx":
                self._new_project()
                self._doc_title = p.stem
                slides = import_pptx_to_slides(p)
                self._apply_slides_storage(slides)
                self._safe_switch_to(self._slides_page, "演示")
            elif kind == "md":
                self._new_project()
                self._doc_title = p.stem
                slides_md = import_markdown_file_to_slides_plain(p)
                if slides_md is not None:
                    self._apply_slides_storage(slides_md)
                    self._safe_switch_to(self._slides_page, "演示")
                else:
                    self._word_editor.setPlainText(import_markdown_to_plain(p))
                    self._safe_switch_to(self._word_page, "文字")
            else:
                raise OfficeImportError("不支持的文件类型。")
        except OfficeImportError as e:
            InfoBar.error("导入失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        except Exception as e:
            InfoBar.error("导入失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return

        # 作为“未保存工程”的临时内容导入
        self._project_path = None
        try:
            self._last_saved_at = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        except OSError:
            _logger.debug("读取导入文件 mtime 失败：%s", p, exc_info=True)
            self._last_saved_at = None
        self.setWindowTitle(f"{self._doc_title} - 写字机上位机")
        self._reset_nonword_undo_anchor()
        self._refresh_preview()
        self._push_recent(p)
        self._update_action_states()
        self._update_status_line()
        InfoBar.success("已导入", p.name, parent=self, position=InfoBarPosition.TOP)

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
            pts = tuple(Point(cx + (p.x - cx) * s + dx, cy + (p.y - cy) * s + dy) for p in vp.points)
            out.append(VectorPath(pts, pen_down=vp.pen_down))
        return out

    def _preview_paths(self) -> List[VectorPath]:
        # 按当前页决定预览来源（避免三种内容叠在一起）
        try:
            cur = self.stackedWidget.currentWidget()
            cur_name = cur.objectName() if cur is not None else ""
        except Exception:
            cur_name = ""

        mm_per_pt = float(self._cfg.mm_per_pt)

        if cur_name == "table":
            base = self._table_paths()
        elif cur_name == "slides":
            base = self._slides_paths()
        else:
            # 默认：文字
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
        return map_document_lines(self._mapper, lines, mm_per_pt=float(self._cfg.mm_per_pt))

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
        m.addAction(a_paste)
        m.addSeparator()
        a_del = Action(text="删除当前页")
        a_del.triggered.connect(self._presentation_editor.delete_slide_interactive)
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
        stem = "".join(c if c not in '<>:"/\\|?*' else "_" for c in (self._doc_title or "preview").strip())[:120]
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
        a_u.triggered.connect(self._perform_undo)
        m.addAction(a_u)
        a_r = Action(text="重做")
        a_r.triggered.connect(self._perform_redo)
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
        # 与右侧预览一致：输出当前 work paths
        g = paths_to_gcode(self._work_paths(), self._cfg, order=False)
        try:
            write_text_atomic(Path(path), g)
        except Exception as e:
            InfoBar.error("导出失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        InfoBar.success("已导出", Path(path).name, parent=self, position=InfoBarPosition.TOP)

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
            paragraphs = self._docx_paragraphs_from_editor()
            src_html = (self._active_text_edit() or self._word_editor).toHtml()
            export_docx(Path(path), paragraphs=paragraphs, html_text=src_html, prefer_soffice=True)
        except OfficeExportError as e:
            InfoBar.error("导出失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        except Exception as e:
            InfoBar.error("导出失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        InfoBar.success("已导出", Path(path).name, parent=self, position=InfoBarPosition.TOP)

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
            export_xlsx(Path(path), table_blob=self._capture_table_blob(), prefer_soffice=True)
        except OfficeExportError as e:
            InfoBar.error("导出失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        except Exception as e:
            InfoBar.error("导出失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        InfoBar.success("已导出", Path(path).name, parent=self, position=InfoBarPosition.TOP)

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
            # PPTX 导出：使用“套用母版页眉/页脚后的纯文本版本”
            export_pptx(Path(path), slides=self._capture_slides_storage_for_export(), prefer_soffice=True)
        except OfficeExportError as e:
            InfoBar.error("导出失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        except Exception as e:
            InfoBar.error("导出失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        InfoBar.success("已导出", Path(path).name, parent=self, position=InfoBarPosition.TOP)

    def _slides_plain_to_markdown(self) -> str:
        parts: list[str] = []
        for s in self._capture_slides_storage_for_export():
            st = (s or "").strip()
            if not st:
                continue
            if st.lstrip().startswith("<"):
                d = QTextDocument()
                d.setHtml(s or "")
                parts.append(d.toPlainText().strip())
            else:
                parts.append(st)
        if not parts:
            return ""
        return "\n\n---\n\n".join(parts)

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
        try:
            cur = self.stackedWidget.currentWidget()
            name = cur.objectName() if cur is not None else ""
        except Exception:
            name = ""
        if name == "slides":
            body = self._slides_plain_to_markdown()
        else:
            body = self._word_editor.toPlainText()
        try:
            export_markdown(Path(path), body=body)
        except Exception as e:
            InfoBar.error("导出失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        InfoBar.success("已导出", Path(path).name, parent=self, position=InfoBarPosition.TOP)

    def _docx_paragraphs_from_editor(self) -> List[DocParagraph]:
        """高保真（基础）：从 QTextDocument 抽取段落与字符级样式。"""
        ed = self._active_text_edit() or self._word_editor
        if not hasattr(ed, "document"):
            raw = ed.toPlainText().split("\n") if hasattr(ed, "toPlainText") else [""]
            if not raw:
                raw = [""]
            return [DocParagraph(runs=[DocRun(text=ln)]) for ln in raw]
        doc = ed.document()
        paras: List[DocParagraph] = []
        block = doc.firstBlock()
        while block.isValid():
            layout = block.layout()
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
                                font_pt=float(f.pointSizeF() if f.pointSizeF() > 0 else f.pointSize() or 0) or None,
                            )
                        )
                it += 1
            # 空段落也要保留
            if not runs:
                runs = [DocRun(text="")]
            paras.append(DocParagraph(runs=runs, align=al))
            block = block.next()
        return paras

    def _soffice_ready_hint(self) -> str:
        return "已检测到 soffice（高保真导出已启用）" if has_soffice() else "未检测到 soffice（使用纯 Python 导出）"

    # ---------- 串口 / GRBL ----------
    def _log_append(self, s: str) -> None:
        self._log.appendPlainText(str(s))
        if hasattr(self, "_dev_log"):
            self._dev_log.appendPlainText(str(s))

    def _refresh_ports(self) -> None:
        if not hasattr(self, "_port_combo"):
            return
        self._port_combo.clear()
        ports = filter_ports(list_port_infos(), bool(getattr(self._cfg, "serial_show_bluetooth_only", False)))
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
            self._btn_connect.setText("连接")
            self._btn_send.setEnabled(False)
            self._btn_send_pause_m800.setEnabled(False)
            self._btn_send_resume.setEnabled(False)
            self._btn_paper_flow.setEnabled(False)
            self._pending_program_after_m800 = None
            self._log_append("已断开串口")
            self._update_action_states()
            self._update_status_line()
            return
        try:
            import serial

            data = self._port_combo.currentData()
            port = (data if isinstance(data, str) and data.strip() else "") or self._port_combo.currentText().strip()
            if "—" in port:
                port = port.split("—", 1)[0].strip()
            if not port or port.startswith("（"):
                raise ValueError("请选择或输入串口设备路径")
            ser = serial.Serial(port, int(self._baud_spin.value()), timeout=0.1)
            ok_probe, probe_msg = verify_serial_responsive(ser, on_line=self._log_append)
            if not ok_probe:
                ser.close()
                InfoBar.error("串口无应答", probe_msg, parent=self, position=InfoBarPosition.TOP)
                return
            self._log_append(probe_msg)
            self._grbl = GrblController(
                ser,
                default_line_timeout_s=float(getattr(self._cfg, "grbl_line_timeout_s", 30.0)),
                on_status=self._on_grbl_status,
                on_log_line=self._log_append,
                on_protocol_error=lambda s: self._log_append(f"[协议] {s}"),
            )
            self._grbl.start_reader()
            time.sleep(0.05)
            self._btn_connect.setText("断开")
            self._btn_send.setEnabled(True)
            self._btn_send_pause_m800.setEnabled(True)
            self._btn_paper_flow.setEnabled(True)
            self._log_append(f"已打开 {port}")
            self._update_action_states()
            self._update_status_line()
        except Exception as e:
            InfoBar.error("串口", str(e), parent=self, position=InfoBarPosition.TOP)

    def _on_grbl_status(self, d: dict) -> None:
        self._log_append(str(d))
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
            "即将向机床发送单条 M800。\n\n请确认 M800 在你的固件中确实作为“暂停/换纸节点”。继续吗？",
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
            "即将发送“前缀 → M800 → 后缀”。\n\n到达 M800 后将停下等待你完成换纸/人工处理。\n继续吗？",
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
                "已发送前缀与 M800（到达流程节点）。完成换纸/人工处理后，点“继续（从 M800 后）”发送后缀。",
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
        self._update_pen_mode_dependent_widgets()

    def _on_fluent_pen_mode_changed(self, _index: int = 0) -> None:
        self._sync_device_machine_widgets_to_cfg()
        self._update_pen_mode_dependent_widgets()

    def _on_device_machine_value_changed(self, *_args) -> None:
        self._sync_device_machine_widgets_to_cfg()
        try:
            self._sync_fluent_editor_margins()
        except Exception:
            _logger.debug("设备页变更后同步编辑区页边距失败", exc_info=True)
        if hasattr(self, "_word_editor"):
            self._word_editor.update()
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

    def _save_config(self) -> None:
        self._sync_device_machine_widgets_to_cfg()
        try:
            save_machine_config(self._cfg, self._cfg_path)
        except Exception as e:
            self._log_append(f"[错误] 保存配置: {e}")
            InfoBar.error("保存配置失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        self._log_append(f"已保存配置 {self._cfg_path}")
        InfoBar.success("已保存配置", str(self._cfg_path), parent=self, position=InfoBarPosition.TOP)

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
            return
        if not self._confirm_dangerous_action(
            "发送 G-code",
            "即将向机床发送当前文档生成的 G-code。\n\n请再次确认：坐标零点、抬落笔模式、纸张/工作区是否正确。\n继续吗？",
        ):
            return
        self._sync_device_machine_widgets_to_cfg()
        g = paths_to_gcode(self._work_paths(), self._cfg, order=False)
        try:
            n_ok, n_tot = self._grbl.send_program(
                g,
                streaming=bool(getattr(self._cfg, "grbl_streaming", False)),
                rx_buffer_size=int(getattr(self._cfg, "grbl_rx_buffer_size", 128)),
            )
            self._log_append(f"已发送 {n_ok}/{n_tot} 行")
            InfoBar.success("发送完成", f"{n_ok}/{n_tot} 行", parent=self, position=InfoBarPosition.TOP)
        except GrblSendError as e:
            self._log_append(f"[错误] {e}")
            InfoBar.error("GRBL 发送失败", str(e), parent=self, position=InfoBarPosition.TOP)
        except Exception as e:
            self._log_append(f"[异常] {e}")
            InfoBar.error("发送失败", str(e), parent=self, position=InfoBarPosition.TOP)

    def _send_gcode_pause_at_m800(self) -> None:
        """发送程序，遇到第一条 M800 时停下，等待用户点击继续。"""
        if not self._grbl:
            return
        if not self._confirm_dangerous_action(
            "发送（遇 M800 暂停）",
            "将发送当前文档的 G-code，并在遇到第一条 M800 时停下等待。\n\n请确认：M800 定义与固件流程一致，且你已准备好“换纸/人工处理”。\n继续吗？",
        ):
            return
        self._sync_device_machine_widgets_to_cfg()
        self._pending_program_after_m800 = None
        g = paths_to_gcode(self._work_paths(), self._cfg, order=False)
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
            f"当前已在 M800 暂停，准备继续发送剩余 {len(after)} 行。\n\n确认换纸/人工处理已完成且机床状态正确。继续吗？",
        ):
            return
        try:
            for ln in after:
                self._grbl.send_line_sync(ln)
            self._log_append(f"已继续发送 {len(after)} 行")
            InfoBar.success("继续完成", f"{len(after)} 行", parent=self, position=InfoBarPosition.TOP)
        except Exception as e:
            self._log_append(f"[错误] 继续发送失败: {e}")
            InfoBar.error("继续失败", str(e), parent=self, position=InfoBarPosition.TOP)
        finally:
            self._pending_program_after_m800 = None
            self._btn_send_resume.setEnabled(False)


class _PreviewView(QGraphicsView):
    """PyQt5 预览视图：滚轮缩放 + 拖拽平移（macOS 下强制抓取鼠标）。"""

    def __init__(self) -> None:
        super().__init__()
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setRenderHints(
            self.renderHints()
            | QPainter.Antialiasing
            | QPainter.SmoothPixmapTransform
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

    def wheelEvent(self, event: QWheelEvent) -> None:
        # 以鼠标位置为中心缩放
        delta = event.angleDelta().y()
        if delta == 0:
            return super().wheelEvent(event)
        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        self._zoom = max(0.1, min(5.0, self._zoom * factor))
        self.scale(factor, factor)
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

