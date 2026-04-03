"""WPS/Office 风格浅色主题（纯 QSS，无第三方 UI 库依赖）。"""

# WPS 品牌绿（标题栏点缀与选中态）
WPS_ACCENT = "#217346"
WPS_ACCENT_LIGHT = "#2d8f5c"


def application_stylesheet() -> str:
    return f"""
    QMainWindow {{
        background-color: #f7f9fb;
    }}
    QWidget {{
        /* 统一全局字体，提升“WPS 风格”观感与清晰度 */
        font-family: "PingFang SC","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
        color: #111111;
    }}
    QMenuBar {{
        background-color: #ffffff;
        border-bottom: 1px solid #e6eaee;
        padding: 2px 4px;
    }}
    QMenuBar::item:selected {{
        background-color: #e6f4ea;
        color: #000000;
    }}
    QMenu {{
        background-color: #ffffff;
        border: 1px solid #dfe6ec;
    }}
    QToolBar {{
        background-color: #f7f9fb;
        border: none;
        border-bottom: 1px solid #e6eaee;
        spacing: 6px;
        padding: 2px 6px;
    }}
    #WpsRibbon {{
        background-color: #f3f3f3;
        border-bottom: 1px solid #c8c8c8;
    }}
    #WpsRibbonTabBar {{
        background-color: #f3f5f7;
        border-bottom: 1px solid #e6eaee;
    }}
    #RibbonTabButton {{
        padding: 6px 16px;
        border: none;
        background: transparent;
        color: #333333;
        font-size: 13px;
        border-bottom: 2px solid transparent;
    }}
    #RibbonTabButton:hover {{
        background-color: #f2f4f6;
    }}
    #RibbonTabButton:checked {{
        background-color: #f7fff9;
        border-top: none;
        border-bottom: 2px solid {WPS_ACCENT};
        color: #0f3d26;
        font-weight: 600;
    }}
    #RibbonPanel {{
        background-color: #ffffff;
        border: none;
    }}
    #RibbonScroll {{
        background-color: #ffffff;
        border: none;
    }}
    #RibbonGroup {{
        background-color: #ffffff;
        border: 1px solid #dfe6ec;
        border-radius: 2px;
        min-height: 64px;
    }}
    #RibbonGroupTitle {{
        color: #6b6f76;
        font-size: 10px;
        font-weight: 600;
        padding: 1px 4px 3px 4px;
    }}
    #DocumentCanvas {{
        background-color: #eef1f4;
        border: none;
    }}
    #DocumentSheet {{
        background-color: #ffffff;
        border: 1px solid #dfe6ec;
    }}
    QTextEdit#DocumentEditor {{
        background-color: #ffffff;
        border: none;
        /* 水平留白主要由 QTextDocument 边距（与配置「页边距 mm」一致）控制 */
        /* 避免 padding 与 QTextDocument margin 叠加导致“纸面布局不合理” */
        padding: 0px;
        font-family: "PingFang SC","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
    }}
    QTextEdit#PresentationSlideEditor {{
        background-color: #ffffff;
        border: none;
        /* 同上：让纵向排版只受 document margin 控制 */
        padding: 0px;
        font-family: "PingFang SC","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
    }}
    QWidget#StrokeTextEditor {{
        background-color: #ffffff;
        border: 1px solid #dfe6ec;
        border-radius: 3px;
    }}
    QFrame#TaskPaneGroup {{
        font-weight: 600;
        border: 1px solid #dfe6ec;
        border-radius: 4px;
        margin-top: 4px;
        padding: 6px;
        background-color: #f8fbfd;
    }}
    QPushButton {{
        padding: 4px 12px;
        border: 1px solid #dfe6ec;
        border-radius: 3px;
        background-color: #ffffff;
        min-height: 22px;
    }}

    /* Ribbon 内部控件不要复用全局 QPushButton 的“厚边框按钮”外观 */
    #WpsRibbon QPushButton {{
        border: none;
        background-color: transparent;
        border-radius: 2px;
        padding: 4px 10px;
        min-height: 0px;
    }}
    #WpsRibbon QPushButton:hover {{
        background-color: #eef8f1;
    }}
    #WpsRibbon QPushButton:pressed {{
        background-color: #e1f2e8;
    }}
    /* 模式按钮例外：仍保持 WPS tab 的边框与选中态 */
    QPushButton#WpsModeTabButton {{
        /* Ribbon 内“文字/表格/演示”模式按钮：与 WPS/Office 选项卡一致的强调样式 */
        background-color: #ffffff;
        border: 1px solid #dfe6ec;
        border-radius: 2px;
        padding: 0px 10px;
        color: #333333;
        font-weight: 600;
        min-height: 0px;
        max-height: 30px;
    }}
    QPushButton#WpsModeTabButton:hover {{
        border-color: {WPS_ACCENT_LIGHT};
        background-color: #eef8f1;
        color: #0f3d26;
    }}
    QPushButton#WpsModeTabButton:checked {{
        background-color: #f7fff9;
        border: 1px solid {WPS_ACCENT};
        color: #0f3d26;
    }}
    QPushButton:hover {{
        border-color: {WPS_ACCENT};
        background-color: #eef8f1;
    }}
    QPushButton:pressed {{
        background-color: #e1f2e8;
    }}
    QComboBox, QSpinBox, QDoubleSpinBox, QFontComboBox {{
        border: 1px solid #dfe6ec;
        border-radius: 3px;
        padding: 2px 6px;
        min-height: 22px;
        background: #ffffff;
    }}
    QCheckBox {{
        spacing: 6px;
    }}
    QPlainTextEdit {{
        background-color: #ffffff;
        color: #222222;
        border: 1px solid #d3d7db;
        border-radius: 3px;
        font-family: "PingFang SC","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
        font-size: 12px;
    }}
    QLabel#StatusHint {{
        color: #555555;
        font-size: 11px;
    }}
    QGraphicsView {{
        background-color: #ffffff;
        border: 1px solid #dfe6ec;
        border-radius: 3px;
    }}
    QSplitter::handle {{
        background: #d0d0d0;
        width: 4px;
    }}
    #WpsBrandStrip {{
        background-color: {WPS_ACCENT};
        min-height: 3px;
        max-height: 3px;
    }}
    #RibbonVSeparator {{
        background-color: #d0d0d0;
        margin-top: 8px;
        margin-bottom: 8px;
    }}
    #RibbonTabVSep {{
        background-color: #c0c0c0;
        margin-top: 6px;
        margin-bottom: 6px;
    }}
    QToolButton#WpsFileButton {{
        background-color: {WPS_ACCENT};
        color: #ffffff;
        border: none;
        border-radius: 0px;
        padding: 8px 18px;
        font-size: 14px;
        font-weight: bold;
        min-height: 28px;
    }}
    QToolButton#WpsFileButton:hover {{
        background-color: {WPS_ACCENT_LIGHT};
    }}
    QToolButton#WpsFileButton::menu-indicator {{
        image: none;
        width: 0px;
    }}
    QLabel#WpsDocTitle {{
        color: #333333;
        font-size: 13px;
        font-weight: 600;
        padding: 0 12px;
    }}
    QStatusBar {{
        background-color: #f7f9fb;
        border-top: 1px solid #e6eaee;
        font-size: 12px;
    }}
    QStatusBar::item {{
        border: none;
    }}
    #StatusBarPermanent {{
        color: #444444;
        padding: 0 8px;
    }}
    QComboBox#StatusZoomCombo {{
        min-width: 72px;
        max-height: 22px;
    }}
    #RulerBar {{
        background-color: #e4e4e4;
        border-bottom: 1px solid #c8c8c8;
        color: #555555;
        font-family: "Menlo", "Consolas", monospace;
        font-size: 10px;
        padding: 2px 8px;
    }}

    /* 表格统一浅色网格（与 WPS 表格观感更接近） */
    QTableWidget {{
        background-color: #ffffff;
        border: 1px solid #dfe6ec;
        gridline-color: #e6eaee;
        font-family: "PingFang SC","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
    }}
    QHeaderView::section {{
        background-color: #f7f9fb;
        color: #2a2a2a;
        border: 1px solid #e6eaee;
        padding: 4px 6px;
        font-weight: 600;
    }}
    QTableWidget::item:selected {{
        background-color: #e6f4ea;
        color: #0f3d26;
    }}
    QTableWidget::item {{
        border: none;
    }}
    """


def apply_wps_theme(window) -> None:
    window.setStyleSheet(application_stylesheet())
