"""Transcript screen: toolbar, editor, player bar and sidebar."""
from __future__ import annotations

import logging
from bisect import bisect_right
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dictify import exporters, settings
from dictify.formatting import ViewOptions, to_text
from dictify.i18n import tr
from dictify.model import Transcript
from dictify.ui import icons
from dictify.ui.editor import TranscriptEditor
from dictify.ui.player import PlayerBar
from dictify.ui.sidebar import Sidebar
from dictify.ui.widgets import Toast, muted

log = logging.getLogger(__name__)


class TranscriptPage(QWidget):
    backRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.t: Transcript | None = None
        self.opts = settings.load_view_options()
        self.dirty = False
        self._starts: list[float] | None = None
        self._visible: list[int] = []

        # toolbar
        bar = QWidget()
        bar.setObjectName("Toolbar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        bar.setFixedHeight(52)
        tb = QHBoxLayout(bar)
        tb.setContentsMargins(10, 8, 10, 8)
        tb.setSpacing(8)

        self.back_btn = QToolButton()
        self.back_btn.setToolTip(tr("New transcription"))
        self.back_btn.clicked.connect(self.backRequested)
        self.file_label = QLabel()
        self.file_label.setObjectName("FileName")
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.edit_btn = QPushButton(tr("Edit"))
        self.edit_btn.setCheckable(True)
        self.edit_btn.setToolTip(tr("Edit the transcript text (Esc to finish)"))
        self.edit_btn.toggled.connect(self._on_edit_toggled)

        self.copy_btn = QPushButton(tr("Copy"))
        self.copy_btn.setToolTip(tr("Copy the whole transcript"))
        self.copy_btn.clicked.connect(self.copy_all)

        self.export_btn = QPushButton(tr("Export"))
        self.export_btn.setObjectName("Menu")
        menu = QMenu(self.export_btn)
        for fmt in exporters.FORMATS:
            menu.addAction(tr(fmt.label), lambda f=fmt: self.export(f))
        self.export_btn.setMenu(menu)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search in transcript"))
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(220)
        self._search_action = self.search.addAction(icons.search(), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self._on_search)
        self.search.returnPressed.connect(lambda: self._step(-1 if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier else 1))
        self.search_count = muted()
        self.prev_btn = QToolButton()
        self.next_btn = QToolButton()
        self.prev_btn.clicked.connect(lambda: self._step(-1))
        self.next_btn.clicked.connect(lambda: self._step(1))

        self.sidebar_btn = QToolButton()
        self.sidebar_btn.setCheckable(True)
        self.sidebar_btn.setToolTip(tr("Show or hide the sidebar"))

        tb.addWidget(self.back_btn)
        tb.addWidget(self.file_label, 1)
        tb.addWidget(self.edit_btn)
        tb.addWidget(self.copy_btn)
        tb.addWidget(self.export_btn)
        tb.addSpacing(6)
        tb.addWidget(self.search_count)
        tb.addWidget(self.prev_btn)
        tb.addWidget(self.next_btn)
        tb.addWidget(self.search)
        tb.addWidget(self.sidebar_btn)
        self._show_search_nav(False)

        # body
        self.editor = TranscriptEditor()
        self.player = PlayerBar()
        self.sidebar = Sidebar(self.opts)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(0)
        left.addWidget(self.editor, 1)
        left.addWidget(self.player)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addLayout(left, 1)
        body.addWidget(self.sidebar)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(bar)
        root.addLayout(body, 1)

        self.toast = Toast(self)

        visible = settings.get("sidebar_visible")
        self.sidebar.setVisible(visible)
        self.sidebar_btn.setChecked(visible)
        self.sidebar_btn.toggled.connect(self._toggle_sidebar)

        self.editor.seekRequested.connect(self._seek_segment)
        self.editor.togglePlay.connect(self.player.toggle)
        self.editor.skip.connect(self.player.skip)
        self.editor.edited.connect(self._on_edited)
        self.editor.editingChanged.connect(self.edit_btn.setChecked)
        self.editor.searchChanged.connect(self._on_search_result)
        self.player.positionChanged.connect(self._on_position)
        self.sidebar.changed.connect(self._on_options)

        for keys, slot in (
            (QKeySequence.StandardKey.Find, self._focus_search),
            (QKeySequence.StandardKey.FindNext, lambda: self._step(1)),
            (QKeySequence.StandardKey.FindPrevious, lambda: self._step(-1)),
            ("Ctrl+Shift+C", self.copy_all),
            ("Ctrl+E", self.edit_btn.toggle),
        ):
            QShortcut(QKeySequence(keys), self, slot)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self.search, self._clear_search,
                  context=Qt.ShortcutContext.WidgetShortcut)
        self.refresh_icons()

    # ----- lifecycle -------------------------------------------------------------

    def set_transcript(self, t: Transcript) -> None:
        self.t = t
        self.dirty = True
        self.file_label.setText(Path(t.media_path).name)
        self.search.clear()
        self.editor.set_editing(False)
        self.editor.set_transcript(t, self.opts)
        self._starts = None
        self.sidebar.set_info(t)
        self.player.load(t.media_path, t.duration)
        self.editor.setFocus()

    def close_transcript(self) -> None:
        self.player.unload()
        self.t = None
        self.dirty = False

    def refresh_icons(self) -> None:
        self.back_btn.setIcon(icons.chevron_left())
        self.prev_btn.setIcon(icons.chevron_up())
        self.next_btn.setIcon(icons.chevron_down())
        self.sidebar_btn.setIcon(icons.sidebar())
        self.edit_btn.setIcon(icons.pencil())
        self.search.removeAction(self._search_action)
        self._search_action = self.search.addAction(icons.search(), QLineEdit.ActionPosition.LeadingPosition)
        for b in (self.back_btn, self.sidebar_btn):
            b.setIconSize(QSize(18, 18))
        self.player.refresh_icons()

    def on_theme_changed(self) -> None:
        self.refresh_icons()
        if self.t:
            self.editor.render(self.opts)
            self._on_position(self.player.position())

    # ----- actions ---------------------------------------------------------------

    def copy_all(self) -> None:
        if not self.t:
            return
        self.editor.sync()
        QApplication.clipboard().setText(to_text(self.t, self.opts))
        self.dirty = False
        self.toast.show_message(tr("Transcript copied to clipboard"))

    def export(self, fmt: exporters.ExportFormat) -> None:
        if not self.t:
            return
        self.editor.sync()
        media = Path(self.t.media_path)
        folder = Path(settings.get("last_dir") or media.parent)
        if not folder.is_dir():
            folder = media.parent
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Export transcript"), str(folder / (media.stem + fmt.ext)), f"{tr(fmt.label)} (*{fmt.ext})"
        )
        if not path:
            return
        if not path.lower().endswith(fmt.ext):
            path += fmt.ext
        try:
            exporters.export(self.t, self.opts, fmt.key, path)
        except Exception as e:
            log.exception("Export failed")
            QMessageBox.warning(self, tr("Export failed"), str(e))
            return
        settings.put("last_dir", str(Path(path).parent))
        self.dirty = False
        self.toast.show_message(tr("Saved {name}", name=Path(path).name))

    # ----- internals -------------------------------------------------------------

    def _seg_at_time(self, seconds: float) -> int | None:
        if self._starts is None:
            self._visible = self.t.visible()
            self._starts = [self.t.segments[i].start for i in self._visible]
        k = bisect_right(self._starts, seconds + 0.05) - 1
        return self._visible[k] if k >= 0 else None

    def _on_position(self, seconds: float) -> None:
        if not self.t:
            return
        if self.editor.set_current(self._seg_at_time(seconds)) and self.player.is_playing():
            self.editor.scroll_to_current()

    def _seek_segment(self, sid: int) -> None:
        self.player.seek(self.t.segments[sid].start)
        self.editor.set_current(sid)

    def _on_edited(self) -> None:
        self.dirty = True
        self._starts = None

    def _on_edit_toggled(self, on: bool) -> None:
        if self.editor.is_editing() != on:
            self.editor.set_editing(on)
        if on:
            self.editor.setFocus()
        elif self.t:
            self.editor.sync()
            self.sidebar.set_info(self.t)

    def _on_options(self, opts: ViewOptions) -> None:
        self.opts = opts
        settings.save_view_options(opts)
        self.editor.render(opts)
        self._starts = None
        self._on_position(self.player.position())

    def _toggle_sidebar(self, on: bool) -> None:
        self.sidebar.setVisible(on)
        settings.put("sidebar_visible", on)

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _clear_search(self) -> None:
        self.search.clear()
        self.editor.setFocus()

    def _on_search(self, text: str) -> None:
        self.editor.search(text)

    def _step(self, delta: int) -> None:
        self.editor.search_step(delta)

    def _on_search_result(self, index: int, count: int) -> None:
        has_query = bool(self.search.text())
        self._show_search_nav(has_query)
        self.search_count.setText(f"{index + 1}/{count}" if count else tr("No matches"))

    def _show_search_nav(self, on: bool) -> None:
        for w in (self.search_count, self.prev_btn, self.next_btn):
            w.setVisible(on)
