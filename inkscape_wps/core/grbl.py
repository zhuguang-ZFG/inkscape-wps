"""GRBL 串口：依赖注入 serial；逐行发送并等待 ok，error/alarm 时失败（对齐 grblapp 思路）。"""

from __future__ import annotations

import threading
import time
from collections import deque
from queue import Empty, Queue
from typing import Callable, Deque, Dict, List, Optional, Protocol, Tuple

from .grbl_protocol import GrblProtocolParser, ParsedMessage


class SerialLike(Protocol):
    def write(self, data: bytes) -> int: ...

    def readline(self) -> bytes: ...

    def reset_input_buffer(self) -> None: ...

    def close(self) -> None: ...


StatusHandler = Callable[[Dict[str, str]], None]
LineHandler = Callable[[str], None]
ErrorHandler = Callable[[str], None]


class GrblSendError(RuntimeError):
    """单行 G-code 未得到 ok（error / alarm / 超时）。"""


def wakeup_serial_port(
    stream: SerialLike,
    *,
    settle_s: float = 0.15,
    drain_timeout_s: float = 0.4,
    on_line: Optional[LineHandler] = None,
) -> None:
    """上电/打开串口后唤醒 GRBL 并排空启动信息（参考 grblapp SerialGrblClient.connect）。"""
    try:
        stream.write(b"\r\n\r\n")
    except OSError:
        return
    time.sleep(settle_s)
    t0 = time.monotonic()
    while time.monotonic() - t0 < drain_timeout_s:
        try:
            n = int(getattr(stream, "in_waiting", 0) or 0)
        except Exception:
            n = 0
        if n <= 0:
            time.sleep(0.02)
            continue
        try:
            raw = stream.readline()
        except Exception:
            break
        if not raw:
            break
        line = raw.decode("utf-8", errors="replace").rstrip()
        if on_line and line.strip():
            on_line(line)


def verify_serial_responsive(
    stream: SerialLike,
    *,
    settle_s: float = 0.15,
    drain_after_wake_s: float = 0.55,
    probe_timeout_s: float = 2.5,
    on_line: Optional[LineHandler] = None,
) -> Tuple[bool, str]:
    """
    确认串口对端有应答，避免「只打开发送 \\r\\n、下面完全静默」仍当连接成功。

    1. 发送 ``\\r\\n\\r\\n``，在 ``drain_after_wake_s`` 内读尽已有数据；
    2. 若此阶段未收到任何非空行，再发 ``$I``（Grbl 1.1+ / Grbl_Esp32 构建信息），
       在 ``probe_timeout_s`` 内等待**任意一行**非空应答（含 ``error:`` 亦视为有固件在线）。

    返回 (是否判定有应答, 简短说明)。
    """
    got_nonempty = False

    def _emit(line: str) -> None:
        nonlocal got_nonempty
        if line.strip():
            got_nonempty = True
        if on_line and line.strip():
            on_line(line)

    try:
        try:
            stream.reset_input_buffer()
        except Exception:
            pass
        stream.write(b"\r\n\r\n")
    except OSError as e:
        return False, f"串口写入失败：{e}"

    time.sleep(settle_s)
    t0 = time.monotonic()
    while time.monotonic() - t0 < drain_after_wake_s:
        try:
            n = int(getattr(stream, "in_waiting", 0) or 0)
        except Exception:
            n = 0
        if n <= 0:
            time.sleep(0.02)
            continue
        try:
            raw = stream.readline()
        except Exception:
            break
        if not raw:
            time.sleep(0.02)
            continue
        line = raw.decode("utf-8", errors="replace").rstrip()
        _emit(line)

    if got_nonempty:
        return True, "下位机在唤醒阶段已有应答，连接有效。"

    try:
        stream.write(b"$I\n")
    except OSError as e:
        return False, f"发送探测命令失败：{e}"

    deadline = time.monotonic() + max(0.5, float(probe_timeout_s))
    while time.monotonic() < deadline:
        try:
            raw = stream.readline()
        except Exception:
            break
        if raw:
            line = raw.decode("utf-8", errors="replace").rstrip()
            _emit(line)
            if line.strip():
                return True, "收到 $I 探测应答，判定串口对端有固件响应。"
        else:
            time.sleep(0.03)

    return (
        False,
        "未收到任何应答：请检查是否接好下位机、波特率是否与固件一致（常见 115200），以及是否为 GRBL/兼容固件。",
    )


