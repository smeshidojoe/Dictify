"""Renders the app icon (dictify/ui/icons.py) into assets/Dictify.{png,ico,icns}."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QGuiApplication, QImageWriter  # noqa: E402

from dictify.ui.icons import app_pixmap  # noqa: E402

app = QGuiApplication([])
out = ROOT / "assets"
out.mkdir(exist_ok=True)
app_pixmap(1024).save(str(out / "Dictify.png"))

writer = QImageWriter(str(out / "Dictify.ico"), b"ico")
for size in (256,):  # Qt's ICO writer stores one image; Windows scales it down cleanly
    writer.write(app_pixmap(size).toImage())

app_pixmap(1024).toImage().save(str(out / "Dictify.icns"), "icns")
print("written:", ", ".join(p.name for p in sorted(out.iterdir())))
