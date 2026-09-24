"""Main window: switches between start, progress and transcript screens and owns the worker thread."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QStackedWidget

from dictify import APP_NAME, settings
from dictify.i18n import tr
from dictify.ui import theme
from dictify.ui.models_dialog import ModelsDialog
from dictify.ui.progress_view import ProgressView
from dictify.ui.start_view import StartView
from dictify.ui.transcript_page import TranscriptPage
from dictify.worker import Job, TranscribeWorker

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    runJob = Signal(object)
    rebuildRequested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1120, 740)
        self.setMinimumSize(860, 580)
        self.setAcceptDrops(True)

        self.start = StartView()
        self.progress = ProgressView()
        self.page = TranscriptPage()
        self.stack = QStackedWidget()
        for w in (self.start, self.progress, self.page):
            self.stack.addWidget(w)
        self.setCentralWidget(self.stack)

        self._job: Job | None = None
        self._thread = QThread(self)
        self._worker = TranscribeWorker()
        self._worker.moveToThread(self._thread)
        self.runJob.connect(self._worker.run)
        self._worker.stage.connect(self.progress.set_stage)
        self._worker.segment.connect(self.progress.add_segment)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._thread.start()

        self.start.fileChosen.connect(self.open_file)
        self.start.manageModels.connect(self._show_models)
        self.start.uiLanguageChanged.connect(self.rebuildRequested)
        self.progress.cancelRequested.connect(self._worker.cancel)
        self.page.backRequested.connect(self._back_to_start)
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_theme)

    # ----- flow ------------------------------------------------------------------

    def open_file(self, path: str) -> None:
        if self._job is not None:
            return
        if not Path(path).is_file():
            QMessageBox.warning(self, APP_NAME, tr("File not found:\n{path}", path=path))
            return
        if not self._confirm_discard():
            return
        self.page.close_transcript()
        settings.put("last_dir", str(Path(path).parent))
        self._job = Job(path=path, **self.start.job_settings())
        self.progress.start(path)
        self.stack.setCurrentWidget(self.progress)
        self.setWindowTitle(f"{Path(path).name} — {APP_NAME}")
        self.runJob.emit(self._job)

    def _on_finished(self, transcript) -> None:
        self._job = None
        self.progress.stop()
        self.start.refresh_models()
        if not transcript.segments:
            QMessageBox.information(self, APP_NAME, tr("No speech was recognized in this file."))
            self._show_start()
            return
        self.page.set_transcript(transcript)
        self.stack.setCurrentWidget(self.page)

    def _on_failed(self, message: str) -> None:
        self._job = None
        self.progress.stop()
        self.start.refresh_models()
        QMessageBox.critical(self, tr("Transcription failed"), message)
        self._show_start()

    def _on_cancelled(self) -> None:
        self._job = None
        self.progress.stop()
        self.start.refresh_models()
        self._show_start()

    def _back_to_start(self) -> None:
        if self._confirm_discard():
            self.page.close_transcript()
            self._show_start()

    def _show_start(self) -> None:
        self.stack.setCurrentWidget(self.start)
        self.setWindowTitle(APP_NAME)

    def _show_models(self) -> None:
        ModelsDialog(self._job.model_id if self._job else None, self).exec()
        self.start.refresh_models()

    def _confirm_discard(self) -> bool:
        if not (self.page.t and self.page.dirty):
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

    def _on_theme(self, *_):
        theme.apply(QApplication.instance())
        self.page.on_theme_changed()
        self.update()

    # ----- window events -----------------------------------------------------------

    def dragEnterEvent(self, e):
        if self._job is None and e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
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
        self.page.close_transcript()
        self._worker.cancel()
        self._thread.quit()
        if not self._thread.wait(8000):
            log.warning("Worker thread did not stop in time")
        return True
