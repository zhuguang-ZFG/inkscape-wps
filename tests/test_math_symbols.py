"""数学符号插入辅助（无 Qt 编辑器时仅测逻辑）。"""

from __future__ import annotations

import unittest

from inkscape_wps.ui.math_symbols import SYMBOL_GROUPS, insert_unicode_at_caret


class _MockStrokeLike:
    def __init__(self) -> None:
        self.inserted: list[str] = []

    def insert_plain(self, text: str) -> None:
        self.inserted.append(text)


class _MockTextEditLike:
    def __init__(self) -> None:
        self._buf = ""
        self.focused = False

    def setFocus(self) -> None:
        self.focused = True

    def textCursor(self):
        return self

    def insertText(self, text: str) -> None:
        self._buf += text

    def setTextCursor(self, _c) -> None:
        pass


class TestMathSymbols(unittest.TestCase):
    def test_groups_non_empty(self) -> None:
        self.assertTrue(SYMBOL_GROUPS)
        for title, items in SYMBOL_GROUPS:
            self.assertTrue(title.strip())
            self.assertTrue(items)
            for _label, ch in items:
                self.assertEqual(len(ch), 1, f"每项应为单字符: {ch!r}")

    def test_insert_mock_stroke(self) -> None:
        m = _MockStrokeLike()
        self.assertTrue(insert_unicode_at_caret(m, "π"))
        self.assertEqual(m.inserted, ["π"])

    def test_insert_mock_qtext(self) -> None:
        m = _MockTextEditLike()
        self.assertTrue(insert_unicode_at_caret(m, "±"))
        self.assertEqual(m._buf, "±")
        self.assertTrue(m.focused)

    def test_insert_empty_false(self) -> None:
        self.assertFalse(insert_unicode_at_caret(_MockStrokeLike(), ""))


if __name__ == "__main__":
    unittest.main()
