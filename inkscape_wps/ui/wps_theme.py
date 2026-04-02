"""WPS/Office 风格浅色主题（纯 QSS，无第三方 UI 库依赖）。"""

# WPS 品牌绿（标题栏点缀与选中态）
WPS_ACCENT = "#217346"
WPS_ACCENT_LIGHT = "#2d8f5c"


def application_stylesheet() -> str:
    return f"""
    QMainWindow {{
        background-color: #e8e8e8;
    }}
    QMenuBar {{
        background-color: #f5f5f5;
        border-bottom: 1px solid #d0d0d0;
        padding: 2px 4px;
    }}
    QMenuBar::item:selected {{
        background-color: #e0e0e0;
    }}
    QMenu {{
        background-color: #ffffff;
        border: 1px solid #d0d0d0;
    }}
    QToolBar {{
        background-color: #f0f0f0;
        border: none;
        border-bottom: 1px solid #d8d8d8;
        spacing: 6px;
        padding: 2px 6px;
    }}
    #WpsRibbon {{
        background-color: #f3f3f3;
        border-bottom: 1px solid #c8c8c8;
    }}
    #RibbonTabButton {{
        padding: 6px 16px;
        border: none;
        background: transparent;
        color: #333333;
        font-size: 13px;
    }}
    #RibbonTabButton:hover {{
        background-color: #e8e8e8;
    }}
    #RibbonTabButton:checked {{
        background-color: #ffffff;
        border-top: 2px solid {WPS_ACCENT};
        color: #000000;
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
        background-color: #fafafa;
        border: 1px solid #e0e0e0;
        border-radius: 3px;
        min-height: 78px;
    }}
    #RibbonGroupTitle {{
        color: #666666;
        font-size: 11px;
        padding: 2px 4px 4px 4px;
    }}
    #DocumentCanvas {{
        background-color: #c8c8c8;
        border: none;
    }}
    #DocumentSheet {{
        background-color: #ffffff;
        border: 1px solid #b0b0b0;
    }}
    QTextEdit#DocumentEditor {{
        background-color: #ffffff;
        border: none;
        /* 水平留白主要由 QTextDocument 边距（与配置「页边距 mm」一致）控制 */
        padding: 20px 6px;
        font-size: 12pt;
    }}
    QTextEdit#PresentationSlideEditor {{
        background-color: #ffffff;
        border: none;
        padding: 16px 6px;
        font-size: 12pt;
    }}
    QFrame#TaskPaneGroup {{
        font-weight: 600;
        border: 1px solid #d0d0d0;
        border-radius: 4px;
        margin-top: 4px;
        padding: 6px;
        background-color: #fafafa;
    }}
    QPushButton {{
        padding: 4px 12px;
        border: 1px solid #c0c0c0;
        border-radius: 3px;
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #ffffff, stop:1 #f0f0f0);
        min-height: 22px;
    }}
    QPushButton:hover {{
        border-color: {WPS_ACCENT};
        background: #f8fff8;
    }}
    QPushButton:pressed {{
        background: #e8e8e8;
    }}
    QComboBox, QSpinBox, QDoubleSpinBox, QFontComboBox {{
        border: 1px solid #c0c0c0;
        border-radius: 3px;
        padding: 2px 6px;
        min-height: 22px;
        background: #ffffff;
    }}
    QCheckBox {{
        spacing: 6px;
    }}
    QPlainTextEdit {{
        background-color: #1e1e1e;
        color: #d4d4d4;
        border: 1px solid #3c3c3c;
        border-radius: 3px;
        font-family: "Menlo", "Consolas", monospace;
        font-size: 11px;
    }}
    QLabel#StatusHint {{
        color: #555555;
        font-size: 11px;
    }}
    QGraphicsView {{
        background-color: #2a2a2a;
        border: 1px solid #404040;
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
        background-color: #f0f0f0;
        border-top: 1px solid #d0d0d0;
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
    """


def apply_wps_theme(window) -> None:
    window.setStyleSheet(application_stylesheet())
