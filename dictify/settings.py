"""Persistent user preferences (QSettings)."""
from __future__ import annotations

from PySide6.QtCore import QSettings

from dictify import APP_NAME
from dictify.catalog import DEFAULT_MODEL
from dictify.formatting import ViewOptions

_DEFAULTS = {
    "ui_language": "system",
    "model": DEFAULT_MODEL,
    "language": "auto",
    "vad": True,
    "device": "auto",
    "last_dir": "",
    "export_format": "txt",
    "sidebar_visible": True,
}


def _store() -> QSettings:
    return QSettings(APP_NAME, APP_NAME)


def get(key: str):
    default = _DEFAULTS[key]
    return _store().value(key, default, type=type(default))


def put(key: str, value) -> None:
    _store().setValue(key, value)


def load_view_options() -> ViewOptions:
    s = _store()
    d = ViewOptions()
    return ViewOptions(
        mode=s.value("view/mode", d.mode, type=str),
        timestamps=s.value("view/timestamps", d.timestamps, type=bool),
        end_times=s.value("view/end_times", d.end_times, type=bool),
        pause=s.value("view/pause", d.pause, type=float),
        paragraph=s.value("view/paragraph", d.paragraph, type=str),
        font_size=s.value("view/font_size", d.font_size, type=int),
    )


def save_view_options(o: ViewOptions) -> None:
    s = _store()
    for key, value in vars(o).items():
        s.setValue(f"view/{key}", value)
