"""Whisper backends: faster-whisper (Windows/Linux/Intel Mac) and mlx-whisper (Apple Silicon)."""
from __future__ import annotations

import contextlib
import io
import logging
import os
import re
import sys
import types
from pathlib import Path
from typing import Callable

import numpy as np

from dictify import align
from dictify.audio import SAMPLE_RATE
from dictify.catalog import backend
from dictify.errors import Cancelled
from dictify.model import Segment, build_words

log = logging.getLogger(__name__)

# report(stage, fraction): stage is "load" or "transcribe"; fraction < 0 means indeterminate.
Report = Callable[[str, float], None]
OnSegment = Callable[[Segment], None]
IsCancelled = Callable[[], bool]


class FasterEngine:
    """CTranslate2 backend. Uses CUDA when the NVIDIA libraries are present, CPU otherwise."""

    def __init__(self) -> None:
        self._model = None
        self._key: tuple | None = None
        self._cuda_broken = False
        self.device = ""

    def transcribe(
        self,
        audio: np.ndarray,
        model_dir: Path,
        language: str | None,
        *,
        vad: bool = True,
        device: str = "auto",
        report: Report,
        on_segment: OnSegment,
        is_cancelled: IsCancelled,
    ) -> tuple[list[Segment], str | None]:
        for dev in self._devices(device):
            emitted: list[Segment] = []
            try:
                lang = self._run(dev, audio, model_dir, language, vad, report, emitted, on_segment, is_cancelled)
                self.device = dev
                return emitted, lang
            except Cancelled:
                raise
            except Exception:
                # Missing cuBLAS/cuDNN only shows up at inference time; retry on CPU.
                if dev == "cuda" and not emitted:
                    log.warning("CUDA transcription failed, falling back to CPU", exc_info=True)
                    self._cuda_broken = True
                    self._model = self._key = None
                    continue
                raise
        raise RuntimeError("No usable compute device")

    def _devices(self, preference: str) -> list[str]:
        if preference == "cpu" or self._cuda_broken:
            return ["cpu"]
        _add_cuda_dll_dirs()
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return ["cuda", "cpu"]
        return ["cpu"]

    def warm(self, model_dir: Path, device: str = "auto") -> None:
        """Loads the model ahead of the first job, so starting a transcription is instant."""
        for dev in self._devices(device):
            try:
                model = self._load(model_dir, dev)
                if dev == "cuda":
                    # Missing cuBLAS/cuDNN only shows up at inference time: find out now,
                    # not in the first job (which would then load the model again on CPU).
                    model.detect_language(np.zeros(SAMPLE_RATE, dtype=np.float32))
                return
            except Exception:
                if dev != "cuda":
                    raise
                log.warning("CUDA is not usable, preloading on CPU", exc_info=True)
                self._cuda_broken = True
                self._model = self._key = None

    def _run(self, device, audio, model_dir, language, vad, report, emitted, on_segment, is_cancelled):
        if self._key != (str(model_dir), device):
            report("load", -1)
        model = self._load(model_dir, device)
        if is_cancelled():
            raise Cancelled()
        report("transcribe", 0.0)
        segments, info = model.transcribe(
            audio,
            language=language,
            beam_size=5,
            vad_filter=vad,
            vad_parameters={"min_silence_duration_ms": 500},
            word_timestamps=True,
            condition_on_previous_text=False,  # keeps one badly decoded window from setting the style
        )
        duration = info.duration or len(audio) / SAMPLE_RATE
        for seg in segments:
            if is_cancelled():
                raise Cancelled()
            s = _segment(seg.start, seg.end, seg.text, [(w.word, w.start, w.end) for w in seg.words or []])
            if s.text:
                emitted.append(s)
                on_segment(s)
            report("transcribe", min(1.0, seg.end / duration) if duration else -1)
        return info.language

    def _load(self, model_dir: Path, device: str):
        key = (str(model_dir), device)
        if self._key != key:
            from faster_whisper import WhisperModel

            self._model = None
            log.info("Loading %s on %s", model_dir, device)
            self._model = WhisperModel(
                str(model_dir),
                device=device,
                compute_type="float16" if device == "cuda" else "int8",
                cpu_threads=max(4, (os.cpu_count() or 4) // 2),
            )
            self._key = key
        return self._model


class MlxEngine:
    """Apple Silicon backend running Whisper on the Metal GPU via MLX."""

    device = "gpu"

    def transcribe(
        self,
        audio: np.ndarray,
        model_dir: Path,
        language: str | None,
        *,
        report: Report,
        on_segment: OnSegment,
        is_cancelled: IsCancelled,
        **_ignored,
    ) -> tuple[list[Segment], str | None]:
        _, mlx_whisper, transcribe_module = self._modules()
        holder = transcribe_module.ModelHolder
        if holder.model is None or holder.model_path != str(model_dir):
            report("load", -1)

        class ProgressBar:
            # Stands in for tqdm inside mlx_whisper to get progress and a cancellation point.
            def __init__(self, total=None, **_kw):
                self.total = total or 1
                self.n = 0
                report("transcribe", 0.0)

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def update(self, n):
                self.n += n
                report("transcribe", min(1.0, self.n / self.total))
                if is_cancelled():
                    raise Cancelled()

        transcribe_module.tqdm = types.SimpleNamespace(tqdm=ProgressBar)
        if is_cancelled():
            raise Cancelled()

        # With verbose=True mlx_whisper prints each finished segment; parse those lines to
        # show text while the file is still being transcribed.
        stream = _SegmentStream(on_segment)
        with contextlib.redirect_stdout(stream):
            result = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=str(model_dir),
                language=language,
                verbose=True,
                word_timestamps=True,
                condition_on_previous_text=False,
            )
        segments = []
        for raw in result.get("segments", []):
            pieces = [(w["word"], w["start"], w["end"]) for w in raw.get("words", [])]
            s = _segment(raw["start"], raw["end"], raw["text"], pieces)
            if s.text:
                segments.append(s)
        return segments, result.get("language")

    def warm(self, model_dir: Path, device: str = "auto") -> None:
        """Loads the model ahead of the first job (mlx_whisper keeps it in ModelHolder)."""
        mx, _, transcribe_module = self._modules()
        transcribe_module.ModelHolder.get_model(str(model_dir), mx.float16)

    def _modules(self):
        _stub_word_timing_deps()
        import importlib

        import mlx.core as mx
        import mlx_whisper

        if self.device == "gpu" and not mx.metal.is_available():
            log.warning("Metal is not available, running MLX on the CPU")
            mx.set_default_device(mx.cpu)
            self.device = "cpu"
        # mlx_whisper.transcribe is the function; the module holding ModelHolder and tqdm is here:
        transcribe_module = importlib.import_module("mlx_whisper.transcribe")
        timing_module = importlib.import_module("mlx_whisper.timing")
        timing_module.dtw = align.dtw
        timing_module.median_filter = align.median_filter
        return mx, mlx_whisper, transcribe_module


