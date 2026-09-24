"""Custom-painted widgets: toggle switch, display-mode cards, drop zone, toast, progress
line, play button, seek slider; plus the small animation helpers they share.

Motion follows one rule set: animate only what would otherwise jump (state changes,
things appearing), keep it under ~250 ms, start every animation from the value currently
on screen so it can be reversed mid-flight, and never animate what the user reads.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QGraphicsOpacityEffect,
    QLabel,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QStyle,
    QStyleOptionSlider,
    QWidget,
)

from dictify.i18n import tr
from dictify.ui import icons, theme


def size_label(mb: int) -> str:
    return f"{mb / 1000:.1f} GB" if mb >= 1000 else f"{mb} MB"


def section_title(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("SectionTitle")
    return label


def muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    return label


# ----- animation helpers --------------------------------------------------------------------


class Tween(QVariantAnimation):
    """Animates one number towards a target, always starting from the value currently on
    screen, so retargeting mid-flight reverses smoothly instead of jumping."""

    def __init__(self, owner: QWidget, value: float = 0.0, duration: int = 160,
                 curve: QEasingCurve | None = None, on_change: Callable[[], None] | None = None):
        super().__init__(owner)
        self.value = value
        self._owner = owner
        self._on_change = on_change or owner.update
        self.setDuration(duration)
        self.setEasingCurve(curve or theme.EASE_OUT)
        self.valueChanged.connect(self._step)

    def _step(self, v) -> None:
        self.value = float(v)
        self._on_change()

    def to(self, target: float, animate: bool = True, duration: int | None = None) -> None:
        self.stop()
        if duration is not None:
            self.setDuration(duration)
        if not animate or not self._owner.isVisible() or abs(target - self.value) < 1e-4:
            self.value = target
            self._on_change()
            self.finished.emit()
            return
        self.setStartValue(self.value)
        self.setEndValue(float(target))
        self.start()


def fade_in(widget: QWidget, duration: int = 200) -> None:
    """Fades a widget in after it becomes visible (an opacity change, kept under reduced motion)."""
    if not widget.window().isVisible():
        return
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setEasingCurve(theme.EASE_OUT)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))  # effects cost a repaint pass
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


class _Snapshot(QWidget):
    def __init__(self, parent: QWidget, pixmap: QPixmap):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._pixmap = pixmap
        self.tween = Tween(self, 1.0, 180, theme.EASE_OUT)
        self.tween.finished.connect(lambda: self.tween.value <= 0 and self.deleteLater())

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setOpacity(self.tween.value)
        p.drawPixmap(0, 0, self._pixmap)


def crossfade(stack: QStackedWidget, index: int) -> None:
    """Switches pages by fading the old one out over the new one, instead of a hard cut."""
    if stack.currentIndex() == index:
        return
    if not stack.isVisible() or stack.currentWidget() is None:
        stack.setCurrentIndex(index)
        return
    cover = _Snapshot(stack, stack.currentWidget().grab())
    cover.setGeometry(stack.rect())
    stack.setCurrentIndex(index)
    cover.show()
    cover.raise_()
    cover.tween.to(0.0)


# ----- controls -----------------------------------------------------------------------------


class Switch(QAbstractButton):
    """iOS-style toggle; the knob glides to its new side."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(36, 22)
        self._pos = Tween(self, 1.0 if checked else 0.0, 180, theme.EASE_OUT)
        self.toggled.connect(lambda on: self._pos.to(1.0 if on else 0.0))

    def sizeHint(self) -> QSize:
        return QSize(36, 22)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        t = self._pos.value
        track = theme.mix(theme.c("border"), theme.c("accent"), t)
        if not self.isEnabled():
            track.setAlphaF(0.45)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 4
        stretch = 4 if self.isDown() else 0  # the knob widens under the finger, like iOS
        left, right = r.left() + 2, r.right() - 2 - d - stretch
        x = left + (right - left) * t
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawRoundedRect(QRectF(x, r.top() + 2.6, d + stretch, d), d / 2, d / 2)
        p.setBrush(QColor("white"))
        p.drawRoundedRect(QRectF(x, r.top() + 2, d + stretch, d), d / 2, d / 2)


