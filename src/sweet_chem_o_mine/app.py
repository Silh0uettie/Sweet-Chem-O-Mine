from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 is required to launch the desktop interface. "
            "Install the project dependencies with: python -m pip install -e .",
            file=sys.stderr,
        )
        return 1

    from .main_window import MainWindow

    application = QApplication(sys.argv)
    application.setApplicationName("Project Sweet Chem O' Mine")
    window = MainWindow()
    window.show()
    return application.exec()
