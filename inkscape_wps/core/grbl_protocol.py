"""GRBL 串口文本行解析（与 grblapp `grbl_protocol.py` 行为一致：剥离行首 ? 回显）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MessageType = Literal["ok", "error", "alarm", "status", "event", "text"]


@dataclass(frozen=True)
class ParsedMessage:
    type: MessageType
    raw: str


class GrblProtocolParser:
    def parse_line(self, line: str) -> ParsedMessage:
        original = line.strip()
        text = original.lstrip("?").strip()
        if not text:
            return ParsedMessage(type="text", raw=original)
        low = text.lower()
        if low == "ok":
            return ParsedMessage(type="ok", raw=text)
        if low.startswith("error"):
            return ParsedMessage(type="error", raw=text)
        if low.startswith("alarm"):
            return ParsedMessage(type="alarm", raw=text)
        if text.startswith("<") and text.endswith(">"):
            return ParsedMessage(type="status", raw=text)
        if text.startswith("[") and text.endswith("]"):
            return ParsedMessage(type="event", raw=text)
        return ParsedMessage(type="text", raw=text)
