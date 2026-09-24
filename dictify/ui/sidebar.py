"""Right-hand panel that slides in once a file is loaded: transcription settings and
progress, then display mode, view options and file info. App preferences at the bottom."""
from __future__ import annotations

import time
from dataclasses import replace

from PySide6.QtCore import QPropertyAnimation, QSize, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dictify import __version__, settings
from dictify.catalog import MODELS, backend, is_downloaded
from dictify.formatting import MODE_SEGMENTS, MODE_TRANSCRIPT, ViewOptions, fmt_time
from dictify.i18n import SPEECH_LANGUAGES, UI_LANGUAGES, speech_language_name, tr
from dictify.model import Transcript
from dictify.paths import logs_dir
from dictify.ui import theme
from dictify.ui.widgets import ModeCard, ProgressLine, Switch, fade_in, muted, section_title, size_label

WIDTH = 300
PARAGRAPH_CHOICES = [("short", "Short"), ("medium", "Medium"), ("long", "Long"), ("none", "No paragraphs")]
STAGES = {
    "download": "Downloading model…",
    "decode": "Reading audio…",
    "load": "Loading model…",
    "transcribe": "Transcribing…",
}


def _line() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: palette(mid);")
    return line


def _minutes(seconds: float) -> str:
    if seconds < 60:
        return tr("less than a minute")
    return tr("~{n} min", n=round(seconds / 60))


class _Body(QWidget):
    # QScrollArea squeezes its widget down to the minimum size before it starts scrolling,
    # which crushes combo boxes and wrapped labels; scroll as soon as it doesn't fit instead.
    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


