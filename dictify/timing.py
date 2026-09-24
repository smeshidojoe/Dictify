"""Refines Whisper word timings against the audio itself.

Whisper's word boundaries are contiguous: after a pause, the next word is timed from the
moment the previous one ended, so a player highlighting it would light it up while the
speaker is still silent. Short-time energy shows where sound actually resumes.
"""
from __future__ import annotations

import numpy as np

from dictify.audio import SAMPLE_RATE
from dictify.model import Segment

FRAMES_PER_SECOND = 100
FRAME = SAMPLE_RATE // FRAMES_PER_SECOND  # 10 ms
MIN_CONTRAST_DB = 15.0  # below this there is no clear silence to snap to (music, noise)
ONSET_MARGIN = 0.03  # start a little before the detected onset: soft consonants are quiet
MIN_WORD = 0.06


def voiced_frames(audio: np.ndarray) -> np.ndarray | None:
    """Per 10 ms frame: does it carry sound above the recording's background level?
    None when the recording has no clear quiet/loud contrast, where snapping would guess."""
    n = len(audio) // FRAME
    if n < 50:
        return None
    frames = audio[: n * FRAME].reshape(n, FRAME)
    energy = np.einsum("ij,ij->i", frames, frames) / FRAME
    db = 10 * np.log10(energy + 1e-10)
    quiet, loud = np.percentile(db, [10, 95])
    if loud - quiet < MIN_CONTRAST_DB:
        return None
    voiced = db > quiet + 0.25 * (loud - quiet)
    # A sound has to last 30 ms to count, so clicks and pops don't start a word.
    sustained = np.zeros_like(voiced)
    sustained[:-2] = voiced[:-2] & voiced[1:-1] & voiced[2:]
    return sustained


def snap_word_starts(segments: list[Segment], voiced: np.ndarray | None) -> None:
    """Moves word starts that fall into silence to where the sound begins (in place)."""
    if voiced is None:
        return
    for seg in segments:
        for w in seg.words:
            a = int(w.start * FRAMES_PER_SECOND)
            b = int(w.end * FRAMES_PER_SECOND)
            if a >= len(voiced) or b - a < 4 or voiced[a]:
                continue
            hits = np.flatnonzero(voiced[a:b])
            if hits.size == 0:
                continue
            onset = (a + hits[0]) / FRAMES_PER_SECOND - ONSET_MARGIN
            w.start = max(w.start, min(onset, w.end - MIN_WORD))
        if seg.words:
            seg.start = max(seg.start, min(seg.words[0].start, seg.end))
