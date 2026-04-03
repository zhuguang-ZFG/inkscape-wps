"""单线字形编辑模型：文本缓冲、光标、选区与撤销重做。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


@dataclass
class EditState:
    text: str
    caret: int
    anchor: Optional[int]


class StrokeTextModel:
    """纯 Python 文本编辑状态机，不依赖 Qt。"""

    def __init__(self, text: str = "") -> None:
        self._text = text
        self._caret = len(text)
        self._anchor: Optional[int] = None
        self._undo: List[EditState] = []
        self._redo: List[EditState] = []

    @property
    def text(self) -> str:
        return self._text

    @property
    def caret(self) -> int:
        return self._caret

    @property
    def anchor(self) -> Optional[int]:
        return self._anchor

    def set_text(self, text: str) -> None:
        self._text = text
        self._caret = len(text)
        self._anchor = None
        self._undo.clear()
        self._redo.clear()

    def snapshot(self) -> EditState:
        return EditState(self._text, self._caret, self._anchor)

    def _restore(self, st: EditState) -> None:
        self._text = st.text
        self._caret = st.caret
        self._anchor = st.anchor

    def _push_undo(self) -> None:
        self._undo.append(self.snapshot())
        if len(self._undo) > 300:
            self._undo = self._undo[-300:]
        self._redo.clear()

    def has_selection(self) -> bool:
        return self._anchor is not None and self._anchor != self._caret

    def selection_range(self) -> Tuple[int, int]:
        if not self.has_selection():
            return self._caret, self._caret
        a = int(self._anchor if self._anchor is not None else self._caret)
        b = self._caret
        return (a, b) if a <= b else (b, a)

    def selected_text(self) -> str:
        s, e = self.selection_range()
        return self._text[s:e]

    def clear_selection(self) -> None:
        self._anchor = None

    def move_caret(self, pos: int, *, keep_selection: bool = False) -> None:
        pos = _clamp(pos, 0, len(self._text))
        if keep_selection:
            if self._anchor is None:
                self._anchor = self._caret
        else:
            self._anchor = None
        self._caret = pos

    def select_all(self) -> None:
        self._anchor = 0
        self._caret = len(self._text)

    def replace_selection(self, content: str, *, record_undo: bool = True) -> None:
        if record_undo:
            self._push_undo()
        s, e = self.selection_range()
        self._text = self._text[:s] + content + self._text[e:]
        self._caret = s + len(content)
        self._anchor = None

    def insert_text(self, content: str) -> None:
        self.replace_selection(content, record_undo=True)

    def backspace(self) -> None:
        if self.has_selection():
            self.replace_selection("", record_undo=True)
            return
        if self._caret <= 0:
            return
        self._push_undo()
        i = self._caret - 1
        self._text = self._text[:i] + self._text[self._caret :]
        self._caret = i

    def delete(self) -> None:
        if self.has_selection():
            self.replace_selection("", record_undo=True)
            return
        if self._caret >= len(self._text):
            return
        self._push_undo()
        self._text = self._text[: self._caret] + self._text[self._caret + 1 :]

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.snapshot())
        self._restore(self._redo.pop())
        return True
