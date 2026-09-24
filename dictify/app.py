"""Application entry point."""
from __future__ import annotations

import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler


def _fix_std_streams() -> None:
    # Windowed builds have no console: libraries that print would crash on None streams.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def _setup_logging() -> None:
    from dictify.paths import logs_dir

    handler = RotatingFileHandler(logs_dir() / "dictify.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if not getattr(sys, "frozen", False):
        root.addHandler(logging.StreamHandler())


def main() -> None:
    _fix_std_streams()
    _setup_logging()

    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        from dictify.selftest import run

        sys.exit(run(sys.argv[2:]))

    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication, QMessageBox

    from dictify import APP_NAME, __version__, i18n, settings
    from dictify.catalog import backend
    from dictify.ui import icons, theme
    from dictify.ui.main_window import MainWindow

    log = logging.getLogger("dictify")
    log.info("Dictify %s starting (%s, backend=%s)", __version__, sys.platform, backend())

    class App(QApplication):
        """Receives files opened from Finder ("Open With", dropping on the Dock icon)."""

        def __init__(self, argv):
            super().__init__(argv)
            self.window = None
            self.pending: str | None = None

        def event(self, e):
            if e.type() == QEvent.Type.FileOpen:
                path = e.file()
                if self.window:
                    self.window.open_file(path)
                else:
                    self.pending = path
                return True
            return super().event(e)

    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(APP_NAME)
    app = App(sys.argv)
    app.setWindowIcon(icons.app_icon())
    theme.apply(app)

    def excepthook(exc_type, exc, tb):
        log.error("Unhandled exception", exc_info=(exc_type, exc, tb))
        QMessageBox.critical(None, APP_NAME, "".join(traceback.format_exception_only(exc_type, exc)))

    sys.excepthook = excepthook

    def build_window(geometry=None):
        i18n.set_language(settings.get("ui_language"))
        win = MainWindow()
        win.rebuildRequested.connect(lambda: rebuild(win))
        if geometry is not None:
            win.setGeometry(geometry)
        win.show()
        app.window = win
        return win

    def rebuild(old):
        # Switching the interface language recreates the window (only offered on the start screen).
        geometry = old.geometry()
        old.shutdown(ask=False)
        old.hide()
        old.deleteLater()
        build_window(geometry)

    build_window()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if app.pending or args:
        app.window.open_file(app.pending or args[0])
    sys.exit(app.exec())
