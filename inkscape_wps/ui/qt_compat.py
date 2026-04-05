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
        QShowEvent,
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
]
