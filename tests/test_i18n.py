import ast
import re
from pathlib import Path

from dictify import i18n
from dictify.exporters import FORMATS
from dictify.i18n import RU, UI_LANGUAGES
from dictify.ui.progress_view import STAGES
from dictify.ui.sidebar import PARAGRAPH_CHOICES

ROOT = Path(__file__).resolve().parent.parent / "dictify"
CALL = re.compile(r"""\btr\(\s*((?:(?:"[^"]*"|'[^']*')\s*)+)""")
UNTRANSLATED = {"English", "Русский"}


def source_keys():
    keys = set()
    for path in ROOT.rglob("*.py"):
        for m in CALL.finditer(path.read_text(encoding="utf-8")):
            keys.add("".join(ast.literal_eval(s) for s in re.findall(r""""[^"]*"|'[^']*'""", m.group(1))))
    return keys


def test_every_ui_string_has_russian_translation():
    keys = source_keys()
    keys |= {f.label for f in FORMATS} | set(STAGES.values()) | {label for _, label in PARAGRAPH_CHOICES}
    keys |= {label for _, label in UI_LANGUAGES}
    keys |= {"Automatic", "CPU", "GPU (NVIDIA CUDA)"}
    missing = sorted(k for k in keys - UNTRANSLATED if k not in RU)
    assert not missing, missing


def test_placeholders_match():
    for en, ru in RU.items():
        assert set(re.findall(r"{\w+}", en)) == set(re.findall(r"{\w+}", ru)), en


def test_tr_formats():
    i18n.set_language("ru")
    try:
        assert i18n.tr("Saved {name}", name="a.txt") == "Сохранено: a.txt"
    finally:
        i18n.set_language("en")
    assert i18n.tr("Saved {name}", name="a.txt") == "Saved a.txt"
