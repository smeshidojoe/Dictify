from dictify.model import WORD_LEAD_IN, Segment, build_words


def test_build_words_offsets():
    text, words = build_words([(" Hello", 1.0, 1.4), (",", 1.4, 1.5), (" world.", 1.6, 2.0)])
    assert text == "Hello, world."
    assert [w.offset for w in words] == [0, 5, 7]
    assert text[words[2].offset:].startswith("world")


def test_time_at_uses_word_start():
    text, words = build_words([(" one", 10.0, 10.5), (" two", 11.0, 11.5), (" three", 12.0, 12.8)])
    seg = Segment(10.0, 13.0, text, words)
    assert seg.time_at(0) == 10.0
    assert seg.time_at(text.index("two") + 1) == 11.0 - WORD_LEAD_IN
    assert seg.time_at(len(text)) == 12.0 - WORD_LEAD_IN


def test_time_at_interpolates_without_words():
    seg = Segment(10.0, 20.0, "0123456789")
    assert seg.time_at(0) == 10.0
    assert seg.time_at(5) == 15.0
    assert seg.time_at(99) == 20.0
