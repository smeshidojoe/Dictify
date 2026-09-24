"""Lists Whisper models, shows which are downloaded and lets the user delete them."""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from dictify.catalog import MODELS, delete_model, is_downloaded, model_path, repo_for
from dictify.i18n import tr
from dictify.paths import models_dir
from dictify.ui.start_view import size_label
from dictify.ui.widgets import muted


class ModelsDialog(QDialog):
    def __init__(self, busy_model: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Models"))
        self.setMinimumWidth(520)
        self._busy = busy_model

        intro = muted(tr("Models are downloaded automatically the first time you use them. "
                         "Larger models are more accurate but slower."))
        intro.setWordWrap(True)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(10)
        self.grid.setColumnStretch(0, 1)

        open_btn = QPushButton(tr("Open models folder"))
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(models_dir()))))
        close_btn = QPushButton(tr("Close"))
        close_btn.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(open_btn)
        buttons.addStretch(1)
        buttons.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)
        layout.addWidget(intro)
        layout.addLayout(self.grid)
        layout.addLayout(buttons)
        self._fill()

    def _fill(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for r, spec in enumerate(MODELS):
            name = QLabel(f"<b>{spec.name}</b>" + (f" · {tr('recommended')}" if spec.recommended else ""))
            name.setToolTip(repo_for(spec))
            self.grid.addWidget(name, r, 0)
            self.grid.addWidget(muted(size_label(spec.size_mb)), r, 1)
            downloaded = is_downloaded(spec)
            self.grid.addWidget(QLabel("✓ " + tr("downloaded") if downloaded else "—"), r, 2)
            delete = QPushButton(tr("Delete"))
            delete.setEnabled(downloaded and spec.id != self._busy)
            delete.clicked.connect(lambda _=False, s=spec: self._delete(s))
            self.grid.addWidget(delete, r, 3)

    def _delete(self, spec) -> None:
        answer = QMessageBox.question(
            self, tr("Delete model"), tr("Delete {name} from disk? It will be downloaded again when needed.", name=spec.name)
        )
        if answer == QMessageBox.StandardButton.Yes:
            delete_model(spec)
            if model_path(spec).exists():
                QMessageBox.warning(self, tr("Delete model"), tr("Some files could not be removed. Close the app and try again."))
            self._fill()