def _segment(start: float, end: float, text: str, pieces: list[tuple[str, float, float]]) -> Segment:
    joined, words = build_words(pieces)
    if words:
        for w in words:  # word times occasionally spill past their segment
            w.start = min(max(w.start, start), end)
        return Segment(float(start), float(end), joined, words)
    return Segment(float(start), float(end), text.strip())


_LINE = re.compile(r"^\[((?:\d+:)?\d+:\d+\.\d+) --> ((?:\d+:)?\d+:\d+\.\d+)\]\s?(.*)$")


def _parse_ts(value: str) -> float:
    seconds = 0.0
    for part in value.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


class _SegmentStream(io.TextIOBase):
    """stdout replacement that turns mlx_whisper's verbose lines into preview segments."""

    def __init__(self, on_segment: OnSegment):
        self._on_segment = on_segment
        self._buffer = ""

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            m = _LINE.match(line.strip())
            if m and m.group(3).strip():
                self._on_segment(Segment(_parse_ts(m.group(1)), _parse_ts(m.group(2)), m.group(3).strip()))
        return len(text)


def create_engine():
    return MlxEngine() if backend() == "mlx" else FasterEngine()


def _stub_word_timing_deps() -> None:
    """mlx_whisper imports numba and scipy at module level for word timestamps. The app
    bundle leaves them out (~200 MB): these stand-ins satisfy the imports, and the two
    functions that need them are replaced with dictify.align."""
    import importlib.util

    if "numba" not in sys.modules and importlib.util.find_spec("numba") is None:
        numba = types.ModuleType("numba")

        def jit(*args, **kwargs):
            if len(args) == 1 and callable(args[0]) and not kwargs:
                return args[0]
            return lambda fn: fn

        numba.jit = jit
        sys.modules["numba"] = numba
    if "scipy" not in sys.modules and importlib.util.find_spec("scipy") is None:
        scipy = types.ModuleType("scipy")
        scipy.signal = types.ModuleType("scipy.signal")
        sys.modules["scipy"] = scipy
        sys.modules["scipy.signal"] = scipy.signal


_cuda_dirs_added = False


def _add_cuda_dll_dirs() -> None:
    """Make pip-installed NVIDIA runtime libraries (nvidia-cublas-cu12, nvidia-cudnn-cu12)
    visible to CTranslate2 on Windows."""
    global _cuda_dirs_added
    if _cuda_dirs_added or sys.platform != "win32":
        return
    _cuda_dirs_added = True
    import site

    roots = [Path(p) for p in site.getsitepackages()]
    if getattr(sys, "frozen", False):
        roots.append(Path(getattr(sys, "_MEIPASS", "")))
    for root in roots:
        for bin_dir in (root / "nvidia").glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
