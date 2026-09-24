"""Light/dark color tokens and the application stylesheet."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

LIGHT = {
    "bg": "#ffffff",
    "sidebar": "#f6f6f8",
    "border": "#e3e3e7",
    "text": "#1d1d1f",
    "muted": "#8a8a8e",
    "accent": "#2f7cf6",
    "accent_soft": "#e4eefe",
    "hover": "#ececf0",
    "field": "#ffffff",
    "current": "#dbe8fd",
    "search": "#fff0a0",
    "search_current": "#ffc64d",
}
DARK = {
    "bg": "#1c1c1e",
    "sidebar": "#242426",
    "border": "#3a3a3d",
    "text": "#ececef",
    "muted": "#98989f",
    "accent": "#4b8ef8",
    "accent_soft": "#1f3252",
    "hover": "#333336",
    "field": "#2b2b2e",
    "current": "#27456f",
    "search": "#6a5a12",
    "search_current": "#a67c00",
}

_tokens = LIGHT


def is_dark() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def c(name: str) -> QColor:
    return QColor(_tokens[name])


def hexc(name: str) -> str:
    return _tokens[name]


def apply(app) -> None:
    global _tokens
    _tokens = DARK if is_dark() else LIGHT
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setStyleSheet(_stylesheet())


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
    t = _tokens
    return f"""
    QMainWindow, #Page {{ background: {t['bg']}; }}
    #Sidebar {{ background: {t['sidebar']}; border: none; border-left: 1px solid {t['border']}; }}
    #SidebarBody {{ background: {t['sidebar']}; }}
    #Toolbar {{ background: {t['sidebar']}; border-bottom: 1px solid {t['border']}; }}
    #PlayerBar {{ background: {t['sidebar']}; border-top: 1px solid {t['border']}; }}
    #Card {{ background: {t['field']}; border: 1px solid {t['border']}; border-radius: 10px; }}

    QLabel {{ color: {t['text']}; background: transparent; }}
    QLabel#Muted {{ color: {t['muted']}; }}
    QLabel#Title {{ font-size: 22px; font-weight: 600; }}
    QLabel#FileName {{ font-weight: 600; }}
    QLabel#SectionTitle {{ color: {t['muted']}; font-size: 11px; font-weight: 600; letter-spacing: 0.5px; }}
    QLabel#Time {{ font-weight: 600; }}

    QPushButton {{
        background: {t['field']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 6px; padding: 5px 12px;
    }}
    QPushButton:hover {{ background: {t['hover']}; }}
    QPushButton:pressed {{ background: {t['border']}; }}
    QPushButton:disabled {{ color: {t['muted']}; }}
    QPushButton:checked {{ background: {t['accent_soft']}; border-color: {t['accent']}; color: {t['accent']}; }}
    QPushButton#Primary {{ background: {t['accent']}; color: white; border: none; font-weight: 600; padding: 7px 18px; }}
    QPushButton#Primary:hover {{ background: {QColor(t['accent']).lighter(110).name()}; }}
    QPushButton::menu-indicator {{ subcontrol-position: right center; right: 6px; }}
    QPushButton#Menu {{ padding-right: 22px; }}

    QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 4px; color: {t['text']}; }}
    QToolButton:hover {{ background: {t['hover']}; }}
    QToolButton:checked {{ background: {t['accent_soft']}; }}
    QToolButton#Speed {{ color: {t['accent']}; background: {t['accent_soft']}; padding: 2px 8px; font-size: 12px; }}
    QToolButton#Speed::menu-indicator {{ image: none; width: 0; }}

    QLineEdit {{
        background: {t['field']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 6px; padding: 5px 8px;
        selection-background-color: {t['accent']};
    }}
    QLineEdit:focus {{ border-color: {t['accent']}; }}

    QTextEdit#Editor, QPlainTextEdit#Preview {{
        background: {t['bg']}; color: {t['text']}; border: none;
        selection-background-color: {t['accent']}; selection-color: white;
    }}

    QProgressBar {{ background: {t['border']}; border: none; border-radius: 3px; max-height: 6px; }}
    QProgressBar::chunk {{ background: {t['accent']}; border-radius: 3px; }}
    QProgressBar#Thin {{ background: transparent; border-radius: 0; max-height: 3px; }}
    QProgressBar#Thin::chunk {{ border-radius: 0; }}

    QSlider::groove:horizontal {{ height: 4px; background: {t['border']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        background: white; border: 1px solid {t['border']};
        width: 16px; height: 16px; margin: -7px 0; border-radius: 8px;
    }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 3px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['muted']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QMenu {{ background: {t['field']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 4px; }}
    QMenu::item {{ padding: 5px 20px 5px 12px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {t['accent']}; color: white; }}
    QToolTip {{ background: {t['field']}; color: {t['text']}; border: 1px solid {t['border']}; }}
    """
