"""GRBL 传输目标与 TCP 文本流。"""

from __future__ import annotations

import select
import socket
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TransportTarget:
    kind: str
    serial_port: str | None = None
    tcp_host: str | None = None
    tcp_port: int | None = None


def parse_transport_target(raw_target: str) -> TransportTarget:
    text = (raw_target or "").strip()
    probe = text
    if probe.lower().startswith("tcp://"):
        probe = probe[6:].strip()
    if ":" in probe:
        host, port = probe.rsplit(":", 1)
        host = host.strip().strip("/")
        try:
            tcp_port = int(port.strip().strip("/"))
        except ValueError:
            return TransportTarget(kind="serial", serial_port=text)
        if host and 1 <= tcp_port <= 65535:
            return TransportTarget(kind="tcp", tcp_host=host, tcp_port=tcp_port)
    return TransportTarget(kind="serial", serial_port=text)


class TcpTextStream:
    """把 TCP/Telnet 连接适配为 GrblController 可消费的文本流。"""

    def __init__(self, host: str, port: int, *, timeout_s: float = 0.2) -> None:
        self._host = host
        self._port = int(port)
        self._timeout_s = max(0.05, float(timeout_s))
        self._sock: Optional[socket.socket] = None
        self._buf = bytearray()

    @property
    def in_waiting(self) -> int:
        ready = 0
        if self._sock is not None:
            try:
                rlist, _, _ = select.select([self._sock], [], [], 0.0)
                ready = 1 if rlist else 0
            except OSError:
                ready = 0
        return len(self._buf) + ready

    def connect(self) -> None:
        if self._sock is not None:
            self.close()
        sock = socket.create_connection((self._host, self._port), timeout=2.0)
        sock.settimeout(self._timeout_s)
        self._sock = sock
        self._buf.clear()

    def write(self, data: bytes) -> int:
        if self._sock is None:
            raise OSError("TCP 连接尚未建立")
        self._sock.sendall(data)
        return len(data)

    def readline(self) -> bytes:
        if self._sock is None:
            return b""
        while True:
            idx = self._buf.find(b"\n")
            if idx >= 0:
                chunk = bytes(self._buf[: idx + 1])
                del self._buf[: idx + 1]
                return chunk
            try:
                block = self._sock.recv(4096)
            except socket.timeout:
                return b""
            if not block:
                pending = bytes(self._buf)
                self._buf.clear()
                return pending
            self._buf.extend(block)

    def reset_input_buffer(self) -> None:
        self._buf.clear()

    def close(self) -> None:
        sock = self._sock
        self._sock = None
        self._buf.clear()
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
