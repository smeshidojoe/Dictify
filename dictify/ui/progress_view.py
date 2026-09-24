"""Progress screen shown while a file is being transcribed."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dictify.formatting import fmt_time
from dictify.i18n import tr
from dictify.ui.widgets import muted

STAGES = {
    "download": "Downloading model…",
    "decode": "Reading audio…",
    "load": "Loading model…",
    "transcribe": "Transcribing…",
}


def _minutes(seconds: float) -> str:
    if seconds < 60:
        return tr("less than a minute")
    return tr("~{n} min", n=round(seconds / 60))


class ProgressView(QWidget):
    cancelRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        self.file_label = QLabel()
        self.file_label.setObjectName("Title")
        self.stage_label = QLabel()
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.detail = muted()
        self.preview = QPlainTextEdit()
        self.preview.setObjectName("Preview")
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText(tr("Recognized text will appear here…"))
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(4, 4, 4, 4)
        card_layout.addWidget(self.preview)
        self.cancel_btn = QPushButton(tr("Cancel"))
        self.cancel_btn.clicked.connect(self._on_cancel)

        column = QVBoxLayout()
        column.setSpacing(10)
        column.addWidget(self.file_label)
        column.addWidget(self.stage_label)
        column.addWidget(self.bar)
        column.addWidget(self.detail)
        column.addSpacing(8)
        column.addWidget(card, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_btn)
        column.addLayout(buttons)

        box = QWidget()
        box.setLayout(column)
        box.setMaximumWidth(720)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(24, 40, 24, 24)
        outer.addStretch(1)
        outer.addWidget(box, 6)
        outer.addStretch(1)

        self._stage = ""
        self._fraction = 0.0
        self._extra = ""
        self._started = 0.0
        self._stage_started = 0.0
        self._clock = QTimer(self, interval=1000, timeout=self._refresh_detail)

    def start(self, path: str) -> None:
        self.file_label.setText(Path(path).name)
        self.preview.clear()
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText(tr("Cancel"))
        self._stage = ""
        self._started = time.monotonic()
        self.set_stage("decode", 0.0, "")
        self._clock.start()

    def stop(self) -> None:
        self._clock.stop()

    def set_stage(self, stage: str, fraction: float, detail: str) -> None:
        if stage != self._stage:
            self._stage = stage
            self._stage_started = time.monotonic()
            self.stage_label.setText(tr(STAGES.get(stage, stage)))
        self._fraction = fraction
        self._extra = detail
        if fraction < 0:
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(fraction * 1000))
        self._refresh_detail()

    def add_segment(self, seg) -> None:
        self.preview.appendPlainText(f"[{fmt_time(seg.start)}]  {seg.text}")

    def _refresh_detail(self) -> None:
        parts = []
        if self._fraction >= 0:
            parts.append(f"{int(self._fraction * 100)}%")
        if self._extra:
            parts.append(self._extra)
        spent = time.monotonic() - self._stage_started
        if self._stage == "transcribe" and 0.03 < self._fraction < 1 and spent > 5:
            left = spent / self._fraction * (1 - self._fraction)
            parts.append(tr("{t} left", t=_minutes(left)))
        parts.append(tr("elapsed {t}", t=fmt_time(time.monotonic() - self._started)))
        self.detail.setText(" · ".join(parts))

    def _on_cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText(tr("Cancelling…"))
        self.cancelRequested.emit()
