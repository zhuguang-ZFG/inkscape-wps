"""
修补 qframelesswindow 在 macOS 上的问题：
构造时 winId 常为 0，updateFrameless 会拿到无效 NSWindow，
引发异常或事件循环异常（Dock 无限弹跳、无窗口）。
"""

from __future__ import annotations

import sys
from typing import Any


def apply_macos_frameless_shim() -> bool:
    """在创建 QApplication 之后、创建 FluentWindow 之前调用。成功返回 True。"""
    if sys.platform != "darwin":
        return False
    try:
        from PyQt5.QtCore import QTimer
        from qframelesswindow.mac import MacFramelessWindow as MFW
    except Exception:
        return False

    _orig_update = MFW.updateFrameless
    _orig_hide = MFW._hideSystemTitleBar

    def _guarded_hide(self: Any, show_button: bool = False) -> None:
        if getattr(self, "_MacFramelessWindow__nsWindow", None) is None:
            return
        _orig_hide(self, show_button)

    def _deferred_finish(self: Any) -> None:
        n = int(getattr(self, "_wps_frameless_shim_n", 0)) + 1
        self._wps_frameless_shim_n = n
        if n > 120:
            return
        if int(self.winId()) == 0:
            QTimer.singleShot(20, lambda: _deferred_finish(self))
            return
        try:
            _orig_update(self)
        except Exception:
            pass

    def _update_patched(self: Any) -> None:
        if int(self.winId()) == 0:
            self._wps_frameless_shim_n = 0
            QTimer.singleShot(0, lambda: _deferred_finish(self))
            return
        try:
            _orig_update(self)
        except Exception:
            pass

    MFW.updateFrameless = _update_patched  # type: ignore[assignment]
    MFW._hideSystemTitleBar = _guarded_hide  # type: ignore[assignment]
    return True