class Sidebar(QScrollArea):
    startRequested = Signal()
    modelSettingsChanged = Signal()  # model or compute device picked
    cancelRequested = Signal()
    optionsChanged = Signal(object)  # ViewOptions
    manageModels = Signal()
    uiLanguageChanged = Signal()

    def __init__(self, opts: ViewOptions, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(0)
        self.setMaximumWidth(WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._opts = opts
        self._state = "idle"
        self._anim: QPropertyAnimation | None = None

        body = _Body()
        body.setObjectName("SidebarBody")
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        body.setMinimumWidth(WIDTH - 12)  # keeps its layout while the panel slides; room for the scrollbar
        self.setWidget(body)
        col = QVBoxLayout(body)
        col.setContentsMargins(16, 16, 16, 14)
        col.setSpacing(10)

        # --- transcription ----------------------------------------------------------
        col.addWidget(section_title(tr("Transcription")))
        self.model = QComboBox()
        self.models_btn = QPushButton("…")
        self.models_btn.setToolTip(tr("Manage models"))
        self.models_btn.setFixedWidth(34)
        self.models_btn.clicked.connect(self.manageModels)
        self.refresh_models()
        self.model.currentIndexChanged.connect(self._on_model)
        model_row = QHBoxLayout()
        model_row.setSpacing(6)
        model_row.addWidget(self.model, 1)
        model_row.addWidget(self.models_btn)

        self.language = QComboBox()
        self.language.addItem(tr("Detect automatically"), "auto")
        for code, name in SPEECH_LANGUAGES:
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(settings.get("language"))))
        self.language.currentIndexChanged.connect(lambda: settings.put("language", self.language.currentData()))

        form = QVBoxLayout()
        form.setSpacing(4)
        form.addWidget(muted(tr("Model")))
        form.addLayout(model_row)
        form.addSpacing(4)
        form.addWidget(muted(tr("Language")))
        form.addWidget(self.language)

        self.device = None
        self.vad = None
        if backend() == "faster":
            self.device = QComboBox()
            for key, label in (("auto", "Automatic"), ("cpu", "CPU"), ("cuda", "GPU (NVIDIA CUDA)")):
                self.device.addItem(tr(label), key)
            self.device.setCurrentIndex(max(0, self.device.findData(settings.get("device"))))
            self.device.currentIndexChanged.connect(self._on_device)
            form.addSpacing(4)
            form.addWidget(muted(tr("Compute on")))
            form.addWidget(self.device)
            self.vad = Switch(settings.get("vad"))
            self.vad.toggled.connect(lambda on: settings.put("vad", on))
            vad_row = QHBoxLayout()
            vad_label = QLabel(tr("Skip silence"))
            vad_label.setToolTip(tr("Fewer hallucinations on long pauses"))
            vad_row.addWidget(vad_label, 1)
            vad_row.addWidget(self.vad)
            form.addSpacing(6)
            form.addLayout(vad_row)
        col.addLayout(form)

        self.action = QPushButton()
        self.action.setObjectName("Primary")
        self.action.clicked.connect(self._on_action)
        col.addSpacing(4)
        col.addWidget(self.action)

        self.status = QWidget()
        status = QVBoxLayout(self.status)
        status.setContentsMargins(0, 4, 0, 0)
        status.setSpacing(6)
        self.stage_label = QLabel()
        self.stage_label.setObjectName("Stage")
        self.bar = ProgressLine()
        self.detail = muted()
        self.detail.setWordWrap(True)
        status.addWidget(self.stage_label)
        status.addWidget(self.bar)
        status.addWidget(self.detail)
        col.addWidget(self.status)

        # --- view -------------------------------------------------------------------
        self.view = QWidget()
        view = QVBoxLayout(self.view)
        view.setContentsMargins(0, 6, 0, 0)
        view.setSpacing(10)
        view.addWidget(_line())
        view.addWidget(section_title(tr("Display mode")))
        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.card_transcript = ModeCard(tr("Transcript"), "transcript")
        self.card_segments = ModeCard(tr("Segments"), "segments")
        cards.addWidget(self.card_transcript)
        cards.addWidget(self.card_segments)
        view.addLayout(cards)
        (self.card_segments if opts.mode == MODE_SEGMENTS else self.card_transcript).setChecked(True)
        self.card_transcript.toggled.connect(self._emit)

        view.addSpacing(4)
        view.addWidget(section_title(tr("Options")))
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
        grid.setColumnStretch(0, 1)
        self._rows: dict[QWidget, QLabel] = {}
        for r, (text, widget) in enumerate([
            (tr("Timestamps"), self.timestamps),
            (tr("Show end time"), self.end_times),
            (tr("Paragraph length"), self.paragraph),
            (tr("New paragraph after pause"), self.pause),
            (tr("Text size"), self.font_size),
        ]):
            label = QLabel(text)
            label.setWordWrap(True)
            self._rows[widget] = label
            grid.addWidget(label, r, 0)
            grid.addWidget(widget, r, 1, Qt.AlignmentFlag.AlignRight)
        view.addLayout(grid)
        for sw in (self.timestamps, self.end_times):
            sw.toggled.connect(self._emit)
        self.pause.valueChanged.connect(self._emit)
        self.paragraph.currentIndexChanged.connect(self._emit)
        self.font_size.valueChanged.connect(self._emit)

        self.info_box = QWidget()
        info_col = QVBoxLayout(self.info_box)
        info_col.setContentsMargins(0, 6, 0, 0)
        info_col.setSpacing(8)
        info_col.addWidget(_line())
        info_col.addWidget(section_title(tr("Info")))
        self.info = QGridLayout()
        self.info.setVerticalSpacing(6)
        self.info.setColumnStretch(1, 1)
        info_col.addLayout(self.info)
        view.addWidget(self.info_box)
        col.addWidget(self.view)
        col.addStretch(1)

        # --- app preferences ------------------------------------------------------------
        col.addWidget(_line())
        footer = QHBoxLayout()
        footer.addWidget(muted(tr("Interface")))
        self.ui_lang = QComboBox()
        for code, label in UI_LANGUAGES:
            self.ui_lang.addItem(tr(label), code)
        self.ui_lang.setCurrentIndex(max(0, self.ui_lang.findData(settings.get("ui_language"))))
        self.ui_lang.currentIndexChanged.connect(self._on_ui_language)
        footer.addWidget(self.ui_lang, 1)
        col.addLayout(footer)
        links = QHBoxLayout()
        logs = QPushButton(tr("Logs"))
        logs.setFlat(True)
        logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(logs_dir()))))
        links.addWidget(logs)
        links.addStretch(1)
        links.addWidget(muted(f"Dictify {__version__}"))
        col.addLayout(links)

        # Long items ("Detect automatically") must not widen the panel past its width.
        for combo in body.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)

        self._stage = ""
        self._fraction = 0.0
        self._extra = ""
        self._run_started = 0.0
        self._stage_started = 0.0
        self.set_state("idle", has_file=False)
        self.set_view_visible(False)
        self.set_info(None)
        self._sync_rows()

    # ----- sliding ---------------------------------------------------------------------

    def sizeHint(self) -> QSize:
        # Always ask for the full (possibly animating) width; QScrollArea's own hint is tiny.
        return QSize(self.maximumWidth(), super().sizeHint().height())

    def is_open(self) -> bool:
        return self.isVisible() and self.maximumWidth() > 0

    def slide(self, show: bool) -> None:
        if self._anim:
            self._anim.stop()
        if not self.window().isVisible() or theme.reduced_motion():
            self.setMaximumWidth(WIDTH if show else 0)
            self.setVisible(show)
            return
        if show == self.is_open():
            return
        if show:
            if not self.isVisible():
                self.setMaximumWidth(0)
                self.show()
        anim = QPropertyAnimation(self, b"maximumWidth", self)
        anim.setDuration(260)
        anim.setEasingCurve(theme.EASE_DRAWER)
        anim.setStartValue(self.maximumWidth())
        anim.setEndValue(WIDTH if show else 0)
        if not show:
            anim.finished.connect(self.hide)
        anim.start()
        self._anim = anim

    # ----- transcription panel ------------------------------------------------------------

    def refresh_models(self) -> None:
        current = self.model.currentData() or settings.get("model")
        self.model.blockSignals(True)
        self.model.clear()
        for spec in MODELS:
            parts = [spec.name, size_label(spec.size_mb)]
            if is_downloaded(spec):
                parts.append("✓")
            self.model.addItem(" · ".join(parts), spec.id)
            tip = tr("downloaded") if is_downloaded(spec) else tr("will be downloaded on first use")
            if spec.recommended:
                tip += " · " + tr("recommended")
            self.model.setItemData(self.model.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        self.model.setCurrentIndex(max(0, self.model.findData(current)))
        self.model.blockSignals(False)

    def _on_model(self) -> None:
        settings.put("model", self.model.currentData())
        self.modelSettingsChanged.emit()

    def _on_device(self) -> None:
        settings.put("device", self.device.currentData())
        self.modelSettingsChanged.emit()

    def job_settings(self) -> dict:
        language = self.language.currentData()
        return {
            "model_id": self.model.currentData(),
            "language": None if language == "auto" else language,
            "vad": self.vad.isChecked() if self.vad else True,
            "device": self.device.currentData() if self.device else "auto",
        }

    def set_state(self, state: str, has_file: bool = True) -> None:
        """idle: ready to start; running: transcription in progress; done: transcript shown."""
        self._state = state
        self.action.setEnabled(has_file)
        self.action.setText({
            "idle": tr("Transcribe"),
            "running": tr("Cancel"),
            "done": tr("Transcribe again"),
        }[state])
        self.action.setObjectName("" if state == "running" else "Primary")
        self.action.style().unpolish(self.action)
        self.action.style().polish(self.action)
        was_running = self.status.isVisible()
        self.status.setVisible(state == "running")
        if state == "running" and not was_running:
            fade_in(self.status)
        if state == "running":
            self._run_started = time.monotonic()
            self._stage = ""
            self.set_stage("decode", 0.0, "")

    def set_stage(self, stage: str, fraction: float, detail: str) -> None:
        if stage != self._stage:
            self._stage = stage
            self._stage_started = time.monotonic()
            self.stage_label.setText(tr(STAGES.get(stage, stage)))
        self._fraction = fraction
        self._extra = detail
        self.bar.set_fraction(fraction)
        self.refresh_detail()

    def refresh_detail(self) -> None:
        if self._state != "running":
            return
        parts = []
        if self._fraction >= 0:
            parts.append(f"{int(self._fraction * 100)}%")
        if self._extra:
            parts.append(self._extra)
        spent = time.monotonic() - self._stage_started
        if self._stage == "transcribe" and 0.03 < self._fraction < 1 and spent > 5:
            parts.append(tr("{t} left", t=_minutes(spent / self._fraction * (1 - self._fraction))))
        parts.append(tr("elapsed {t}", t=fmt_time(time.monotonic() - self._run_started)))
        self.detail.setText(" · ".join(parts))

    def _on_action(self) -> None:
        if self._state == "running":
            self.action.setEnabled(False)
            self.action.setText(tr("Cancelling…"))
            self.cancelRequested.emit()
        else:
            self.startRequested.emit()

    # ----- view options -------------------------------------------------------------------

    def options(self) -> ViewOptions:
        return self._opts

    def set_view_visible(self, on: bool) -> None:
        appearing = on and not self.view.isVisible()
        self.view.setVisible(on)
        if appearing:
            fade_in(self.view)

    def set_info(self, t: Transcript | None) -> None:
        while self.info.count():
            item = self.info.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        appearing = t is not None and self.info_box.isHidden()
        self.info_box.setVisible(t is not None)
        if t is None:
            return
        if appearing:
            fade_in(self.info_box)
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

    def _sync_rows(self) -> None:
        segments = self._opts.mode == MODE_SEGMENTS
        paragraphs = not segments and self._opts.paragraph != "none"
        for widget, visible in (
            (self.timestamps, segments),
            (self.end_times, segments),
            (self.paragraph, not segments),
            (self.pause, paragraphs),
        ):
            widget.setVisible(visible)
            self._rows[widget].setVisible(visible)
        self.end_times.setEnabled(self._opts.timestamps)
        self._rows[self.end_times].setEnabled(self._opts.timestamps)

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
        self._sync_rows()
        self.optionsChanged.emit(self._opts)

    def _on_ui_language(self) -> None:
        settings.put("ui_language", self.ui_lang.currentData())
        self.uiLanguageChanged.emit()
