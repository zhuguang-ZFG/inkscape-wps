"""主窗口：更贴近 WPS 的 Ribbon + 文件入口 + 状态栏 + 标尺。"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QKeySequence,
    QMouseEvent,
    QPen,
    QShortcut,
    QTextCharFormat,
)
from PyQt6.QtWidgets import (
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
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
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
from inkscape_wps.core.grbl import GrblController, GrblSendError, parse_bf_field, verify_serial_responsive
from inkscape_wps.core.grbl_firmware_ref import GRBL_ESP32_DEFAULT_RX_BUFFER_SIZE
from inkscape_wps.core.hershey import HersheyFontMapper, map_document_lines
from inkscape_wps.core.kdraw_paths import suggest_gcode_fonts_dirs
from inkscape_wps.core.raster_trace import trace_image_to_svg
from inkscape_wps.core.serial_discovery import filter_ports, list_port_infos
from inkscape_wps.core.svg_import import vector_paths_from_svg_file, vector_paths_from_svg_string
from inkscape_wps.core.types import Point, VectorPath, paths_bounding_box
from inkscape_wps.ui.document_bridge import apply_default_tab_stops, text_edit_to_layout_lines
from inkscape_wps.ui.drawing_view_model import DrawingViewModel
from inkscape_wps.ui.presentation_editor import WpsPresentationEditor
from inkscape_wps.ui.table_editor import WpsTableEditor
from inkscape_wps.ui.ribbon import RibbonGroup, RibbonTabVSep, RibbonVSeparator, WpsRibbon
from inkscape_wps.ui.wps_theme import apply_wps_theme
from inkscape_wps.ui.wps_widgets import make_horizontal_ruler_mm


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
            kuixiang_mm_per_unit=self._cfg.kuixiang_mm_per_unit,
        )
        self._view_model = DrawingViewModel(self._cfg)
        self._grbl: Optional[GrblController] = None
        self._pending_bf_for_rx_spin = False
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

        self._build_ui()
        self._table_editor.set_font_point_size_resolver(lambda: float(self._size_spin.value()))
        _f0 = self._editor.currentFont()
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

        self._mapper.preload_background()
        self._on_document_changed()
        self._update_window_title()
        self._update_status_bar()
        self._sync_undo_actions(self._editor.document().isUndoAvailable())
        _d = self._editor.document()
        self._sync_redo_actions(_d.isRedoAvailable() if hasattr(_d, "isRedoAvailable") else False)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._preview.viewport():
            et = event.type()
            if et == QEvent.Type.Leave and self._insert_resize_drag is None and self._insert_move_drag is None:
                self._preview.viewport().unsetCursor()
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
        self._act_undo = QAction("撤销", self, triggered=self._editor.undo)
        m_edit.addAction(self._act_undo)
        self._act_redo = QAction("重做", self, triggered=self._editor.redo)
        m_edit.addAction(self._act_redo)
        m_edit.addSeparator()
        m_edit.addAction("全选", self._select_all_current)

        m_tool = mb.addMenu("工具")
        m_tool.addAction("生成 G-code…", self._show_gcode)

        m_help = mb.addMenu("帮助")
        m_help.addAction(
            "关于",
            lambda: QMessageBox.information(
                self,
                "关于",
                "写字机上位机 · WPS 风格界面\n核心逻辑与 PyQt 视图分离，便于后续移植。",
            ),
        )

        qt = QToolBar("快速访问")
        qt.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, qt)
        qt.addAction(self._act_undo)
        qt.addAction(self._act_redo)
        qt.addSeparator()
        qt.addAction(QAction("保存配置", self, triggered=self._save_config))
        qt.addAction(QAction("生成 G-code", self, triggered=self._show_gcode))

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
        b_pick.setToolTip("支持包内 Hershey JSON、或 grblapp/奎享导出的合并字库 JSON（大文件将延迟加载）")
        b_pick.clicked.connect(self._pick_stroke_font_json)
        g_stroke.add_widget(b_pick)
        b_reset = QPushButton("恢复包内")
        b_reset.clicked.connect(self._reset_stroke_font_to_bundled)
        g_stroke.add_widget(b_reset)
        b_kd = QPushButton("KDraw 字库")
        b_kd.setToolTip("在访达中打开本机 KDraw 的 gcodeFonts（.gfont 需先导出为 JSON）")
        b_kd.clicked.connect(self._open_kdraw_gcode_fonts_dir)
        g_stroke.add_widget(b_kd)
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
            f"新建默认 {GRBL_ESP32_DEFAULT_RX_BUFFER_SIZE}（对齐 Grbl_Esp32 Serial.h 的 RX_BUFFER_SIZE；AVR 常见 128）。"
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

        g_run = RibbonGroup("运行")
        self._connect_btn = QPushButton("连接")
        self._connect_btn.clicked.connect(self._toggle_serial)
        self._send_btn = QPushButton("发送 G-code")
        self._send_btn.clicked.connect(self._send_gcode)
        self._send_btn.setEnabled(False)
        g_run.add_widget(self._connect_btn)
        g_run.add_widget(self._send_btn)
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
        self._apply_font_size(self._size_spin.value())
        self._table_editor = WpsTableEditor(self._cfg)
        self._presentation_editor = WpsPresentationEditor(self._cfg)
        self._stack.addWidget(self._editor)
        self._stack.addWidget(self._table_editor)
        self._stack.addWidget(self._presentation_editor)
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
        self._preview.setRenderHints(self._preview.renderHints())
        pf.addWidget(self._preview)
        tv.addWidget(prev_frame, stretch=2)

        log_frame = QFrame()
        log_frame.setObjectName("TaskPaneGroup")
        lf = QVBoxLayout(log_frame)
        lf.addWidget(QLabel("串口 / 状态"))
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)
        lf.addWidget(self._log)
        tv.addWidget(log_frame, stretch=3)

        splitter.addWidget(task)
        splitter.setStretchFactor(1, 3)

        self._cb_bt_only.setChecked(self._cfg.serial_show_bluetooth_only)
        self._apply_cfg_to_coord_widgets()
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
            self._act_undo.setEnabled(False)
            self._act_redo.setEnabled(False)
        self._on_document_changed()
        self._update_status_bar()
        self._update_window_title()

    def _on_nonword_content_changed(self) -> None:
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

    def _new_document(self) -> None:
        self._editor.clear()
        self._table_editor.clear_all()
        self._presentation_editor.clear_all()
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
        self._sync_doc_title_label()
        self._editor.document().setModified(False)
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
            self._st_cursor.setText(f"第 {line} 行，第 {col} 列  │  {chars} 字符  │  {nlines} 行")
        elif idx == 1:
            r, c = self._table_editor.row_column_count()
            self._st_cursor.setText(f"表格  │  {r} 行 × {c} 列")
        else:
            self._st_cursor.setText(self._presentation_editor.status_line())
        if self._grbl is not None:
            self._st_conn.setText("串口：已连接")
        else:
            self._st_conn.setText("串口：未连接")
        d = self._editor.document()
        if idx == 0:
            if hasattr(d, "isUndoAvailable"):
                self._act_undo.setEnabled(d.isUndoAvailable())
            if hasattr(d, "isRedoAvailable"):
                self._act_redo.setEnabled(d.isRedoAvailable())
        else:
            self._act_undo.setEnabled(False)
            self._act_redo.setEnabled(False)

    def _sync_undo_actions(self, available: bool) -> None:
        if self._stack.currentIndex() != 0:
            self._act_undo.setEnabled(False)
        else:
            self._act_undo.setEnabled(available)

    def _sync_redo_actions(self, available: bool) -> None:
        if self._stack.currentIndex() != 0:
            self._act_redo.setEnabled(False)
        else:
            self._act_redo.setEnabled(available)

    def _remap_stroke_font(self) -> None:
        self._mapper = HersheyFontMapper(
            _resolve_stroke_font_path(self._cfg),
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
                "若已安装奎享 KDraw，可将 .gfont 用 grblapp 的导出工具转为 JSON 后放入本应用可读路径。",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(dirs[0].resolve())))

    def _mm_per_px_for(self, editor: QTextEdit) -> float:
        w = max(1, editor.viewport().width())
        return self._cfg.page_width_mm / float(w)

    def _mm_per_px(self) -> float:
        return self._mm_per_px_for(self._editor)

    def _current_paths(self) -> List[VectorPath]:
        idx = self._stack.currentIndex()
        if idx == 1:
            lines = self._table_editor.to_layout_lines()
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
                return True
            if self._insert_move_drag is not None:
                sp = self._preview.mapToScene(event.position())
                st: QPointF = self._insert_move_drag["start_scene"]
                dmm_x, dmm_y = self._scene_delta_to_mm_delta(QPointF(sp.x() - st.x(), sp.y() - st.y()), mpp)
                self._insert_vector_dx_mm = self._insert_move_drag["dx0"] + dmm_x
                self._insert_vector_dy_mm = self._insert_move_drag["dy0"] + dmm_y
                self._insert_offset_x_spin.blockSignals(True)
                self._insert_offset_y_spin.blockSignals(True)
                self._insert_offset_x_spin.setValue(self._insert_vector_dx_mm)
                self._insert_offset_y_spin.setValue(self._insert_vector_dy_mm)
                self._insert_offset_x_spin.blockSignals(False)
                self._insert_offset_y_spin.blockSignals(False)
                self._on_document_changed()
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
                    return True
                if self._insert_move_drag is not None:
                    self._insert_move_drag = None
                    self._preview.viewport().unsetCursor()
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
        combined = list(text_paths) + self._scaled_insert_paths()
        ordered = order_paths_nearest_neighbor(combined)
        return transform_paths(ordered, self._cfg)

    def _fill_standard_file_menu(self, menu: QMenu) -> None:
        """菜单栏与绿色「文件」按钮共用，顺序贴近 WPS/Word。"""
        menu.clear()
        menu.addAction("新建", self._new_document)
        act_open = QAction("打开…", self)
        act_open.setEnabled(False)
        act_open.setStatusTip("写字机文档打开/保存后续提供；当前可编辑后直接「生成 G-code」。")
        menu.addAction(act_open)
        menu.addSeparator()
        m_ins = menu.addMenu("插入")
        self._populate_insert_vector_menu(m_ins)
        menu.addSeparator()
        menu.addAction("保存配置…", self._save_config)
        menu.addAction("生成 G-code…", self._show_gcode)
        menu.addSeparator()
        menu.addAction("退出", self.close)

    def _active_rich_text_edit(self) -> Optional[QTextEdit]:
        idx = self._stack.currentIndex()
        if idx == 0:
            return self._editor
        if idx == 2:
            return self._presentation_editor.slide_editor()
        return None

    def _sync_text_document_margins(self) -> None:
        """正文边距（px）与 MachineConfig.document_margin_mm、纸宽对齐，贴近 WPS 页边距观感。"""
        pw = float(self._cfg.page_width_mm)
        vw = max(1, self._editor.viewport().width())
        mpx = float(self._cfg.document_margin_mm) / (pw / float(vw))
        self._editor.document().setDocumentMargin(mpx)
        self._presentation_editor.set_slide_document_margin_px(mpx)

    def _install_editor_shortcuts(self) -> None:
        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
        parent = self._stack

        def _bind(key, slot) -> None:
            sc = QShortcut(QKeySequence(key), parent)
            sc.setContext(ctx)
            sc.activated.connect(slot)

        _bind(QKeySequence.StandardKey.Bold, self._toggle_bold)
        _bind(QKeySequence.StandardKey.Italic, self._toggle_italic)
        _bind(QKeySequence.StandardKey.Underline, self._toggle_underline)
        _bind("Ctrl+L", lambda: self._set_alignment(Qt.AlignmentFlag.AlignLeft))
        _bind("Ctrl+E", lambda: self._set_alignment(Qt.AlignmentFlag.AlignCenter))
        _bind("Ctrl+R", lambda: self._set_alignment(Qt.AlignmentFlag.AlignRight))
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

    def _apply_font_family(self, font: QFont) -> None:
        te = self._active_rich_text_edit()
        fam = font.family()
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

    def _sync_cfg_widgets(self) -> None:
        self._sync_coord_from_widgets()
        self._cfg.z_up_mm = self._z_up.value()
        self._cfg.z_down_mm = self._z_down.value()
        self._cfg.grbl_streaming = self._cb_stream.isChecked()
        self._cfg.grbl_rx_buffer_size = int(self._rx_buf_spin.value())

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

    def _save_config(self) -> None:
        self._sync_cfg_widgets()
        self._cfg.serial_show_bluetooth_only = self._cb_bt_only.isChecked()
        self._cfg.grbl_streaming = self._cb_stream.isChecked()
        save_machine_config(self._cfg, self._cfg_path)
        self._log_append(f"已保存配置 {self._cfg_path}")
        self.statusBar().showMessage("已保存配置", 3000)

    def _show_gcode(self) -> None:
        self._sync_cfg_widgets()
        g = paths_to_gcode(self._work_paths(), self._cfg, order=False)
        dlg = QMessageBox(self)
        dlg.setWindowTitle("G-code")
        dlg.setText("当前程序（可复制）")
        dlg.setDetailedText(g)
        dlg.exec()

    def _log_append(self, s: str) -> None:
        self._log.appendPlainText(s)

    def _refresh_ports(self) -> None:
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
            self._connect_btn.setText("连接")
            self._send_btn.setEnabled(False)
            self._log_append("已断开串口")
            self._update_status_bar()
            return
        try:
            import serial

            data = self._port_combo.currentData()
            port = (data if isinstance(data, str) and data.strip() else "") or self._port_combo.currentText().strip()
            if "—" in port:
                port = port.split("—", 1)[0].strip()
            if not port or port.startswith("（"):
                raise ValueError("请选择或输入串口设备路径")
            ser = serial.Serial(port, self._baud_spin.value(), timeout=0.1)
            ok_probe, probe_msg = verify_serial_responsive(ser, on_line=self._log_append)
            if not ok_probe:
                ser.close()
                QMessageBox.warning(self, "串口无应答", probe_msg + "\n\n端口已关闭，未建立连接。")
                return
            self._log_append(probe_msg)
            self._grbl = GrblController(
                ser,
                default_line_timeout_s=self._cfg.grbl_line_timeout_s,
                on_status=self._on_grbl_status,
                on_log_line=self._log_append,
                on_protocol_error=lambda s: self._log_append(f"[协议] {s}"),
            )
            self._grbl.start_reader()
            time.sleep(0.05)
            self._connect_btn.setText("断开")
            self._send_btn.setEnabled(True)
            self._log_append(f"已打开 {port}")
            self._update_status_bar()
        except Exception as e:
            QMessageBox.warning(self, "串口", str(e))

    def _on_grbl_status(self, d: dict) -> None:
        self._log_append(str(d))
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
                "Bf→RX：本帧状态无有效 Bf。请确认固件启用 REPORT_FIELD_BUFFER_STATE（Grbl_Esp32 Report.cpp），并重试。"
            )

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
        g = paths_to_gcode(self._work_paths(), self._cfg, order=False)
        try:
            n_ok, n_tot = self._grbl.send_program(
                g,
                streaming=self._cfg.grbl_streaming,
                rx_buffer_size=self._cfg.grbl_rx_buffer_size,
            )
            self._log_append(f"已发送 {n_ok}/{n_tot} 行")
            self.statusBar().showMessage(f"G-code 已发送 {n_ok} 行", 5000)
        except GrblSendError as e:
            QMessageBox.warning(self, "GRBL 发送失败", str(e))
            self._log_append(f"[错误] {e}")
        except Exception as e:
            QMessageBox.warning(self, "发送", str(e))

    def _feed_hold(self) -> None:
        if self._grbl:
            self._grbl.feed_hold()

    def _cycle_start(self) -> None:
        if self._grbl:
            self._grbl.cycle_start()
