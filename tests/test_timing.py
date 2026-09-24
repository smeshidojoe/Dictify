import numpy as np

from dictify.audio import SAMPLE_RATE
from dictify.model import Segment, Word
from dictify.timing import snap_word_starts, voiced_frames


def tone(seconds: float, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def silence(seconds: float) -> np.ndarray:
    rng = np.random.default_rng(0)
    return (rng.standard_normal(int(seconds * SAMPLE_RATE)) * 1e-4).astype(np.float32)


def test_word_after_pause_starts_when_sound_resumes():
    # speech 0-1 s, pause 1-2 s, speech 2-3 s
    audio = np.concatenate([tone(1.0), silence(1.0), tone(1.0)])
    # Whisper-style timing: the second word starts where the first one ended
    seg = Segment(0.0, 3.0, "one two", [Word(0.0, 1.0, 0), Word(1.0, 3.0, 4)])
    snap_word_starts([seg], voiced_frames(audio))
    assert seg.words[0].start == 0.0
    assert 1.9 < seg.words[1].start < 2.01


def test_segment_start_follows_first_word():
    audio = np.concatenate([silence(1.5), tone(1.0), silence(0.5)])
    seg = Segment(0.5, 2.6, "hello", [Word(0.5, 2.5, 0)])
    snap_word_starts([seg], voiced_frames(audio))
    assert 1.4 < seg.start == seg.words[0].start < 1.51


def test_no_change_without_quiet_background():
    audio = tone(3.0)  # constant sound: nothing to snap to
    assert voiced_frames(audio) is None
    seg = Segment(0.0, 3.0, "one two", [Word(0.0, 1.0, 0), Word(1.0, 3.0, 4)])
    snap_word_starts([seg], voiced_frames(audio))
    assert seg.words[1].start == 1.0


def test_silent_word_is_left_alone():
    audio = np.concatenate([tone(1.0), silence(2.0)])
    seg = Segment(0.0, 3.0, "one two", [Word(0.0, 1.0, 0), Word(1.0, 3.0, 4)])
    snap_word_starts([seg], voiced_frames(audio))
    assert seg.words[1].start == 1.0
