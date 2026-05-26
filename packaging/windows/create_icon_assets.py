from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "assets" / "app_icon.svg"
PNG_TARGET = ROOT / "src" / "sweet_chem_o_mine" / "assets" / "app_icon.png"
ICO_TARGET = ROOT / "packaging" / "windows" / "app_icon.ico"


def main() -> int:
    QApplication.instance() or QApplication([])
    renderer = QSvgRenderer(QByteArray(SOURCE.read_bytes()))
    if not renderer.isValid():
        raise RuntimeError(f"Unable to render icon source: {SOURCE}")
    PNG_TARGET.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(QSize(512, 512), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    if not image.save(str(PNG_TARGET), "PNG"):
        raise RuntimeError(f"Unable to write icon PNG: {PNG_TARGET}")
    with Image.open(PNG_TARGET) as icon:
        icon.save(ICO_TARGET, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Wrote {PNG_TARGET.relative_to(ROOT)}")
    print(f"Wrote {ICO_TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
