"""Main window: one workspace, plus the transcription flow and the worker thread."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from dictify import APP_NAME, settings
from dictify.audio import probe_duration
from dictify.i18n import tr
from dictify.ui import chrome, theme
from dictify.ui.models_dialog import ModelsDialog
from dictify.ui.workspace import Workspace
from dictify.worker import Job, TranscribeService

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    rebuildRequested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1120, 740)
        self.setMinimumSize(760, 520)
        self.setAcceptDrops(True)

        self.ws = Workspace()
        self.setCentralWidget(self.ws)
        self.chrome = chrome.create(self, self.ws)

        self._job: Job | None = None
        self._duration = 0.0
        self._service = TranscribeService(self)
        self._service.stage.connect(self.ws.set_stage)
        self._service.segment.connect(self.ws.add_live_segment)
        self._service.finished.connect(self._on_finished)
        self._service.failed.connect(self._on_failed)
        self._service.cancelled.connect(self._on_cancelled)

        self.ws.fileChosen.connect(self.open_file)
        self.ws.sidebar.startRequested.connect(self.start_job)
        self.ws.sidebar.cancelRequested.connect(self._service.cancel)
        self.ws.sidebar.manageModels.connect(self._show_models)
        self.ws.sidebar.uiLanguageChanged.connect(self._on_ui_language)
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_theme)

    # ----- flow --------------------------------------------------------------------------

    def open_file(self, path: str) -> None:
        if self._job is not None:
            self.ws.toast.show_message(tr("Wait for the transcription to finish or cancel it first."))
            return
        if not Path(path).is_file():
            QMessageBox.warning(self, APP_NAME, tr("File not found:\n{path}", path=path))
            return
        if not self._confirm_discard():
            return
        settings.put("last_dir", str(Path(path).parent))
        self._duration = probe_duration(path)
        self.ws.load_media(path, self._duration)
        self.setWindowTitle(f"{Path(path).name} — {APP_NAME}")
        self.start_job()

    def start_job(self) -> None:
        if self._job is not None or not self.ws.path:
            return
        if self.ws.t is not None and not self._confirm_discard():
            return
        self._job = Job(path=self.ws.path, **self.ws.sidebar.job_settings())
        self.ws.begin_live(self._duration)
        self._service.run(self._job)

    def _job_done(self) -> None:
        self._job = None
        self.ws.sidebar.refresh_models()

    def _on_finished(self, transcript) -> None:
        self._job_done()
        if not transcript.segments:
            self.ws.end_run_without_result()
            QMessageBox.information(self, APP_NAME, tr("No speech was recognized in this file."))
            return
        self.ws.set_transcript(transcript)

    def _on_failed(self, message: str) -> None:
        self._job_done()
        self.ws.end_run_without_result()
        QMessageBox.critical(self, tr("Transcription failed"), message)

    def _on_cancelled(self) -> None:
        self._job_done()
        self.ws.end_run_without_result()

    def _show_models(self) -> None:
        ModelsDialog(self._job.model_id if self._job else None, self).exec()
        self.ws.sidebar.refresh_models()

    def _confirm_discard(self) -> bool:
        if not (self.ws.t and self.ws.dirty):
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(APP_NAME)
        box.setText(tr("The transcript hasn't been exported or copied."))
        box.setInformativeText(tr("Discard it?"))
        discard = box.addButton(tr("Discard"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is discard

    def _on_ui_language(self) -> None:
        # Rebuilding the window would drop a loaded file, so only do it when nothing is open.
        if self.ws.path is None and self._job is None:
            self.rebuildRequested.emit()
        else:
            self.ws.toast.show_message(tr("The interface language will change after restarting the app."))

    def _on_theme(self, *_):
        theme.apply(QApplication.instance())
        self.ws.on_theme_changed()
        self.update()

    # ----- window events ---------------------------------------------------------------------

    def nativeEvent(self, event_type, message):
        handled = self.chrome.native_event(event_type, message)
        return handled if handled is not None else super().nativeEvent(event_type, message)

    def showEvent(self, e):
        super().showEvent(e)
        self.chrome.on_show()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.Type.WindowStateChange:
            self.chrome.on_state_change()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.ws.show_drop_overlay(True)

    def dragLeaveEvent(self, e):
        self.ws.show_drop_overlay(False)

    def dropEvent(self, e):
        self.ws.show_drop_overlay(False)
        urls = [u for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            e.acceptProposedAction()
            self.open_file(urls[0].toLocalFile())

    def closeEvent(self, e):
        if not self.shutdown(ask=True):
            e.ignore()
            return
        super().closeEvent(e)

    def shutdown(self, ask: bool) -> bool:
        if ask and not self._confirm_discard():
            return False
        self.ws.player.unload()
        self._service.shutdown()
        return True
