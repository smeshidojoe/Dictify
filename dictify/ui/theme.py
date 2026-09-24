"""Light/dark color tokens, motion tokens and the application stylesheet."""
from __future__ import annotations

import ctypes
import subprocess
import sys
from functools import lru_cache

from PySide6.QtCore import QEasingCurve, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette

LIGHT = {
    "bg": "#ffffff",
    "sidebar": "#f5f5f7",
    "border": "#e2e2e6",
    "text": "#1d1d1f",
    "muted": "#86868b",
    "accent": "#2f7cf6",
    "accent_soft": "#e6effe",
    "hover": "#ececf0",
    "field": "#ffffff",
    "current": "#dbe8fd",
    "word": "#2f7cf6",  # drawn translucent over the spoken word
    "search": "#fff0a0",
    "search_current": "#ffc64d",
    "toast": "#1d1d1f",
    "toast_text": "#ffffff",
}
DARK = {
    "bg": "#1c1c1e",
    "sidebar": "#232325",
    "border": "#38383b",
    "text": "#ececef",
    "muted": "#98989f",
    "accent": "#4b8ef8",
    "accent_soft": "#1f3252",
    "hover": "#313134",
    "field": "#2a2a2d",
    "current": "#27456f",
    "word": "#5c9bff",
    "search": "#6a5a12",
    "search_current": "#a67c00",
    "toast": "#3a3a3d",
    "toast_text": "#ffffff",
}

_tokens = LIGHT


def is_dark() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def c(name: str, alpha: float | None = None) -> QColor:
    color = QColor(_tokens[name])
    if alpha is not None:
        color.setAlphaF(alpha)
    return color


def hexc(name: str) -> str:
    return _tokens[name]


def mix(a: QColor, b: QColor, t: float) -> QColor:
    """Linear blend between two colors (t = 0 gives a, 1 gives b)."""
    return QColor.fromRgbF(*(x + (y - x) * t for x, y in zip(a.getRgbF(), b.getRgbF())))


# ----- motion -------------------------------------------------------------------------------
# One shared vocabulary: strong ease-out for things that appear or respond to a press,
# ease-in-out for things moving on screen, the iOS drawer curve for the sliding panel.


def _bezier(x1: float, y1: float, x2: float, y2: float) -> QEasingCurve:
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2), QPointF(1, 1))
    return curve


EASE = _bezier(0.25, 0.1, 0.25, 1)  # color / hover changes
EASE_OUT = _bezier(0.23, 1, 0.32, 1)
EASE_IN_OUT = _bezier(0.77, 0, 0.175, 1)
EASE_DRAWER = _bezier(0.32, 0.72, 0, 1)


@lru_cache(maxsize=1)
def reduced_motion() -> bool:
    """The OS asks for less motion: slides and scrolls become instant, fades stay."""
    try:
        if sys.platform == "win32":
            enabled = ctypes.c_bool(True)
            SPI_GETCLIENTAREAANIMATION = 0x1042
            ctypes.windll.user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0)
            return not enabled.value
        if sys.platform == "darwin":
            out = subprocess.run(
                ["defaults", "read", "com.apple.universalaccess", "reduceMotion"],
                capture_output=True, text=True, timeout=2,
            )
            return out.stdout.strip() == "1"
    except Exception:
        pass
    return False


# ----- application --------------------------------------------------------------------------


def apply(app) -> None:
    global _tokens
    _tokens = DARK if is_dark() else LIGHT
    app.setStyle("Fusion")
    app.setFont(_ui_font(app.font()))
    app.setPalette(_palette())
    app.setStyleSheet(_stylesheet())


def _ui_font(current: QFont) -> QFont:
    # The platform UI face: Qt on Windows otherwise inherits the legacy dialog font
    # (often Tahoma). macOS already gives the system font (SF) at the native size.
    if sys.platform != "win32":
        return current
    font = QFont("Segoe UI")
    font.setPointSizeF(9.75)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def _palette() -> QPalette:
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: "sidebar",
        QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "field",
        QPalette.ColorRole.AlternateBase: "sidebar",
        QPalette.ColorRole.Text: "text",
        QPalette.ColorRole.Button: "field",
        QPalette.ColorRole.ButtonText: "text",
        QPalette.ColorRole.Highlight: "accent",
        QPalette.ColorRole.PlaceholderText: "muted",
        QPalette.ColorRole.ToolTipBase: "field",
        QPalette.ColorRole.ToolTipText: "text",
        QPalette.ColorRole.Mid: "border",
        QPalette.ColorRole.Midlight: "border",
        QPalette.ColorRole.Light: "field",
        QPalette.ColorRole.Dark: "border",
    }
    for role, token in roles.items():
        p.setColor(role, c(token))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, c("muted"))
    return p


