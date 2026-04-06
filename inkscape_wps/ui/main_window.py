"""主窗口：更贴近 WPS 的 Ribbon + 文件入口 + 状态栏 + 标尺。"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QCloseEvent,
    QColor,
    QDesktopServices,
    QFont,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPen,
    QShortcut,
    QTextCharFormat,
    QUndoStack,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFrame,
    QGraphicsRectItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from inkscape_wps.core.config import MachineConfig
from inkscape_wps.core.config_io import load_machine_config, save_machine_config
from inkscape_wps.core.coordinate_transform import transform_paths
from inkscape_wps.core.gcode import order_paths_nearest_neighbor, paths_to_gcode
from inkscape_wps.core.grbl import (
    GrblController,
    GrblSendError,
    parse_bf_field,
    verify_grbl_responsive,
)
from inkscape_wps.core.grbl_firmware_ref import GRBL_ESP32_DEFAULT_RX_BUFFER_SIZE
from inkscape_wps.core.hershey import HersheyFontMapper, map_document_lines
from inkscape_wps.core.kdraw_paths import suggest_gcode_fonts_dirs
from inkscape_wps.core.machine_monitor import MachineMonitor
from inkscape_wps.core.project_io import (
    deserialize_vector_paths,
    load_project_file,
    save_project_file,
    serialize_vector_paths,
    write_text_atomic,
)
from inkscape_wps.core.raster_trace import trace_image_to_svg
from inkscape_wps.core.serial_discovery import filter_ports, list_port_infos
from inkscape_wps.core.svg_import import vector_paths_from_svg_file, vector_paths_from_svg_string
from inkscape_wps.core.transport import TcpTextStream
from inkscape_wps.core.types import Point, VectorPath, paths_bounding_box
from inkscape_wps.ui.document_bridge import apply_default_tab_stops, text_edit_to_layout_lines
from inkscape_wps.ui.drawing_view_model import DrawingViewModel
from inkscape_wps.ui.math_symbols import populate_qmenu_symbols
from inkscape_wps.ui.nonword_undo import NonWordEditCommand, capture_nonword_state
from inkscape_wps.ui.presentation_editor import WpsPresentationEditor
from inkscape_wps.ui.ribbon import RibbonGroup, RibbonTabVSep, RibbonVSeparator, WpsRibbon
from inkscape_wps.ui.table_editor import WpsTableEditor
from inkscape_wps.ui.wps_theme import apply_wps_theme
from inkscape_wps.ui.wps_widgets import make_horizontal_ruler_mm

# 预览区手绘：相邻采样点最小间距（mm，文档坐标）
_MIN_SKETCH_SAMPLE_MM = 0.2


def _package_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def _preset_svg_dir() -> Path:
    return _package_data_dir() / "preset_svgs"


def _resolve_stroke_font_path(cfg: MachineConfig) -> Path | None:
    raw = (cfg.stroke_font_json_path or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if p.is_file():
            return p
    bundled = _package_data_dir() / "hershey_roman.json"
    if bundled.is_file():
        return bundled
    return None


def _resolve_merge_stroke_font_path(cfg: MachineConfig) -> Path | None:
    raw = (cfg.stroke_font_merge_json_path or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.is_file() else None


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._doc_title = "未命名文档"
        self._nonword_modified = False
        self._preview_zoom = 1.0
        self.resize(1280, 860)
        apply_wps_theme(self)

        _cfg_dir = Path.home() / ".config" / "inkscape-wps"
        self._cfg, self._cfg_path = load_machine_config(_cfg_dir)

        self._mapper = HersheyFontMapper(
            _resolve_stroke_font_path(self._cfg),
            merge_font_path=_resolve_merge_stroke_font_path(self._cfg),
            kuixiang_mm_per_unit=self._cfg.kuixiang_mm_per_unit,
        )
        self._view_model = DrawingViewModel(self._cfg)
        self._grbl: Optional[GrblController] = None
        self._machine_monitor = MachineMonitor()
        self._pending_bf_for_rx_spin = False
        self._job_state_text = "就绪"
        self._job_progress = (0, 0)
        self._nonword_undo_stack = QUndoStack(self)
        self._nonword_undo_stack.setUndoLimit(300)
        self._nonword_undo_anchor: tuple[str, str, str] = ("", "", "")
        self._nonword_undo_restoring = False
        self._sketch_paths: List[VectorPath] = []
        self._sketch_drag_pts: Optional[List[Point]] = None
        self._insert_paths_base: List[VectorPath] = []
        self._insert_vector_scale: float = 1.0
        self._insert_vector_cx_mm: float = 0.0
        self._insert_vector_cy_mm: float = 0.0
        self._insert_vector_dx_mm: float = 0.0
        self._insert_vector_dy_mm: float = 0.0
        self._insert_resize_drag: Optional[dict] = None
        self._insert_move_drag: Optional[dict] = None
        self._overlay_handle_rects_scene: List[QRectF] = []
        self._insert_overlay_bbox_scene: Optional[QRectF] = None
        self._project_path: Optional[Path] = None

        self._build_ui()
        self._status_poll_timer = QTimer(self)
        self._status_poll_timer.setInterval(700)
        self._status_poll_timer.timeout.connect(self._poll_grbl_status)
        self._status_poll_timer.start()
        self._table_editor.set_font_point_size_resolver(lambda: float(self._size_spin.value()))
        _f0 = self._editor.currentFont()
        # 提升文字抗锯齿策略（对“字体不清晰”通常最有效之一）
        try:
            _f0.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        except Exception:
            pass
        self._table_editor.apply_document_font(_f0)
        self._presentation_editor.apply_document_font(_f0)
        self._build_menus_and_quick_toolbar()
        self._build_status_bar()

        self._editor.textChanged.connect(self._on_document_changed)
        self._editor.textChanged.connect(self._schedule_status_update)
        self._editor.selectionChanged.connect(self._schedule_status_update)
        self._editor.document().modificationChanged.connect(self._update_window_title)
        doc = self._editor.document()
        doc.undoAvailable.connect(self._sync_undo_actions)
        if hasattr(doc, "redoAvailable"):
            doc.redoAvailable.connect(self._sync_redo_actions)
        self._editor.viewport().installEventFilter(self)
        self._editor.installEventFilter(self)
        self._preview.viewport().installEventFilter(self)
        self._preview.viewport().setMouseTracking(True)

        self._table_editor.contentChanged.connect(self._on_nonword_content_changed)
        self._presentation_editor.contentChanged.connect(self._on_nonword_content_changed)
        self._nonword_undo_stack.canUndoChanged.connect(self._refresh_undo_redo_from_stacks)
        self._nonword_undo_stack.canRedoChanged.connect(self._refresh_undo_redo_from_stacks)

        self._mapper.preload_background()
        self._on_document_changed()
        self._update_window_title()
        self._update_status_bar()
        self._sync_undo_actions(self._editor.document().isUndoAvailable())
        _d = self._editor.document()
        self._sync_redo_actions(_d.isRedoAvailable() if hasattr(_d, "isRedoAvailable") else False)
        self._reset_nonword_undo_anchor()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._preview.viewport():
            et = event.type()
            if (
                et == QEvent.Type.Leave
                and self._insert_resize_drag is None
                and self._insert_move_drag is None
                and self._sketch_drag_pts is None
            ):
                self._preview.viewport().unsetCursor()
            if et in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseMove,
                QEvent.Type.MouseButtonRelease,
            ):
                if self._preview_sketch_mouse_event(event):
                    return True
            if self._insert_paths_base and et in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseMove,
                QEvent.Type.MouseButtonRelease,
            ):
                if self._preview_vector_overlay_mouse_event(event):
                    return True
        if obj is self._editor.viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            self._update_status_bar()
        if obj is self._editor and event.type() == QEvent.Type.KeyRelease:
            self._update_status_bar()
        return super().eventFilter(obj, event)

    def _build_menus_and_quick_toolbar(self) -> None:
        mb = QMenuBar(self)
        self.setMenuBar(mb)

        m_file = mb.addMenu("文件")
        self._fill_standard_file_menu(m_file)

        m_edit = mb.addMenu("编辑")
        self._act_undo = QAction("撤销", self, triggered=self._perform_undo)
        m_edit.addAction(self._act_undo)
        self._act_redo = QAction("重做", self, triggered=self._perform_redo)
        m_edit.addAction(self._act_redo)
        m_edit.addSeparator()
        m_edit.addAction("全选", self._select_all_current)

        m_tool = mb.addMenu("工具")
        m_tool.addAction("生成 G-code…", self._show_gcode)
        m_tool.addAction("导出 G-code 到文件…", self._export_gcode_to_file)
        m_tool.addAction("查看缺失字符…", self._show_missing_glyphs_dialog)

        m_help = mb.addMenu("帮助")
        m_help.addAction("快速入门…", self._show_quick_start)
        m_help.addAction("查阅 SPEC（规格说明）…", self._open_spec_document)
        m_help.addAction("查阅 AI 提示词指南…", self._open_ai_prompts_document)
        m_help.addAction("查看缺失字符…", self._show_missing_glyphs_dialog)
        m_help.addSeparator()
        m_help.addAction(
            "关于",
            lambda: QMessageBox.information(
                self,
                "关于",
                "写字机上位机 · WPS 风格界面\n核心逻辑与 PyQt 视图分离，便于后续移植。\n"
                "详细能力见仓库根目录 SPEC.md；AI 协作提示词见 AI_PROMPTS.md。",
            ),
        )

        qt = QToolBar("快速访问")
        qt.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, qt)
        qt.addAction(self._act_undo)
        qt.addAction(self._act_redo)
        qt.addSeparator()
        self._act_open_project = QAction("打开工程", self, triggered=self._open_project)
        self._act_open_project.setShortcut(QKeySequence.StandardKey.Open)
        self._act_open_project.setToolTip("打开工程（Ctrl+O / Cmd+O）")
        qt.addAction(self._act_open_project)
        self._act_save_project = QAction("保存工程", self, triggered=self._save_project)
        self._act_save_project.setShortcut(QKeySequence.StandardKey.Save)
        self._act_save_project.setToolTip("保存工程（Ctrl+S / Cmd+S）；无路径时另存为")
        qt.addAction(self._act_save_project)
        qt.addSeparator()
        qt.addAction(QAction("保存配置", self, triggered=self._save_config))
        qt.addAction(QAction("生成 G-code", self, triggered=self._show_gcode))
        qt.addAction(QAction("导出 G-code", self, triggered=self._export_gcode_to_file))

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        brand = QFrame()
        brand.setObjectName("WpsBrandStrip")
        outer.addWidget(brand)

        self._ribbon = WpsRibbon()
        outer.addWidget(self._ribbon)

        # ----- Ribbon: 开始 -----
        start_row, _ = self._ribbon.add_page("开始")
        g_comp = RibbonGroup("组件")
        self._mode_btns: list[QPushButton] = []
        for idx, lab in enumerate(("文字", "表格", "演示")):
            b = QPushButton(lab)
            # 让“组件”模式按钮更像 WPS：固定尺寸 + 明确选中态样式
            b.setObjectName("WpsModeTabButton")
            b.setFixedSize(76, 30)
            b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            b.setCheckable(True)
            b.clicked.connect(lambda _checked=False, i=idx: self._set_editor_mode(i))
            self._mode_btns.append(b)
            g_comp.add_widget(b)
        self._mode_btns[0].setChecked(True)
        start_row.addWidget(g_comp)
        start_row.addWidget(RibbonVSeparator())

        g_ins = RibbonGroup("插入")
        ins_btn = QToolButton()
        ins_btn.setText("图片 / 矢量")
        ins_btn.setToolTip(
            "类 WPS「插入图片」：预置 / 本机文件 / 位图矢量化；"
            "导入后默认在纸面居中，可再拖预览框或调 Ribbon「矢量」。"
        )
        ins_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        ins_menu = QMenu(self)
        self._populate_insert_vector_menu(ins_menu)
        ins_btn.setMenu(ins_menu)
        g_ins.add_widget(ins_btn)
        sym_btn = QToolButton()
        sym_btn.setText("符号")
        sym_btn.setToolTip("插入数学、单位等 Unicode 符号（「文字」或「演示」页）")
        sym_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        sym_menu = QMenu(self)
        populate_qmenu_symbols(sym_menu, self._insert_math_symbol)
        sym_btn.setMenu(sym_menu)
        g_ins.add_widget(sym_btn)
        start_row.addWidget(g_ins)
        start_row.addWidget(RibbonVSeparator())

        g_vec = RibbonGroup("矢量")
        vec_tool = QWidget()
        vec_v = QVBoxLayout(vec_tool)
        vec_v.setContentsMargins(0, 0, 0, 0)
        vec_v.setSpacing(4)
        row_scale = QHBoxLayout()
        row_scale.setSpacing(6)
        row_scale.addWidget(QLabel("比例"))
        self._insert_scale_slider = QSlider(Qt.Orientation.Horizontal)
        self._insert_scale_slider.setRange(10, 400)
        self._insert_scale_slider.setValue(100)
        self._insert_scale_slider.setMaximumWidth(160)
        self._insert_scale_slider.setEnabled(False)
        self._insert_scale_slider.setToolTip(
            "仅作用于「插入的矢量图」。可拖滑块，或在预览中拖四角缩放。"
        )
        self._insert_scale_slider.valueChanged.connect(self._on_insert_scale_slider_changed)
        row_scale.addWidget(self._insert_scale_slider)
        self._insert_scale_pct_lbl = QLabel("—")
        self._insert_scale_pct_lbl.setObjectName("StatusHint")
        row_scale.addWidget(self._insert_scale_pct_lbl)
        vec_v.addLayout(row_scale)
        row_off = QHBoxLayout()
        row_off.setSpacing(6)
        ox_lbl = QLabel("偏移 X")
        ox_lbl.setToolTip("插入矢量相对枢轴缩放后的整体平移（mm，文档坐标 X）。")
        row_off.addWidget(ox_lbl)
        self._insert_offset_x_spin = QDoubleSpinBox()
        self._insert_offset_x_spin.setRange(-2000.0, 2000.0)
        self._insert_offset_x_spin.setDecimals(2)
        self._insert_offset_x_spin.setSingleStep(1.0)
        self._insert_offset_x_spin.setMaximumWidth(88)
        self._insert_offset_x_spin.setEnabled(False)
        self._insert_offset_x_spin.valueChanged.connect(self._on_insert_offset_spin_changed)
        row_off.addWidget(self._insert_offset_x_spin)
        oy_lbl = QLabel("Y")
        oy_lbl.setToolTip("整体平移（mm，文档 Y 向上为正）。")
        row_off.addWidget(oy_lbl)
        self._insert_offset_y_spin = QDoubleSpinBox()
        self._insert_offset_y_spin.setRange(-2000.0, 2000.0)
        self._insert_offset_y_spin.setDecimals(2)
        self._insert_offset_y_spin.setSingleStep(1.0)
        self._insert_offset_y_spin.setMaximumWidth(88)
        self._insert_offset_y_spin.setEnabled(False)
        self._insert_offset_y_spin.valueChanged.connect(self._on_insert_offset_spin_changed)
        row_off.addWidget(self._insert_offset_y_spin)
        self._insert_offset_reset_btn = QPushButton("重置位置")
        self._insert_offset_reset_btn.setEnabled(False)
        self._insert_offset_reset_btn.setToolTip("将偏移归零（缩放与枢轴不变）。")
        self._insert_offset_reset_btn.clicked.connect(self._on_insert_offset_reset)
        row_off.addWidget(self._insert_offset_reset_btn)
        self._insert_page_center_btn = QPushButton("页面居中")
        self._insert_page_center_btn.setEnabled(False)
        self._insert_page_center_btn.setToolTip(
            "将插入矢量包围盒中心对齐到纸张中心（类 WPS 图片居中）。"
        )
        self._insert_page_center_btn.clicked.connect(self._center_insert_vector_on_page)
        row_off.addWidget(self._insert_page_center_btn)
        vec_v.addLayout(row_off)
        row_sk = QHBoxLayout()
        row_sk.setSpacing(8)
        self._cb_sketch_pen = QCheckBox("手绘笔")
        self._cb_sketch_pen.setToolTip(
            "在右侧路径预览上按住左键拖动绘制折线（文档毫米坐标）；"
            "与插入矢量一并参与 G-code。开启时优先于拖入预览的缩放/平移。"
        )
        row_sk.addWidget(self._cb_sketch_pen)
        b_clr_sk = QPushButton("清除手绘")
        b_clr_sk.setToolTip("清空预览手绘路径（不影响插入的 SVG/位图矢量）")
        b_clr_sk.clicked.connect(self._clear_sketch_paths)
        row_sk.addWidget(b_clr_sk)
        row_sk.addStretch(1)
        vec_v.addLayout(row_sk)
        g_vec.add_widget(vec_tool)
        start_row.addWidget(g_vec)
        start_row.addWidget(RibbonVSeparator())

        g_font = RibbonGroup("字体")
        self._font_combo = QFontComboBox()
        self._font_combo.currentFontChanged.connect(self._apply_font_family)
        g_font.add_widget(QLabel("字体"))
        g_font.add_widget(self._font_combo)
        start_row.addWidget(g_font)
        start_row.addWidget(RibbonVSeparator())

        g_size = RibbonGroup("字号")
        self._size_spin = QSpinBox()
        self._size_spin.setRange(6, 200)
        self._size_spin.setValue(12)
        self._size_spin.valueChanged.connect(self._apply_font_size)
        g_size.add_widget(QLabel("字号"))
        g_size.add_widget(self._size_spin)
        start_row.addWidget(g_size)
        start_row.addWidget(RibbonVSeparator())

        g_style = RibbonGroup("样式")
        bold_btn = QPushButton("加粗")
        bold_btn.setToolTip("加粗（Ctrl+B）")
        bold_btn.clicked.connect(self._toggle_bold)
        g_style.add_widget(bold_btn)
        it_btn = QPushButton("倾斜")
        it_btn.setToolTip("倾斜（Ctrl+I）")
        it_btn.clicked.connect(self._toggle_italic)
        g_style.add_widget(it_btn)
        ul_btn = QPushButton("下划线")
        ul_btn.setToolTip("下划线（Ctrl+U）")
        ul_btn.clicked.connect(self._toggle_underline)
        g_style.add_widget(ul_btn)
        start_row.addWidget(g_style)
        start_row.addWidget(RibbonVSeparator())

        g_para = RibbonGroup("段落")
        for label, al, tip in [
            ("左对齐", Qt.AlignmentFlag.AlignLeft, "Ctrl+L"),
            ("居中", Qt.AlignmentFlag.AlignCenter, "Ctrl+E"),
            ("右对齐", Qt.AlignmentFlag.AlignRight, "Ctrl+R"),
            ("两端对齐", Qt.AlignmentFlag.AlignJustify, "Ctrl+J"),
        ]:
            b = QPushButton(label)
            b.setToolTip(tip)
            b.clicked.connect(lambda _, a=al: self._set_alignment(a))
            g_para.add_widget(b)
        start_row.addWidget(g_para)
        start_row.addWidget(RibbonVSeparator())

        g_stroke = RibbonGroup("单线字库")
        b_pick = QPushButton("选择 JSON…")
        b_pick.setToolTip(
            "支持包内 Hershey JSON、或 grblapp/奎享导出的合并字库 JSON"
            "（大文件将延迟加载）"
        )
        b_pick.clicked.connect(self._pick_stroke_font_json)
        g_stroke.add_widget(b_pick)
        b_reset = QPushButton("恢复包内")
        b_reset.clicked.connect(self._reset_stroke_font_to_bundled)
        g_stroke.add_widget(b_reset)
        b_kd = QPushButton("KDraw 字库")
        b_kd.setToolTip("在访达中打开本机 KDraw 的 gcodeFonts（.gfont 需先导出为 JSON）")
        b_kd.clicked.connect(self._open_kdraw_gcode_fonts_dir)
        g_stroke.add_widget(b_kd)
        b_merge = QPushButton("合并字库…")
        b_merge.setToolTip(
            "叠加第二份 JSON（奎享/Hershey 格式），覆盖同码位；"
            "可与主编译大包中文库组合"
        )
        b_merge.clicked.connect(self._pick_stroke_merge_json)
        g_stroke.add_widget(b_merge)
        b_merge_clr = QPushButton("清除合并")
        b_merge_clr.setToolTip("移除叠加字库，仅保留主编译")
        b_merge_clr.clicked.connect(self._clear_stroke_merge_json)
        g_stroke.add_widget(b_merge_clr)
        b_cjk = QPushButton("中文小样")
        b_cjk.setToolTip("将包内 cjk_stroke_sample.json 设为合并字库（演示笔画，非大字库）")
        b_cjk.clicked.connect(self._use_cjk_sample_merge_font)
        g_stroke.add_widget(b_cjk)
        start_row.addWidget(g_stroke)
        start_row.addStretch(1)

        # ----- Ribbon: 坐标系 -----
        coord_row, _ = self._ribbon.add_page("坐标系")
        g_mirror = RibbonGroup("镜像")
        self._cb_mirror_x = QCheckBox("镜像 X")
        self._cb_mirror_x.toggled.connect(self._on_coord_changed)
        self._cb_mirror_y = QCheckBox("镜像 Y")
        self._cb_mirror_y.toggled.connect(self._on_coord_changed)
        g_mirror.add_widget(self._cb_mirror_x)
        g_mirror.add_widget(self._cb_mirror_y)
        coord_row.addWidget(g_mirror)
        coord_row.addWidget(RibbonVSeparator())

        g_piv = RibbonGroup("枢轴 (mm)")
        g_piv.add_widget(QLabel("X"))
        self._pivot_x = QDoubleSpinBox()
        self._pivot_x.setRange(-10000, 10000)
        self._pivot_x.setDecimals(3)
        self._pivot_x.valueChanged.connect(self._on_coord_changed)
        g_piv.add_widget(self._pivot_x)
        g_piv.add_widget(QLabel("Y"))
        self._pivot_y = QDoubleSpinBox()
        self._pivot_y.setRange(-10000, 10000)
        self._pivot_y.setDecimals(3)
        self._pivot_y.valueChanged.connect(self._on_coord_changed)
        g_piv.add_widget(self._pivot_y)
        pc = QPushButton("纸张中心")
        pc.clicked.connect(self._pivot_page_center)
        g_piv.add_widget(pc)
        coord_row.addWidget(g_piv)
        coord_row.addWidget(RibbonVSeparator())

        g_ax = RibbonGroup("轴反向")
        self._cb_invert_x = QCheckBox("X ×(−1)")
        self._cb_invert_x.toggled.connect(self._on_coord_changed)
        self._cb_invert_y = QCheckBox("Y ×(−1)")
        self._cb_invert_y.toggled.connect(self._on_coord_changed)
        g_ax.add_widget(self._cb_invert_x)
        g_ax.add_widget(self._cb_invert_y)
        coord_row.addWidget(g_ax)
        coord_row.addWidget(RibbonVSeparator())

        g_off = RibbonGroup("偏移 (mm)")
        g_off.add_widget(QLabel("ΔX"))
        self._off_x = QDoubleSpinBox()
        self._off_x.setRange(-10000, 10000)
        self._off_x.setDecimals(3)
        self._off_x.valueChanged.connect(self._on_coord_changed)
        g_off.add_widget(self._off_x)
        g_off.add_widget(QLabel("ΔY"))
        self._off_y = QDoubleSpinBox()
        self._off_y.setRange(-10000, 10000)
        self._off_y.setDecimals(3)
        self._off_y.valueChanged.connect(self._on_coord_changed)
        g_off.add_widget(self._off_y)
        coord_row.addWidget(g_off)

        hint_c = QLabel("顺序：镜像 X→Y → 缩放 → 平移")
        hint_c.setObjectName("StatusHint")
        coord_row.addWidget(hint_c)
        coord_row.addStretch(1)

        # ----- Ribbon: 设备 -----
        dev_row, _ = self._ribbon.add_page("设备")
        g_serial = RibbonGroup("连接方式")
        self._conn_mode_combo = QComboBox()
        self._conn_mode_combo.addItem("串口 / 蓝牙 SPP", "serial")
        self._conn_mode_combo.addItem("Wi-Fi / Telnet (TCP)", "tcp")
        self._conn_mode_combo.currentIndexChanged.connect(self._on_connection_mode_changed)
        g_serial.add_widget(QLabel("模式"))
        g_serial.add_widget(self._conn_mode_combo)
        dev_row.addWidget(g_serial)
        dev_row.addWidget(RibbonVSeparator())

        g_serial = RibbonGroup("串口 / 蓝牙 SPP")
        self._cb_bt_only = QCheckBox("仅蓝牙")
        self._cb_bt_only.toggled.connect(self._on_bluetooth_filter_toggled)
        g_serial.add_widget(self._cb_bt_only)
        self._port_combo = QComboBox()
        self._port_combo.setEditable(True)
        self._port_combo.setMinimumWidth(220)
        g_serial.add_widget(QLabel("端口"))
        g_serial.add_widget(self._port_combo)
        rb = QPushButton("刷新")
        rb.clicked.connect(self._refresh_ports)
        g_serial.add_widget(rb)
        dev_row.addWidget(g_serial)
        dev_row.addWidget(RibbonVSeparator())

        g_baud = RibbonGroup("波特率")
        self._baud_spin = QSpinBox()
        self._baud_spin.setRange(9600, 921600)
        self._baud_spin.setValue(115200)
        g_baud.add_widget(self._baud_spin)
        dev_row.addWidget(g_baud)
        dev_row.addWidget(RibbonVSeparator())

        g_tcp = RibbonGroup("Wi-Fi / Telnet")
        g_tcp.add_widget(QLabel("主机"))
        self._tcp_host_edit = QLineEdit()
        self._tcp_host_edit.setPlaceholderText("192.168.4.1")
        self._tcp_host_edit.setMinimumWidth(150)
        g_tcp.add_widget(self._tcp_host_edit)
        g_tcp.add_widget(QLabel("端口"))
        self._tcp_port_spin = QSpinBox()
        self._tcp_port_spin.setRange(1, 65535)
        self._tcp_port_spin.setValue(23)
        g_tcp.add_widget(self._tcp_port_spin)
        dev_row.addWidget(g_tcp)
        dev_row.addWidget(RibbonVSeparator())

        g_stream = RibbonGroup("发送")
        self._cb_stream = QCheckBox("流式填满缓冲")
        self._cb_stream.setToolTip(
            "在仍逐行等待 ok 的前提下，按接收缓冲字节预算尽量多发；不稳时可关闭。"
        )
        self._cb_stream.setChecked(self._cfg.grbl_streaming)
        self._cb_stream.toggled.connect(lambda c: setattr(self._cfg, "grbl_streaming", bool(c)))
        g_stream.add_widget(self._cb_stream)
        g_stream.add_widget(QLabel("RX 预算"))
        self._rx_buf_spin = QSpinBox()
        self._rx_buf_spin.setRange(32, 16384)
        self._rx_buf_spin.setValue(max(32, int(self._cfg.grbl_rx_buffer_size)))
        self._rx_buf_spin.setToolTip(
            f"流式发送时按字节估算固件串口 RX 缓冲。"
            f"新建默认 {GRBL_ESP32_DEFAULT_RX_BUFFER_SIZE}"
            "（对齐 Grbl_Esp32 Serial.h 的 RX_BUFFER_SIZE；AVR 常见 128）。"
            f"可点「Bf→RX」在已连接且固件上报 Bf 时，用 Idle 下的剩余空间近似容量。"
        )
        self._rx_buf_spin.valueChanged.connect(self._sync_cfg_widgets)
        g_stream.add_widget(self._rx_buf_spin)
        bf_rx_btn = QPushButton("Bf→RX")
        bf_rx_btn.setToolTip(
            "已连接时发送实时「?」。若状态含 Bf:a,b，则用 b（串口 RX 剩余字节）写入左侧预算；"
            "请在 Idle、缓冲空时点击，使 b 接近固件真实容量（需固件开启缓冲状态报告）。"
        )
        bf_rx_btn.clicked.connect(self._sync_rx_from_grbl_bf)
        g_stream.add_widget(bf_rx_btn)
        dev_row.addWidget(g_stream)
        dev_row.addWidget(RibbonVSeparator())

        g_z = RibbonGroup("抬落笔 Z (mm)")
        g_z.add_widget(QLabel("抬笔"))
        self._z_up = QDoubleSpinBox()
        self._z_up.setRange(-50, 50)
        self._z_up.setValue(self._cfg.z_up_mm)
        self._z_up.valueChanged.connect(self._sync_cfg_widgets)
        g_z.add_widget(self._z_up)
        g_z.add_widget(QLabel("落笔"))
        self._z_down = QDoubleSpinBox()
        self._z_down.setRange(-50, 50)
        self._z_down.setValue(self._cfg.z_down_mm)
        self._z_down.valueChanged.connect(self._sync_cfg_widgets)
        g_z.add_widget(self._z_down)
        dev_row.addWidget(g_z)
        dev_row.addWidget(RibbonVSeparator())

        g_pen = RibbonGroup("抬落笔方式")
        g_pen.add_widget(QLabel("模式"))
        self._pen_mode_combo = QComboBox()
        self._pen_mode_combo.addItem("Z 轴 (G1 Z)", "z")
        self._pen_mode_combo.addItem("M3 / M5 (伺服笔)", "m3m5")
        self._pen_mode_combo.setToolTip(
            "默认用 Z 抬落笔；若固件用 M5 抬笔、M3 S… 落笔（伺服笔等），选 M3/M5。"
        )
        self._pen_mode_combo.currentIndexChanged.connect(self._on_pen_mode_ui_changed)
        g_pen.add_widget(self._pen_mode_combo)
        g_pen.add_widget(QLabel("M3 S"))
        self._m3_s_spin = QSpinBox()
        self._m3_s_spin.setRange(0, 10000)
        self._m3_s_spin.setValue(max(0, int(self._cfg.gcode_m3_s_value)))
        self._m3_s_spin.setToolTip("落笔行 M3 S 的数值（仅 M3/M5 模式生效）。")
        self._m3_s_spin.valueChanged.connect(self._sync_cfg_widgets)
        g_pen.add_widget(self._m3_s_spin)
        dev_row.addWidget(g_pen)
        dev_row.addWidget(RibbonVSeparator())

        g_gc_extra = RibbonGroup("程序附加")
        gc_wrap = QWidget()
        gc_lay = QVBoxLayout(gc_wrap)
        gc_lay.setContentsMargins(0, 0, 0, 0)
        gc_lay.setSpacing(2)
        self._gcode_prefix_edit = QPlainTextEdit()
        self._gcode_prefix_edit.setPlaceholderText("前缀：F 行后、笔画前，每行一条")
        self._gcode_prefix_edit.setMaximumHeight(40)
        self._gcode_prefix_edit.setMaximumWidth(200)
        gc_lay.addWidget(QLabel("前缀"))
        gc_lay.addWidget(self._gcode_prefix_edit)
        self._gcode_suffix_edit = QPlainTextEdit()
        self._gcode_suffix_edit.setPlaceholderText("后缀：抬笔后、M2/M30 前")
        self._gcode_suffix_edit.setMaximumHeight(40)
        self._gcode_suffix_edit.setMaximumWidth(200)
        gc_lay.addWidget(QLabel("后缀"))
        gc_lay.addWidget(self._gcode_suffix_edit)
        row_gc_chk = QHBoxLayout()
        self._cb_gcode_g92 = QCheckBox("G92 程序零点")
        self._cb_gcode_g92.setToolTip("生成 G92 X0 Y0 Z0（与现有配置一致）")
        row_gc_chk.addWidget(self._cb_gcode_g92)
        self._cb_gcode_m30 = QCheckBox("结尾 M30")
        self._cb_gcode_m30.setToolTip("以 M30 结束（常用于换纸类流程，行为依固件而定）")
        row_gc_chk.addWidget(self._cb_gcode_m30)
        gc_lay.addLayout(row_gc_chk)
        row_gc_btn = QHBoxLayout()
        b_m800 = QPushButton("+M800")
        b_m800.setToolTip("在前缀末尾追加一行 M800（奎享等授权占位，请按固件修改）")
        b_m800.clicked.connect(lambda: self._append_gcode_line("prefix", "M800"))
        row_gc_btn.addWidget(b_m800)
        b_esp = QPushButton("+ESP")
        b_esp.setToolTip("在前缀追加示例 [ESP800]（Grbl_Esp32 等扩展指令，按固件文档修改）")
        b_esp.clicked.connect(lambda: self._append_gcode_line("prefix", "[ESP800]"))
        row_gc_btn.addWidget(b_esp)
        gc_lay.addLayout(row_gc_btn)
        g_gc_extra.add_widget(gc_wrap)
        dev_row.addWidget(g_gc_extra)
        dev_row.addWidget(RibbonVSeparator())

        g_run = RibbonGroup("运行")
        self._connect_btn = QPushButton("连接")
        self._connect_btn.clicked.connect(self._toggle_serial)
        self._send_btn = QPushButton("发送 G-code")
        self._send_btn.clicked.connect(self._send_gcode)
        self._send_btn.setEnabled(False)
        g_run.add_widget(self._connect_btn)
        g_run.add_widget(self._send_btn)
        self._resume_checkpoint_btn = QPushButton("断点续发")
        self._resume_checkpoint_btn.clicked.connect(self._resume_from_checkpoint)
        self._resume_checkpoint_btn.setEnabled(False)
        g_run.add_widget(self._resume_checkpoint_btn)
        self._reset_btn = QPushButton("软复位 Ctrl+X")
        self._reset_btn.clicked.connect(self._soft_reset_machine)
        self._reset_btn.setEnabled(False)
        g_run.add_widget(self._reset_btn)
        _h1 = QPushButton("暂停 !")
        _h1.clicked.connect(self._feed_hold)
        g_run.add_widget(_h1)
        _h2 = QPushButton("继续 ~")
        _h2.clicked.connect(self._cycle_start)
        g_run.add_widget(_h2)
        dev_row.addWidget(g_run)
        dev_row.addStretch(1)

        # ----- Ribbon: 视图 -----
        view_row, _ = self._ribbon.add_page("视图")
        g_prev = RibbonGroup("预览说明")
        vh = QLabel("右侧：Hershey 路径（黑=落笔，红=空移）；状态栏可缩放预览。")
        vh.setObjectName("StatusHint")
        vh.setWordWrap(True)
        g_prev.row().addWidget(vh)
        view_row.addWidget(g_prev)
        view_row.addStretch(1)

        self._ribbon.add_tab_trailing_stretch()

        # WPS 式「文件」+ 文档标题
        self._file_btn = QToolButton()
        self._file_btn.setObjectName("WpsFileButton")
        self._file_btn.setText("文件")
        self._file_btn.setToolTip("文件菜单")
        self._file_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        fmenu = QMenu(self)
        self._fill_standard_file_menu(fmenu)
        self._file_btn.setMenu(fmenu)

        self._doc_title_lbl = QLabel()
        self._doc_title_lbl.setObjectName("WpsDocTitle")
        self._sync_doc_title_label()

        self._ribbon.prepend_to_tab_bar(
            self._file_btn,
            RibbonTabVSep(),
            self._doc_title_lbl,
            RibbonTabVSep(),
        )

        # ----- 中间：纸张 + 任务窗格 -----
        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, stretch=1)

        doc_canvas = QFrame()
        doc_canvas.setObjectName("DocumentCanvas")
        doc_lay = QVBoxLayout(doc_canvas)
        doc_lay.setContentsMargins(12, 12, 12, 12)
        sheet = QFrame()
        sheet.setObjectName("DocumentSheet")
        sheet_lay = QVBoxLayout(sheet)
        sheet_lay.setContentsMargins(0, 0, 0, 0)
        sheet_lay.addWidget(make_horizontal_ruler_mm(int(self._cfg.page_width_mm)))
        self._stack = QStackedWidget()
        self._editor = QTextEdit()
        self._editor.setObjectName("DocumentEditor")
        self._editor.setPlaceholderText("在此编辑文字内容…")
        self._editor.document().setDocumentMargin(0.0)
        self._table_editor = WpsTableEditor(self._cfg)
        self._presentation_editor = WpsPresentationEditor(self._cfg)
        # _apply_font_size 依赖 _table_editor / _presentation_editor；因此需在它们初始化之后调用。
        self._apply_font_size(self._size_spin.value())
        self._stack.addWidget(self._editor)
        self._stack.addWidget(self._table_editor)
        self._stack.addWidget(self._presentation_editor)
        tw = self._table_editor.table_widget()
        tw.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tw.customContextMenuRequested.connect(self._open_table_context_menu)
        sheet_lay.addWidget(self._stack)
        apply_default_tab_stops(self._editor)
        self._install_editor_shortcuts()
        self._sync_text_document_margins()
        doc_lay.addWidget(sheet, stretch=1)
        splitter.addWidget(doc_canvas)
        splitter.setStretchFactor(0, 7)

        task = QWidget()
        tv = QVBoxLayout(task)
        tv.setContentsMargins(8, 8, 8, 8)
        tv.setSpacing(8)

        prev_frame = QFrame()
        prev_frame.setObjectName("TaskPaneGroup")
        pf = QVBoxLayout(prev_frame)
        pf.addWidget(QLabel("路径预览"))
        self._preview = QGraphicsView()
        self._preview.setMinimumHeight(220)
        # 预览线条抗锯齿：改善小线段/字体路径观感
        self._preview.setRenderHints(
            self._preview.renderHints()
            | QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        pf.addWidget(self._preview)
        tv.addWidget(prev_frame, stretch=2)

        log_frame = QFrame()
        log_frame.setObjectName("TaskPaneGroup")
        lf = QVBoxLayout(log_frame)
        lf.addWidget(QLabel("串口 / 状态"))
        self._machine_state_label = QLabel("设备状态: 未连接")
        self._job_state_label = QLabel("作业状态: 就绪")
        self._job_progress_label = QLabel("作业进度: 0/0")
        self._machine_pos_label = QLabel("机械坐标: X0.000 Y0.000 Z0.000")
        self._machine_buf_label = QLabel("缓冲: Planner - / RX -")
        self._machine_alarm_label = QLabel("告警: -")
        for lbl in (
            self._machine_state_label,
            self._job_state_label,
            self._job_progress_label,
            self._machine_pos_label,
            self._machine_buf_label,
            self._machine_alarm_label,
        ):
            lf.addWidget(lbl)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)
        lf.addWidget(self._log)
        tv.addWidget(log_frame, stretch=3)

        splitter.addWidget(task)
        splitter.setStretchFactor(1, 3)

        self._cb_bt_only.setChecked(self._cfg.serial_show_bluetooth_only)
        mode = getattr(self._cfg, "connection_mode", "serial")
        self._conn_mode_combo.setCurrentIndex(1 if mode == "tcp" else 0)
        self._tcp_host_edit.setText(str(getattr(self._cfg, "tcp_host", "") or ""))
        self._tcp_port_spin.setValue(max(1, int(getattr(self._cfg, "tcp_port", 23) or 23)))
        self._apply_cfg_to_coord_widgets()
        self._apply_pen_mode_widgets()
        self._apply_gcode_extra_widgets_from_cfg()
        self._update_connection_mode_widgets()
        self._refresh_ports()

    def _build_status_bar(self) -> None:
        sb = QStatusBar()
        sb.setSizeGripEnabled(True)
        self.setStatusBar(sb)
        self._st_main = QLabel("就绪")
        self._st_main.setObjectName("StatusBarPermanent")
        sb.addWidget(self._st_main, 1)

        self._st_cursor = QLabel()
        self._st_cursor.setObjectName("StatusBarPermanent")
        sb.addPermanentWidget(self._st_cursor)

        self._st_conn = QLabel("串口：未连接")
        self._st_conn.setObjectName("StatusBarPermanent")
        sb.addPermanentWidget(self._st_conn)

        sb.addPermanentWidget(QLabel("预览缩放"))
        self._zoom_combo = QComboBox()
        self._zoom_combo.setObjectName("StatusZoomCombo")
        for z in (50, 75, 100, 125, 150, 200):
            self._zoom_combo.addItem(f"{z}%", z)
        self._zoom_combo.setCurrentIndex(2)
        self._zoom_combo.currentIndexChanged.connect(self._on_preview_zoom_changed)
        sb.addPermanentWidget(self._zoom_combo)

    def _on_preview_zoom_changed(self) -> None:
        z = self._zoom_combo.currentData()
        if z is not None:
            self._preview_zoom = float(z) / 100.0
        self._on_document_changed()

    def _sync_doc_title_label(self) -> None:
        self._doc_title_lbl.setText(f"{self._doc_title}  ·  写字机上位机")

    def _set_editor_mode(self, mode: int) -> None:
        mode = max(0, min(2, int(mode)))
        self._stack.setCurrentIndex(mode)
        for i, btn in enumerate(self._mode_btns):
            btn.blockSignals(True)
            btn.setChecked(i == mode)
            btn.blockSignals(False)
        if mode == 0:
            d = self._editor.document()
            self._act_undo.setEnabled(d.isUndoAvailable())
            self._act_redo.setEnabled(
                d.isRedoAvailable() if hasattr(d, "isRedoAvailable") else False
            )
        else:
            self._act_undo.setEnabled(self._nonword_undo_stack.canUndo())
            self._act_redo.setEnabled(self._nonword_undo_stack.canRedo())
        self._on_document_changed()
        self._update_status_bar()
        self._update_window_title()

    def _on_nonword_content_changed(self) -> None:
        self._push_nonword_undo_snapshot()
        self._nonword_modified = True
        self._on_document_changed()
        self._update_window_title()

    def _update_window_title(self) -> None:
        if not hasattr(self, "_editor"):
            self.setWindowTitle(f"{self._doc_title} - 写字机上位机")
            return
        if self._stack.currentIndex() == 0:
            star = "● " if self._editor.document().isModified() else ""
        else:
            star = "● " if self._nonword_modified else ""
        self.setWindowTitle(f"{star}{self._doc_title} - 写字机上位机")

    def _is_document_dirty(self) -> bool:
        return bool(self._editor.document().isModified() or self._nonword_modified)

    def _mark_saved_state(self) -> None:
        self._editor.document().setModified(False)
        self._nonword_modified = False
        self._update_window_title()

    def _ask_save_if_dirty(self, title: str, message: str) -> bool:
        """有未保存修改时询问；返回 False 表示用户取消。"""
        if not self._is_document_dirty():
            return True
        r = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if r == QMessageBox.StandardButton.Cancel:
            return False
        if r == QMessageBox.StandardButton.Discard:
            return True
        return self._save_project()

    def _repo_root_file(self, name: str) -> Path:
        return Path(__file__).resolve().parents[2] / name

    def _show_quick_start(self) -> None:
        QMessageBox.information(
            self,
            "快速入门",
            "启动（仓库根目录）：\n  python3 -m inkscape_wps\n\n"
            "简要流程：\n"
            "• 在「文字 / 表格 / 演示」编辑；右侧为路径预览。\n"
            "• 「文件」→ 保存工程（*.inkwps.json）；机床参数用「保存配置…」（TOML/JSON）。\n"
            "• 「设备」→ 抬落笔方式（Z 或 M3/M5）、串口、连接后可发送 G-code。\n"
            "• 「工具」或「文件」→ 导出 G-code 到 .nc / .gcode 等。\n\n"
            "完整能力与维护约定见 SPEC.md；AI 协作提示词见 AI_PROMPTS.md。",
        )

    def _open_spec_document(self) -> None:
        spec = self._repo_root_file("SPEC.md")
        if not spec.is_file():
            QMessageBox.information(
                self,
                "帮助",
                "未在预期路径找到 SPEC.md。\n若从安装包运行，请参阅发布包内文档。",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(spec.resolve())))

    def _open_ai_prompts_document(self) -> None:
        doc = self._repo_root_file("AI_PROMPTS.md")
        if not doc.is_file():
            QMessageBox.information(self, "帮助", "未在预期路径找到 AI_PROMPTS.md。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(doc.resolve())))

    def _new_document(self) -> None:
        if not self._ask_save_if_dirty("新建", "当前内容已修改，是否保存工程？"):
            return
        self._nonword_undo_restoring = True
        try:
            self._editor.clear()
            self._table_editor.clear_all()
            self._presentation_editor.clear_all()
            self._sketch_paths.clear()
            self._sketch_drag_pts = None
            self._insert_paths_base.clear()
            self._insert_vector_scale = 1.0
            self._insert_vector_dx_mm = 0.0
            self._insert_vector_dy_mm = 0.0
            self._insert_resize_drag = None
            self._insert_move_drag = None
            self._insert_overlay_bbox_scene = None
            self._overlay_handle_rects_scene.clear()
            self._preview.viewport().unsetCursor()
            self._nonword_modified = False
            self._doc_title = "未命名文档"
            self._project_path = None
            self._sync_doc_title_label()
            self._editor.document().setModified(False)
        finally:
            self._nonword_undo_restoring = False
        self._reset_nonword_undo_anchor()
        self._update_window_title()
        self._on_document_changed()

    def _select_all_current(self) -> None:
        idx = self._stack.currentIndex()
        if idx == 0:
            self._editor.selectAll()
        elif idx == 1:
            self._table_editor.select_all()
        else:
            self._presentation_editor.select_all_current()

    def _schedule_status_update(self) -> None:
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        idx = self._stack.currentIndex()
        if idx == 0:
            cur = self._editor.textCursor()
            line = cur.blockNumber() + 1
            col = cur.positionInBlock() + 1
            plain = self._editor.toPlainText()
            chars = len(plain)
            nlines = max(1, plain.count("\n") + 1)
            extra = self._glyph_status_hint("word")
            self._st_cursor.setText(
                f"第 {line} 行，第 {col} 列  │  {chars} 字符  │  {nlines} 行"
                + (f"  │  {extra}" if extra else "")
            )
        elif idx == 1:
            r, c = self._table_editor.row_column_count()
            extra = self._glyph_status_hint("table")
            cursor_text = f"表格  │  {r} 行 × {c} 列"
            self._st_cursor.setText(cursor_text + (f"  │  {extra}" if extra else ""))
        else:
            extra = self._glyph_status_hint("slides")
            self._st_cursor.setText(
                self._presentation_editor.status_line() + (f"  │  {extra}" if extra else "")
            )
        snap = self._machine_monitor.snapshot
        if self._grbl is not None:
            is_tcp = str(getattr(self._cfg, "connection_mode", "serial")) == "tcp"
            conn_mode = "Wi-Fi" if is_tcp else "串口"
            parts = [f"{conn_mode}：已连接", f"状态：{snap.state}"]
            if snap.rx_free >= 0:
                parts.append(f"RX：{snap.rx_free}")
            if snap.mpos != (0.0, 0.0, 0.0):
                parts.append(f"MPos X{snap.mpos[0]:.3f} Y{snap.mpos[1]:.3f} Z{snap.mpos[2]:.3f}")
            self._st_conn.setText("  │  ".join(parts))
        else:
            self._st_conn.setText("连接：未连接")
        d = self._editor.document()
        if idx == 0:
            if hasattr(d, "isUndoAvailable"):
                self._act_undo.setEnabled(d.isUndoAvailable())
            if hasattr(d, "isRedoAvailable"):
                self._act_redo.setEnabled(d.isRedoAvailable())
        else:
            self._act_undo.setEnabled(self._nonword_undo_stack.canUndo())
            self._act_redo.setEnabled(self._nonword_undo_stack.canRedo())
        self._refresh_machine_summary()

    def _open_table_context_menu(self, pos) -> None:  # noqa: ANN001
        tw = self._table_editor.table_widget()
        idx = tw.indexAt(pos)
        if idx.isValid():
            row = int(idx.row())
            col = int(idx.column())
            in_selection = any(
                rng.topRow() <= row <= rng.bottomRow()
                and rng.leftColumn() <= col <= rng.rightColumn()
                for rng in tw.selectedRanges()
            )
            if not in_selection:
                tw.setCurrentCell(row, col)
        global_pos = tw.viewport().mapToGlobal(pos)
        menu = QMenu(self)
        menu.addAction("上方插入行", self._table_editor.insert_row_above)
        menu.addAction("下方插入行", self._table_editor.insert_row_below)
        menu.addAction("左侧插入列", self._table_editor.insert_column_left)
        menu.addAction("右侧插入列", self._table_editor.insert_column_right)
        menu.addSeparator()
        del_row = menu.addAction("删除当前行", self._table_editor.delete_current_row)
        del_row.setEnabled(tw.rowCount() > 1)
        del_col = menu.addAction("删除当前列", self._table_editor.delete_current_column)
        del_col.setEnabled(tw.columnCount() > 1)
        menu.addSeparator()
        merge_enable = bool(tw.selectedRanges())
        act_merge = menu.addAction("合并选区单元格", self._table_editor.merge_selected_cells)
        act_merge.setEnabled(merge_enable)
        ar, ac = self._table_editor.current_grid_indices()
        act_split = menu.addAction("拆分当前合并", self._table_editor.split_current_merged_cell)
        act_split.setEnabled(
            int(tw.rowSpan(ar, ac) or 1) > 1 or int(tw.columnSpan(ar, ac) or 1) > 1
        )
        menu.exec(global_pos)

    def _refresh_machine_summary(self) -> None:
        snap = self._machine_monitor.snapshot
        if hasattr(self, "_machine_state_label"):
            self._machine_state_label.setText(f"设备状态: {snap.state}")
            self._job_state_label.setText(f"作业状态: {self._job_state_text}")
            self._job_progress_label.setText(
                f"作业进度: {self._job_progress[0]}/{self._job_progress[1]}"
            )
            self._machine_pos_label.setText(
                f"机械坐标: X{snap.mpos[0]:.3f} Y{snap.mpos[1]:.3f} Z{snap.mpos[2]:.3f}"
            )
            planner = "-" if snap.planner_free < 0 else str(snap.planner_free)
            rx = "-" if snap.rx_free < 0 else str(snap.rx_free)
            self._machine_buf_label.setText(f"缓冲: Planner {planner} / RX {rx}")
            self._machine_alarm_label.setText(f"告警: {snap.last_alarm or '-'}")

    def _poll_grbl_status(self) -> None:
        if self._grbl is None:
            return
        try:
            self._grbl.send_realtime_status_request()
        except Exception:
            return

    def _sync_undo_actions(self, available: bool) -> None:
        if self._stack.currentIndex() != 0:
            self._act_undo.setEnabled(self._nonword_undo_stack.canUndo())
        else:
            self._act_undo.setEnabled(available)

    def _sync_redo_actions(self, available: bool) -> None:
        if self._stack.currentIndex() != 0:
            self._act_redo.setEnabled(self._nonword_undo_stack.canRedo())
        else:
            self._act_redo.setEnabled(available)

    def _refresh_undo_redo_from_stacks(self) -> None:
        if self._stack.currentIndex() != 0:
            self._act_undo.setEnabled(self._nonword_undo_stack.canUndo())
            self._act_redo.setEnabled(self._nonword_undo_stack.canRedo())

    def _perform_undo(self) -> None:
        if self._stack.currentIndex() == 0:
            self._editor.undo()
        else:
            self._nonword_undo_stack.undo()

    def _perform_redo(self) -> None:
        if self._stack.currentIndex() == 0:
            self._editor.redo()
        else:
            self._nonword_undo_stack.redo()

    def _capture_nonword_tuple(self) -> tuple[str, str, str]:
        return capture_nonword_state(
            self._table_editor.to_project_blob(),
            self._presentation_editor.slides_storage(),
            serialize_vector_paths(self._sketch_paths),
        )

    def _restore_nonword_state(self, state: tuple[str, str, str]) -> None:
        self._nonword_undo_restoring = True
        try:
            tb_s, sl_s, sk_s = state
            self._table_editor.from_project_blob(json.loads(tb_s))
            slides = json.loads(sl_s)
            self._presentation_editor.load_slides(slides if isinstance(slides, list) else [""])
            self._sketch_paths = deserialize_vector_paths(json.loads(sk_s))
        finally:
            self._nonword_undo_restoring = False
        self._nonword_undo_anchor = state
        self._on_document_changed()
        self._update_window_title()

    def _push_nonword_undo_snapshot(self) -> None:
        if self._nonword_undo_restoring:
            return
        cur = self._capture_nonword_tuple()
        if cur == self._nonword_undo_anchor:
            return
        self._nonword_undo_stack.push(
            NonWordEditCommand(self, self._nonword_undo_anchor, cur, text="表格 / 演示 / 手绘")
        )
        self._nonword_undo_anchor = cur

    def _reset_nonword_undo_anchor(self) -> None:
        self._nonword_undo_stack.clear()
        self._nonword_undo_anchor = self._capture_nonword_tuple()

    def _mm_yup_from_scene(self, sp: QPointF, mpp: float) -> Point:
        x_mm = sp.x() * mpp
        y_mm = self._cfg.page_height_mm - sp.y() * mpp
        pw, ph = float(self._cfg.page_width_mm), float(self._cfg.page_height_mm)
        return Point(max(0.0, min(pw, x_mm)), max(0.0, min(ph, y_mm)))

    def _preview_sketch_mouse_event(self, event: QEvent) -> bool:
        if not self._cb_sketch_pen.isChecked():
            return False
        if not isinstance(event, QMouseEvent):
            return False
        mpp = self._mm_per_px()
        et = event.type()
        sp = self._preview.mapToScene(event.position())
        if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            p = self._mm_yup_from_scene(sp, mpp)
            self._sketch_drag_pts = [p]
            # 拖动期间强制接管鼠标，避免 macOS/HiDPI 下事件丢失导致“拖不动”
            self._preview.viewport().grabMouse()
            event.accept()
            self._preview.viewport().setCursor(Qt.CursorShape.CrossCursor)
            return True
        if et == QEvent.Type.MouseMove and self._sketch_drag_pts is not None:
            p = self._mm_yup_from_scene(sp, mpp)
            last = self._sketch_drag_pts[-1]
            if math.hypot(p.x - last.x, p.y - last.y) >= _MIN_SKETCH_SAMPLE_MM:
                self._sketch_drag_pts.append(p)
            event.accept()
            return True
        if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            if self._sketch_drag_pts is None:
                return False
            pts = self._sketch_drag_pts
            self._sketch_drag_pts = None
            self._preview.viewport().releaseMouse()
            self._preview.viewport().unsetCursor()
            if len(pts) >= 2:
                self._sketch_paths.append(VectorPath(tuple(pts), pen_down=True))
            elif len(pts) == 1:
                q = pts[0]
                self._sketch_paths.append(VectorPath((q, q), pen_down=True))
            else:
                return True
            self._nonword_modified = True
            self._push_nonword_undo_snapshot()
            self._update_window_title()
            self._on_document_changed()
            return True
        return False

    def _clear_sketch_paths(self) -> None:
        if not self._sketch_paths:
            return
        self._sketch_paths.clear()
        self._nonword_modified = True
        self._push_nonword_undo_snapshot()
        self._update_window_title()
        self._on_document_changed()
        self.statusBar().showMessage("已清除手绘路径", 2500)

    def _append_gcode_line(self, where: str, line: str) -> None:
        ln = line.strip()
        if not ln:
            return
        ed = self._gcode_prefix_edit if where == "prefix" else self._gcode_suffix_edit
        t = ed.toPlainText().rstrip()
        ed.setPlainText(t + ("\n" if t else "") + ln)
        self._sync_cfg_widgets()

    def _apply_gcode_extra_widgets_from_cfg(self) -> None:
        self._gcode_prefix_edit.setPlainText(self._cfg.gcode_program_prefix or "")
        self._gcode_suffix_edit.setPlainText(self._cfg.gcode_program_suffix or "")
        self._cb_gcode_g92.setChecked(bool(self._cfg.gcode_use_g92))
        self._cb_gcode_m30.setChecked(bool(self._cfg.gcode_end_m30))

    def _pick_stroke_merge_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择合并用单线字库 JSON",
            str(Path.home()),
            "JSON (*.json);;所有文件 (*)",
        )
        if not path:
            return
        p = Path(path)
        if not p.is_file():
            return
        self._cfg.stroke_font_merge_json_path = str(p.resolve())
        self._remap_stroke_font()
        self.statusBar().showMessage(f"已设置合并字库：{p.name}", 5000)

    def _clear_stroke_merge_json(self) -> None:
        self._cfg.stroke_font_merge_json_path = ""
        self._remap_stroke_font()
        self.statusBar().showMessage("已清除合并字库", 3000)

    def _use_cjk_sample_merge_font(self) -> None:
        p = _package_data_dir() / "fonts" / "cjk_stroke_sample.json"
        if not p.is_file():
            QMessageBox.warning(self, "中文小样", "未找到包内 cjk_stroke_sample.json。")
            return
        self._cfg.stroke_font_merge_json_path = str(p.resolve())
        self._remap_stroke_font()
        self.statusBar().showMessage("已启用包内中文演示合并字库", 5000)

    def _remap_stroke_font(self) -> None:
        self._mapper = HersheyFontMapper(
            _resolve_stroke_font_path(self._cfg),
            merge_font_path=_resolve_merge_stroke_font_path(self._cfg),
            kuixiang_mm_per_unit=self._cfg.kuixiang_mm_per_unit,
        )
        self._mapper.preload_background()
        self._on_document_changed()

    def _pick_stroke_font_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择单线字库 JSON",
            str(Path.home()),
            "JSON (*.json);;所有文件 (*)",
        )
        if not path:
            return
        p = Path(path)
        if not p.is_file():
            return
        self._cfg.stroke_font_json_path = str(p.resolve())
        self._remap_stroke_font()
        self.statusBar().showMessage(f"已切换字库：{p.name}", 5000)

    def _reset_stroke_font_to_bundled(self) -> None:
        self._cfg.stroke_font_json_path = ""
        self._remap_stroke_font()
        self.statusBar().showMessage("已恢复包内默认字库", 3000)

    def _open_kdraw_gcode_fonts_dir(self) -> None:
        dirs = suggest_gcode_fonts_dirs()
        if not dirs:
            QMessageBox.information(
                self,
                "KDraw 字库",
                "未检测到常见安装路径下的 gcodeFonts。\n"
                "若已安装奎享 KDraw，可将 .gfont 用 grblapp 的导出工具"
                "转为 JSON 后放入本应用可读路径。",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(dirs[0].resolve())))

    def _mm_per_px_for(self, editor: QTextEdit) -> float:
        w = max(1, editor.viewport().width())
        return self._cfg.page_width_mm / float(w)

    def _mm_per_px(self) -> float:
        return self._mm_per_px_for(self._editor)

    def _current_content_page_id(self) -> str:
        return {0: "word", 1: "table", 2: "slides"}.get(self._stack.currentIndex(), "word")

    def _content_mode_label(self, pid: str) -> str:
        return {"word": "文字", "table": "表格", "slides": "演示"}.get(pid, "文字")

    def _current_content_plain_text_for_glyph_check(self, pid: str) -> str:
        if pid == "table":
            blob = self._table_editor.to_project_blob()
            rows = blob.get("cells") or []
            parts: list[str] = []
            for row in rows:
                for cell in row:
                    text = str((cell or {}).get("text", "") or "").strip()
                    if text:
                        parts.append(text)
            return "\n".join(parts)
        if pid == "slides":
            return "\n".join(self._presentation_editor.slides_storage_for_export())
        return self._editor.toPlainText()

    def _glyph_status_hint(self, pid: str) -> str:
        text = self._current_content_plain_text_for_glyph_check(pid)
        if not text.strip():
            return ""
        missing = self._mapper.missing_text_chars(text)
        if not missing:
            return "字形：完整"
        preview = " ".join(repr(ch)[1:-1] for ch in missing[:4])
        if len(missing) > 4:
            preview += " ..."
        return f"缺字形：{len(missing)}（{preview}）"

    def _show_missing_glyphs_dialog(self) -> None:
        pid = self._current_content_page_id()
        source = self._content_mode_label(pid)
        text = self._current_content_plain_text_for_glyph_check(pid)
        if not text.strip():
            QMessageBox.information(self, "缺失字符检查", f"当前“{source}”没有可检查的文本内容。")
            return
        missing = self._mapper.missing_text_chars(text)
        if not missing:
            QMessageBox.information(
                self,
                "缺失字符检查",
                f"当前“{source}”内容的字形覆盖完整，可以继续生成预览或 G-code。",
            )
            return
        QMessageBox.warning(
            self,
            "缺失字符检查",
            f"当前“{source}”存在 {len(missing)} 个未覆盖字符：\n\n{' '.join(missing)}\n\n"
            "这些字符可能不会出现在预览或 G-code 中。"
            "如需完整输出，请更换/合并单线字库，或调整文档内容。",
        )

    def _current_work_paths_checked(self) -> List[VectorPath]:
        paths = self._work_paths()
        if paths:
            return paths
        pid = self._current_content_page_id()
        source = self._content_mode_label(pid)
        glyph_hint = self._glyph_status_hint(pid)
        glyph_extra = f" {glyph_hint}。" if glyph_hint.startswith("缺字形：") else ""
        raise ValueError(
            f"当前“{source}”没有可导出的笔画路径。请先输入内容，或检查字库/表格/演示内容是否为空。{glyph_extra}"
        )

    def _build_job_summary(self, paths: List[VectorPath]) -> str:
        pid = self._current_content_page_id()
        source = self._content_mode_label(pid)
        glyph_hint = self._glyph_status_hint(pid)
        summary = (
            f"来源：{source}\n"
            f"路径段：{len(paths)}，点数：{sum(len(vp.points) for vp in paths)}\n"
            f"纸张：{float(self._cfg.page_width_mm):.1f} × {float(self._cfg.page_height_mm):.1f} mm"
        )
        if glyph_hint.startswith("缺字形："):
            summary += f"\n注意：{glyph_hint}"
        return summary

    def _current_paths(self) -> List[VectorPath]:
        idx = self._stack.currentIndex()
        if idx == 1:
            lines = self._table_editor.to_layout_lines(self._mm_per_px())
            return map_document_lines(
                self._mapper,
                lines,
                mm_per_pt=self._cfg.mm_per_pt,
            ) + list(self._table_editor.to_grid_paths())
        elif idx == 2:
            lines = self._presentation_editor.to_layout_lines_all_slides(
                mm_per_px_resolver=self._mm_per_px_for,
            )
        else:
            lines = text_edit_to_layout_lines(
                self._editor,
                self._cfg,
                mm_per_px=self._mm_per_px_for(self._editor),
            )
        return map_document_lines(
            self._mapper,
            lines,
            mm_per_pt=self._cfg.mm_per_pt,
        )

    def _recompute_insert_pivot(self) -> None:
        if not self._insert_paths_base:
            return
        bb = paths_bounding_box(self._insert_paths_base)
        self._insert_vector_cx_mm = (bb[0] + bb[2]) / 2.0
        self._insert_vector_cy_mm = (bb[1] + bb[3]) / 2.0

    def _scaled_insert_paths(self) -> List[VectorPath]:
        if not self._insert_paths_base:
            return []
        cx, cy = self._insert_vector_cx_mm, self._insert_vector_cy_mm
        s = float(self._insert_vector_scale)
        dx, dy = self._insert_vector_dx_mm, self._insert_vector_dy_mm
        out: List[VectorPath] = []
        for vp in self._insert_paths_base:
            pts = tuple(
                Point(cx + (p.x - cx) * s + dx, cy + (p.y - cy) * s + dy) for p in vp.points
            )
            out.append(VectorPath(pts, pen_down=vp.pen_down))
        return out

    def _mm_scene_from_mm_yup(self, p_mm: Point, mpp: float) -> QPointF:
        x_px = p_mm.x / mpp
        y_px = (self._cfg.page_height_mm - p_mm.y) / mpp
        return QPointF(x_px, y_px)

    def _hit_insert_resize_handle(self, scene_pos: QPointF) -> Optional[int]:
        pad = 8.0
        for i, r in enumerate(self._overlay_handle_rects_scene):
            if r.adjusted(-pad, -pad, pad, pad).contains(scene_pos):
                return i
        return None

    def _scene_delta_to_mm_delta(self, d_scene: QPointF, mpp: float) -> Tuple[float, float]:
        """场景坐标增量（Y 向下）→ 文档 mm（Y 向上）。"""
        return (d_scene.x() * mpp, -d_scene.y() * mpp)

    def _resize_cursor_for_handle(self, handle_idx: int) -> Qt.CursorShape:
        # 0=左上 1=右上 2=右下 3=左下
        if handle_idx in (0, 2):
            return Qt.CursorShape.SizeFDiagCursor
        return Qt.CursorShape.SizeBDiagCursor

    def _preview_vector_overlay_mouse_event(self, event: QEvent) -> bool:
        if not isinstance(event, QMouseEvent):
            return False
        mpp = self._mm_per_px()
        cx_mm, cy_mm = self._insert_vector_cx_mm, self._insert_vector_cy_mm
        c_scene = self._mm_scene_from_mm_yup(Point(cx_mm, cy_mm), mpp)
        et = event.type()
        sp = self._preview.mapToScene(event.position())

        if et == QEvent.Type.MouseButtonPress:
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            hi = self._hit_insert_resize_handle(sp)
            if hi is not None:
                d0 = math.hypot(sp.x() - c_scene.x(), sp.y() - c_scene.y())
                self._insert_resize_drag = {"d0": max(d0, 1e-6), "s0": self._insert_vector_scale}
                self._insert_move_drag = None
                self._preview.viewport().grabMouse()
                event.accept()
                return True
            bb = self._insert_overlay_bbox_scene
            if bb is not None and bb.contains(sp):
                self._insert_move_drag = {
                    "start_scene": QPointF(sp),
                    "dx0": self._insert_vector_dx_mm,
                    "dy0": self._insert_vector_dy_mm,
                }
                self._insert_resize_drag = None
                self._preview.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                self._preview.viewport().grabMouse()
                event.accept()
                return True
            return False

        if et == QEvent.Type.MouseMove:
            if self._insert_resize_drag is not None:
                sp = self._preview.mapToScene(event.position())
                d1 = math.hypot(sp.x() - c_scene.x(), sp.y() - c_scene.y())
                ratio = d1 / self._insert_resize_drag["d0"]
                new_s = self._insert_resize_drag["s0"] * ratio
                new_s = max(0.05, min(10.0, new_s))
                self._insert_vector_scale = new_s
                self._insert_scale_slider.blockSignals(True)
                self._insert_scale_slider.setValue(int(round(new_s * 100)))
                self._insert_scale_slider.blockSignals(False)
                self._insert_scale_pct_lbl.setText(f"{int(round(new_s * 100))}%")
                self._on_document_changed()
                event.accept()
                return True
            if self._insert_move_drag is not None:
                sp = self._preview.mapToScene(event.position())
                st: QPointF = self._insert_move_drag["start_scene"]
                delta = QPointF(sp.x() - st.x(), sp.y() - st.y())
                dmm_x, dmm_y = self._scene_delta_to_mm_delta(delta, mpp)
                self._insert_vector_dx_mm = self._insert_move_drag["dx0"] + dmm_x
                self._insert_vector_dy_mm = self._insert_move_drag["dy0"] + dmm_y
                self._insert_offset_x_spin.blockSignals(True)
                self._insert_offset_y_spin.blockSignals(True)
                self._insert_offset_x_spin.setValue(self._insert_vector_dx_mm)
                self._insert_offset_y_spin.setValue(self._insert_vector_dy_mm)
                self._insert_offset_x_spin.blockSignals(False)
                self._insert_offset_y_spin.blockSignals(False)
                self._on_document_changed()
                event.accept()
                return True
            if self._insert_overlay_bbox_scene is not None:
                hi = self._hit_insert_resize_handle(sp)
                if hi is not None:
                    self._preview.viewport().setCursor(self._resize_cursor_for_handle(hi))
                elif self._insert_overlay_bbox_scene.contains(sp):
                    self._preview.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
                else:
                    self._preview.viewport().unsetCursor()
            return False

        if et == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                if self._insert_resize_drag is not None:
                    self._insert_resize_drag = None
                    self._preview.viewport().releaseMouse()
                    return True
                if self._insert_move_drag is not None:
                    self._insert_move_drag = None
                    self._preview.viewport().unsetCursor()
                    self._preview.viewport().releaseMouse()
                    return True
        return False

    def _on_insert_scale_slider_changed(self, v: int) -> None:
        self._insert_vector_scale = max(0.05, min(10.0, v / 100.0))
        self._insert_scale_pct_lbl.setText(f"{v}%")
        self._on_document_changed()

    def _on_insert_offset_spin_changed(self) -> None:
        if not self._insert_paths_base:
            return
        self._insert_vector_dx_mm = self._insert_offset_x_spin.value()
        self._insert_vector_dy_mm = self._insert_offset_y_spin.value()
        self._on_document_changed()

    def _on_insert_offset_reset(self) -> None:
        self._insert_vector_dx_mm = 0.0
        self._insert_vector_dy_mm = 0.0
        self._insert_offset_x_spin.blockSignals(True)
        self._insert_offset_y_spin.blockSignals(True)
        self._insert_offset_x_spin.setValue(0.0)
        self._insert_offset_y_spin.setValue(0.0)
        self._insert_offset_x_spin.blockSignals(False)
        self._insert_offset_y_spin.blockSignals(False)
        self._on_document_changed()

    def _sync_insert_scale_controls(self) -> None:
        has = bool(self._insert_paths_base)
        self._insert_scale_slider.setEnabled(has)
        self._insert_offset_x_spin.setEnabled(has)
        self._insert_offset_y_spin.setEnabled(has)
        self._insert_offset_reset_btn.setEnabled(has)
        self._insert_page_center_btn.setEnabled(has)
        if has:
            self._insert_scale_slider.blockSignals(True)
            self._insert_scale_slider.setValue(int(round(self._insert_vector_scale * 100)))
            self._insert_scale_slider.blockSignals(False)
            self._insert_scale_pct_lbl.setText(f"{int(round(self._insert_vector_scale * 100))}%")
            self._insert_offset_x_spin.blockSignals(True)
            self._insert_offset_y_spin.blockSignals(True)
            self._insert_offset_x_spin.setValue(self._insert_vector_dx_mm)
            self._insert_offset_y_spin.setValue(self._insert_vector_dy_mm)
            self._insert_offset_x_spin.blockSignals(False)
            self._insert_offset_y_spin.blockSignals(False)
        else:
            self._insert_scale_slider.blockSignals(True)
            self._insert_scale_slider.setValue(100)
            self._insert_scale_slider.blockSignals(False)
            self._insert_scale_pct_lbl.setText("—")
            self._insert_offset_x_spin.blockSignals(True)
            self._insert_offset_y_spin.blockSignals(True)
            self._insert_offset_x_spin.setValue(0.0)
            self._insert_offset_y_spin.setValue(0.0)
            self._insert_offset_x_spin.blockSignals(False)
            self._insert_offset_y_spin.blockSignals(False)

    def _add_vector_resize_overlay(self, scene, mpp: float) -> None:
        self._overlay_handle_rects_scene.clear()
        self._insert_overlay_bbox_scene = None
        if not self._insert_paths_base:
            return
        scaled = self._scaled_insert_paths()
        bb = paths_bounding_box(scaled)
        if bb[0] >= bb[2] or bb[1] >= bb[3]:
            return
        tl_s = self._mm_scene_from_mm_yup(Point(bb[0], bb[3]), mpp)
        br_s = self._mm_scene_from_mm_yup(Point(bb[2], bb[1]), mpp)
        rect = QRectF(tl_s, br_s).normalized()
        pen = QPen(QColor(30, 144, 255))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidthF(1.0)
        pen.setCosmetic(True)
        border = QGraphicsRectItem(rect)
        border.setPen(pen)
        border.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        border.setZValue(1500)
        scene.addItem(border)
        self._insert_overlay_bbox_scene = QRectF(rect)
        hs = max(5.0, min(rect.width(), rect.height()) * 0.05)
        for c in (rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()):
            hr = QRectF(c.x() - hs / 2, c.y() - hs / 2, hs, hs)
            self._overlay_handle_rects_scene.append(hr)
            hi = QGraphicsRectItem(hr)
            hi.setBrush(QBrush(QColor(30, 144, 255, 220)))
            hi.setPen(QPen(QColor(20, 100, 200)))
            hi.setZValue(2000)
            scene.addItem(hi)

    def _work_paths(self) -> List[VectorPath]:
        text_paths = self._current_paths()
        combined = list(text_paths) + list(self._sketch_paths) + self._scaled_insert_paths()
        ordered = order_paths_nearest_neighbor(combined)
        return transform_paths(ordered, self._cfg)

    def _fill_standard_file_menu(self, menu: QMenu) -> None:
        """菜单栏与绿色「文件」按钮共用，顺序贴近 WPS/Word。"""
        menu.clear()
        menu.addAction("新建", self._new_document)
        menu.addAction("打开工程…", self._open_project)
        menu.addSeparator()
        m_ins = menu.addMenu("插入")
        self._populate_insert_vector_menu(m_ins)
        menu.addSeparator()
        menu.addAction("保存工程", self._save_project)
        menu.addAction("另存工程为…", self._save_project_as)
        menu.addSeparator()
        menu.addAction("保存配置…", self._save_config)
        menu.addAction("生成 G-code…", self._show_gcode)
        menu.addAction("导出 G-code 到文件…", self._export_gcode_to_file)
        menu.addSeparator()
        menu.addAction("退出", self.close)

    def _active_rich_text_edit(self) -> Optional[QTextEdit]:
        idx = self._stack.currentIndex()
        if idx == 0:
            return self._editor
        if idx == 2:
            return self._presentation_editor.slide_editor()
        return None

    def _insert_math_symbol(self, ch: str) -> None:
        from inkscape_wps.ui.math_symbols import insert_unicode_at_caret

        te = self._active_rich_text_edit()
        if te is None:
            QMessageBox.information(self, "符号", "请切换到「文字」或「演示」页后再插入符号。")
            return
        if not insert_unicode_at_caret(te, ch):
            QMessageBox.warning(self, "符号", "当前编辑器不支持插入。")
            return
        self._on_document_changed()

    def _sync_text_document_margins(self) -> None:
        """正文边距（px）与 MachineConfig.document_margin_mm、纸宽对齐，贴近 WPS 页边距观感。"""
        pw = float(self._cfg.page_width_mm)
        vw = max(1, self._editor.viewport().width())
        mpx = float(self._cfg.document_margin_mm) / (pw / float(vw))
        self._editor.document().setDocumentMargin(mpx)
        self._presentation_editor.set_slide_document_margin_px(mpx)

    def _install_editor_shortcuts(self) -> None:
        """StandardKey 在 macOS 上映为 Cmd，在 Windows 上为 Ctrl。"""
        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
        parent = self._stack
        sk = QKeySequence.StandardKey

        def _bind(key, slot) -> None:
            sc = QShortcut(QKeySequence(key), parent)
            sc.setContext(ctx)
            sc.activated.connect(slot)

        _bind(sk.Bold, self._toggle_bold)
        _bind(sk.Italic, self._toggle_italic)
        _bind(sk.Underline, self._toggle_underline)
        align_std = [
            ("AlignLeft", Qt.AlignmentFlag.AlignLeft),
            ("AlignCenter", Qt.AlignmentFlag.AlignCenter),
            ("AlignRight", Qt.AlignmentFlag.AlignRight),
        ]
        for name, al in align_std:
            std = getattr(sk, name, None)
            if std is not None:
                _bind(std, lambda a=al: self._set_alignment(a))
        justify_std = getattr(sk, "AlignJustify", None)
        if justify_std is not None:
            _bind(justify_std, lambda: self._set_alignment(Qt.AlignmentFlag.AlignJustify))
        else:
            _bind("Ctrl+J", lambda: self._set_alignment(Qt.AlignmentFlag.AlignJustify))

    def _center_insert_vector_on_page(self, *, announce: bool = True) -> None:
        if not self._insert_paths_base:
            return
        pw, ph = float(self._cfg.page_width_mm), float(self._cfg.page_height_mm)
        cx, cy = self._insert_vector_cx_mm, self._insert_vector_cy_mm
        self._insert_vector_dx_mm = pw / 2.0 - cx
        self._insert_vector_dy_mm = ph / 2.0 - cy
        self._insert_offset_x_spin.blockSignals(True)
        self._insert_offset_y_spin.blockSignals(True)
        self._insert_offset_x_spin.setValue(self._insert_vector_dx_mm)
        self._insert_offset_y_spin.setValue(self._insert_vector_dy_mm)
        self._insert_offset_x_spin.blockSignals(False)
        self._insert_offset_y_spin.blockSignals(False)
        self._on_document_changed()
        if announce:
            self.statusBar().showMessage("已按纸张中心对齐插入矢量", 2500)

    def _populate_insert_vector_menu(self, menu: QMenu) -> None:
        menu.clear()
        preset_dir = _preset_svg_dir()
        if preset_dir.is_dir():
            sub = menu.addMenu("预置素材")
            for fp in sorted(preset_dir.glob("*.svg")):
                act = QAction(fp.stem, self)
                path = fp.resolve()

                def _go(p: Path = path) -> None:
                    self._insert_svg_paths_from_file(p)

                act.triggered.connect(_go)
                sub.addAction(act)
            if not sub.actions():
                sub.setEnabled(False)
        menu.addAction("来自文件…", self._insert_svg_from_dialog)
        menu.addAction("从图片导入矢量…", self._insert_bitmap_traced)
        menu.addSeparator()
        menu.addAction("清除已插入内容", self._clear_inserted_vectors)
        menu.addAction("清除手绘路径", self._clear_sketch_paths)

    def _insert_svg_paths_from_file(self, path: Path) -> None:
        try:
            vps = vector_paths_from_svg_file(
                path,
                page_width_mm=self._cfg.page_width_mm,
                page_height_mm=self._cfg.page_height_mm,
            )
            if not vps:
                QMessageBox.information(self, "插入", "SVG 中未解析到可绘制的折线路径。")
                return
            self._insert_paths_base.extend(vps)
            self._insert_vector_scale = 1.0
            self._insert_vector_dx_mm = 0.0
            self._insert_vector_dy_mm = 0.0
            self._recompute_insert_pivot()
            self._center_insert_vector_on_page(announce=False)
            self._nonword_modified = True
            self._update_window_title()
            self.statusBar().showMessage(
                f"已导入 {len(vps)} 段矢量（{path.name}），已页面居中；可拖预览缩放/平移",
                5000,
            )
        except Exception as e:
            QMessageBox.warning(self, "插入 SVG", str(e))

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
            "导入图片（Potrace / Autotrace 转矢量）",
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
            if not vps:
                QMessageBox.information(
                    self,
                    "插入",
                    "矢量化结果中未解析到路径，可尝试调高对比度或安装 potrace 后重试。",
                )
                return
            self._insert_paths_base.extend(vps)
            self._insert_vector_scale = 1.0
            self._insert_vector_dx_mm = 0.0
            self._insert_vector_dy_mm = 0.0
            self._recompute_insert_pivot()
            self._center_insert_vector_on_page(announce=False)
            self._nonword_modified = True
            self._update_window_title()
            self.statusBar().showMessage(
                f"图片已转为 {len(vps)} 段矢量并页面居中；可拖预览缩放/平移",
                5000,
            )
        except Exception as e:
            QMessageBox.warning(self, "位图矢量化", str(e))

    def _clear_inserted_vectors(self) -> None:
        if not self._insert_paths_base:
            return
        self._insert_paths_base.clear()
        self._insert_vector_scale = 1.0
        self._insert_vector_dx_mm = 0.0
        self._insert_vector_dy_mm = 0.0
        self._insert_resize_drag = None
        self._insert_move_drag = None
        self._overlay_handle_rects_scene.clear()
        self._insert_overlay_bbox_scene = None
        self._preview.viewport().unsetCursor()
        self._on_document_changed()
        self.statusBar().showMessage("已清除插入的矢量路径", 3000)

    def _apply_preview_transform(self) -> None:
        sc = self._preview.scene()
        if sc is None:
            return
        self._preview.resetTransform()
        self._preview.fitInView(sc.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        if abs(self._preview_zoom - 1.0) > 1e-6:
            self._preview.scale(self._preview_zoom, self._preview_zoom)

    def _on_document_changed(self) -> None:
        # 初始化阶段 _build_ui 尚未创建预览/状态栏控件时，这里会被 _apply_font_size() 间接调用；
        # 直接返回，待 __init__ 末尾再由 _on_document_changed() 统一刷新。
        if not hasattr(self, "_preview") or not hasattr(self, "_st_cursor"):
            return
        paths = self._work_paths()
        mpp = self._mm_per_px()
        scene, _ = self._view_model.paths_to_scene_items(paths, mm_per_px=mpp)
        self._add_vector_resize_overlay(scene, mpp)
        self._preview.setScene(scene)
        self._apply_preview_transform()
        self._sync_insert_scale_controls()
        self._update_status_bar()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_text_document_margins()
        self._apply_preview_transform()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._ask_save_if_dirty("退出", "内容已修改，是否在退出前保存工程？"):
            event.accept()
        else:
            event.ignore()

    def _apply_font_family(self, font: QFont) -> None:
        fam = font.family()
        if self._stack.currentIndex() == 1:
            self._table_editor.merge_font_family_current_cell(fam)
        te = self._active_rich_text_edit()
        if te is not None:
            c = te.textCursor()
            fmt = QTextCharFormat()
            fmt.setFontFamily(fam)
            c.mergeCharFormat(fmt)
            te.mergeCurrentCharFormat(fmt)
        f = self._editor.currentFont()
        f.setFamily(fam)
        self._editor.setFont(f)
        self._table_editor.apply_document_font(f)
        self._presentation_editor.apply_document_font(f)
        apply_default_tab_stops(self._editor)
        self._on_document_changed()

    def _apply_font_size(self, sz: int) -> None:
        if self._stack.currentIndex() == 1:
            self._table_editor.merge_font_point_size_current_cell(float(sz))
        te = self._active_rich_text_edit()
        if te is not None:
            c = te.textCursor()
            fmt = QTextCharFormat()
            fmt.setFontPointSize(float(sz))
            c.mergeCharFormat(fmt)
            te.mergeCurrentCharFormat(fmt)
        f = self._editor.currentFont()
        f.setPointSize(sz)
        self._editor.setFont(f)
        self._table_editor.apply_document_font(f)
        self._presentation_editor.apply_document_font(f)
        apply_default_tab_stops(self._editor)
        self._on_document_changed()

    def _toggle_bold(self) -> None:
        if self._stack.currentIndex() == 1:
            self._table_editor.apply_bold_current_cell()
            self._on_document_changed()
            return
        te = self._active_rich_text_edit()
        if te is None:
            return
        cur = te.textCursor()
        bold_on = cur.charFormat().fontWeight() >= QFont.Weight.DemiBold
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Normal if bold_on else QFont.Weight.Bold)
        cur.mergeCharFormat(fmt)
        te.mergeCurrentCharFormat(fmt)
        self._on_document_changed()

    def _toggle_italic(self) -> None:
        if self._stack.currentIndex() == 1:
            self._table_editor.apply_italic_current_cell()
            self._on_document_changed()
            return
        te = self._active_rich_text_edit()
        if te is None:
            return
        cur = te.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontItalic(not cur.charFormat().fontItalic())
        cur.mergeCharFormat(fmt)
        te.mergeCurrentCharFormat(fmt)
        self._on_document_changed()

    def _toggle_underline(self) -> None:
        if self._stack.currentIndex() == 1:
            self._table_editor.apply_underline_current_cell()
            self._on_document_changed()
            return
        te = self._active_rich_text_edit()
        if te is None:
            return
        cur = te.textCursor()
        u = cur.charFormat().underlineStyle()
        fmt = QTextCharFormat()
        if u != QTextCharFormat.UnderlineStyle.NoUnderline:
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.NoUnderline)
        else:
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
        cur.mergeCharFormat(fmt)
        te.mergeCurrentCharFormat(fmt)
        self._on_document_changed()

    def _set_alignment(self, al: Qt.AlignmentFlag) -> None:
        if self._stack.currentIndex() == 1:
            self._table_editor.set_alignment_current_cell(al)
            self._on_document_changed()
            return
        te = self._active_rich_text_edit()
        if te is None:
            return
        te.setAlignment(al)
        self._on_document_changed()

    def _apply_cfg_to_coord_widgets(self) -> None:
        self._cb_mirror_x.setChecked(self._cfg.coord_mirror_x)
        self._cb_mirror_y.setChecked(self._cfg.coord_mirror_y)
        self._pivot_x.setValue(self._cfg.coord_pivot_x_mm)
        self._pivot_y.setValue(self._cfg.coord_pivot_y_mm)
        self._cb_invert_x.setChecked(self._cfg.coord_scale_x < 0)
        self._cb_invert_y.setChecked(self._cfg.coord_scale_y < 0)
        self._off_x.setValue(self._cfg.coord_offset_x_mm)
        self._off_y.setValue(self._cfg.coord_offset_y_mm)

    def _sync_coord_from_widgets(self) -> None:
        self._cfg.coord_mirror_x = self._cb_mirror_x.isChecked()
        self._cfg.coord_mirror_y = self._cb_mirror_y.isChecked()
        self._cfg.coord_pivot_x_mm = self._pivot_x.value()
        self._cfg.coord_pivot_y_mm = self._pivot_y.value()
        self._cfg.coord_scale_x = -1.0 if self._cb_invert_x.isChecked() else 1.0
        self._cfg.coord_scale_y = -1.0 if self._cb_invert_y.isChecked() else 1.0
        self._cfg.coord_offset_x_mm = self._off_x.value()
        self._cfg.coord_offset_y_mm = self._off_y.value()

    def _apply_pen_mode_widgets(self) -> None:
        pm = (self._cfg.gcode_pen_mode or "z").strip().lower()
        use_m3 = pm in ("m3m5", "m3", "spindle")
        self._pen_mode_combo.blockSignals(True)
        self._pen_mode_combo.setCurrentIndex(1 if use_m3 else 0)
        self._pen_mode_combo.blockSignals(False)
        self._m3_s_spin.blockSignals(True)
        self._m3_s_spin.setValue(max(0, min(10000, int(self._cfg.gcode_m3_s_value))))
        self._m3_s_spin.blockSignals(False)
        self._update_z_widgets_enabled()

    def _on_pen_mode_ui_changed(self, _index: int = 0) -> None:
        self._sync_cfg_widgets()
        self._update_z_widgets_enabled()

    def _update_z_widgets_enabled(self) -> None:
        data = self._pen_mode_combo.currentData()
        use_z = str(data) == "z" or data is None
        self._z_up.setEnabled(use_z)
        self._z_down.setEnabled(use_z)
        self._m3_s_spin.setEnabled(not use_z)

    def _sync_cfg_widgets(self) -> None:
        self._sync_coord_from_widgets()
        self._cfg.z_up_mm = self._z_up.value()
        self._cfg.z_down_mm = self._z_down.value()
        self._cfg.grbl_streaming = self._cb_stream.isChecked()
        self._cfg.grbl_rx_buffer_size = int(self._rx_buf_spin.value())
        self._cfg.connection_mode = str(self._conn_mode_combo.currentData() or "serial")
        self._cfg.tcp_host = self._tcp_host_edit.text().strip()
        self._cfg.tcp_port = int(self._tcp_port_spin.value())
        dm = self._pen_mode_combo.currentData()
        self._cfg.gcode_pen_mode = str(dm) if dm is not None else "z"
        self._cfg.gcode_m3_s_value = int(self._m3_s_spin.value())
        self._cfg.gcode_program_prefix = self._gcode_prefix_edit.toPlainText()
        self._cfg.gcode_program_suffix = self._gcode_suffix_edit.toPlainText()
        self._cfg.gcode_use_g92 = self._cb_gcode_g92.isChecked()
        self._cfg.gcode_end_m30 = self._cb_gcode_m30.isChecked()

    def _on_coord_changed(self) -> None:
        self._sync_coord_from_widgets()
        self._on_document_changed()

    def _pivot_page_center(self) -> None:
        self._pivot_x.setValue(self._cfg.page_width_mm / 2.0)
        self._pivot_y.setValue(self._cfg.page_height_mm / 2.0)
        self._on_coord_changed()

    def _on_bluetooth_filter_toggled(self, checked: bool) -> None:
        self._cfg.serial_show_bluetooth_only = bool(checked)
        self._refresh_ports()

    def _on_connection_mode_changed(self, _index: int) -> None:
        self._cfg.connection_mode = str(self._conn_mode_combo.currentData() or "serial")
        self._update_connection_mode_widgets()
        self._refresh_ports()

    def _update_connection_mode_widgets(self) -> None:
        mode = str(getattr(self._cfg, "connection_mode", "serial") or "serial").strip().lower()
        is_serial = mode != "tcp"
        self._cb_bt_only.setEnabled(is_serial)
        self._port_combo.setEnabled(is_serial)
        self._baud_spin.setEnabled(is_serial)
        self._tcp_host_edit.setEnabled(not is_serial)
        self._tcp_port_spin.setEnabled(not is_serial)

    def _write_project_to_path(self, path: Path) -> None:
        iv = None
        if self._insert_paths_base:
            iv = {
                "paths": serialize_vector_paths(self._insert_paths_base),
                "scale": self._insert_vector_scale,
                "dx_mm": self._insert_vector_dx_mm,
                "dy_mm": self._insert_vector_dy_mm,
            }
        sk_blob: dict = {}
        if self._sketch_paths:
            sk_blob = {"paths": serialize_vector_paths(self._sketch_paths)}
        save_project_file(
            path,
            title=self._doc_title,
            word_html=self._editor.toHtml(),
            table_blob=self._table_editor.to_project_blob(),
            slides=self._presentation_editor.slides_storage(),
            sketch_blob=sk_blob,
            insert_vector=iv,
            slides_master=None,
        )

    def _save_project(self) -> bool:
        if self._project_path is None:
            return self._save_project_as()
        try:
            self._write_project_to_path(self._project_path)
        except OSError as e:
            QMessageBox.warning(self, "保存工程", str(e))
            return False
        self._mark_saved_state()
        self.statusBar().showMessage(f"已保存工程 {self._project_path.name}", 3000)
        return True

    def _save_project_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "另存工程为",
            str(Path.home()),
            "inkscape-wps 工程 (*.inkwps.json);;JSON (*.json);;所有文件 (*)",
        )
        if not path:
            return False
        p = Path(path)
        try:
            self._write_project_to_path(p)
        except OSError as e:
            QMessageBox.warning(self, "保存工程", str(e))
            return False
        self._project_path = p
        self._doc_title = p.stem
        self._sync_doc_title_label()
        self._mark_saved_state()
        self._update_window_title()
        self.statusBar().showMessage(f"已保存工程 {p.name}", 3000)
        return True

    def _open_project(self) -> None:
        if not self._ask_save_if_dirty("打开工程", "当前内容已修改，是否保存工程？"):
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开工程",
            str(Path.home()),
            "工程 (*.inkwps.json *.json);;所有文件 (*)",
        )
        if not path:
            return
        try:
            d = load_project_file(Path(path))
        except (OSError, ValueError, json.JSONDecodeError) as e:
            QMessageBox.warning(self, "打开工程", str(e))
            return
        self._apply_loaded_project(d)
        self._project_path = Path(path)
        t = d.get("title")
        if isinstance(t, str) and t.strip():
            self._doc_title = t.strip()
        else:
            self._doc_title = Path(path).stem
        self._sync_doc_title_label()
        self._update_window_title()
        self._on_document_changed()
        self.statusBar().showMessage(f"已打开工程 {Path(path).name}", 3000)

    def _apply_loaded_project(self, d: dict) -> None:
        self._nonword_undo_restoring = True
        try:
            self._editor.setHtml(str(d.get("word_html", "")))
            tbl = d.get("table")
            if isinstance(tbl, dict):
                self._table_editor.from_project_blob(tbl)
            slides = d.get("slides")
            if not isinstance(slides, list):
                slides = [""]
            self._presentation_editor.load_slides([str(s) if s is not None else "" for s in slides])
            self._sketch_paths.clear()
            sk = d.get("sketch")
            if isinstance(sk, dict) and sk.get("paths"):
                try:
                    self._sketch_paths.extend(deserialize_vector_paths(sk["paths"]))
                except (TypeError, ValueError):
                    pass
            self._insert_paths_base.clear()
            self._insert_vector_scale = 1.0
            self._insert_vector_dx_mm = 0.0
            self._insert_vector_dy_mm = 0.0
            self._insert_resize_drag = None
            self._insert_move_drag = None
            iv = d.get("insert_vector")
            if isinstance(iv, dict) and iv.get("paths"):
                try:
                    vps = deserialize_vector_paths(iv["paths"])
                    self._insert_paths_base.extend(vps)
                    self._insert_vector_scale = float(iv.get("scale", 1.0))
                    self._insert_vector_dx_mm = float(iv.get("dx_mm", 0.0))
                    self._insert_vector_dy_mm = float(iv.get("dy_mm", 0.0))
                    self._recompute_insert_pivot()
                except (TypeError, ValueError):
                    pass
            self._editor.document().setModified(False)
            self._nonword_modified = False
        finally:
            self._nonword_undo_restoring = False
        self._reset_nonword_undo_anchor()

    def _save_config(self) -> None:
        self._sync_cfg_widgets()
        self._cfg.serial_show_bluetooth_only = self._cb_bt_only.isChecked()
        self._cfg.grbl_streaming = self._cb_stream.isChecked()
        save_machine_config(self._cfg, self._cfg_path)
        self._log_append(f"已保存配置 {self._cfg_path}")
        self.statusBar().showMessage("已保存配置", 3000)

    def _show_gcode(self) -> None:
        self._sync_cfg_widgets()
        try:
            paths = self._current_work_paths_checked()
        except ValueError as e:
            QMessageBox.warning(self, "G-code", str(e))
            return
        g = paths_to_gcode(paths, self._cfg, order=False)
        dlg = QMessageBox(self)
        dlg.setWindowTitle("G-code")
        dlg.setText(
            self._build_job_summary(paths)
            + "\n\n当前程序（可复制）；亦可「导出 G-code 到文件」。"
        )
        dlg.setDetailedText(g)
        dlg.exec()

    def _export_gcode_to_file(self) -> None:
        self._sync_cfg_widgets()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 G-code",
            str(Path.home() / "output.nc"),
            "G-code (*.nc *.gcode *.tap *.txt);;所有文件 (*)",
        )
        if not path:
            return
        try:
            paths = self._current_work_paths_checked()
        except ValueError as e:
            QMessageBox.warning(self, "导出 G-code", str(e))
            return
        g = paths_to_gcode(paths, self._cfg, order=False)
        try:
            write_text_atomic(Path(path), g)
        except OSError as e:
            QMessageBox.warning(self, "导出 G-code", str(e))
            return
        summary = self._build_job_summary(paths).replace(chr(10), "  │  ")
        self.statusBar().showMessage(f"已导出 {Path(path).name}  │  {summary}", 5000)

    def _log_append(self, s: str) -> None:
        self._log.appendPlainText(s)

    def _refresh_ports(self) -> None:
        if (
            hasattr(self, "_conn_mode_combo")
            and str(self._conn_mode_combo.currentData() or "serial") != "serial"
        ):
            self._port_combo.clear()
            self._port_combo.addItem("TCP 模式无需扫描串口", "")
            return
        self._port_combo.clear()
        ports = filter_ports(list_port_infos(), self._cfg.serial_show_bluetooth_only)
        for info in ports:
            self._port_combo.addItem(info.label(), info.device)
        if self._port_combo.count() == 0:
            self._port_combo.addItem("（无端口，请手输设备名）", "")
            for dev in ("/dev/rfcomm0", "/dev/tty.Bluetooth-Incoming-Port", "COM5"):
                self._port_combo.addItem(dev, dev)

    def _toggle_serial(self) -> None:
        if self._grbl is not None:
            self._grbl.close()
            self._grbl = None
            self._machine_monitor.on_disconnected()
            self._connect_btn.setText("连接")
            self._send_btn.setEnabled(False)
            self._resume_checkpoint_btn.setEnabled(False)
            self._reset_btn.setEnabled(False)
            self._set_job_status("就绪", 0, 0)
            self._log_append("已断开设备连接")
            self._update_status_bar()
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
                    (data if isinstance(data, str) and data.strip() else "")
                    or self._port_combo.currentText().strip()
                )
                if "—" in port:
                    port = port.split("—", 1)[0].strip()
                if not port or port.startswith("（"):
                    raise ValueError("请选择或输入串口设备路径")
                stream = serial.Serial(port, self._baud_spin.value(), timeout=0.1)
                target_desc = port
                connect_title = "串口"
            ok_probe, probe_msg = verify_grbl_responsive(stream, on_line=self._log_append)
            if not ok_probe:
                stream.close()
                QMessageBox.warning(
                    self,
                    f"{connect_title}无应答",
                    probe_msg + "\n\n连接已关闭，未建立连接。",
                )
                return
            self._log_append(probe_msg)
            self._grbl = GrblController(
                stream,
                default_line_timeout_s=self._cfg.grbl_line_timeout_s,
                on_status=self._on_grbl_status,
                on_log_line=self._log_append,
                on_protocol_error=self._on_grbl_protocol_error,
            )
            self._machine_monitor.on_connected()
            self._grbl.start_reader()
            time.sleep(0.05)
            self._connect_btn.setText("断开")
            self._send_btn.setEnabled(True)
            self._resume_checkpoint_btn.setEnabled(False)
            self._reset_btn.setEnabled(True)
            self._set_job_status("就绪", 0, 0)
            self._log_append(f"已连接 {target_desc}")
            self._update_status_bar()
        except Exception as e:
            QMessageBox.warning(self, "连接", str(e))

    def _on_grbl_status(self, d: dict) -> None:
        self._machine_monitor.apply_status_fields(d)
        self._update_status_bar()
        if not self._pending_bf_for_rx_spin:
            return
        _, rx_free = parse_bf_field(d)
        self._pending_bf_for_rx_spin = False
        if rx_free is not None and rx_free > 0:
            v = max(32, min(16384, rx_free))
            self._rx_buf_spin.blockSignals(True)
            self._rx_buf_spin.setValue(v)
            self._rx_buf_spin.blockSignals(False)
            self._sync_cfg_widgets()
            self._log_append(f"Bf→RX：已将 RX 预算设为 {v}（来自固件状态 Bf 第二项）")
            self.statusBar().showMessage(f"RX 预算已同步为 {v}", 4000)
        else:
            self._log_append(
                "Bf→RX：本帧状态无有效 Bf。"
                "请确认固件启用 REPORT_FIELD_BUFFER_STATE"
                "（Grbl_Esp32 Report.cpp），并重试。"
            )

    def _on_grbl_protocol_error(self, s: str) -> None:
        self._machine_monitor.apply_alarm_or_error(s)
        self._log_append(f"[协议] {s}")
        self._update_status_bar()

    def _set_job_status(
        self,
        text: str,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        self._job_state_text = text
        if current is not None and total is not None:
            self._job_progress = (int(current), int(total))
        self._update_status_bar()

    def _job_progress_callback(self, current: int, total: int) -> None:
        self._set_job_status("运行中", current, total)
        QApplication.processEvents()

    def _bf_rx_sync_timeout(self) -> None:
        if self._pending_bf_for_rx_spin:
            self._pending_bf_for_rx_spin = False
            self._log_append("Bf→RX：超时未收到含 Bf 的状态报告。")

    def _sync_rx_from_grbl_bf(self) -> None:
        if not self._grbl:
            QMessageBox.information(self, "Bf→RX", "请先连接串口后再同步。")
            return
        self._pending_bf_for_rx_spin = True
        QTimer.singleShot(1500, self._bf_rx_sync_timeout)
        self._grbl.send_realtime_status_request()

    def _send_gcode(self) -> None:
        if not self._grbl:
            return
        self._sync_cfg_widgets()
        try:
            paths = self._current_work_paths_checked()
        except ValueError as e:
            QMessageBox.warning(self, "发送", str(e))
            return
        g = paths_to_gcode(paths, self._cfg, order=False)
        try:
            self._set_job_status("发送中", 0, len([ln for ln in g.splitlines() if ln.strip()]))
            n_ok, n_tot = self._grbl.send_program(
                g,
                streaming=self._cfg.grbl_streaming,
                rx_buffer_size=self._cfg.grbl_rx_buffer_size,
                on_progress=self._job_progress_callback,
            )
            self._resume_checkpoint_btn.setEnabled(False)
            self._set_job_status("已完成", n_ok, n_tot)
            self._log_append(f"已发送 {n_ok}/{n_tot} 行")
            summary = self._build_job_summary(paths).replace(chr(10), "  │  ")
            self.statusBar().showMessage(f"G-code 已发送 {n_ok} 行  │  {summary}", 5000)
        except GrblSendError as e:
            self._set_job_status("失败", e.acked_count or 0, e.total_count or 0)
            QMessageBox.warning(self, "GRBL 发送失败", str(e))
            self._log_append(f"[错误] {e}")
            remaining = len(self._grbl.remaining_program_lines_from_checkpoint())
            self._resume_checkpoint_btn.setEnabled(self._grbl.can_resume_from_checkpoint)
            if self._grbl.can_resume_from_checkpoint:
                self._log_append(
                    f"[断点] 已确认 {e.acked_count or 0} 行，剩余 {remaining} 行可续发"
                )
        except Exception as e:
            QMessageBox.warning(self, "发送", str(e))

    def _resume_from_checkpoint(self) -> None:
        if not self._grbl or not self._grbl.can_resume_from_checkpoint:
            self._resume_checkpoint_btn.setEnabled(False)
            return
        remaining = self._grbl.remaining_program_lines_from_checkpoint()
        r = QMessageBox.question(
            self,
            "断点续发",
            f"准备从上次确认断点继续发送，剩余 {len(remaining)} 行。\n\n"
            "请确认机床位置和纸张状态未变更。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if r != QMessageBox.Yes:
            return
        try:
            self._set_job_status("断点续发", 0, len(remaining))
            n_ok, n_tot = self._grbl.resume_from_checkpoint(
                streaming=self._cfg.grbl_streaming,
                rx_buffer_size=self._cfg.grbl_rx_buffer_size,
                on_progress=self._job_progress_callback,
            )
            self._resume_checkpoint_btn.setEnabled(False)
            self._set_job_status("已完成", n_ok, n_tot)
            self._log_append(f"断点续发完成 {n_ok}/{n_tot} 行")
            self.statusBar().showMessage(f"断点续发完成 {n_ok} 行", 5000)
        except GrblSendError as e:
            self._set_job_status("失败", e.acked_count or 0, e.total_count or 0)
            self._resume_checkpoint_btn.setEnabled(self._grbl.can_resume_from_checkpoint)
            QMessageBox.warning(self, "断点续发失败", str(e))
            self._log_append(f"[错误] 断点续发失败: {e}")

    def _soft_reset_machine(self) -> None:
        if not self._grbl:
            return
        r = QMessageBox.question(
            self,
            "软复位",
            "即将发送 Ctrl+X 软复位，当前作业会被中断。继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if r != QMessageBox.Yes:
            return
        try:
            self._grbl.soft_reset()
            self._set_job_status("已复位", 0, 0)
            self._log_append("已发送软复位 Ctrl+X")
        except Exception as e:
            QMessageBox.warning(self, "软复位失败", str(e))

    def _feed_hold(self) -> None:
        if self._grbl:
            self._grbl.feed_hold()

    def _cycle_start(self) -> None:
        if self._grbl:
            self._grbl.cycle_start()
