"""Decodes any audio/video file to 16 kHz mono float32 using PyAV (bundled FFmpeg)."""
from __future__ import annotations

from typing import Callable

import numpy as np

from dictify.errors import Cancelled, NoAudioError

SAMPLE_RATE = 16000


def load_audio(
    path: str,
    on_progress: Callable[[float], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> np.ndarray:
    import av

    try:
        return _decode(av, path, on_progress, is_cancelled)
    except av.error.FFmpegError as e:
        raise NoAudioError(str(e)) from e


def _decode(av, path, on_progress, is_cancelled) -> np.ndarray:
    chunks: list[np.ndarray] = []
    with av.open(path, metadata_errors="ignore") as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise NoAudioError(path)
        total = _duration_seconds(container, stream)
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        for n, frame in enumerate(container.decode(stream)):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray())
            if n % 200 == 0:
                if is_cancelled and is_cancelled():
                    raise Cancelled()
                if on_progress and total and frame.time is not None:
                    on_progress(min(1.0, frame.time / total))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray())

    if not chunks:
        raise NoAudioError(path)
    audio = np.concatenate(chunks, axis=1).reshape(-1)
    return audio.astype(np.float32) / 32768.0


def _duration_seconds(container, stream) -> float:
    if stream.duration is not None and stream.time_base is not None:
        return float(stream.duration * stream.time_base)
    if container.duration is not None:
        return container.duration / 1_000_000
    return 0.0


def probe_duration(path: str) -> float:
    """Container duration in seconds without decoding (0 when unknown)."""
    import av

    try:
        with av.open(path, metadata_errors="ignore") as container:
            stream = next((s for s in container.streams if s.type == "audio"), None)
            return _duration_seconds(container, stream) if stream else 0.0
    except av.error.FFmpegError:
        return 0.0
