"""python -m inkscape_wps

优先使用 Fluent UI（PyQt5 + qfluentwidgets）。若环境缺失则回退 PyQt6 版本。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import logging
import os
import sys
from pathlib import Path

_logger = logging.getLogger(__name__)


def _darwin_clear_offscreen_for_gui() -> None:
    """
    IDE / pytest / 其他工具常在环境里留下 QT_QPA_PLATFORM=offscreen，导致「进程在跑但永远无窗口」。
    本应用为桌面 GUI，默认清除；无头测试请设 INKSCAPE_WPS_ALLOW_OFFSCREEN=1。
    """
    if sys.platform != "darwin":
        return
    if (os.environ.get("INKSCAPE_WPS_ALLOW_OFFSCREEN") or "").strip() in (
        "1",
        "true",
        "yes",
    ):
        return
    qpa = (os.environ.get("QT_QPA_PLATFORM") or "").strip().lower()
    if qpa == "offscreen":
        os.environ.pop("QT_QPA_PLATFORM", None)
        print(
            "inkscape-wps: 检测到 QT_QPA_PLATFORM=offscreen，已为本进程清除以便显示窗口。\n"
            "  若需保持 offscreen（无界面测试），请设置 INKSCAPE_WPS_ALLOW_OFFSCREEN=1。",
            file=sys.stderr,
            flush=True,
        )


def _ensure_pyqt_binding_plugin_env(
    binding: str, *, prefer_this_binding: bool = False
) -> None:
    """
    在首次 import PyQt* 之前调用。
    修正常见「找不到平台插件 / cocoa」：venv、IDE、打包后未继承 QT_PLUGIN_PATH 时 Qt 能加载但不出窗。
    prefer_this_binding: 进入 PyQt6 入口时为 True，避免先前已为 PyQt5 写入的 QT_PLUGIN_PATH 阻碍 Qt6。
    """
    if sys.platform == "darwin":
        os.environ.setdefault("QT_QPA_PLATFORM", "cocoa")

    pkg = "PyQt5" if binding.lower() == "pyqt5" else "PyQt6"
    try:
        spec = importlib.util.find_spec(pkg)
        origin = getattr(spec, "origin", None) if spec is not None else None
        if not origin:
            return
        root = Path(origin).resolve().parent
        candidates = (
            ("Qt5", "plugins"),
            ("Qt6", "plugins"),
            ("Qt", "plugins"),
        )
        plug: Path | None = None
        for rel in candidates:
            p = root.joinpath(*rel)
            if p.is_dir():
                plug = p
                break
        if plug is None:
            return
        plat = plug / "platforms"
        if prefer_this_binding:
            os.environ["QT_PLUGIN_PATH"] = str(plug)
            if plat.is_dir():
                os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plat)
        else:
            os.environ.setdefault("QT_PLUGIN_PATH", str(plug))
            if plat.is_dir():
                os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(plat))
        if os.environ.get("INKSCAPE_WPS_DEBUG_QT", "").strip() in ("1", "true", "yes"):
            print(
                f"inkscape-wps: QT 插件路径已指向 {pkg} →\n"
                f"  QT_PLUGIN_PATH={os.environ.get('QT_PLUGIN_PATH')}\n"
                f"  QT_QPA_PLATFORM_PLUGIN_PATH={os.environ.get('QT_QPA_PLATFORM_PLUGIN_PATH')}",
                file=sys.stderr,
                flush=True,
            )
    except Exception:
        _logger.debug("配置 QT 插件路径时跳过（可设 INKSCAPE_WPS_DEBUG_QT=1 查看详情）", exc_info=True)
        return


def _center_on_primary_screen(app: "QApplication", w: "QWidget") -> None:
    """把主窗口移到主屏可用区域中心（多显示器 / 终端启动时避免出现在屏外）。"""
    screen = app.primaryScreen()
    if screen is None:
        return
    ag = screen.availableGeometry()
    fg = w.frameGeometry()
    fg.moveCenter(ag.center())
    w.move(fg.topLeft())


def _macos_set_activation_policy_regular() -> None:
    """终端里跑 python 时默认可能是 Accessory，窗口不进 Dock / 不显示；改为常规 GUI 应用。"""
    if sys.platform != "darwin":
        return
    try:
        import Cocoa  # type: ignore[import-untyped]

        pol = getattr(Cocoa, "NSApplicationActivationPolicyRegular", None)
        if pol is None:
            pol = 0  # NSApplicationActivationPolicyRegular
        Cocoa.NSApplication.sharedApplication().setActivationPolicy_(pol)
    except Exception:
        _logger.debug("设置 NSApplicationActivationPolicyRegular 失败（可忽略，未装 PyObjC 时常见）", exc_info=True)


def _macos_activate_application() -> None:
    """从终端启动时让本应用成为前台应用（比仅 raise 窗口更可靠，需 PyObjC / Cocoa）。"""
    if sys.platform != "darwin":
        return
    try:
        import Cocoa  # type: ignore[import-untyped]

        Cocoa.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        _logger.debug("activateIgnoringOtherApps 失败（可忽略，未装 PyObjC 时常见）", exc_info=True)


def _run_fluent() -> None:
    _ensure_pyqt_binding_plugin_env("pyqt5")
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import QApplication

    qpa = (os.environ.get("QT_QPA_PLATFORM") or "").strip().lower()
    if qpa == "offscreen":
        print(
            "inkscape-wps: QT_QPA_PLATFORM 仍为 offscreen（可能已设 INKSCAPE_WPS_ALLOW_OFFSCREEN=1）。\n"
            "Qt 只在内存里渲染，不会出现真实窗口。",
            file=sys.stderr,
            flush=True,
        )
    if sys.platform.startswith("linux"):
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            print(
                "inkscape-wps: 未设置 DISPLAY / WAYLAND_DISPLAY，图形界面通常无法显示（常见于纯 SSH 无 X11 转发）。",
                file=sys.stderr,
                flush=True,
            )

    if sys.platform == "darwin":
        os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")
        for name in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
            attr = getattr(Qt, "ApplicationAttribute", None)
            if attr is not None:
                a = getattr(attr, name, None)
                if a is not None:
                    QApplication.setAttribute(a, True)

    app = QApplication(sys.argv)
    app.setApplicationName("写字机上位机")
    app.setQuitOnLastWindowClosed(True)

    # macOS：qframelesswindow 在 winId 未就绪时调 NS API 会导致 Dock 无限弹跳且无窗口
    if sys.platform == "darwin":
        from inkscape_wps.ui.macos_frameless_shim import apply_macos_frameless_shim

        apply_macos_frameless_shim()

    # 须在 QApplication 存在之后再 import 主窗口：qfluentwidgets 等可能在导入链上构造 QWidget，否则会 qFatal。
    from inkscape_wps.ui.main_window_fluent import MainWindowFluent

    w = MainWindowFluent()
    w.setMinimumSize(640, 480)
    _center_on_primary_screen(app, w)

    w.show()
    w.showNormal()
    w.setVisible(True)
    w.raise_()
    w.activateWindow()

    def _bring_front() -> None:
        _macos_set_activation_policy_regular()
        _macos_activate_application()
        _center_on_primary_screen(app, w)
        w.raise_()
        w.activateWindow()

    # 事件循环跑起来后尽快抢前台；200ms 再补一次（部分环境下首次 tick 过早无效）
    QTimer.singleShot(0, _bring_front)
    QTimer.singleShot(200, _bring_front)

    print(
        "提示：若未见窗口——\n"
        "  • macOS：Dock 点 Python；Command+Tab。若仍异常可设环境变量 INKSCAPE_WPS_NO_FLUENT=1 使用经典界面（PyQt6）。\n"
        "  • 远程/服务器：需在带桌面的会话运行，或配置 X11/Wayland 转发；勿设 QT_QPA_PLATFORM=offscreen。\n"
        "  • 进程若立即回到 shell 提示符，说明已退出，请把完整终端输出（含报错）发出来。",
        file=sys.stderr,
        flush=True,
    )
    sys.exit(app.exec_())


def _run_pyqt6() -> None:
    _ensure_pyqt_binding_plugin_env("pyqt6", prefer_this_binding=True)
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    from inkscape_wps.ui.main_window import MainWindow

    w = MainWindow()
    w.show()
    w.raise_()
    w.activateWindow()
    sys.exit(app.exec())


def main() -> None:
    # 重要：不要在同一进程内同时加载 PyQt5 与 PyQt6（macOS 上会触发 QtCore 冲突）。
    # 因此这里只在“导入失败”时回退，而不是捕获所有运行时异常。
    # 须在首次 import PyQt* 之前配置平台插件路径（与下面分支一致；NO_FLUENT 只配 PyQt6）。
    _darwin_clear_offscreen_for_gui()

    # macOS 12 上常见 PyQt6/Qt6 wheel 要求 13+，Fluent（PyQt5）反而可运行；勿再强制 NO_FLUENT。

    no_fluent = (os.environ.get("INKSCAPE_WPS_NO_FLUENT") or "").strip() in (
        "1",
        "true",
        "yes",
    )
    if no_fluent:
        _ensure_pyqt_binding_plugin_env("pyqt6")
    else:
        _ensure_pyqt_binding_plugin_env("pyqt5")

    if no_fluent:
        print(
            "inkscape-wps: INKSCAPE_WPS_NO_FLUENT=1，使用经典 PyQt6 界面（勿与 PyQt5 混用）。",
            file=sys.stderr,
            flush=True,
        )
        _run_pyqt6()
        return
    try:
        import PyQt5  # noqa: F401
        # qfluentwidgets 在 import 时向 stdout 打印 Pro 推广，干扰终端判断是否真的起 GUI
        if (os.environ.get("INKSCAPE_WPS_SHOW_QFW_BANNER") or "").strip() not in (
            "1",
            "true",
            "yes",
        ):
            _qfw_out = io.StringIO()
            with contextlib.redirect_stdout(_qfw_out):
                import qfluentwidgets  # noqa: F401
        else:
            import qfluentwidgets  # noqa: F401
    except Exception as e:
        _logger.warning("PyQt5 或 qfluentwidgets 不可用，回退 PyQt6：%s", e, exc_info=True)
        print(
            "inkscape-wps: PyQt5 或 qfluentwidgets 不可用，回退 PyQt6（macOS 12 可能无法运行，请用 .venv310）。",
            file=sys.stderr,
            flush=True,
        )
        _run_pyqt6()
        return
    print("inkscape-wps: 启动 Fluent UI (PyQt5)…", file=sys.stderr, flush=True)
    _run_fluent()


if __name__ == "__main__":
    main()
