from dictify.model import Segment, Transcript, build_words


def make_transcript():
    a_text, a_words = build_words([(" Hello", 0.5, 0.9), (" there.", 1.0, 1.6)])
    b_text, b_words = build_words([(" How", 4.0, 4.3), (" are", 4.35, 4.6), (" you?", 4.7, 5.2)])
    # Whisper often starts a segment before its first word (here at 2.0 instead of 4.0).
    return Transcript("/tmp/a.mp3", [Segment(0.5, 1.6, a_text, a_words), Segment(2.0, 5.2, b_text, b_words)],
                      "en", 6.0, "tiny")


def workspace(qapp):
    from dictify.ui.workspace import Workspace

    ws = Workspace()
    ws.resize(900, 600)
    ws.path = "/tmp/a.mp3"
    ws.set_transcript(make_transcript())
    return ws


def test_pause_keeps_last_spoken_word(qapp):
    ws = workspace(qapp)
    ws._on_position(0.7)
    assert ws.editor._current_key == (0, 0)
    ws._on_position(1.2)
    assert ws.editor._current_key == (0, 1)
    # silence between the segments: still "there.", not the unspoken "How"
    for t in (1.7, 2.5, 3.9):
        ws._on_position(t)
        assert ws.editor._current_key == (0, 1), t
    ws._on_position(4.05)
    assert ws.editor._current_key == (1, 0)


def test_clicked_word_is_shown_during_lead_in(qapp):
    ws = workspace(qapp)
    ws.player.toggle = lambda: None  # no real playback in tests
    ws._seek_to(1, ws.t.segments[1].text.index("are"))
    assert ws.editor._current_key == (1, 1)
    ws._on_position(4.3)  # playback starts a moment before the word
    assert ws.editor._current_key == (1, 1)
    ws._on_position(4.8)
    assert ws.editor._current_key == (1, 2)


def test_before_first_word_nothing_is_highlighted(qapp):
    ws = workspace(qapp)
    ws._on_position(0.1)
    assert ws.editor._current_key == (None, None)
