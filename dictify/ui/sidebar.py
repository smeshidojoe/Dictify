"""Right-hand panel: display mode, view options, file info."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dictify.formatting import MODE_SEGMENTS, MODE_TRANSCRIPT, ViewOptions, fmt_time
from dictify.i18n import speech_language_name, tr
from dictify.model import Transcript
from dictify.ui.widgets import ModeCard, Switch, muted, section_title

PARAGRAPH_CHOICES = [("short", "Short"), ("medium", "Medium"), ("long", "Long")]


def _line() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: palette(mid);")
    return line


class Sidebar(QWidget):
    changed = Signal(object)  # ViewOptions

    def __init__(self, opts: ViewOptions, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedWidth(280)
        self._opts = opts

        col = QVBoxLayout(self)
        col.setContentsMargins(16, 16, 16, 16)
        col.setSpacing(10)

        col.addWidget(section_title(tr("Display mode")))
        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.card_transcript = ModeCard(tr("Transcript"), "transcript")
        self.card_segments = ModeCard(tr("Segments"), "segments")
        cards.addWidget(self.card_transcript)
        cards.addWidget(self.card_segments)
        col.addLayout(cards)
        (self.card_segments if opts.mode == MODE_SEGMENTS else self.card_transcript).setChecked(True)
        self.card_transcript.toggled.connect(self._emit)

        col.addSpacing(6)
        col.addWidget(_line())
        col.addWidget(section_title(tr("Options")))

        self.timestamps = Switch(opts.timestamps)
        self.end_times = Switch(opts.end_times)
        self.pause = QDoubleSpinBox()
        self.pause.setRange(0.5, 10.0)
        self.pause.setSingleStep(0.5)
        self.pause.setDecimals(1)
        self.pause.setSuffix(tr(" s"))
        self.pause.setValue(opts.pause)
        self.paragraph = QComboBox()
        for key, label in PARAGRAPH_CHOICES:
            self.paragraph.addItem(tr(label), key)
        self.paragraph.setCurrentIndex(max(0, self.paragraph.findData(opts.paragraph)))
        self.font_size = QSpinBox()
        self.font_size.setRange(11, 30)
        self.font_size.setValue(opts.font_size)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(10)
        rows = [
            (tr("Timestamps"), self.timestamps),
            (tr("Show end time"), self.end_times),
            (tr("New paragraph after pause"), self.pause),
            (tr("Paragraph length"), self.paragraph),
            (tr("Text size"), self.font_size),
        ]
        self._labels = {}
        for r, (text, widget) in enumerate(rows):
            label = QLabel(text)
            label.setWordWrap(True)
            self._labels[widget] = label
            grid.addWidget(label, r, 0)
            grid.addWidget(widget, r, 1, Qt.AlignmentFlag.AlignRight)
        grid.setColumnStretch(0, 1)
        col.addLayout(grid)

        for sw in (self.timestamps, self.end_times):
            sw.toggled.connect(self._emit)
        self.pause.valueChanged.connect(self._emit)
        self.paragraph.currentIndexChanged.connect(self._emit)
        self.font_size.valueChanged.connect(self._emit)

        col.addSpacing(6)
        col.addWidget(_line())
        col.addWidget(section_title(tr("Info")))
        self.info = QGridLayout()
        self.info.setVerticalSpacing(6)
        self.info.setColumnStretch(1, 1)
        col.addLayout(self.info)
        col.addStretch(1)
        self._sync_enabled()

    def options(self) -> ViewOptions:
        return self._opts

    def set_info(self, t: Transcript) -> None:
        while self.info.count():
            item = self.info.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = [
            (tr("Duration"), fmt_time(t.duration, t.duration >= 3600)),
            (tr("Language"), speech_language_name(t.language)),
            (tr("Model"), t.model),
            (tr("Words"), f"{t.word_count():,}".replace(",", " ")),
            (tr("Segments"), str(len(t.visible()))),
        ]
        for r, (name, value) in enumerate(rows):
            self.info.addWidget(muted(name), r, 0)
            v = QLabel(value)
            v.setAlignment(Qt.AlignmentFlag.AlignRight)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.info.addWidget(v, r, 1)

    def _sync_enabled(self) -> None:
        transcript_mode = self._opts.mode == MODE_TRANSCRIPT
        for widget, enabled in (
            (self.end_times, self._opts.timestamps),
            (self.pause, transcript_mode),
            (self.paragraph, transcript_mode),
        ):
            widget.setEnabled(enabled)
            self._labels[widget].setEnabled(enabled)

    def _emit(self, *_):
        self._opts = replace(
            self._opts,
            mode=MODE_TRANSCRIPT if self.card_transcript.isChecked() else MODE_SEGMENTS,
            timestamps=self.timestamps.isChecked(),
            end_times=self.end_times.isChecked(),
            pause=self.pause.value(),
            paragraph=self.paragraph.currentData(),
            font_size=self.font_size.value(),
        )
        self._sync_enabled()
        self.changed.emit(self._opts)
