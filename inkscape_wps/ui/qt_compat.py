"""Qt兼容性层 - 统一PyQt5/PyQt6接口"""

from __future__ import annotations

import os

_requested_binding = (os.environ.get("INKSCAPE_WPS_QT_BINDING") or "").strip().lower()
if _requested_binding not in {"", "pyqt5", "pyqt6"}:
    _requested_binding = ""

try:
    if _requested_binding == "pyqt5":
        raise ImportError("forced-pyqt5")
    # 优先使用PyQt6
    from PyQt6.QtCore import (
        QEvent,
        QObject,
        QPoint,
        QPointF,
        QRectF,
        QSize,
        Qt,
        QTimer,
        QUrl,
        pyqtSignal,
        pyqtSlot,
    )
    from PyQt6.QtGui import (
        QAction,
        QBrush,
        QColor,
        QDesktopServices,
        QFont,
        QFontMetricsF,
        QIcon,
        QKeyEvent,
        QKeySequence,
        QMouseEvent,
        QPainter,
        QPen,
        QPixmap,
        QShowEvent,
        QTextCharFormat,
        QTextCursor,
        QTextDocument,
        QTransform,
    )
    from PyQt6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QComboBox,
        QDialog,
        QDoubleSpinBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLayout,
        QLineEdit,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QSizePolicy,
        QStackedWidget,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    PYQT_VERSION = 6

except ImportError:
    if _requested_binding == "pyqt6":
        raise
    # 回退到PyQt5
    from PyQt5.QtCore import (
        QEvent,
        QObject,
        QPoint,
        QPointF,
        QRectF,
        QSize,
        Qt,
        QTimer,
        QUrl,
        pyqtSignal,
        pyqtSlot,
    )
    from PyQt5.QtGui import (
        QBrush,
        QColor,
        QDesktopServices,
        QFont,
        QFontMetricsF,
        QIcon,
        QKeyEvent,
        QKeySequence,
        QMouseEvent,
        QPainter,
        QPen,
        QPixmap,
        QTextCharFormat,
        QTextCursor,
        QTextDocument,
        QTransform,
    )
    from PyQt5.QtWidgets import (
        QAbstractItemView,
        QAction,
        QApplication,
        QComboBox,
        QDialog,
        QDoubleSpinBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLayout,
        QLineEdit,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QSizePolicy,
        QStackedWidget,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    PYQT_VERSION = 5

# 兼容性函数

def get_application_style() -> str:
    """获取应用程序样式"""
    if PYQT_VERSION == 6:
        return QApplication.style().name()
    else:
        return QApplication.style().objectName()

def create_key_sequence(*args) -> QKeySequence:
    """创建快捷键序列"""
    if PYQT_VERSION == 6:
        return QKeySequence(*args)
    else:
        return QKeySequence(*args)

# 信号兼容性包装
class CompatibleSignal:
    """信号兼容性包装器"""

    def __init__(self, signal_func):
        self.signal_func = signal_func

    def connect(self, slot):
        """连接槽函数"""
        if PYQT_VERSION == 6:
            self.signal_func.connect(slot)
        else:
            self.signal_func.connect(slot)

    def disconnect(self, slot=None):
        """断开连接"""
        if PYQT_VERSION == 6:
            if slot:
                self.signal_func.disconnect(slot)
            else:
                self.signal_func.disconnect()
        else:
            if slot:
                self.signal_func.disconnect(slot)
            else:
                self.signal_func.disconnect()

    def emit(self, *args):
        """发射信号"""
        self.signal_func.emit(*args)

# 常用兼容性常量
ALIGN_LEFT = Qt.AlignmentFlag.AlignLeft if PYQT_VERSION == 6 else Qt.AlignLeft
ALIGN_RIGHT = Qt.AlignmentFlag.AlignRight if PYQT_VERSION == 6 else Qt.AlignRight
ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter if PYQT_VERSION == 6 else Qt.AlignCenter
ALIGN_JUSTIFY = Qt.AlignmentFlag.AlignJustify if PYQT_VERSION == 6 else Qt.AlignJustify

# 导出常用类和函数
__all__ = [
    # Qt核心
    'QEvent', 'QObject', 'QPoint', 'QPointF', 'QRectF', 'QSize', 'QTimer', 'QUrl', 'Qt',
    'pyqtSignal', 'pyqtSlot', 'PYQT_VERSION',

    # Qt GUI
    'QAction', 'QBrush', 'QColor', 'QDesktopServices', 'QFont', 'QFontMetricsF',
    'QIcon', 'QKeyEvent', 'QKeySequence', 'QMouseEvent', 'QPainter', 'QPen',
    'QPixmap', 'QShowEvent', 'QTextCharFormat', 'QTextCursor', 'QTextDocument',
    'QTransform',

    # Qt Widgets
    'QApplication', 'QComboBox', 'QDialog', 'QFileDialog', 'QFrame', 'QGridLayout',
    'QHBoxLayout', 'QLabel', 'QLineEdit', 'QLayout', 'QMainWindow', 'QMenu', 'QMessageBox',
    'QPushButton', 'QSizePolicy', 'QStackedWidget', 'QTableWidget',
    'QTableWidgetItem', 'QTextEdit', 'QVBoxLayout', 'QWidget', 'QAbstractItemView',
    'QDoubleSpinBox',

    # 兼容性函数
    'get_application_style', 'create_key_sequence', 'CompatibleSignal',

    # 对齐常量
    'ALIGN_LEFT', 'ALIGN_RIGHT', 'ALIGN_CENTER', 'ALIGN_JUSTIFY'
]
