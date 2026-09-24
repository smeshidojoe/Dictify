"""Transcript view/editor.

Every character of segment text carries its segment index in a char-format property,
so edits can be mapped back to segments (and clicks to timestamps) no matter how the
text is laid out. Timestamp labels are tagged HEADER and protected from editing.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from collections import defaultdict

from PySide6.QtCore import QMimeData, Qt, QTimer, Signal
from PySide6.QtGui import (
    QFont,
    QFontMetricsF,
    QKeySequence,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
    QTextOption,
)
from PySide6.QtWidgets import QApplication, QFrame, QTextEdit

from dictify.formatting import MODE_SEGMENTS, ViewOptions, blocks
from dictify.model import Transcript
from dictify.ui import theme

SEG = QTextFormat.Property.UserProperty + 1
HEADER = -1
MAX_TEXT_WIDTH = 760
WHOLE_BLOCK = -1  # protection marker: the entire block is a timestamp header


def _sid(fmt: QTextCharFormat) -> int | None:
    value = fmt.property(SEG)
    return value if isinstance(value, int) else None


def _is_text(fmt: QTextCharFormat) -> bool:
    sid = _sid(fmt)
    return sid is not None and sid >= 0


class TranscriptEditor(QTextEdit):
    seekRequested = Signal(int, int)  # segment index, character offset inside the segment
    togglePlay = Signal()
    skip = Signal(float)
    edited = Signal()
    editingChanged = Signal(bool)
    searchChanged = Signal(int, int)  # current hit index, hit count

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Editor")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptRichText(False)
        self.setAcceptDrops(False)
        self.setTabChangesFocus(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(28)

        self._t: Transcript | None = None
        self._opts = ViewOptions()
        self._rendered: list[int] = []
        self._protect: list[tuple[int, str]] = []  # per block: (protected prefix length, text)
        self._index = None
        self._rendering = False
        self._reverting = False
        self._dirty = False
        self._editing = False
        self._current: int | None = None
        self._cur_sels: list = []
        self._search_sels: list = []
        self._query = ""
        self._hits: list[tuple[int, int]] = []
        self._hit = -1
        self._press = None
        self._side = -1

        self.document().contentsChange.connect(self._on_contents_change)
        self._research = QTimer(self, singleShot=True, interval=250, timeout=self._rerun_search)
        self.set_editing(False)

    # ----- content -------------------------------------------------------------

    def set_transcript(self, t: Transcript, opts: ViewOptions) -> None:
        self._t = t
        self._dirty = False
        self._query = ""
        self.render(opts)

    def render(self, opts: ViewOptions) -> None:
        """Rebuilds the document from the model. Pending edits are synced first."""
        if self._t is None:
            return
        self.sync()
        self._opts = opts
        t = self._t
        seg_mode = opts.mode == MODE_SEGMENTS
        scroll = self.verticalScrollBar().value()

        self._rendering = True
        doc = self.document()
        doc.setUndoRedoEnabled(False)
        doc.clear()
        base = QFont(self.font())
        base.setPointSizeF(opts.font_size)
        doc.setDefaultFont(base)

        head_fmt = QTextCharFormat()
        head_fmt.setForeground(theme.c("muted"))
        head_fmt.setFontPointSize(max(8.0, opts.font_size * 0.78))
        head_fmt.setProperty(SEG, HEADER)

        para_fmt = QTextBlockFormat()
        para_fmt.setLineHeight(135, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        para_fmt.setBottomMargin(opts.font_size * (0.5 if seg_mode else 1.0))
        head_block = QTextBlockFormat()
        head_block.setBottomMargin(3)

        bls = blocks(t, opts)
        if seg_mode and opts.timestamps and bls:
            head_font = QFont(base)
            head_font.setPointSizeF(head_fmt.fontPointSize())
            metrics = QFontMetricsF(head_font)
            column = max(metrics.horizontalAdvance(b.label) for b in bls) + opts.font_size * 1.2
            para_fmt.setLeftMargin(column)
            para_fmt.setTextIndent(-column)
            para_fmt.setTabPositions([QTextOption.Tab(column, QTextOption.TabType.LeftTab)])

        cursor = QTextCursor(doc)
        self._protect = []
        self._rendered = []
        first = True

        def new_block(block_fmt, char_fmt):
            nonlocal first
            if first:
                cursor.setBlockFormat(block_fmt)
                cursor.setBlockCharFormat(char_fmt)
                first = False
            else:
                cursor.insertBlock(block_fmt, char_fmt)

        for b in bls:
            if not seg_mode and b.label:
                new_block(head_block, head_fmt)
                cursor.insertText(b.label, head_fmt)
                self._protect.append((WHOLE_BLOCK, b.label))
            new_block(para_fmt, self._text_fmt(b.items[0]))
            prefix = f"{b.label}\t" if seg_mode and b.label else ""
            if prefix:
                cursor.insertText(prefix, head_fmt)
            self._protect.append((len(prefix), prefix))
            for k, i in enumerate(b.items):
                sep = " " if k < len(b.items) - 1 else ""
                cursor.insertText(t.segments[i].text.strip() + sep, self._text_fmt(i))
                self._rendered.append(i)

        doc.setUndoRedoEnabled(True)
        self._rendering = False
        self._index = None
        self._dirty = False
        self._current = None
        self._cur_sels = []
        self.verticalScrollBar().setValue(scroll)
        if self._query:
            self._rerun_search()
        else:
            self._apply_selections()

    def sync(self) -> None:
        """Writes edited text back into the transcript segments."""
        if not self._dirty or self._t is None:
            return
        parts: dict[int, list[str]] = defaultdict(list)
        for frag in self._fragments():
            if _is_text(frag.charFormat()):
                parts[_sid(frag.charFormat())].append(frag.text())
        for i in self._rendered:
            seg = self._t.segments[i]
            text = " ".join("".join(parts.get(i, [])).split())
            if text != seg.text:
                seg.text = text
                seg.words = []  # word offsets no longer match; clicks fall back to interpolation
        self._dirty = False

    def _text_fmt(self, sid: int) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setProperty(SEG, sid)
        return fmt

    def _fragments(self):
        block = self.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    yield frag
                it += 1
            block = block.next()

    def _ensure_index(self):
        if self._index is None:
            starts, ends, sids = [], [], []
            for frag in self._fragments():
                if not _is_text(frag.charFormat()):
                    continue
                sid = _sid(frag.charFormat())
                s = frag.position()
                e = s + frag.length()
                if sids and sids[-1] == sid and ends[-1] == s:
                    ends[-1] = e
                else:
                    starts.append(s)
                    ends.append(e)
                    sids.append(sid)
            ranges: dict[int, list[tuple[int, int]]] = defaultdict(list)
            for s, e, sid in zip(starts, ends, sids):
                ranges[sid].append((s, e))
            self._index = (starts, ends, sids, ranges)
        return self._index

    def seg_at(self, pos: int) -> int | None:
        """Segment under a document position; timestamps map to the segment they label."""
        starts, ends, sids, _ = self._ensure_index()
        if not sids:
            return None
        k = bisect_right(starts, pos) - 1
        if k >= 0 and pos < ends[k]:
            return sids[k]
        if k + 1 < len(sids):
            return sids[k + 1]
        return sids[k]

    def offset_in_segment(self, sid: int, pos: int) -> int:
        """Character offset of document position `pos` within segment `sid`'s text."""
        offset = 0
        for start, end in self._ensure_index()[3].get(sid, []):
            if pos < start:
                break
            if pos < end:
                return offset + pos - start
            offset += end - start
        return offset

    # ----- playback highlight --------------------------------------------------

    def set_current(self, sid: int | None) -> bool:
        if sid == self._current:
            return False
        self._current = sid
        self._cur_sels = []
        if sid is not None:
            fmt = QTextCharFormat()
            fmt.setBackground(theme.c("current"))
            for s, e in self._ensure_index()[3].get(sid, []):
                self._cur_sels.append(self._selection(s, e, fmt))
        self._apply_selections()
        return True

    def scroll_to_current(self) -> None:
        ranges = self._ensure_index()[3].get(self._current) if self._current is not None else None
        if not ranges:
            return
        c = QTextCursor(self.document())
        c.setPosition(ranges[0][0])
        rect = self.cursorRect(c)
        height = self.viewport().height()
        if rect.top() < 0 or rect.bottom() > height:
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() + rect.top() - height // 3)

    def _selection(self, start: int, end: int, fmt: QTextCharFormat):
        sel = QTextEdit.ExtraSelection()
        c = QTextCursor(self.document())
        c.setPosition(start)
        c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        sel.cursor = c
        sel.format = fmt
        return sel

    def _apply_selections(self) -> None:
        self.setExtraSelections(self._cur_sels + self._search_sels)

    # ----- search --------------------------------------------------------------

    def search(self, query: str) -> None:
        self._query = query
        self._hit = -1
        self._rerun_search(reveal=True)

    def search_step(self, delta: int) -> None:
        if not self._hits:
            return
        self._hit = (self._hit + delta) % len(self._hits)
        self._paint_hits()
        self._reveal_hit()

    def _rerun_search(self, reveal: bool = False) -> None:
        self._hits = []
        if self._query:
            doc = self.document()
            c = QTextCursor(doc)
            while True:
                c = doc.find(self._query, c)
                if c.isNull():
                    break
                self._hits.append((c.selectionStart(), c.selectionEnd()))
        if not self._hits:
            self._hit = -1
        elif not 0 <= self._hit < len(self._hits):
            self._hit = 0
        self._paint_hits()
        if reveal:
            self._reveal_hit()

    def _paint_hits(self) -> None:
        normal = QTextCharFormat()
        normal.setBackground(theme.c("search"))
        strong = QTextCharFormat()
        strong.setBackground(theme.c("search_current"))
        self._search_sels = [
            self._selection(s, e, strong if n == self._hit else normal) for n, (s, e) in enumerate(self._hits)
        ]
        self._apply_selections()
        self.searchChanged.emit(self._hit, len(self._hits))

    def _reveal_hit(self) -> None:
        if 0 <= self._hit < len(self._hits):
            c = QTextCursor(self.document())
            c.setPosition(self._hits[self._hit][0])
            self.setTextCursor(c)
            self.ensureCursorVisible()

    # ----- editing -------------------------------------------------------------

    def is_editing(self) -> bool:
        return self._editing

    def set_editing(self, on: bool) -> None:
        self._editing = on
        self.setReadOnly(not on)
        flags = Qt.TextInteractionFlag
        if on:
            self.setTextInteractionFlags(flags.TextEditorInteraction)
            self.setCursorWidth(1)
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.setTextInteractionFlags(flags.TextSelectableByMouse | flags.TextSelectableByKeyboard)
            self.setCursorWidth(0)  # reading mode: selectable, but no blinking caret
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.editingChanged.emit(on)

    def _on_contents_change(self, pos: int, removed: int, added: int) -> None:
        if self._rendering or self._reverting:
            return
        if removed == added == 0:
            return
        self._index = None
        self._dirty = True
        if not self._structure_intact(pos, added):
            # Safety net for edits the key filters didn't anticipate (IME, exotic shortcuts).
            self._reverting = True
            QTimer.singleShot(0, self._revert)
            return
        self.edited.emit()
        if self._query:
            self._research.start()

    def _revert(self) -> None:
        self.document().undo()
        self._reverting = False
        self._index = None
        QApplication.beep()

    def _structure_intact(self, pos: int, added: int) -> bool:
        doc = self.document()
        if doc.blockCount() != len(self._protect):
            return False
        block = doc.findBlock(pos)
        last = doc.findBlock(pos + added).blockNumber()
        while block.isValid() and block.blockNumber() <= last:
            plen, text = self._protect[block.blockNumber()]
            if plen == WHOLE_BLOCK and block.text() != text:
                return False
            if plen > 0 and not block.text().startswith(text):
                return False
            block = block.next()
        return True

    def _range_editable(self, start: int, end: int) -> bool:
        doc = self.document()
        start = max(0, start)
        block = doc.findBlock(start)
        if not block.isValid() or block.blockNumber() != doc.findBlock(end).blockNumber():
            return False
        plen, _ = self._protect[block.blockNumber()]
        if plen == WHOLE_BLOCK:
            return False
        return start >= block.position() + plen and end <= block.position() + block.length() - 1

    def _insert_format(self, cursor: QTextCursor) -> QTextCharFormat | None:
        """Format for typed/pasted text so it joins the right segment, never a timestamp."""
        doc = self.document()
        pos = cursor.selectionStart()
        block = doc.findBlock(pos)
        probe = QTextCursor(doc)
        candidates = []
        if cursor.hasSelection():
            candidates.append(pos + 1)  # first selected character
        candidates.append(pos)  # character before the caret
        if pos < block.position() + block.length() - 1:
            candidates.append(pos + 1)  # character after the caret
        for p in candidates:
            probe.setPosition(p)
            fmt = probe.charFormat()
            if _is_text(fmt):
                return fmt
        fmt = block.charFormat()
        return fmt if _is_text(fmt) else None

    def _insert(self, text: str) -> None:
        cursor = self.textCursor()
        fmt = self._insert_format(cursor)
        if not text or fmt is None or not self._range_editable(cursor.selectionStart(), cursor.selectionEnd()):
            QApplication.beep()
            return
        cursor.insertText(text, fmt)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _delete_range(self, e) -> tuple[int, int] | None:
        c = self.textCursor()
        if c.hasSelection():
            return c.selectionStart(), c.selectionEnd()
        probe = QTextCursor(c)
        K = QKeySequence.StandardKey
        moves = {
            K.DeleteStartOfWord: QTextCursor.MoveOperation.PreviousWord,
            K.DeleteEndOfWord: QTextCursor.MoveOperation.NextWord,
            K.DeleteEndOfLine: QTextCursor.MoveOperation.EndOfLine,
        }
        for key, move in moves.items():
            if e.matches(key):
                probe.movePosition(move, QTextCursor.MoveMode.KeepAnchor)
                return probe.selectionStart(), probe.selectionEnd()
        if e.key() == Qt.Key.Key_Backspace:
            return c.position() - 1, c.position()
        if e.key() == Qt.Key.Key_Delete:
            return c.position(), c.position() + 1
        return None

    def keyPressEvent(self, e):
        K = QKeySequence.StandardKey
        if not self._editing:
            if e.key() == Qt.Key.Key_Space and not e.modifiers():
                self.togglePlay.emit()
                return
            if e.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and not e.modifiers():
                self.skip.emit(-5.0 if e.key() == Qt.Key.Key_Left else 5.0)
                return
            super().keyPressEvent(e)
            return

        if e.key() == Qt.Key.Key_Escape:
            self.set_editing(False)
            return
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            QApplication.beep()
            return
        if any(e.matches(k) for k in (K.Copy, K.SelectAll, K.Undo, K.Redo, K.Paste)):
            super().keyPressEvent(e)  # paste goes through insertFromMimeData
            return
        if e.matches(K.Cut) or e.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) or any(
            e.matches(k) for k in (K.DeleteStartOfWord, K.DeleteEndOfWord, K.DeleteEndOfLine)
        ):
            rng = self._delete_range(e)
            if rng is None or rng[0] == rng[1] or self._range_editable(*rng):
                super().keyPressEvent(e)
            else:
                QApplication.beep()
            return
        text = e.text()
        mods = e.modifiers()
        command = mods & Qt.KeyboardModifier.ControlModifier and not mods & Qt.KeyboardModifier.AltModifier
        if text and text.isprintable() and not command:
            self._insert(text)
            return
        super().keyPressEvent(e)

    def insertFromMimeData(self, source) -> None:
        if self._editing:
            self._insert(re.sub(r"\s+", " ", source.text()))

    def createMimeDataFromSelection(self) -> QMimeData:
        data = QMimeData()
        data.setText(self.textCursor().selection().toPlainText())
        return data

    def inputMethodEvent(self, e):
        # IME composition (CJK etc.): make sure committed text lands in segment format.
        if self._editing and e.commitString():
            fmt = self._insert_format(self.textCursor())
            if fmt is not None and not self.textCursor().hasSelection():
                self.setCurrentCharFormat(fmt)
        super().inputMethodEvent(e)

    # ----- mouse & layout --------------------------------------------------------

    def mousePressEvent(self, e):
        self._press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if e.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        moved = (e.position().toPoint() - self._press).manhattanLength()
        self._press = None
        wants_seek = not self._editing or e.modifiers() & Qt.KeyboardModifier.ControlModifier
        if moved < 4 and wants_seek and not self.textCursor().hasSelection():
            pos = self.cursorForPosition(e.position().toPoint()).position()
            sid = self.seg_at(pos)
            if sid is not None:
                self.seekRequested.emit(sid, self.offset_in_segment(sid, pos))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        side = max(0, (self.width() - MAX_TEXT_WIDTH) // 2)
        if side != self._side:
            self._side = side
            self.setViewportMargins(side, 0, side, 0)
            self.document().setTextWidth(self.viewport().width())
