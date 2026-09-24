"""Window chrome: the app toolbar doubles as the window's title bar.

Windows: WM_NCCALCSIZE removes the native caption while the window keeps its resizable
frame, so the system still provides the shadow, Aero Snap, min/max animations and
edge resizing. WM_NCHITTEST maps the edges to resize handles and empty toolbar space to
the caption (drag, double-click to maximize, system menu). Caption buttons are ours.

macOS: the content extends under a transparent title bar (Qt::ExpandedClientAreaHint)
and the native traffic-light buttons stay where they are; empty toolbar space drags the
window. Everything else (fullscreen, zoom, Mission Control) stays native.
"""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QWidget,
)

from dictify.ui import icons, theme

# Qt::ExpandedClientAreaHint (Qt 6.9+) isn't exposed by PySide6 under that name; the value
# is shared with a legacy flag, so pass it numerically.
EXPANDED_CLIENT_AREA = Qt.WindowType(0x00400000)
MAC_TRAFFIC_LIGHTS_WIDTH = 78


def create(window, workspace) -> "Chrome":
    platform = QGuiApplication.platformName()  # "offscreen" in tests and CI self-tests
    if sys.platform == "win32" and platform == "windows":
        return WindowsChrome(window, workspace)
    if sys.platform == "darwin" and platform == "cocoa":
        return MacChrome(window, workspace)
    return Chrome(window, workspace)


def _is_drag_area(widget: QWidget | None, bar: QWidget) -> bool:
    """Empty toolbar space and plain labels move the window; controls stay clickable."""
    if widget is None or widget is bar:
        return True
    if isinstance(widget, (QAbstractButton, QLineEdit, QComboBox, QAbstractSpinBox)):
        return False
    if isinstance(widget, QLabel) and not widget.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse:
        return bar.isAncestorOf(widget)
    return False


class Chrome:
    """Default: native window decorations (Linux)."""

    def __init__(self, window, workspace):
        self.window = window
        self.bar = workspace.bar

    def native_event(self, event_type, message):
        return None

    def on_show(self) -> None:
        pass

    def on_state_change(self) -> None:
        pass


# ----- macOS ------------------------------------------------------------------------------


class MacChrome(QObject):
    def __init__(self, window, workspace):
        super().__init__(window)
        self.window = window
        self.bar = workspace.bar
        window.setWindowFlags(window.windowFlags() | EXPANDED_CLIENT_AREA | Qt.WindowType.NoTitleBarBackgroundHint)
        # Toolbar sits in the title bar: leave room for the traffic lights, keep it compact.
        self.bar.setFixedHeight(40)
        margins = workspace.toolbar_layout.contentsMargins()
        workspace.toolbar_layout.setContentsMargins(MAC_TRAFFIC_LIGHTS_WIDTH, 4, margins.right(), 4)
        # The native title (window title) is drawn centered; hide ours to avoid doubling it.
        workspace.title.hide()
        self.bar.installEventFilter(self)

    def eventFilter(self, obj, e):
        if obj is self.bar:
            if e.type() == QEvent.Type.MouseButtonPress and e.button() == Qt.MouseButton.LeftButton:
                child = self.bar.childAt(e.position().toPoint())
                if _is_drag_area(child, self.bar) and self.window.windowHandle():
                    self.window.windowHandle().startSystemMove()
                    return True
            if e.type() == QEvent.Type.MouseButtonDblClick:
                self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()
                return True
        return False

    def native_event(self, event_type, message):
        return None

    def on_show(self) -> None:
        pass

    def on_state_change(self) -> None:
        pass


# ----- Windows ----------------------------------------------------------------------------

WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
HTCLIENT, HTCAPTION = 1, 2
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 10, 11, 12, 13, 14, 15, 16, 17
SM_CXSIZEFRAME, SM_CYSIZEFRAME, SM_CXPADDEDBORDER = 32, 33, 92
SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0002, 0x0001, 0x0004, 0x0010


