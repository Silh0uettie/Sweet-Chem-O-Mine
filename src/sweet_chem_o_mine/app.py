from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    try:
        from PySide6.QtGui import QIcon
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
    application.setOrganizationName("SweetChemOMine")
    application.setApplicationName("Project Sweet Chem O' Mine")
    icon_path = Path(__file__).parent / "assets" / "app_icon.png"
    if icon_path.exists():
        application.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    return application.exec()
