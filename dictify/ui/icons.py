"""Small vector icons painted with QPainter, so the app ships no image assets."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

from dictify.ui import theme

SCALE = 3  # render at 3x so icons stay crisp on Retina / high-DPI screens


def _icon(draw: Callable[[QPainter, float], None], size: int = 18, color: str = "text") -> QIcon:
    pm = QPixmap(size * SCALE, size * SCALE)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(SCALE, SCALE)
    pen = QPen(theme.c(color), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    draw(p, size)
    p.end()
    pm.setDevicePixelRatio(SCALE)
    return QIcon(pm)


def chevron_left(color="text") -> QIcon:
    return _icon(lambda p, s: p.drawPolyline([QPointF(11, 4), QPointF(6, 9), QPointF(11, 14)]), color=color)


def chevron_up(color="text") -> QIcon:
    return _icon(lambda p, s: p.drawPolyline([QPointF(4.5, 11), QPointF(9, 6.5), QPointF(13.5, 11)]), 16, color)


def chevron_down(color="text") -> QIcon:
    return _icon(lambda p, s: p.drawPolyline([QPointF(4.5, 6.5), QPointF(9, 11), QPointF(13.5, 6.5)]), 16, color)


def sidebar(color="text") -> QIcon:
    def draw(p, s):
        p.drawRoundedRect(QRectF(2.5, 3.5, 13, 11), 2, 2)
        p.drawLine(QPointF(10.5, 3.5), QPointF(10.5, 14.5))

    return _icon(draw, color=color)


def search(color="muted") -> QIcon:
    def draw(p, s):
        p.drawEllipse(QRectF(3, 3, 8.5, 8.5))
        p.drawLine(QPointF(10.2, 10.2), QPointF(14.5, 14.5))

    return _icon(draw, 16, color)


def pencil(color="text") -> QIcon:
    def draw(p, s):
        path = QPainterPath(QPointF(3.5, 14.5))
        path.lineTo(4.2, 11.3)
        path.lineTo(12, 3.5)
        path.lineTo(14.5, 6)
        path.lineTo(6.7, 13.8)
        path.closeSubpath()
        p.drawPath(path)

    return _icon(draw, color=color)


def play(color="accent") -> QIcon:
    def draw(p, s):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.c(color))
        path = QPainterPath(QPointF(6, 3.5))
        path.lineTo(15, 9)
        path.lineTo(6, 14.5)
        path.closeSubpath()
        p.drawPath(path)

    return _icon(draw, 18, color)


def pause(color="accent") -> QIcon:
    def draw(p, s):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.c(color))
        p.drawRoundedRect(QRectF(4.5, 3.5, 3.2, 11), 1, 1)
        p.drawRoundedRect(QRectF(10.3, 3.5, 3.2, 11), 1, 1)

    return _icon(draw, 18, color)


def waveform_pixmap(size: int, color: QColor) -> QPixmap:
    pm = QPixmap(size * SCALE, size * SCALE)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(SCALE, SCALE)
    _waveform(p, QRectF(0, 0, size, size), color)
    p.end()
    pm.setDevicePixelRatio(SCALE)
    return pm


def _waveform(p: QPainter, r: QRectF, color: QColor) -> None:
    heights = [0.28, 0.5, 0.82, 0.6, 0.95, 0.45, 0.7, 0.34]
    bar = r.width() / (len(heights) * 1.9)
    gap = (r.width() - bar * len(heights)) / (len(heights) + 1)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    for i, h in enumerate(heights):
        height = r.height() * h * 0.8
        x = r.left() + gap + i * (bar + gap)
        y = r.center().y() - height / 2
        p.drawRoundedRect(QRectF(x, y, bar, height), bar / 2, bar / 2)


def app_pixmap(size: int = 256) -> QPixmap:
    """The app icon: white waveform on a blue-violet rounded square."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    inset = size * 0.08
    rect = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0, QColor("#4f8df9"))
    grad.setColorAt(1, QColor("#8a5cf6"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(rect, size * 0.2, size * 0.2)
    wave = rect.adjusted(rect.width() * 0.2, rect.height() * 0.22, -rect.width() * 0.2, -rect.height() * 0.22)
    _waveform(p, wave, QColor("white"))
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 32, 64, 128, 256, 512):
        icon.addPixmap(app_pixmap(s))
    return icon
