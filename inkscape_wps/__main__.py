"""python -m inkscape_wps"""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from inkscape_wps.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
