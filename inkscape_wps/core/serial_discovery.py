"""
枚举串口（含蓝牙 SPP 配对后出现的虚拟串口）。纯标准库 + 可选 pyserial。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence


@dataclass(frozen=True)
class PortInfo:
    device: str
    description: str
    manufacturer: str
    is_bluetooth: bool

    def label(self) -> str:
        d = (self.description or "").strip() or "串口"
        return f"{self.device} — {d}"


def _guess_bluetooth(device: str, desc: str, mfg: str) -> bool:
    u = f"{device} {desc} {mfg}".lower()
    keys = (
        "bluetooth",
        "bt ",
        "bt-",
        "_bt",
        "rfcomm",
        "spp",
        "serial port profile",
        "wireless",
        "hci",
    )
    if any(k in u for k in keys):
        return True
    if "bluetooth" in device.lower():
        return True
    return False


def list_port_infos() -> List[PortInfo]:
    try:
        from serial.tools import list_ports
    except ImportError:
        return []

    out: List[PortInfo] = []
    for p in list_ports.comports():
        desc = p.description or ""
        mfg = getattr(p, "manufacturer", None) or ""
        out.append(
            PortInfo(
                device=p.device,
                description=desc,
                manufacturer=mfg or "",
                is_bluetooth=_guess_bluetooth(p.device, desc, mfg),
            )
        )
    out.sort(key=lambda x: (not x.is_bluetooth, x.device.lower()))
    return out


def filter_ports(ports: Sequence[PortInfo], bluetooth_only: bool) -> List[PortInfo]:
    if not bluetooth_only:
        return list(ports)
    return [p for p in ports if p.is_bluetooth]