class CaptionButton(QAbstractButton):
    """Windows-style caption button (minimize / maximize-restore / close)."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.maximized = False
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def sizeHint(self) -> QSize:
        return QSize(46, 44)

    def paintEvent(self, _e):
        p = QPainter(self)
        hovered = self.underMouse()
        pressed = self.isDown()
        if self.kind == "close" and (hovered or pressed):
            p.fillRect(self.rect(), QColor("#c42b1c" if pressed else "#e81123"))
            color = QColor("white")
        else:
            if hovered or pressed:
                p.fillRect(self.rect(), theme.c("border" if pressed else "hover"))
            color = theme.c("text")
        p.setRenderHint(QPainter.RenderHint.Antialiasing, self.kind == "close")
        p.setPen(QPen(color, 1.0))
        c = QPointF(self.width() / 2, self.height() / 2)
        s = 5.0
        if self.kind == "min":
            p.drawLine(QPointF(c.x() - s, c.y()), QPointF(c.x() + s, c.y()))
        elif self.kind == "max" and not self.maximized:
            p.drawRect(QRectF(c.x() - s, c.y() - s, 2 * s, 2 * s))
        elif self.kind == "max":
            p.drawRect(QRectF(c.x() - s, c.y() - s + 2, 2 * s - 2, 2 * s - 2))
            p.drawPolyline([QPointF(c.x() - s + 2, c.y() - s + 2), QPointF(c.x() - s + 2, c.y() - s),
                            QPointF(c.x() + s, c.y() - s), QPointF(c.x() + s, c.y() + s - 2),
                            QPointF(c.x() + s - 2, c.y() + s - 2)])
        else:
            p.drawLine(QPointF(c.x() - s, c.y() - s), QPointF(c.x() + s, c.y() + s))
            p.drawLine(QPointF(c.x() + s, c.y() - s), QPointF(c.x() - s, c.y() + s))


class _MARGINS(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int), ("top", ctypes.c_int), ("bottom", ctypes.c_int)]


class WindowsChrome(Chrome):
    def __init__(self, window, workspace):
        super().__init__(window, workspace)
        from ctypes import wintypes

        self._wt = wintypes

        class NCCALCSIZE_PARAMS(ctypes.Structure):
            _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

        self._NCCALCSIZE_PARAMS = NCCALCSIZE_PARAMS
        u = self._user32 = ctypes.WinDLL("user32")
        u.GetDpiForWindow.argtypes = [wintypes.HWND]
        u.GetDpiForWindow.restype = ctypes.c_uint
        u.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, ctypes.c_uint]
        u.IsZoomed.argtypes = [wintypes.HWND]
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [ctypes.c_uint]
        self._dwm = ctypes.WinDLL("dwmapi")
        self._dwm.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.POINTER(_MARGINS)]
        self._shown = False

        height = 44
        self.bar.setFixedHeight(height)
        layout = workspace.toolbar_layout
        m = layout.contentsMargins()
        layout.setContentsMargins(m.left(), 0, 0, 0)
        icon = QLabel()
        icon.setPixmap(icons.app_pixmap(40))
        icon.setFixedSize(20, 20)
        icon.setScaledContents(True)
        layout.insertWidget(0, icon)
        layout.addSpacing(4)
        self.buttons = {}
        for kind in ("min", "max", "close"):
            b = CaptionButton(kind)
            b.setFixedSize(46, height)
            layout.addWidget(b)
            self.buttons[kind] = b
        self.buttons["min"].clicked.connect(window.showMinimized)
        self.buttons["max"].clicked.connect(self._toggle_max)
        self.buttons["close"].clicked.connect(window.close)

    def _toggle_max(self) -> None:
        self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()

    def on_state_change(self) -> None:
        b = self.buttons["max"]
        b.maximized = self.window.isMaximized()
        b.update()

    def on_show(self) -> None:
        if self._shown:
            return
        self._shown = True
        hwnd = int(self.window.winId())
        # Keeps the DWM drop shadow now that the client area covers the whole window.
        self._dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(_MARGINS(0, 0, 1, 0)))
        self._user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                  SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)

    def _frame(self, hwnd: int) -> tuple[int, int]:
        dpi = self._user32.GetDpiForWindow(hwnd) or 96
        metric = self._user32.GetSystemMetricsForDpi
        pad = metric(SM_CXPADDEDBORDER, dpi)
        return metric(SM_CXSIZEFRAME, dpi) + pad, metric(SM_CYSIZEFRAME, dpi) + pad

    def native_event(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return None
        msg = self._wt.MSG.from_address(int(message))
        if msg.message == WM_NCCALCSIZE and msg.wParam:
            if self._user32.IsZoomed(msg.hWnd):
                # A maximized window overhangs the screen by its frame; pull the client back in.
                fx, fy = self._frame(msg.hWnd)
                rect = self._NCCALCSIZE_PARAMS.from_address(msg.lParam).rgrc[0]
                rect.left += fx
                rect.right -= fx
                rect.top += fy
                rect.bottom -= fy
            return True, 0
        if msg.message == WM_NCHITTEST:
            x = ctypes.c_short(msg.lParam & 0xFFFF).value
            y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
            return True, self.hit_test(msg.hWnd, x, y)
        return None

    def hit_test(self, hwnd: int, x: int, y: int) -> int:
        """x, y: screen position in physical pixels."""
        rect = self._wt.RECT()
        self._user32.GetWindowRect(hwnd, ctypes.byref(rect))
        lx, ly = x - rect.left, y - rect.top
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if not self._user32.IsZoomed(hwnd):
            fx, fy = self._frame(hwnd)
            left, right = lx < fx, lx >= w - fx
            top, bottom = ly < fy, ly >= h - fy
            if top and left:
                return HTTOPLEFT
            if top and right:
                return HTTOPRIGHT
            if bottom and left:
                return HTBOTTOMLEFT
            if bottom and right:
                return HTBOTTOMRIGHT
            if left:
                return HTLEFT
            if right:
                return HTRIGHT
            if top:
                return HTTOP
            if bottom:
                return HTBOTTOM
        dpr = self.window.devicePixelRatioF()
        pos = QPoint(int(lx / dpr), int(ly / dpr))
        bar_pos = self.bar.mapFrom(self.window, pos)
        if self.bar.rect().contains(bar_pos) and _is_drag_area(self.bar.childAt(bar_pos), self.bar):
            return HTCAPTION
        return HTCLIENT
