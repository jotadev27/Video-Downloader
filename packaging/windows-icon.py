"""Export the existing scalable application artwork as a Windows icon."""
import os
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
application = QApplication([])
source, target = map(Path, sys.argv[1:])
renderer = QSvgRenderer(str(source))
canvas = QImage(QSize(256, 256), QImage.Format_RGBA8888)
canvas.fill(Qt.transparent)
painter = QPainter(canvas)
renderer.render(painter)
painter.end()
image = Image.frombytes("RGBA", (256, 256), canvas.constBits().tobytes())
image.save(target, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

# Use the same scalable mark at every native icon size and on wizard pages.
for size in (16, 32, 48, 64, 128, 256):
    image.resize((size, size), Image.Resampling.LANCZOS).save(source.parent / f"desktop-icon-{size}.png")
image.save(source.parent / "VideoDownloader.png")
wizard = Image.new("RGB", (164, 314), "#172438")
wizard.paste(image.resize((138, 138), Image.Resampling.LANCZOS), (13, 78), image.resize((138, 138), Image.Resampling.LANCZOS))
wizard.save(target.parent / "wizard-banner.bmp")
small = Image.new("RGB", (55, 55), "white")
small_icon = image.resize((51, 51), Image.Resampling.LANCZOS)
small.paste(small_icon, (2, 2), small_icon)
small.save(target.parent / "wizard-logo.bmp")