def _stylesheet() -> str:
    from dictify.ui import icons

    t = _tokens
    down = icons.chevron_file("down", "muted")
    up = icons.chevron_file("up", "muted")
    return f"""
    QMainWindow, #Page {{ background: {t['bg']}; }}
    #Sidebar {{
        background: {t['sidebar']}; border: none;
        border-left: 1px solid {t['border']}; border-top: 1px solid {t['border']};
    }}
    #SidebarBody {{ background: {t['sidebar']}; }}
    #Toolbar {{ background: {t['bg']}; border-bottom: 1px solid transparent; }}
    #Toolbar[scrolled="true"] {{ border-bottom-color: {t['border']}; }}
    #PlayerBar {{ background: {t['bg']}; border-top: 1px solid {t['border']}; }}

    QLabel {{ color: {t['text']}; background: transparent; }}
    QLabel#Muted {{ color: {t['muted']}; }}
    QLabel#FileName {{ font-weight: 600; }}
    QLabel#SectionTitle {{ color: {t['muted']}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; }}
    QLabel#Time {{ color: {t['muted']}; }}
    QLabel#Stage {{ font-weight: 600; }}

    QPushButton {{
        background: {t['field']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 7px; padding: 5px 12px;
    }}
    QPushButton:hover {{ background: {t['hover']}; }}
    QPushButton:pressed {{ background: {t['border']}; }}
    QPushButton:disabled {{ color: {t['muted']}; }}
    QPushButton:checked {{ background: {t['accent_soft']}; border-color: {t['accent']}; color: {t['accent']}; }}
    QPushButton:flat {{ background: transparent; border: none; color: {t['muted']}; padding: 4px 6px; }}
    QPushButton:flat:hover {{ color: {t['text']}; }}
    QPushButton#Primary {{
        background: {t['accent']}; color: white; border: none; font-weight: 600; padding: 8px 18px;
    }}
    QPushButton#Primary:hover {{ background: {QColor(t['accent']).lighter(108).name()}; }}
    QPushButton#Primary:pressed {{ background: {QColor(t['accent']).darker(112).name()}; }}
    QPushButton#Primary:disabled {{ background: {t['border']}; color: {t['muted']}; }}
    QPushButton::menu-indicator {{ image: url({down}); subcontrol-position: right center; right: 8px; width: 10px; }}
    QPushButton#Menu {{ padding-right: 24px; }}

    QToolButton {{ background: transparent; border: none; border-radius: 7px; padding: 4px; color: {t['text']}; }}
    QToolButton:hover {{ background: {t['hover']}; }}
    QToolButton:pressed {{ background: {t['border']}; }}
    QToolButton:checked {{ background: {t['accent_soft']}; }}
    QToolButton#Speed {{
        color: {t['accent']}; background: {t['accent_soft']}; padding: 3px 9px; font-weight: 600;
    }}
    QToolButton#Speed::menu-indicator {{ image: none; width: 0; }}

    QLineEdit {{
        background: {t['field']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 7px; padding: 5px 8px;
        selection-background-color: {t['accent']};
    }}
    QLineEdit:focus {{ border-color: {t['accent']}; }}

    QComboBox, QAbstractSpinBox {{
        background: {t['field']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 7px; padding: 4px 8px;
        selection-background-color: {t['accent']};
    }}
    QComboBox:hover, QAbstractSpinBox:hover {{ border-color: {QColor(t['border']).darker(125).name() if t is LIGHT else QColor(t['border']).lighter(140).name()}; }}
    QComboBox:focus, QAbstractSpinBox:focus {{ border-color: {t['accent']}; }}
    QComboBox:disabled, QAbstractSpinBox:disabled {{ color: {t['muted']}; }}
    QComboBox {{ padding-right: 24px; }}
    QComboBox::drop-down {{ border: none; width: 22px; subcontrol-position: center right; }}
    QComboBox::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}
    QComboBox QAbstractItemView {{
        background: {t['field']}; color: {t['text']}; border: 1px solid {t['border']};
        padding: 4px; outline: none; selection-background-color: {t['accent']}; selection-color: white;
    }}
    QAbstractSpinBox {{ padding-right: 20px; }}
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
        subcontrol-origin: border; width: 18px; border: none; background: transparent;
    }}
    QAbstractSpinBox::up-button {{ subcontrol-position: top right; margin: 2px 2px 0 0; }}
    QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; margin: 0 2px 2px 0; }}
    QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
        background: {t['hover']}; border-radius: 4px;
    }}
    QAbstractSpinBox::up-arrow {{ image: url({up}); width: 9px; height: 9px; }}
    QAbstractSpinBox::down-arrow {{ image: url({down}); width: 9px; height: 9px; }}

    QTextEdit#Editor {{
        background: {t['bg']}; color: {t['text']}; border: none;
        selection-background-color: {t['accent']}; selection-color: white;
    }}

    QSlider::groove:horizontal {{ height: 4px; background: {t['border']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        background: white; border: 1px solid {QColor(t['border']).darker(115).name()};
        width: 12px; height: 12px; margin: -5px 0; border-radius: 7px;
    }}
    QSlider::handle:horizontal:hover {{ border-color: {t['accent']}; }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 3px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['muted']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QMenu {{ background: {t['field']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 4px; }}
    QMenu::item {{ padding: 5px 20px 5px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {t['accent']}; color: white; }}
    QMenu::indicator {{ width: 0; }}
    QMenu::item:checked {{ color: {t['accent']}; font-weight: 600; }}
    QMenu::item:checked:selected {{ color: white; }}
    QToolTip {{ background: {t['field']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 3px 6px; }}
    """
