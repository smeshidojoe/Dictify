"""The single window body: full-window drop zone when empty; once a file is loaded, the
text area (live while transcribing, editable afterwards), player bar and sliding sidebar."""
from __future__ import annotations

import logging
from bisect import bisect_right
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dictify import APP_NAME, exporters, settings
from dictify.formatting import ViewOptions, to_text
from dictify.i18n import tr
from dictify.model import Segment, Transcript
from dictify.ui import icons
from dictify.ui.editor import TranscriptEditor
from dictify.ui.player import PlayerBar
from dictify.ui.sidebar import Sidebar
from dictify.ui.widgets import DropZone, Toast, muted

log = logging.getLogger(__name__)

MEDIA_EXTENSIONS = (
    "mp3 wav m4a aac flac ogg oga opus wma aiff aif amr caf "
    "mp4 m4v mov mkv webm avi wmv flv mpeg mpg 3gp ts"
).split()


class Workspace(QWidget):
    fileChosen = Signal(str)
    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.opts = settings.load_view_options()
        self.path: str | None = None
        self.t: Transcript | None = None  # finished transcript
        self.live: Transcript | None = None  # transcript being filled while running
        self.dirty = False
        self._starts: list[float] | None = None
        self._visible: list[int] = []

        # ----- toolbar -------------------------------------------------------------------
        bar = QWidget()
        bar.setObjectName("Toolbar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        bar.setFixedHeight(52)
        tb = QHBoxLayout(bar)
        tb.setContentsMargins(10, 8, 10, 8)
        tb.setSpacing(8)

        self.close_btn = QToolButton()
        self.close_btn.setToolTip(tr("Close file"))
        self.close_btn.clicked.connect(self.closeRequested)
        self.title = QLabel(APP_NAME)
        self.title.setObjectName("FileName")

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
        self.search.textChanged.connect(lambda text: self.editor.search(text))
        self.search.returnPressed.connect(
            lambda: self.editor.search_step(
                -1 if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            )
        )
        self.search_count = muted()
        self.prev_btn = QToolButton()
        self.next_btn = QToolButton()
        self.prev_btn.clicked.connect(lambda: self.editor.search_step(-1))
        self.next_btn.clicked.connect(lambda: self.editor.search_step(1))

        self.sidebar_btn = QToolButton()
        self.sidebar_btn.setCheckable(True)
        self.sidebar_btn.setToolTip(tr("Show or hide the sidebar"))

        tb.addWidget(self.close_btn)
        tb.addWidget(self.title, 1)
        for w in (self.edit_btn, self.copy_btn, self.export_btn):
            tb.addWidget(w)
        tb.addSpacing(6)
        for w in (self.search_count, self.prev_btn, self.next_btn, self.search):
            tb.addWidget(w)
        tb.addWidget(self.sidebar_btn)

        # ----- body ------------------------------------------------------------------------
        self.drop = DropZone()
        self.drop.clicked.connect(self.choose_file)
        self.drop.fileDropped.connect(self.fileChosen)
        drop_page = QWidget()
        drop_layout = QVBoxLayout(drop_page)
        drop_layout.setContentsMargins(28, 28, 28, 28)
        drop_layout.addWidget(self.drop)

        self.editor = TranscriptEditor()
        self.stack = QStackedWidget()
        self.stack.addWidget(drop_page)
        self.stack.addWidget(self.editor)

        self.thin = QProgressBar()
        self.thin.setObjectName("Thin")
        self.thin.setTextVisible(False)
        self.thin.setFixedHeight(3)
        self.player = PlayerBar()
        self.sidebar = Sidebar(self.opts)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(0)
        left.addWidget(self.thin)
        left.addWidget(self.stack, 1)
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

        self._live_timer = QTimer(self, singleShot=True, interval=300, timeout=self._render_live)
        self._clock = QTimer(self, interval=1000, timeout=self.sidebar.refresh_detail)

        self.sidebar_btn.toggled.connect(self.sidebar.slide)
        self.editor.seekRequested.connect(self._seek_to)
        self.editor.togglePlay.connect(self.player.toggle)
        self.editor.skip.connect(self.player.skip)
        self.editor.edited.connect(self._on_edited)
        self.editor.editingChanged.connect(self.edit_btn.setChecked)
        self.editor.searchChanged.connect(self._on_search_result)
        self.player.positionChanged.connect(self._on_position)
        self.sidebar.optionsChanged.connect(self._on_options)

        for keys, slot in (
            (QKeySequence.StandardKey.Find, self._focus_search),
            (QKeySequence.StandardKey.FindNext, lambda: self.editor.search_step(1)),
            (QKeySequence.StandardKey.FindPrevious, lambda: self.editor.search_step(-1)),
            ("Ctrl+Shift+C", self.copy_all),
            ("Ctrl+E", lambda: self.edit_btn.isVisible() and self.edit_btn.toggle()),
            ("Ctrl+O", self.choose_file),
        ):
            QShortcut(QKeySequence(keys), self, slot)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self.search, self._clear_search,
                  context=Qt.ShortcutContext.WidgetShortcut)
        self.refresh_icons()
        self.show_empty()

    # ----- states ------------------------------------------------------------------------

    def current(self) -> Transcript | None:
        return self.live or self.t

    def show_empty(self) -> None:
        self.path = self.t = self.live = None
        self.dirty = False
        self.player.unload()
        self.player.hide()
        self.editor.set_editing(False)
        self.title.setText(APP_NAME)
        self.close_btn.hide()
        self.stack.setCurrentIndex(0)
        self.thin.hide()
        self._clock.stop()
        self._show_actions(False)
        self._show_search(False)
        self.sidebar.set_state("idle", has_file=False)
        self.sidebar.set_view_visible(False)
        self.sidebar.set_info(None)
        self.sidebar_btn.setChecked(False)
        self.sidebar.slide(False)

    def load_media(self, path: str, duration: float) -> None:
        """A new file: show it, load the player and slide the sidebar in."""
        self.path = path
        self.t = self.live = None
        self.dirty = False
        self.title.setText(Path(path).name)
        self.close_btn.show()
        self.editor.set_editing(False)
        self.editor.set_transcript(Transcript(path, duration=duration), self.opts)
        self.editor.setPlaceholderText(tr("Press “Transcribe” to start."))
        self.stack.setCurrentIndex(1)
        self.player.show()
        self.player.load(path, duration)
        self._show_actions(False)
        self._show_search(False)
        self.sidebar.set_state("idle")
        self.sidebar.set_info(None)
        self.sidebar.set_view_visible(False)
        self.sidebar_btn.setChecked(True)
        self.sidebar.slide(True)

    def begin_live(self, duration: float) -> None:
        self.live = Transcript(self.path, duration=duration)
        self.editor.set_editing(False)
        self.editor.set_transcript(self.live, self.opts)
        self.editor.setPlaceholderText(tr("Recognized text will appear here…"))
        self._starts = None
        self._show_actions(False)
        self._show_search(True)
        self.thin.show()
        self.thin.setRange(0, 0)
        self.sidebar.set_state("running")
        self.sidebar.set_view_visible(True)
        self.sidebar.set_info(None)
        self._clock.start()

    def add_live_segment(self, seg: Segment) -> None:
        if self.live is None:
            return
        self.live.segments.append(seg)
        if not self._live_timer.isActive():
            self._live_timer.start()

    def set_stage(self, stage: str, fraction: float, detail: str) -> None:
        self.sidebar.set_stage(stage, fraction, detail)
        if fraction < 0:
            self.thin.setRange(0, 0)
        else:
            self.thin.setRange(0, 1000)
            self.thin.setValue(int(fraction * 1000))

    def set_transcript(self, t: Transcript) -> None:
        self._end_run()
        self.t = t
        self.dirty = True
        self.editor.set_transcript(t, self.opts)
        self._starts = None
        self._show_actions(True)
        self._show_search(True)
        self.editor.search(self.search.text())
        self.sidebar.set_state("done")
        self.sidebar.set_view_visible(True)
        self.sidebar.set_info(t)
        self._on_position(self.player.position())
        self.editor.setFocus()

    def end_run_without_result(self) -> None:
        """Cancelled or failed: go back to the previous transcript, or to the loaded file."""
        self._end_run()
        if self.t is not None:
            self.editor.set_transcript(self.t, self.opts)
            self.sidebar.set_state("done")
            self._show_actions(True)
        elif self.path:
            self.editor.set_transcript(Transcript(self.path), self.opts)
            self.editor.setPlaceholderText(tr("Press “Transcribe” to start."))
            self.sidebar.set_state("idle")
            self.sidebar.set_view_visible(False)
            self._show_search(False)
        self._starts = None

    def _end_run(self) -> None:
        self._live_timer.stop()
        self._clock.stop()
        self.live = None
        self.thin.hide()

    def _render_live(self) -> None:
        if self.live is None:
            return
        bar = self.editor.verticalScrollBar()
        follow = bar.value() >= bar.maximum() - 4
        self.editor.render(self.opts)
        self._starts = None
        if follow:
            bar.setValue(bar.maximum())

    def _show_actions(self, on: bool) -> None:
        for w in (self.edit_btn, self.copy_btn, self.export_btn):
            w.setVisible(on)

    def _show_search(self, on: bool) -> None:
        self.search.setVisible(on)
        if not on:
            self.search.clear()
        if not self.search.text():
            self._on_search_result(-1, 0)

    def refresh_icons(self) -> None:
        self.close_btn.setIcon(icons.chevron_left())
        self.prev_btn.setIcon(icons.chevron_up())
        self.next_btn.setIcon(icons.chevron_down())
        self.sidebar_btn.setIcon(icons.sidebar())
        self.edit_btn.setIcon(icons.pencil())
        self.search.removeAction(self._search_action)
        self._search_action = self.search.addAction(icons.search(), QLineEdit.ActionPosition.LeadingPosition)
        for b in (self.close_btn, self.sidebar_btn):
            b.setIconSize(QSize(18, 18))
        self.player.refresh_icons()

    def on_theme_changed(self) -> None:
        self.refresh_icons()
        if self.current():
            self.editor.render(self.opts)
            self._on_position(self.player.position())

    # ----- actions -------------------------------------------------------------------------

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

    # ----- playback sync ---------------------------------------------------------------------

    def _seg_at_time(self, seconds: float) -> int | None:
        t = self.current()
        if t is None:
            return None
        if self._starts is None:
            self._visible = t.visible()
            self._starts = [t.segments[i].start for i in self._visible]
        k = bisect_right(self._starts, seconds + 0.05) - 1
        return self._visible[k] if k >= 0 else None

    def _on_position(self, seconds: float) -> None:
        if self.current() and self.editor.set_current(self._seg_at_time(seconds)) and self.player.is_playing():
            self.editor.scroll_to_current()

    def _seek_to(self, sid: int, offset: int) -> None:
        t = self.current()
        if t is None:
            return
        self.editor.sync()
        self.player.seek(t.segments[sid].time_at(offset))
        self.editor.set_current(sid)
        if not self.player.is_playing():
            self.player.toggle()

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
        if self.current():
            self.editor.render(opts)
            self._starts = None
            self._on_position(self.player.position())

    # ----- search ------------------------------------------------------------------------------

    def _focus_search(self) -> None:
        if self.search.isVisible():
            self.search.setFocus()
            self.search.selectAll()

    def _clear_search(self) -> None:
        self.search.clear()
        self.editor.setFocus()

    def _on_search_result(self, index: int, count: int) -> None:
        has_query = bool(self.search.text())
        for w in (self.search_count, self.prev_btn, self.next_btn):
            w.setVisible(has_query)
        self.search_count.setText(f"{index + 1}/{count}" if count else tr("No matches"))
