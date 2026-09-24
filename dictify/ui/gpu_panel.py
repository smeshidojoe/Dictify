"""Sidebar card offering NVIDIA GPU acceleration on Windows. It downloads cuBLAS
(dictify.gpu) in a background thread with progress and cancel, and is hidden when there is
no NVIDIA card or the libraries are already installed."""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from dictify import gpu
from dictify.errors import Cancelled
from dictify.i18n import tr
from dictify.ui.widgets import ProgressLine, fade_in, muted, size_label

log = logging.getLogger(__name__)


class _Bridge(QObject):
    # Carries results from the download thread to the GUI thread (queued connections).
    progress = Signal(object, object)  # done, total bytes
    done = Signal()
    failed = Signal(str)
    cancelled = Signal()


class GpuPanel(QWidget):
    installed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GpuCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._closing = False
        self._bridge = _Bridge(self)
        self._bridge.progress.connect(self._on_progress)
        self._bridge.done.connect(self._on_done)
        self._bridge.failed.connect(lambda message: self._offer(message))
        self._bridge.cancelled.connect(lambda: self._offer())

        self.title = QLabel(tr("Faster on your graphics card"))
        self.title.setObjectName("Stage")
        self.text = muted()
        self.text.setWordWrap(True)
        self.bar = ProgressLine()
        self.detail = muted()
        self.button = QPushButton()
        self.button.clicked.connect(self._on_button)
        row = QHBoxLayout()
        row.addWidget(self.detail, 1)
        row.addWidget(self.button)

        col = QVBoxLayout(self)
        col.setContentsMargins(12, 10, 12, 12)
        col.setSpacing(6)
        col.addWidget(self.title)
        col.addWidget(self.text)
        col.addWidget(self.bar)
        col.addLayout(row)
        self.refresh()

    def is_busy(self) -> bool:
        return self._thread is not None

    def refresh(self) -> None:
        """Shows the offer when an NVIDIA card is present but its libraries are not."""
        if self.is_busy():
            return
        self.setVisible(gpu.nvidia_gpu() and not gpu.is_installed())
        self._offer()

    def stop(self) -> None:
        """Cancels a running download (it resumes next time) before the window goes away."""
        if self._thread is not None:
            self._closing = True
            self._stop.set()
            self._thread.join(3)
            self._thread = None

    # ----- states --------------------------------------------------------------------------

    def _offer(self, error: str = "") -> None:
        self._thread = None
        if error:
            self.text.setText(tr("Could not download the libraries: {error}", error=error))
        else:
            self.text.setText(tr(
                "Your NVIDIA card can transcribe many times faster than the processor. "
                "It needs NVIDIA's CUDA libraries, a one-time {size} download.",
                size=size_label(gpu.DOWNLOAD_MB),
            ))
        self.bar.hide()
        self.detail.setText("")
        self.button.setText(tr("Try again") if error else tr("Download"))
        self.button.setEnabled(True)

    def _start(self) -> None:
        self._stop.clear()
        self.text.setText(tr("Downloading NVIDIA CUDA libraries…"))
        self.bar.set_fraction(0.0)
        self.bar.show()
        fade_in(self.bar)
        self.detail.setText("")
        self.button.setText(tr("Cancel"))
        self.button.setEnabled(True)
        self._thread = threading.Thread(target=self._run, name="gpu-download", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            gpu.download(self._bridge.progress.emit, self._stop.is_set)
            signal, args = self._bridge.done, ()
        except Cancelled:
            signal, args = self._bridge.cancelled, ()
        except Exception as e:
            log.warning("CUDA libraries download failed", exc_info=True)
            signal, args = self._bridge.failed, (str(e),)
        if not self._closing:
            signal.emit(*args)

    def _on_button(self) -> None:
        if self.is_busy():
            self.button.setEnabled(False)
            self._stop.set()  # the thread reports back through `cancelled`
        else:
            self._start()

    def _on_progress(self, done: int, total: int) -> None:
        if not self.is_busy():
            return
        self.bar.set_fraction(done / total if total else -1)
        self.detail.setText(f"{done / 1e6:,.0f} / {total / 1e6:,.0f} MB".replace(",", " "))

    def _on_done(self) -> None:
        self._thread = None
        self.hide()
        self.installed.emit()
