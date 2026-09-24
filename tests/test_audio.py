import wave

import numpy as np
import pytest

from dictify.audio import SAMPLE_RATE, load_audio
from dictify.errors import Cancelled, NoAudioError


def write_wav(path, seconds=2.0, rate=44100, channels=2):
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    tone = (np.sin(2 * np.pi * 440 * t) * 0.5 * 32767).astype(np.int16)
    data = np.repeat(tone[:, None], channels, axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


def test_resamples_to_16k_mono(tmp_path):
    path = tmp_path / "tone.wav"
    write_wav(path)
    audio = load_audio(str(path))
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert abs(len(audio) - 2 * SAMPLE_RATE) < 200
    assert 0.3 < np.abs(audio).max() <= 1.0


def test_encoded_container(tmp_path):
    import av

    src = tmp_path / "tone.wav"
    write_wav(src, seconds=1.0, rate=48000, channels=1)
    dst = tmp_path / "tone.m4a"
    with av.open(str(src)) as inp, av.open(str(dst), "w") as out:
        stream = out.add_stream("aac", rate=48000)
        for frame in inp.decode(audio=0):
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    audio = load_audio(str(dst))
    assert abs(len(audio) / SAMPLE_RATE - 1.0) < 0.1


def test_not_media(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    with pytest.raises(NoAudioError):
        load_audio(str(path))


def test_cancel(tmp_path):
    path = tmp_path / "tone.wav"
    write_wav(path)
    with pytest.raises(Cancelled):
        load_audio(str(path), is_cancelled=lambda: True)
