"""GRBL 设备状态聚合。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

MachinePosition = Tuple[float, float, float]


@dataclass
class MachineSnapshot:
    state: str = "DISCONNECTED"
    mpos: MachinePosition = (0.0, 0.0, 0.0)
    wpos: MachinePosition = (0.0, 0.0, 0.0)
    wco: MachinePosition = (0.0, 0.0, 0.0)
    limit_pins: str = ""
    feed_rate: float = 0.0
    spindle_rpm: float = 0.0
    ov_feed: int = 100
    ov_rapid: int = 100
    ov_spindle: int = 100
    planner_free: int = -1
    rx_free: int = -1
    last_alarm: str = ""


class MachineMonitor:
    def __init__(self) -> None:
        self.snapshot = MachineSnapshot()

    def on_connected(self) -> None:
        self.snapshot.state = "IDLE"

    def on_disconnected(self) -> None:
        self.snapshot = MachineSnapshot()

    def apply_status_fields(self, fields: Dict[str, str]) -> MachineSnapshot:
        snap = self.snapshot
        snap.state = str(fields.get("state", snap.state or "UNKNOWN")).upper()
        mpos = self._parse_xyz(fields.get("mpos"))
        if mpos is not None:
            snap.mpos = mpos
        wpos = self._parse_xyz(fields.get("wpos"))
        if wpos is not None:
            snap.wpos = wpos
        wco = self._parse_xyz(fields.get("wco"))
        if wco is not None:
            snap.wco = wco
        pins = fields.get("pn")
        if isinstance(pins, str):
            snap.limit_pins = pins
        fs = self._parse_float_pair(fields.get("fs"))
        if fs is not None:
            snap.feed_rate, snap.spindle_rpm = fs
        ov = self._parse_int_triple(fields.get("ov"))
        if ov is not None:
            snap.ov_feed, snap.ov_rapid, snap.ov_spindle = ov
        bf = self._parse_int_pair(fields.get("bf"))
        if bf is not None:
            snap.planner_free, snap.rx_free = bf
        return snap

    def apply_alarm_or_error(self, line: str) -> MachineSnapshot:
        text = (line or "").strip()
        low = text.lower()
        if low.startswith("alarm"):
            self.snapshot.state = "ALARM"
            self.snapshot.last_alarm = self._alarm_text(text)
        elif low.startswith("error"):
            self.snapshot.last_alarm = text
        return self.snapshot

    @staticmethod
    def _parse_xyz(raw: Optional[str]) -> Optional[MachinePosition]:
        if not raw:
            return None
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 3:
            return None
        try:
            return (float(parts[0]), float(parts[1]), float(parts[2]))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_float_pair(raw: Optional[str]) -> Optional[Tuple[float, float]]:
        if not raw:
            return None
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 2:
            return None
        try:
            return (float(parts[0]), float(parts[1]))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_int_pair(raw: Optional[str]) -> Optional[Tuple[int, int]]:
        if not raw:
            return None
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 2:
            return None
        try:
            return (int(float(parts[0])), int(float(parts[1])))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_int_triple(raw: Optional[str]) -> Optional[Tuple[int, int, int]]:
        if not raw:
            return None
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 3:
            return None
        try:
            return (int(float(parts[0])), int(float(parts[1])), int(float(parts[2])))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _alarm_text(raw: str) -> str:
        code = raw.split(":", 1)[1].strip() if ":" in raw else ""
        mapping = {
            "1": "硬限位触发，运动已终止",
            "2": "软限位触发，目标超出行程",
            "3": "复位中止，处于报警锁定",
            "4": "探针失败，未触发",
            "5": "探针失败，触发后未离开",
            "6": "回零失败，复位期间检测到限位",
            "7": "回零失败，安全门被打开",
            "8": "回零失败，超出搜索距离",
            "9": "回零失败，找不到限位开关",
        }
        return mapping.get(code, raw)
