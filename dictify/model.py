from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field

# Start playback slightly before the clicked word so its first sound isn't clipped.
WORD_LEAD_IN = 0.12


@dataclass
class Word:
    start: float
    end: float
    offset: int  # character offset of the word inside Segment.text


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)

    def word_at(self, offset: int) -> int | None:
        """Index of the word containing the character at `offset` (None without word timings)."""
        if not self.words:
            return None
        return max(0, bisect_right([w.offset for w in self.words], offset) - 1)

    def time_at(self, offset: int) -> float:
        """Media time of the character at `offset` in the segment text: the word's own
        timestamp when known, otherwise interpolated across the segment."""
        k = self.word_at(offset)
        if k is not None:
            return max(0.0, self.words[k].start - WORD_LEAD_IN)
        if not self.text:
            return self.start
        share = min(1.0, max(0.0, offset / len(self.text)))
        return self.start + (self.end - self.start) * share


def build_words(pieces: list[tuple[str, float, float]]) -> tuple[str, list[Word]]:
    """Joins Whisper word pieces (which carry their leading space) into segment text,
    remembering where each word starts."""
    text = ""
    words: list[Word] = []
    for piece, start, end in pieces:
        if not text:
            piece = piece.lstrip()
        if not piece.strip():
            continue
        words.append(Word(float(start), float(end), len(text) + len(piece) - len(piece.lstrip())))
        text += piece
    return text.rstrip(), words


@dataclass
class Transcript:
    media_path: str
    segments: list[Segment] = field(default_factory=list)
    language: str | None = None
    duration: float = 0.0
    model: str = ""

    def visible(self) -> list[int]:
        """Indexes of segments that still have text (edits can empty a segment)."""
        return [i for i, s in enumerate(self.segments) if s.text.strip()]

    def word_count(self) -> int:
        return sum(len(s.text.split()) for s in self.segments)
