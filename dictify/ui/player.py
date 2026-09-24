"""Bottom playback bar: play/pause, seek slider, time, speed."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QToolButton, QWidget

from dictify.formatting import fmt_time
from dictify.i18n import tr
from dictify.ui.widgets import PlayButton, SeekSlider

log = logging.getLogger(__name__)
RATES = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]


def _rate_label(rate: float) -> str:
    return f"{rate:g}×"


class PlayerBar(QWidget):
    positionChanged = Signal(float)  # seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PlayerBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedHeight(58)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self._dragging = False
        self._fallback_duration = 0.0

        self.play_btn = PlayButton()
        self.play_btn.setToolTip(tr("Play / pause (Space)"))
        self.play_btn.clicked.connect(self.toggle)

        self.slider = SeekSlider()
        self.slider.setRange(0, 0)
        self.slider.sliderPressed.connect(self._on_press)
        self.slider.sliderMoved.connect(self._on_moved)
        self.slider.sliderReleased.connect(self._on_release)

        self.time = QLabel("00:00 / 00:00")
        self.time.setObjectName("Time")

        self.speed = QToolButton()
        self.speed.setObjectName("Speed")
        self.speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.speed.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.speed.setToolTip(tr("Playback speed"))
        menu = QMenu(self.speed)
        group = QActionGroup(menu)
        for rate in RATES:
            act = QAction(_rate_label(rate), menu, checkable=True, checked=rate == 1.0)
            act.triggered.connect(lambda _=False, r=rate: self.set_rate(r))
            group.addAction(act)
            menu.addAction(act)
        self.speed.setMenu(menu)
        self.speed.setText(_rate_label(1.0))

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 16, 8)
        row.setSpacing(14)
        row.addWidget(self.play_btn)
        row.addWidget(self.slider, 1)
        row.addWidget(self.time)
        row.addWidget(self.speed)

        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._update_icon)
        self.player.errorOccurred.connect(self._on_error)
        self.refresh_icons()

    def load(self, path: str, duration: float) -> None:
        self._fallback_duration = duration
        self.play_btn.setEnabled(True)
        self.player.setSource(QUrl.fromLocalFile(path))
        self.slider.setRange(0, int(duration * 1000))
        self._show_time(0)

    def unload(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())

    def is_playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def toggle(self) -> None:
        if self.is_playing():
            self.player.pause()
        else:
            self.player.play()

    def seek(self, seconds: float) -> None:
        self.player.setPosition(int(max(0.0, seconds) * 1000))

    def skip(self, delta: float) -> None:
        self.seek(self.player.position() / 1000 + delta)

    def set_rate(self, rate: float) -> None:
        self.player.setPlaybackRate(rate)
        self.speed.setText(_rate_label(rate))

    def position(self) -> float:
        return self.player.position() / 1000

    def refresh_icons(self) -> None:
        self._update_icon()

    def _update_icon(self, *_):
        self.play_btn.set_playing(self.is_playing())

    def _duration_ms(self) -> int:
        return self.player.duration() or int(self._fallback_duration * 1000)

    def _show_time(self, ms: int) -> None:
        total = self._duration_ms() / 1000
        hours = total >= 3600
        self.time.setText(f"{fmt_time(ms / 1000, hours)} / {fmt_time(total, hours)}")

    def _on_position(self, ms: int) -> None:
        if not self._dragging:
            self.slider.setValue(ms)
            self._show_time(ms)
        self.positionChanged.emit(ms / 1000)

    def _on_duration(self, ms: int) -> None:
        if ms > 0:
            self.slider.setRange(0, ms)
            self._show_time(self.player.position())

    def _on_press(self) -> None:
        self._dragging = True

    def _on_moved(self, value: int) -> None:
        self._show_time(value)

    def _on_release(self) -> None:
        self._dragging = False
        self.player.setPosition(self.slider.value())
        self.positionChanged.emit(self.slider.value() / 1000)

    def _on_error(self, error, message: str) -> None:
        log.warning("Playback error %s: %s", error, message)
        self.play_btn.setEnabled(False)
        self.time.setText(tr("Playback unavailable"))
