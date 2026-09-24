"""The MLX backend only runs on Apple Silicon; these tests exercise its glue code
against a fake mlx_whisper that mirrors the real package layout."""
import sys
import types

import numpy as np
import pytest

from dictify.errors import Cancelled


@pytest.fixture
def fake_mlx(monkeypatch):
    module = types.ModuleType("mlx_whisper.transcribe")
    module.tqdm = types.SimpleNamespace(tqdm=None)  # replaced by the engine
    calls = {}

    def transcribe(audio, path_or_hf_repo, language=None, verbose=None, word_timestamps=False, **kw):
        calls.update(path=path_or_hf_repo, language=language, verbose=verbose, words=word_timestamps,
                     dtw=timing.dtw, median_filter=timing.median_filter)
        print("Detecting language using up to the first 30 seconds.")
        with module.tqdm.tqdm(total=300, unit="frames", disable=verbose is not False) as bar:
            for _ in range(3):
                bar.update(100)
            print("[00:00.000 --> 00:01.500]  Привет.")
            print("[01:02:03.250 --> 01:02:04.000] Как дела?")
        return {
            "language": language or "ru",
            "segments": [
                {"start": 0.0, "end": 1.5, "text": " Привет. ",
                 "words": [{"word": " Привет.", "start": 0.1, "end": 1.2}]},
                {"start": 1.5, "end": 2.0, "text": "   "},
                {"start": 2.0, "end": 3.0, "text": "Как дела?",
                 "words": [{"word": " Как", "start": 2.0, "end": 2.4}, {"word": " дела?", "start": 2.5, "end": 3.1}]},
            ],
        }

    module.transcribe = transcribe
    package = types.ModuleType("mlx_whisper")
    package.transcribe = transcribe  # like the real package: the function shadows the submodule
    monkeypatch.setitem(sys.modules, "mlx_whisper", package)
    monkeypatch.setitem(sys.modules, "mlx_whisper.transcribe", module)
    timing = types.ModuleType("mlx_whisper.timing")
    monkeypatch.setitem(sys.modules, "mlx_whisper.timing", timing)

    core = types.ModuleType("mlx.core")
    core.metal = types.SimpleNamespace(is_available=lambda: calls.get("metal", True))
    core.cpu = "cpu"
    core.set_default_device = lambda d: calls.update(default_device=d)
    mlx = types.ModuleType("mlx")
    mlx.core = core
    monkeypatch.setitem(sys.modules, "mlx", mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", core)
    return calls


def test_mlx_engine_reports_progress_and_segments(fake_mlx, tmp_path):
    from dictify.engines import MlxEngine

    progress, emitted = [], []
    segs, lang = MlxEngine().transcribe(
        np.zeros(16000, dtype=np.float32),
        tmp_path,
        None,
        report=lambda stage, f: progress.append((stage, round(f, 2))),
        on_segment=emitted.append,
        is_cancelled=lambda: False,
    )
    from dictify import align

    assert lang == "ru"
    assert [s.text for s in segs] == ["Привет.", "Как дела?"]
    # streamed previews parsed from verbose output, including hour timestamps
    assert [(s.start, s.text) for s in emitted] == [(0.0, "Привет."), (3723.25, "Как дела?")]
    assert [w.offset for w in segs[1].words] == [0, 4]
    assert segs[1].words[1].start == 2.5
    assert segs[1].words[1].end == 3.1
    assert fake_mlx["words"] is True
    assert fake_mlx["dtw"] is align.dtw and fake_mlx["median_filter"] is align.median_filter
    assert progress[0] == ("load", -1)
    assert progress[-1] == ("transcribe", 1.0)
    assert ("transcribe", 0.33) in progress
    assert fake_mlx["path"] == str(tmp_path)


def test_mlx_engine_cancel(fake_mlx, tmp_path):
    from dictify.engines import MlxEngine

    ticks = []

    def cancelled():
        ticks.append(1)
        return len(ticks) > 2

    with pytest.raises(Cancelled):
        MlxEngine().transcribe(
            np.zeros(10, dtype=np.float32), tmp_path, "en",
            report=lambda *_: None, on_segment=lambda _: None, is_cancelled=cancelled,
        )


def test_word_timing_stubs(monkeypatch):
    import importlib.util

    from dictify import engines

    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *a: None if name in ("numba", "scipy") else real_find_spec(name, *a))
    monkeypatch.delitem(sys.modules, "numba", raising=False)
    monkeypatch.delitem(sys.modules, "scipy", raising=False)
    monkeypatch.delitem(sys.modules, "scipy.signal", raising=False)
    engines._stub_word_timing_deps()

    import numba
    from scipy import signal  # noqa: F401

    @numba.jit(nopython=True, parallel=True)
    def f(x):
        return x + 1

    @numba.jit
    def g(x):
        return x * 2

    assert f(1) == 2 and g(2) == 4


def test_mlx_engine_falls_back_to_cpu_without_metal(fake_mlx, tmp_path):
    from dictify.engines import MlxEngine

    fake_mlx["metal"] = False
    engine = MlxEngine()
    engine.transcribe(
        np.zeros(10, dtype=np.float32), tmp_path, "en",
        report=lambda *_: None, on_segment=lambda _: None, is_cancelled=lambda: False,
    )
    assert fake_mlx["default_device"] == "cpu"
    assert engine.device == "cpu"
