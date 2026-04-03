"""数学与常用技术符号：Unicode 字符表 + 插入到编辑器光标处（无 LaTeX）。"""

from __future__ import annotations

from typing import Any, Callable, List, Tuple

# (分组名, [(显示名, 单个 Unicode 字符), ...])
SYMBOL_GROUPS: List[Tuple[str, List[Tuple[str, str]]]] = [
    (
        "常用",
        [
            ("正负", "±"),
            ("乘", "×"),
            ("除", "÷"),
            ("点乘", "·"),
            ("星乘", "∗"),
            ("度", "°"),
            ("分", "′"),
            ("秒", "″"),
            ("上标2", "²"),
            ("上标3", "³"),
            ("上标1", "¹"),
            ("上标0", "⁰"),
            ("四分之一", "¼"),
            ("二分之一", "½"),
            ("四分之三", "¾"),
            ("无穷", "∞"),
            ("千分比", "‰"),
        ],
    ),
    (
        "比较与近似",
        [
            ("小于等于", "≤"),
            ("大于等于", "≥"),
            ("不等于", "≠"),
            ("约等于", "≈"),
            ("恒等于", "≡"),
            ("远小于", "≪"),
            ("远大于", "≫"),
            ("波浪", "∼"),
        ],
    ),
    (
        "希腊小写",
        [
            ("alpha", "α"),
            ("beta", "β"),
            ("gamma", "γ"),
            ("delta", "δ"),
            ("epsilon", "ε"),
            ("zeta", "ζ"),
            ("eta", "η"),
            ("theta", "θ"),
            ("lambda", "λ"),
            ("mu", "μ"),
            ("pi", "π"),
            ("rho", "ρ"),
            ("sigma", "σ"),
            ("tau", "τ"),
            ("phi", "φ"),
            ("omega", "ω"),
        ],
    ),
    (
        "希腊大写",
        [
            ("Gamma", "Γ"),
            ("Delta", "Δ"),
            ("Lambda", "Λ"),
            ("Sigma", "Σ"),
            ("Omega", "Ω"),
            ("Pi", "Π"),
        ],
    ),
    (
        "箭头",
        [
            ("右", "→"),
            ("左", "←"),
            ("上", "↑"),
            ("下", "↓"),
            ("左右", "↔"),
            ("双线右", "⇒"),
            ("双线左", "⇐"),
            ("双线左右", "⇔"),
        ],
    ),
    (
        "集合与逻辑",
        [
            ("属于", "∈"),
            ("不属于", "∉"),
            ("交", "∩"),
            ("并", "∪"),
            ("真子集", "⊂"),
            ("子集", "⊆"),
            ("空集", "∅"),
            ("任意", "∀"),
            ("存在", "∃"),
            ("与", "∧"),
            ("或", "∨"),
            ("非", "¬"),
        ],
    ),
    (
        "微积分与算子",
        [
            ("根号", "√"),
            ("求和", "∑"),
            ("连乘", "∏"),
            ("积分", "∫"),
            ("偏导", "∂"),
            ("梯度∇", "∇"),
            ("拉普拉斯", "∆"),
        ],
    ),
]


def insert_unicode_at_caret(editor: Any, text: str) -> bool:
    """
    在 editor 的光标处插入 text。
    支持 StrokeTextEditor.insert_plain 与 QTextEdit.textCursor().insertText。
    """
    if not text:
        return False
    insert_plain = getattr(editor, "insert_plain", None)
    if callable(insert_plain):
        insert_plain(text)
        return True
    text_cursor = getattr(editor, "textCursor", None)
    if callable(text_cursor):
        editor.setFocus()
        cur = text_cursor()
        cur.insertText(text)
        set_cursor = getattr(editor, "setTextCursor", None)
        if callable(set_cursor):
            set_cursor(cur)
        return True
    return False


def populate_qmenu_symbols(menu: Any, on_pick: Callable[[str], None]) -> None:
    """向 QMenu 填充分组子菜单（PyQt5/PyQt6 通用）。"""
    for group_title, entries in SYMBOL_GROUPS:
        sub = menu.addMenu(group_title)
        for label, ch in entries:
            sub.addAction(f"{label}\t{ch}", lambda checked=False, c=ch: on_pick(c))
