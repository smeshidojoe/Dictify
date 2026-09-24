import importlib
import pkgutil

import dictify


def test_all_modules_import(qapp):
    """Catches missing runtime dependencies (e.g. a Qt module absent from the installed wheel)."""
    for mod in pkgutil.walk_packages(dictify.__path__, "dictify."):
        if mod.name in ("dictify.__main__",):
            continue
        importlib.import_module(mod.name)