class GrblController:
    """
    读线程解析行 → 将 ok/error/alarm 放入队列；send_line_sync 发送一行并阻塞等到 ok。
    避免「只累加 pending_ok、遇 error 不递减」导致的死锁。
    """

    def __init__(
        self,
        stream: SerialLike,
        *,
        on_status: Optional[StatusHandler] = None,
        on_log_line: Optional[LineHandler] = None,
        on_protocol_error: Optional[ErrorHandler] = None,
        default_line_timeout_s: float = 30.0,
    ) -> None:
        self._s = stream
        self._on_status = on_status
        self._on_log = on_log_line
        self._on_err = on_protocol_error
        self._default_timeout = max(1.0, default_line_timeout_s)
        self._parser = GrblProtocolParser()
        self._resp_queue: Queue[ParsedMessage] = Queue()
        self._reader_alive = False
        self._reader_thread: Optional[threading.Thread] = None
        self._send_lock = threading.Lock()

    def start_reader(self) -> None:
        if self._reader_thread and self._reader_alive:
            return

        def _loop() -> None:
            self._reader_alive = True
            while self._reader_alive:
                try:
                    raw = self._s.readline()
                except Exception:
                    break
                if not raw:
                    time.sleep(0.005)
                    continue
                line = raw.decode("utf-8", errors="replace").rstrip()
                if self._on_log and line.strip():
                    self._on_log(line)
                msg = self._parser.parse_line(line)
                if msg.type == "ok":
                    self._resp_queue.put(msg)
                elif msg.type == "error":
                    self._resp_queue.put(msg)
                    if self._on_err:
                        self._on_err(msg.raw)
                elif msg.type == "alarm":
                    self._resp_queue.put(msg)
                    if self._on_err:
                        self._on_err(msg.raw)
                elif msg.type == "status":
                    parsed = _parse_status_line(msg.raw)
                    if parsed and self._on_status:
                        self._on_status(parsed)
                # event / text：仅日志，不进 ack 队列

        self._reader_thread = threading.Thread(target=_loop, daemon=True)
        self._reader_thread.start()

    def stop_reader(self) -> None:
        self._reader_alive = False

    def clear_response_queue(self) -> None:
        while True:
            try:
                self._resp_queue.get_nowait()
            except Empty:
                break

    def wait_ok(self, timeout_s: Optional[float] = None) -> None:
        """阻塞直到收到一条 ok；若收到 error/alarm 则抛 GrblSendError。"""
        to = timeout_s if timeout_s is not None else self._default_timeout
        deadline = time.monotonic() + to
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GrblSendError("等待 ok 超时")
            try:
                msg = self._resp_queue.get(timeout=min(remaining, 0.25))
            except Empty:
                continue
            if msg.type == "ok":
                return
            if msg.type == "error":
                raise GrblSendError(f"GRBL 错误: {msg.raw}")
            if msg.type == "alarm":
                raise GrblSendError(f"GRBL 报警: {msg.raw}")

    def send_line_sync(self, line: str, *, timeout_s: Optional[float] = None) -> None:
        """发送一行（无换行符则自动加 \\n），并等待对应 ok。"""
        stripped = line.strip()
        if not stripped:
            return
        with self._send_lock:
            payload = (stripped + "\n").encode("utf-8")
            self._s.write(payload)
            self.wait_ok(timeout_s=timeout_s)

    def send_program(
        self,
        gcode_text: str,
        *,
        line_timeout_s: Optional[float] = None,
        streaming: bool = False,
        rx_buffer_size: int = 128,
    ) -> Tuple[int, int]:
        """
        逐行发送程序（跳过空行与括号注释行）。
        streaming=True 时按字节预算在固件缓冲内尽量排队多行，仍逐条等待 ok（与 grblapp JobRunner 思路一致）。
        返回 (收到 ok 的行数, 总行数)。
        """
        lines = executable_gcode_lines(gcode_text)
        to = line_timeout_s if line_timeout_s is not None else self._default_timeout
        if not streaming:
            for ln in lines:
                self.send_line_sync(ln, timeout_s=to)
            return len(lines), len(lines)

        cap = max(8, int(rx_buffer_size) - 2)
        pending: Deque[int] = deque()
        buf_used = 0
        li = 0
        n = len(lines)
        ok_count = 0
        while ok_count < n:
            while li < n:
                raw = (lines[li] + "\n").encode("utf-8")
                cost = len(raw)
                # 超长单行无法与「预算内拼包」；先排空已排队再单独发，避免 buf_used 逻辑死锁
                if cost > cap:
                    while pending:
                        self.wait_ok(timeout_s=to)
                        buf_used -= pending.popleft()
                        ok_count += 1
                    with self._send_lock:
                        self._s.write(raw)
                    pending.append(cost)
                    buf_used += cost
                    li += 1
                    break
                if pending and buf_used + cost > cap:
                    break
                with self._send_lock:
                    self._s.write(raw)
                buf_used += cost
                pending.append(cost)
                li += 1
            if not pending:
                raise GrblSendError("流式发送无法推进（缓冲预算过小或内部状态错误）")
            self.wait_ok(timeout_s=to)
            buf_used -= pending.popleft()
            ok_count += 1
        return ok_count, n

    def soft_reset(self) -> None:
        self._s.write(b"\x18")

    def feed_hold(self) -> None:
        self._s.write(b"!")

    def cycle_start(self) -> None:
        self._s.write(b"~")

    def send_realtime_status_request(self) -> None:
        """发送实时 ``?``，固件返回 ``<...|Bf:...>`` 时由 ``on_status`` 回调接收。"""
        with self._send_lock:
            try:
                self._s.write(b"?")
            except OSError:
                pass

    def close(self) -> None:
        self.stop_reader()
        self._s.close()


def parse_bf_field(status_fields: Dict[str, str]) -> Tuple[Optional[int], Optional[int]]:
    """
    解析 Grbl 实时状态中的 ``Bf:`` 字段：``Bf:<planner 空闲块数>,<串口 RX 剩余字节>``。
    空闲、无积压时第二项通常接近固件串口接收缓冲容量（Grbl_Esp32 见 ``Report.cpp`` / ``Serial.*``）。
    """
    raw = status_fields.get("bf")
    if not raw:
        return None, None
    parts = raw.replace(" ", "").split(",", 1)
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def _parse_status_line(line: str) -> Optional[Dict[str, str]]:
    s = line.strip()
    if not (s.startswith("<") and s.endswith(">")):
        return None
    inner = s[1:-1]
    parts = inner.split("|")
    if not parts:
        return None
    out: Dict[str, str] = {"state": parts[0].strip()}
    for p in parts[1:]:
        if ":" in p:
            k, v = p.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def executable_gcode_lines(gcode_text: str) -> List[str]:
    return [
        ln.strip()
        for ln in gcode_text.splitlines()
        if ln.strip() and not ln.strip().startswith("(")
    ]
