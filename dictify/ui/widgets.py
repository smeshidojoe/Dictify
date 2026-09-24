"""Custom-painted widgets: toggle switch, display-mode cards, drop zone, toast, seek slider."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QLabel,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QWidget,
)

from dictify.i18n import tr
from dictify.ui import icons, theme


def section_title(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("SectionTitle")
    return label


def muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    return label


class Switch(QAbstractButton):
    """iOS-style toggle."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(34, 20)

    def sizeHint(self) -> QSize:
        return QSize(34, 20)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        track = theme.c("accent") if self.isChecked() else theme.c("border")
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 4
        x = r.right() - d - 2 if self.isChecked() else r.left() + 2
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, r.top() + 2, d, d))


class ModeCard(QAbstractButton):
    """Display-mode picker card with a small illustration (continuous text vs. segment rows)."""

    def __init__(self, text: str, kind: str, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.kind = kind
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(100, 84)

    def sizeHint(self) -> QSize:
        return QSize(110, 88)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        checked = self.isChecked()
        p.setPen(QPen(theme.c("accent") if checked else theme.c("border"), 1.6 if checked else 1))
        p.setBrush(theme.c("accent_soft") if checked else theme.c("field"))
        p.drawRoundedRect(r, 10, 10)

        art = QRectF(r.center().x() - 34, r.top() + 12, 68, 38)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.c("field"))
        p.drawRoundedRect(art, 6, 6)
        line = theme.c("accent") if checked else theme.c("muted")
        p.setPen(QPen(line, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        x0, x1 = art.left() + 8, art.right() - 8
        for i in range(4):
            y = art.top() + 9 + i * 7
            if self.kind == "segments":
                p.drawLine(QPointF(x0, y), QPointF(x0 + 8, y))
                p.drawLine(QPointF(x0 + 13, y), QPointF(x1 - (i % 2) * 10, y))
            else:
                p.drawLine(QPointF(x0, y), QPointF(x1 - (12 if i == 3 else 0), y))

        p.setPen(theme.c("accent") if checked else theme.c("text"))
        f = QFont(self.font())
        f.setPointSizeF(f.pointSizeF() * 0.92)
        p.setFont(f)
        p.drawText(QRectF(r.left(), art.bottom() + 4, r.width(), r.bottom() - art.bottom() - 6),
                   Qt.AlignmentFlag.AlignCenter, self.text())


class DropZone(QAbstractButton):
    """Large dashed target: click to choose a file or drop one on it."""

    fileDropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(230)
        self._hover_drag = False

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self._hover_drag = True
            self.update()
            e.acceptProposedAction()

    def dragLeaveEvent(self, _e):
        self._hover_drag = False
        self.update()

    def dropEvent(self, e):
        self._hover_drag = False
        self.update()
        urls = [u for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            e.acceptProposedAction()
            self.fileDropped.emit(urls[0].toLocalFile())

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        active = self._hover_drag or self.underMouse()
        p.setBrush(theme.c("accent_soft") if active else theme.c("sidebar"))
        pen = QPen(theme.c("accent") if active else theme.c("border"), 2, Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 4])
        p.setPen(pen)
        p.drawRoundedRect(r, 16, 16)

        size = 56
        icon = icons.waveform_pixmap(size, theme.c("accent"))
        top = r.center().y() - 62
        p.drawPixmap(int(r.center().x() - size / 2), int(top), icon)

        f = QFont(self.font())
        f.setPointSizeF(f.pointSizeF() * 1.25)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(theme.c("text"))
        p.drawText(QRectF(r.left(), top + size + 10, r.width(), 28), Qt.AlignmentFlag.AlignCenter,
                   tr("Drop an audio or video file here"))
        p.setFont(self.font())
        p.setPen(theme.c("muted"))
        p.drawText(QRectF(r.left(), top + size + 38, r.width(), 22), Qt.AlignmentFlag.AlignCenter,
                   tr("or click to choose a file"))

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class Toast(QLabel):
    """Short-lived message floating at the bottom of its parent."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        self._timer = QTimer(self, singleShot=True, timeout=self.hide)

    def show_message(self, text: str, ms: int = 2200) -> None:
        self.setText(text)
        self.setStyleSheet(
            "QLabel { background: rgba(30,30,32,0.92); color: white; border-radius: 8px; padding: 8px 16px; }"
        )
        self.adjustSize()
        parent = self.parentWidget()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 90)
        self.raise_()
        self.show()
        self._timer.start(ms)


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
