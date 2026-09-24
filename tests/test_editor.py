from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

from dictify.formatting import MODE_SEGMENTS, MODE_TRANSCRIPT, ViewOptions
from dictify.ui.editor import TranscriptEditor


def make(qapp, transcript, **opts):
    ed = TranscriptEditor()
    ed.resize(800, 600)
    ed.set_transcript(transcript, ViewOptions(**opts))
    ed.set_editing(True)
    ed.show()
    return ed


def move_to(ed, needle, offset=0):
    pos = ed.toPlainText().index(needle) + offset
    c = ed.textCursor()
    c.setPosition(pos)
    ed.setTextCursor(c)
    return pos


def test_render_transcript_mode(qapp, transcript):
    ed = make(qapp, transcript)
    # two paragraphs split by the 4 s pause, no timestamps
    assert ed.toPlainText().splitlines() == [
        "Hello and welcome. Tell me about yourself.",
        "I love working with people. I was a teacher.",
    ]


def test_render_segments_mode(qapp, transcript):
    ed = make(qapp, transcript, mode=MODE_SEGMENTS, end_times=False)
    assert ed.toPlainText().splitlines()[0] == "00:00\tHello and welcome."
    assert len(ed.toPlainText().splitlines()) == 4


def test_typing_updates_segment(qapp, transcript):
    ed = make(qapp, transcript)
    move_to(ed, "welcome", len("welcome"))
    QTest.keyClicks(ed, " everyone")
    ed.sync()
    assert transcript.segments[0].text == "Hello and welcome everyone."
    assert transcript.segments[1].text == "Tell me about yourself."


def test_typing_at_segment_start_after_timestamp(qapp, transcript):
    ed = make(qapp, transcript, mode=MODE_SEGMENTS)
    move_to(ed, "Tell")
    QTest.keyClicks(ed, "So, ")
    ed.sync()
    assert transcript.segments[1].text == "So, Tell me about yourself."
    assert ed.toPlainText().splitlines()[1].startswith("00:04 – 00:08\t")


def test_first_segment_editable(qapp, transcript):
    ed = make(qapp, transcript)
    move_to(ed, "Hello")
    QTest.keyClicks(ed, "Oh. ")
    ed.sync()
    assert transcript.segments[0].text == "Oh. Hello and welcome."


def test_timestamp_protected(qapp, transcript):
    ed = make(qapp, transcript, mode=MODE_SEGMENTS)
    before = ed.toPlainText()
    move_to(ed, "00:12", 2)
    QTest.keyClicks(ed, "x")
    QTest.keyClick(ed, Qt.Key.Key_Backspace)
    QTest.keyClick(ed, Qt.Key.Key_Delete)
    assert ed.toPlainText() == before


def test_cannot_merge_blocks(qapp, transcript):
    ed = make(qapp, transcript)
    before = ed.toPlainText()
    move_to(ed, "I love")
    QTest.keyClick(ed, Qt.Key.Key_Backspace)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    move_to(ed, "yourself.", len("yourself."))
    QTest.keyClick(ed, Qt.Key.Key_Delete)
    assert ed.toPlainText() == before


