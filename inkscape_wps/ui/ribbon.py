"""仿 WPS / Office 的 Ribbon：页签 + 分组工具区（仅 PyQt6）。"""

from __future__ import annotations

from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class RibbonVSeparator(QFrame):
    """Ribbon 分组之间的竖线（类似 Office / WPS）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RibbonVSeparator")
        self.setFixedWidth(1)
        self.setMinimumHeight(62)
        self.setMaximumWidth(1)


class RibbonTabVSep(QFrame):
    """页签行内竖线（「文件」与功能页签之间）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RibbonTabVSep")
        self.setFixedWidth(1)
        self.setFixedHeight(22)


class RibbonGroup(QFrame):
    """带底部标题的分组框（如「字体」「段落」）。"""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RibbonGroup")
        self._row = QHBoxLayout()
        # WPS Ribbon 更紧凑：减少内边距与组高度
        self._row.setContentsMargins(6, 4, 6, 2)
        self._row.setSpacing(6)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 0)
        outer.setSpacing(0)
        outer.addLayout(self._row)
        t = QLabel(title)
        t.setObjectName("RibbonGroupTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(t)

    def row(self) -> QHBoxLayout:
        return self._row

    def add_widget(self, w: QWidget) -> None:
        self._row.addWidget(w)


class WpsRibbon(QWidget):
    """
    顶部分页按钮 + 下方白色面板；每页内容为横向 ScrollArea，可放多个 RibbonGroup。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WpsRibbon")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tab_bar = QWidget()
        self._tab_bar.setObjectName("WpsRibbonTabBar")
        tab_lay = QHBoxLayout(self._tab_bar)
        tab_lay.setContentsMargins(8, 4, 8, 0)
        tab_lay.setSpacing(2)

        self._stack = QStackedWidget()
        self._stack.setObjectName("RibbonPanel")

        self._buttons: List[QPushButton] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._stack.setCurrentIndex)

        root.addWidget(self._tab_bar)
        root.addWidget(self._stack)

    def add_page(self, title: str) -> tuple[QHBoxLayout, QWidget]:
        """新增一页，返回 (横向布局, 内部容器) 用于 addWidget(RibbonGroup...)。"""
        idx = len(self._buttons)
        btn = QPushButton(title)
        btn.setObjectName("RibbonTabButton")
        btn.setCheckable(True)
        btn.setAutoExclusive(False)
        btn.setMinimumHeight(30)
        self._group.addButton(btn, idx)
        self._tab_bar.layout().addWidget(btn)
        self._buttons.append(btn)

        scroll = QScrollArea()
        scroll.setObjectName("RibbonScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        inner.setObjectName("RibbonScrollInner")
        h = QHBoxLayout(inner)
        h.setContentsMargins(10, 8, 10, 10)
        h.setSpacing(12)
        h.setAlignment(Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(inner)
        self._stack.addWidget(scroll)

        if idx == 0:
            btn.setChecked(True)
        return h, inner

    def add_tab_trailing_stretch(self) -> None:
        lay = self._tab_bar.layout()
        if isinstance(lay, QHBoxLayout):
            lay.addStretch(1)

    def prepend_to_tab_bar(self, *widgets: QWidget) -> None:
        """在页签按钮列最左侧插入（如「文件」、文档标题）。"""
        lay = self._tab_bar.layout()
        if not isinstance(lay, QHBoxLayout):
            return
        for i, w in enumerate(widgets):
            lay.insertWidget(i, w)

    def set_current_page(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)
            self._stack.setCurrentIndex(index)
