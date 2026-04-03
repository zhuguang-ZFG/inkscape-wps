"""表格 / 演示 / 手绘 等非文字区的统一撤销（与 QTextDocument 撤销分离）。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Tuple

from PyQt6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from inkscape_wps.ui.main_window import MainWindow

NonWordState = Tuple[str, str, str]


def capture_nonword_state(
    table_blob: dict,
    slides: list,
    sketch_paths_serialized: list,
) -> NonWordState:
    return (
        json.dumps(table_blob, ensure_ascii=False, sort_keys=True),
        json.dumps(slides, ensure_ascii=False),
        json.dumps(sketch_paths_serialized, ensure_ascii=False),
    )


class NonWordEditCommand(QUndoCommand):
    """连续编辑会由 QUndoStack 与 mergeWith 合并为一步。"""

    COMMAND_ID = 7001

    def __init__(
        self,
        mw: MainWindow,
        old_state: NonWordState,
        new_state: NonWordState,
        *,
        text: str = "表格 / 演示 / 手绘",
    ) -> None:
        super().__init__(text)
        self._mw = mw
        self._first_old = old_state
        self._cur_new = new_state

    def undo(self) -> None:
        self._mw._restore_nonword_state(self._first_old)

    def redo(self) -> None:
        self._mw._restore_nonword_state(self._cur_new)

    def id(self) -> int:
        return self.COMMAND_ID

    def mergeWith(self, other: QUndoCommand) -> bool:
        if other.id() != self.COMMAND_ID:
            return False
        o = other
        if not isinstance(o, NonWordEditCommand):
            return False
        self._cur_new = o._cur_new
        return True