def test_delete_across_segments_in_paragraph(qapp, transcript):
    ed = make(qapp, transcript)
    start = move_to(ed, "welcome")
    c = ed.textCursor()
    c.setPosition(start + len("welcome. Tell"), QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(c)
    QTest.keyClick(ed, Qt.Key.Key_Delete)
    ed.sync()
    assert transcript.segments[0].text == "Hello and"
    assert transcript.segments[1].text == "me about yourself."


def test_selection_across_paragraphs_not_deleted(qapp, transcript):
    ed = make(qapp, transcript)
    before = ed.toPlainText()
    start = move_to(ed, "yourself")
    c = ed.textCursor()
    c.setPosition(before.index("I love") + 3, QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(c)
    QTest.keyClicks(ed, "z")
    QTest.keyClick(ed, Qt.Key.Key_Backspace)
    assert ed.toPlainText() == before


def test_paste_flattens_newlines(qapp, transcript):
    from PySide6.QtCore import QMimeData

    ed = make(qapp, transcript)
    move_to(ed, "teacher", len("teacher"))
    md = QMimeData()
    md.setText(" of\n\nmath")
    ed.insertFromMimeData(md)
    ed.sync()
    assert transcript.segments[3].text == "I was a teacher of math."
    assert ed.document().blockCount() == 2


def test_emptied_segment_disappears_after_rerender(qapp, transcript):
    ed = make(qapp, transcript, mode=MODE_SEGMENTS, timestamps=False)
    move_to(ed, "Tell")
    c = ed.textCursor()
    c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(c)
    QTest.keyClick(ed, Qt.Key.Key_Delete)
    ed.render(ViewOptions(mode=MODE_TRANSCRIPT))
    assert transcript.segments[1].text == ""
    assert "Tell" not in ed.toPlainText()


def test_seg_at_and_highlight(qapp, transcript):
    ed = make(qapp, transcript, mode=MODE_SEGMENTS)
    text = ed.toPlainText()
    assert ed.seg_at(text.index("people")) == 2
    assert ed.seg_at(text.index("00:12")) == 2  # timestamp maps to the segment it labels
    assert ed.offset_in_segment(2, text.index("00:12")) == 0
    assert ed.offset_in_segment(2, text.index("people")) == len("I love working with ")
    assert ed.seg_at(0) == 0
    assert ed.set_current(3) is True
    assert ed.set_current(3) is False
    assert len(ed.extraSelections()) == 1


def test_search(qapp, transcript):
    ed = make(qapp, transcript)
    counts = []
    ed.searchChanged.connect(lambda i, n: counts.append((i, n)))
    ed.search("i")
    assert counts[-1][1] > 3
    ed.search("teacher")
    assert counts[-1] == (0, 1)
    ed.search("nothing-here")
    assert counts[-1] == (-1, 0)


def test_read_mode_space_toggles_play(qapp, transcript):
    ed = make(qapp, transcript)
    ed.set_editing(False)
    fired = []
    ed.togglePlay.connect(lambda: fired.append(1))
    before = ed.toPlainText()
    QTest.keyClick(ed, Qt.Key.Key_Space)
    assert fired == [1]
    assert ed.toPlainText() == before


def test_undo_restores_edit(qapp, transcript):
    ed = make(qapp, transcript)
    before = ed.toPlainText()
    move_to(ed, "teacher", len("teacher"))
    QTest.keyClicks(ed, "abc")
    ed.undo()
    assert ed.toPlainText() == before


def test_click_emits_segment_and_offset(qapp, transcript):
    from PySide6.QtCore import QPoint

    ed = make(qapp, transcript)
    ed.set_editing(False)
    got = []
    ed.seekRequested.connect(lambda sid, off: got.append((sid, off)))
    c = QTextCursor(ed.document())
    c.setPosition(ed.toPlainText().index("people") + 2)
    point = ed.cursorRect(c).center()
    QTest.mouseClick(ed.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    assert got and got[0][0] == 2
    assert abs(got[0][1] - (len("I love working with ") + 2)) <= 1


def test_edit_drops_word_timings_of_that_segment(qapp, transcript):
    from dictify.model import Word

    transcript.segments[0].words = [Word(0.0, 1.0, 0)]
    transcript.segments[1].words = [Word(4.2, 5.0, 0)]
    ed = make(qapp, transcript)
    move_to(ed, "welcome", len("welcome"))
    QTest.keyClicks(ed, "!")
    ed.sync()
    assert transcript.segments[0].words == []
    assert transcript.segments[1].words != []


def test_highlights_current_word(qapp, transcript):
    from dictify.model import build_words

    text, words = build_words([(" I", 12.0, 12.2), (" love", 12.2, 12.6), (" working", 12.6, 13.0),
                               (" with", 13.0, 13.2), (" people.", 13.2, 14.0)])
    transcript.segments[2].text, transcript.segments[2].words = text, words
    ed = make(qapp, transcript)
    ed.set_editing(False)
    plain = ed.toPlainText()

    def marked():
        a, b = ed._word
        return plain[a:b]

    assert ed.set_current(2, 1) is True
    assert marked() == "love" and not ed.extraSelections()
    rects = ed._range_rects(*ed._word)
    assert len(rects) == 1 and rects[0].width() > 10
    ed.set_current(2, 4)
    assert marked() == "people."
    # no word timings -> whole segment
    ed.set_current(3, None)
    assert ed.extraSelections()[0].cursor.selectedText().strip() == "I was a teacher."