class ModeCard(QAbstractButton):
    """Display-mode picker card with a small illustration (continuous text vs. segment rows)."""

    def __init__(self, text: str, kind: str, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.kind = kind
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setMinimumSize(100, 84)
        self._on = Tween(self, 0.0, 150, theme.EASE)
        self.toggled.connect(lambda on: self._on.to(1.0 if on else 0.0))

    def sizeHint(self) -> QSize:
        return QSize(110, 88)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        t = self._on.value
        idle_border = theme.c("muted" if self.underMouse() and t < 0.5 else "border")
        p.setPen(QPen(theme.mix(idle_border, theme.c("accent"), t), 1 + 0.6 * t))
        p.setBrush(theme.mix(theme.c("field"), theme.c("accent_soft"), t))
        p.drawRoundedRect(r, 10, 10)

        art = QRectF(r.center().x() - 34, r.top() + 12, 68, 38)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.c("bg"))
        p.drawRoundedRect(art, 6, 6)
        line = theme.mix(theme.c("muted"), theme.c("accent"), t)
        p.setPen(QPen(line, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        x0, x1 = art.left() + 8, art.right() - 8
        for i in range(4):
            y = art.top() + 9 + i * 7
            if self.kind == "segments":
                p.drawLine(QPointF(x0, y), QPointF(x0 + 8, y))
                p.drawLine(QPointF(x0 + 13, y), QPointF(x1 - (i % 2) * 10, y))
            else:
                p.drawLine(QPointF(x0, y), QPointF(x1 - (12 if i == 3 else 0), y))

        p.setPen(theme.mix(theme.c("text"), theme.c("accent"), t))
        f = QFont(self.font())
        f.setPointSizeF(f.pointSizeF() * 0.92)
        f.setWeight(QFont.Weight.DemiBold if t > 0.5 else QFont.Weight.Normal)
        p.setFont(f)
        p.drawText(QRectF(r.left(), art.bottom() + 4, r.width(), r.bottom() - art.bottom() - 6),
                   Qt.AlignmentFlag.AlignCenter, self.text())


class PlayButton(QAbstractButton):
    """Round accent play/pause button that dips slightly while pressed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.playing = False
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._press = Tween(self, 0.0, 120, theme.EASE_OUT)
        self.pressed.connect(lambda: self._press.to(1.0))
        self.released.connect(lambda: self._press.to(0.0, duration=160))

    def set_playing(self, playing: bool) -> None:
        self.playing = playing
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        p.translate(c)
        scale = 1 - 0.06 * self._press.value
        p.scale(scale, scale)
        color = theme.c("accent")
        if not self.isEnabled():
            color = theme.c("border")
        elif self.underMouse():
            color = color.lighter(108)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        radius = self.width() / 2 - 1
        p.drawEllipse(QPointF(0, 0), radius, radius)
        p.setBrush(QColor("white"))
        if self.playing:
            for x in (-4.6, 1.4):
                p.drawRoundedRect(QRectF(x, -6, 3.2, 12), 1.2, 1.2)
        else:
            path = QPainterPath(QPointF(-3.6, -6.8))
            path.lineTo(7.2, 0)
            path.lineTo(-3.6, 6.8)
            path.closeSubpath()
            p.drawPath(path)


class DropZone(QAbstractButton):
    """Large dashed target: click to choose a file or drop one on it."""

    fileDropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._drag = False
        self._active = Tween(self, 0.0, 150, theme.EASE)

    def _sync(self) -> None:
        self._active.to(1.0 if self._drag or self.underMouse() else 0.0)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self._drag = True
            self._sync()
            e.acceptProposedAction()

    def dragLeaveEvent(self, _e):
        self._drag = False
        self._sync()

    def dropEvent(self, e):
        self._drag = False
        self._sync()
        urls = [u for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            e.acceptProposedAction()
            self.fileDropped.emit(urls[0].toLocalFile())

    def enterEvent(self, e):
        super().enterEvent(e)
        self._sync()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        QTimer.singleShot(0, self._sync)  # underMouse() still reports True during leaveEvent

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._active.value
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.setBrush(theme.mix(theme.c("bg"), theme.c("accent_soft"), t * 0.8))
        pen = QPen(theme.mix(theme.c("border"), theme.c("accent"), t), 1.6, Qt.PenStyle.DashLine)
        pen.setDashPattern([5, 4])
        p.setPen(pen)
        p.drawRoundedRect(r, 18, 18)

        badge = 76
        top = r.center().y() - 86
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.mix(theme.c("accent_soft"), theme.c("accent", 0.22), t))
        p.drawEllipse(QRectF(r.center().x() - badge / 2, top, badge, badge))
        size = 40
        p.drawPixmap(int(r.center().x() - size / 2), int(top + (badge - size) / 2),
                     icons.waveform_pixmap(size, theme.c("accent")))

        title = QFont(self.font())
        title.setPointSizeF(title.pointSizeF() * 1.35)
        title.setWeight(QFont.Weight.DemiBold)
        title.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 99)  # large text: slightly tighter
        p.setFont(title)
        p.setPen(theme.c("text"))
        y = top + badge + 18
        p.drawText(QRectF(r.left(), y, r.width(), 30), Qt.AlignmentFlag.AlignCenter,
                   tr("Drop an audio or video file here"))
        p.setFont(self.font())
        p.setPen(theme.c("muted"))
        p.drawText(QRectF(r.left(), y + 32, r.width(), 22), Qt.AlignmentFlag.AlignCenter,
                   tr("or click to choose a file"))
        small = QFont(self.font())
        small.setPointSizeF(small.pointSizeF() * 0.88)
        p.setFont(small)
        p.setPen(theme.mix(theme.c("muted"), theme.c("bg"), 0.3))
        p.drawText(QRectF(r.left(), y + 58, r.width(), 20), Qt.AlignmentFlag.AlignCenter,
                   "MP3 · WAV · M4A · FLAC · OGG · MP4 · MOV · MKV · WEBM")


class DropOverlay(QWidget):
    """Translucent dashed frame that fades in over the text while a file is dragged onto it."""

    fileDropped = Signal(str)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.hide()
        self._fade = Tween(self, 0.0, 150, theme.EASE_OUT)
        self._fade.finished.connect(lambda: self._fade.value <= 0 and self.hide())

    def appear(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self._fade.to(1.0, duration=150)

    def disappear(self) -> None:
        if self.isVisible():
            self._fade.to(0.0, duration=120)  # exits a little faster than it enters

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dragLeaveEvent(self, _e):
        self.disappear()

    def dropEvent(self, e):
        self.disappear()
        urls = [u for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            e.acceptProposedAction()
            self.fileDropped.emit(urls[0].toLocalFile())

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._fade.value)
        p.fillRect(self.rect(), theme.c("bg", 0.88))
        r = QRectF(self.rect()).adjusted(16, 16, -16, -16)
        pen = QPen(theme.c("accent"), 1.6, Qt.PenStyle.DashLine)
        pen.setDashPattern([5, 4])
        p.setPen(pen)
        p.setBrush(theme.c("accent_soft"))
        p.drawRoundedRect(r, 18, 18)
        f = QFont(self.font())
        f.setPointSizeF(f.pointSizeF() * 1.35)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(theme.c("text"))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, tr("Drop the file to transcribe it"))


class Toast(QWidget):
    """Short-lived pill message that rises in above the bottom of its parent and sinks
    back out the same way."""

    RISE = 8

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        self._text = ""
        self.bottom_margin = 24
        self._shown = Tween(self, 0.0, 220, theme.EASE_OUT, on_change=self._animate)
        self._shown.finished.connect(lambda: self._shown.value <= 0 and self.hide())
        self._timer = QTimer(self, singleShot=True, timeout=lambda: self._shown.to(0.0, duration=160))

    def show_message(self, text: str, ms: int = 2200) -> None:
        self._text = text
        font = QFont(self.font())
        font.setWeight(QFont.Weight.Medium)
        self.setFont(font)
        m = QFontMetricsF(font)
        self.resize(int(m.horizontalAdvance(text) + 40), int(m.height() + 22))
        self._place()
        self.show()
        self.raise_()
        self._shown.to(1.0, duration=220)
        self._timer.start(ms)

    def _animate(self) -> None:
        self._place()
        self.update()

    def _place(self) -> None:
        parent = self.parentWidget()
        lift = 0 if theme.reduced_motion() else (1 - self._shown.value) * self.RISE
        self.move((parent.width() - self.width()) // 2,
                  int(parent.height() - self.height() - self.bottom_margin + lift))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._shown.value)
        r = QRectF(self.rect()).adjusted(6, 4, -6, -8)
        p.setPen(Qt.PenStyle.NoPen)
        for i, alpha in enumerate((0.05, 0.07, 0.09)):  # soft shadow, heavier near the pill
            grow = 3 - i
            p.setBrush(QColor(0, 0, 0, int(255 * alpha)))
            p.drawRoundedRect(r.adjusted(-grow, -grow + 2, grow, grow + 2), r.height() / 2 + grow, r.height() / 2 + grow)
        p.setBrush(theme.c("toast", 0.96))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(theme.c("toast_text"))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self._text)


class ProgressLine(QWidget):
    """Thin rounded progress bar. Determinate values glide (linearly, like any progress);
    unknown progress shows a sliding band."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._value = Tween(self, 0.0, 250, QEasingCurve(QEasingCurve.Type.Linear))
        self._busy = False
        self._phase = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1100, loopCount=-1)
        self._phase.valueChanged.connect(self.update)

    def set_fraction(self, fraction: float) -> None:
        if fraction < 0:
            if not self._busy:
                self._busy = True
                self._phase.start()
            return
        if self._busy:
            self._busy = False
            self._phase.stop()
        # Moving back (a new stage starting from zero) is a reset, not progress: jump.
        self._value.to(fraction, animate=fraction >= self._value.value)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        radius = r.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.c("border"))
        p.drawRoundedRect(r, radius, radius)
        p.setBrush(theme.c("accent"))
        if self._busy:
            band = r.width() * 0.3
            x = -band + (r.width() + band) * float(self._phase.currentValue() or 0.0)
            p.setClipRect(r)
            p.drawRoundedRect(QRectF(x, r.top(), band, r.height()), radius, radius)
        elif self._value.value > 0:
            w = max(r.height(), r.width() * min(1.0, self._value.value))
            p.drawRoundedRect(QRectF(r.left(), r.top(), w, r.height()), radius, radius)


class SeekSlider(QSlider):
    """Horizontal slider that jumps to the clicked position and keeps dragging from there."""

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            handle = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self
            )
            if not handle.contains(e.position().toPoint()):
                span = self.width() - handle.width()
                x = int(e.position().x() - handle.width() / 2)
                self.setValue(QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), x, span))
        super().mousePressEvent(e)
