# PyInstaller spec: pyinstaller Dictify.spec
# Builds dist/Dictify (Windows) or dist/Dictify.app (macOS).
import importlib.util
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, collect_submodules

sys.path.insert(0, SPECPATH)
from dictify import __version__  # noqa: E402

mac = sys.platform == "darwin"
datas = collect_data_files("docx")  # default Word template
binaries = []
hiddenimports = []

if mac:
    d, b, h = collect_all("mlx_whisper")  # includes tokenizer + mel filter assets
    datas += d
    binaries += b
    hiddenimports += h + ["tiktoken_ext", "tiktoken_ext.openai_public"]
    # mlx is a namespace package whose native library and Metal kernels come from the
    # separate mlx-metal wheel; add them explicitly, side by side as MLX expects.
    hiddenimports += collect_submodules("mlx")
    for root in importlib.util.find_spec("mlx").submodule_search_locations:
        lib = Path(root) / "lib"
        for name in ("libmlx.dylib", "libjaccl.dylib"):
            if (lib / name).exists():
                binaries.append((str(lib / name), "mlx/lib"))
        if (lib / "mlx.metallib").exists():
            datas.append((str(lib / "mlx.metallib"), "mlx/lib"))
else:
    datas += collect_data_files("faster_whisper")  # Silero VAD model
    binaries += collect_dynamic_libs("ctranslate2")
    hiddenimports += ["faster_whisper"]

# Keep the bundle to what Dictify imports, even when built from a Python that has more
# installed (a global interpreter with PyQt, Jupyter, ML stacks...). PyInstaller aborts
# outright if it sees more than one Qt binding, so all but PySide6 are excluded.
excludes = [
    # other Qt bindings
    "PyQt5", "PyQt6", "PySide2", "qtpy", "sip",
    # not used by Dictify (mlx_whisper word timing uses dictify.align instead of numba/scipy)
    "torch", "torchaudio", "torchvision", "tensorflow", "keras", "jax",
    "numba", "llvmlite", "scipy", "sklearn", "pandas", "matplotlib", "cv2", "sympy",
    "IPython", "jupyter", "jupyter_client", "jupyter_core", "ipykernel", "notebook", "nbformat",
    "tkinter", "_tkinter", "pytest",
    # unused parts of PySide6
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
]

a = Analysis(
    ["dictify/__main__.py"],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Dictify",
    console=False,
    icon="assets/Dictify.icns" if mac else "assets/Dictify.ico",
    target_arch="arm64" if mac else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Dictify")

if mac:
    app = BUNDLE(
        coll,
        name="Dictify.app",
        icon="assets/Dictify.icns",
        bundle_identifier="io.github.smeshidojoe.dictify",
        version=__version__,
        info_plist={
            "CFBundleName": "Dictify",
            "CFBundleDisplayName": "Dictify",
            "CFBundleShortVersionString": __version__,
            "LSMinimumSystemVersion": "13.5",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.productivity",
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "Audio or video",
                    "CFBundleTypeRole": "Viewer",
                    "LSHandlerRank": "Alternate",
                    "LSItemContentTypes": ["public.audio", "public.movie", "public.audiovisual-content"],
                }
            ],
        },
    )
