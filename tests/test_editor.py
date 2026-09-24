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
    text = ed.toPlainText()
    # two paragraphs split by the 4 s pause, each with a timestamp header
    assert text.splitlines() == [
        "00:00 – 00:08",
        "Hello and welcome. Tell me about yourself.",
        "00:12 – 00:20",
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
    ed = make(qapp, transcript)
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
    assert ed.document().blockCount() == 4


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
    ed = make(qapp, transcript)
    text = ed.toPlainText()
    assert ed.seg_at(text.index("people")) == 2
    assert ed.seg_at(text.index("00:12")) == 2  # timestamp maps to the segment it labels
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
