"""Home screen: drop zone plus transcription settings."""
from __future__ import annotations

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dictify import __version__, settings
from dictify.catalog import MODELS, backend, is_downloaded
from dictify.i18n import SPEECH_LANGUAGES, UI_LANGUAGES, tr
from dictify.paths import logs_dir
from dictify.ui import icons
from dictify.ui.widgets import DropZone, Switch, muted

MEDIA_EXTENSIONS = (
    "mp3 wav m4a aac flac ogg oga opus wma aiff aif amr caf "
    "mp4 m4v mov mkv webm avi wmv flv mpeg mpg 3gp ts"
).split()


def size_label(mb: int) -> str:
    return f"{mb / 1000:.1f} GB" if mb >= 1000 else f"{mb} MB"


class StartView(QWidget):
    fileChosen = Signal(str)
    uiLanguageChanged = Signal()
    manageModels = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        column = QVBoxLayout()
        column.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(14)
        self.logo = QLabel()
        self.logo.setPixmap(icons.app_pixmap(112))
        self.logo.setFixedSize(56, 56)
        self.logo.setScaledContents(True)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Dictify")
        title.setObjectName("Title")
        titles.addWidget(title)
        titles.addWidget(muted(tr("Audio and video to text. Offline, on your computer.")))
        header.addWidget(self.logo)
        header.addLayout(titles, 1)
        column.addLayout(header)

        self.drop = DropZone()
        self.drop.clicked.connect(self.choose_file)
        self.drop.fileDropped.connect(self.fileChosen)
        column.addWidget(self.drop)

        card = QFrame()
        card.setObjectName("Card")
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)

        self.model = QComboBox()
        self.models_btn = QPushButton(tr("Models…"))
        self.models_btn.clicked.connect(self.manageModels)
        self.refresh_models()
        self.model.currentIndexChanged.connect(lambda: settings.put("model", self.model.currentData()))

        self.language = QComboBox()
        self.language.addItem(tr("Detect automatically"), "auto")
        for code, name in SPEECH_LANGUAGES:
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(settings.get("language"))))
        self.language.currentIndexChanged.connect(lambda: settings.put("language", self.language.currentData()))

        row = 0
        grid.addWidget(QLabel(tr("Model")), row, 0)
        grid.addWidget(self.model, row, 1)
        grid.addWidget(self.models_btn, row, 2)
        row += 1
        grid.addWidget(QLabel(tr("Language")), row, 0)
        grid.addWidget(self.language, row, 1, 1, 2)

        self.device = None
        self.vad = None
        if backend() == "faster":
            row += 1
            self.device = QComboBox()
            for key, label in (("auto", "Automatic"), ("cpu", "CPU"), ("cuda", "GPU (NVIDIA CUDA)")):
                self.device.addItem(tr(label), key)
            self.device.setCurrentIndex(max(0, self.device.findData(settings.get("device"))))
            self.device.currentIndexChanged.connect(lambda: settings.put("device", self.device.currentData()))
            grid.addWidget(QLabel(tr("Compute on")), row, 0)
            grid.addWidget(self.device, row, 1, 1, 2)

            row += 1
            self.vad = Switch(settings.get("vad"))
            self.vad.toggled.connect(lambda on: settings.put("vad", on))
            vad_label = QLabel(tr("Skip silence (fewer hallucinations)"))
            grid.addWidget(vad_label, row, 0, 1, 2)
            grid.addWidget(self.vad, row, 2, Qt.AlignmentFlag.AlignRight)
        column.addWidget(card)

        footer = QHBoxLayout()
        footer.addWidget(muted(tr("Interface")))
        self.ui_lang = QComboBox()
        for code, label in UI_LANGUAGES:
            self.ui_lang.addItem(tr(label), code)
        self.ui_lang.setCurrentIndex(max(0, self.ui_lang.findData(settings.get("ui_language"))))
        self.ui_lang.currentIndexChanged.connect(self._on_ui_language)
        footer.addWidget(self.ui_lang)
        footer.addStretch(1)
        logs = QPushButton(tr("Logs"))
        logs.setFlat(True)
        logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(logs_dir()))))
        footer.addWidget(logs)
        footer.addWidget(muted(f"v{__version__}"))
        column.addLayout(footer)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addStretch(1)
        wrapper = QVBoxLayout()
        wrapper.addStretch(1)
        wrapper.addLayout(column)
        wrapper.addStretch(2)
        box = QWidget()
        box.setLayout(wrapper)
        box.setMaximumWidth(600)
        box.setMinimumWidth(460)
        outer.addWidget(box, 4)
        outer.addStretch(1)

    def refresh_models(self) -> None:
        current = self.model.currentData() or settings.get("model")
        self.model.blockSignals(True)
        self.model.clear()
        for spec in MODELS:
            parts = [spec.name, size_label(spec.size_mb)]
            if is_downloaded(spec):
                parts.append("✓ " + tr("downloaded"))
            elif spec.recommended:
                parts.append(tr("recommended"))
            self.model.addItem(" · ".join(parts), spec.id)
        self.model.setCurrentIndex(max(0, self.model.findData(current)))
        self.model.blockSignals(False)

    def job_settings(self) -> dict:
        language = self.language.currentData()
        return {
            "model_id": self.model.currentData(),
            "language": None if language == "auto" else language,
            "vad": self.vad.isChecked() if self.vad else True,
            "device": self.device.currentData() if self.device else "auto",
        }

    def choose_file(self) -> None:
        patterns = " ".join(f"*.{e}" for e in MEDIA_EXTENSIONS)
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Choose an audio or video file"),
            settings.get("last_dir"),
            f"{tr('Audio and video')} ({patterns});;{tr('All files')} (*)",
        )
        if path:
            self.fileChosen.emit(path)

    def _on_ui_language(self) -> None:
        settings.put("ui_language", self.ui_lang.currentData())
        self.uiLanguageChanged.emit()
