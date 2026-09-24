"""Turns a Transcript into display blocks and plain-text formats (TXT, Markdown, SRT)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dictify.model import Transcript

MODE_TRANSCRIPT = "transcript"
MODE_SEGMENTS = "segments"

# Soft limit of characters per paragraph in transcript mode.
PARAGRAPH_SIZES = {"short": 300, "medium": 700, "long": 1500}
SENTENCE_END = (".", "!", "?", "…", '."', '?"', '!"', "»")


@dataclass
class ViewOptions:
    mode: str = MODE_TRANSCRIPT
    timestamps: bool = True
    end_times: bool = True
    pause: float = 2.0
    paragraph: str = "medium"
    font_size: int = 15


@dataclass
class Block:
    label: str | None  # timestamp label, None when timestamps are hidden
    items: list[int]  # segment indexes


def fmt_time(seconds: float, hours: bool = False) -> str:
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h or hours:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fmt_srt_time(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def paragraphs(t: Transcript, pause: float, max_chars: int) -> list[list[int]]:
    """Groups visible segments into paragraphs: break on long pauses,
    or at a sentence end once the paragraph is long enough."""
    groups: list[list[int]] = []
    cur: list[int] = []
    length = 0
    for i in t.visible():
        seg = t.segments[i]
        if cur:
            prev = t.segments[cur[-1]]
            gap = seg.start - prev.end
            long_enough = length >= max_chars and prev.text.rstrip().endswith(SENTENCE_END)
            if gap >= pause or long_enough or length >= max_chars * 2:
                groups.append(cur)
                cur, length = [], 0
        cur.append(i)
        length += len(seg.text) + 1
    if cur:
        groups.append(cur)
    return groups


def blocks(t: Transcript, opts: ViewOptions) -> list[Block]:
    hours = t.duration >= 3600

    def label(first: int, last: int) -> str | None:
        if not opts.timestamps:
            return None
        start = fmt_time(t.segments[first].start, hours)
        if not opts.end_times:
            return start
        return f"{start} – {fmt_time(t.segments[last].end, hours)}"

    if opts.mode == MODE_SEGMENTS:
        return [Block(label(i, i), [i]) for i in t.visible()]
    max_chars = PARAGRAPH_SIZES.get(opts.paragraph, PARAGRAPH_SIZES["medium"])
    return [Block(label(g[0], g[-1]), g) for g in paragraphs(t, opts.pause, max_chars)]


def block_text(t: Transcript, block: Block) -> str:
    return " ".join(t.segments[i].text.strip() for i in block.items)


def to_text(t: Transcript, opts: ViewOptions) -> str:
    lines = []
    for b in blocks(t, opts):
        text = block_text(t, b)
        if b.label is None:
            lines.append(text)
        elif opts.mode == MODE_SEGMENTS:
            lines.append(f"[{b.label}] {text}")
        else:
            lines.append(f"[{b.label}]\n{text}")
    sep = "\n" if opts.mode == MODE_SEGMENTS else "\n\n"
    return sep.join(lines) + "\n" if lines else ""


def to_markdown(t: Transcript, opts: ViewOptions) -> str:
    out = [f"# {Path(t.media_path).stem}", ""]
    for b in blocks(t, opts):
        text = _md_escape(block_text(t, b))
        if b.label is None:
            out.append(text)
        elif opts.mode == MODE_SEGMENTS:
            out.append(f"**[{b.label}]** {text}")
        else:
            out.append(f"**{b.label}**  \n{text}")
        out.append("")
    return "\n".join(out)


def to_srt(t: Transcript) -> str:
    out = []
    for n, i in enumerate(t.visible(), 1):
        seg = t.segments[i]
        out.append(f"{n}\n{fmt_srt_time(seg.start)} --> {fmt_srt_time(seg.end)}\n{seg.text.strip()}\n")
    return "\n".join(out)


def _md_escape(text: str) -> str:
    # Only escape what would visibly break rendering of spoken text.
    for ch in ("\\", "*", "_", "`"):
        text = text.replace(ch, "\\" + ch)
    return text
