from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Segment:
    start: float
    end: float
    text: str


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
