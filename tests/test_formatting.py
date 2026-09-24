from dictify.formatting import (
    MODE_SEGMENTS,
    ViewOptions,
    fmt_srt_time,
    fmt_time,
    paragraphs,
    to_markdown,
    to_srt,
    to_text,
)
from dictify.model import Segment, Transcript


def test_fmt_time():
    assert fmt_time(0) == "00:00"
    assert fmt_time(84.9) == "01:24"
    assert fmt_time(3725) == "1:02:05"
    assert fmt_time(65, hours=True) == "0:01:05"
    assert fmt_srt_time(3725.5) == "01:02:05,500"
    assert fmt_srt_time(0.0004) == "00:00:00,000"


def test_paragraph_breaks_on_pause(transcript):
    assert paragraphs(transcript, pause=2.0, max_chars=700) == [[0, 1], [2, 3]]
    assert paragraphs(transcript, pause=10.0, max_chars=700) == [[0, 1, 2, 3]]


def test_paragraph_breaks_on_length_at_sentence_end():
    segs = [Segment(i, i + 1, f"Sentence number {i}.") for i in range(10)]
    t = Transcript("a.mp3", segs, duration=10)
    groups = paragraphs(t, pause=5, max_chars=40)
    assert all(len(g) <= 3 for g in groups)
    assert sum(len(g) for g in groups) == 10


def test_empty_segments_skipped(transcript):
    transcript.segments[1].text = "  "
    out = to_text(transcript, ViewOptions(timestamps=False))
    assert "Tell me" not in out
    assert to_srt(transcript).count("-->") == 3


def test_text_transcript_mode(transcript):
    out = to_text(transcript, ViewOptions())
    assert out == (
        "[00:00 – 00:08]\nHello and welcome. Tell me about yourself.\n\n"
        "[00:12 – 00:20]\nI love working with people. I was a teacher.\n"
    )


def test_text_plain_no_timestamps(transcript):
    out = to_text(transcript, ViewOptions(timestamps=False))
    assert out == "Hello and welcome. Tell me about yourself.\n\nI love working with people. I was a teacher.\n"


def test_text_segments_mode(transcript):
    out = to_text(transcript, ViewOptions(mode=MODE_SEGMENTS, end_times=False))
    assert out.splitlines() == [
        "[00:00] Hello and welcome.",
        "[00:04] Tell me about yourself.",
        "[00:12] I love working with people.",
        "[00:16] I was a teacher.",
    ]


def test_markdown(transcript):
    transcript.segments[0].text = "Use *stars* here."
    md = to_markdown(transcript, ViewOptions(mode=MODE_SEGMENTS, end_times=False))
    assert md.startswith("# interview\n")
    assert r"**[00:00]** Use \*stars\* here." in md


def test_srt(transcript):
    srt = to_srt(transcript)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:04,000\nHello and welcome.\n")
    assert "4\n00:00:16,100 --> 00:00:20,000\nI was a teacher.\n" in srt


def test_hours_format_for_long_media(transcript):
    transcript.duration = 4000
    assert to_text(transcript, ViewOptions(end_times=False)).startswith("[0:00:00]")
