from __future__ import annotations

import unittest

from inkscape_wps.core.grbl import GrblController, GrblSendError


class _FakeStream:
    def __init__(self, responses: list[str]) -> None:
        self._responses = [r.encode("utf-8") + b"\n" for r in responses]
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def readline(self) -> bytes:
        if self._responses:
            return self._responses.pop(0)
        return b""

    def reset_input_buffer(self) -> None:
        return None

    def close(self) -> None:
        return None


class TestGrblStreaming(unittest.TestCase):
    def test_streaming_eeprom_write_forces_queue_drain(self) -> None:
        stream = _FakeStream(["ok", "ok", "ok"])
        controller = GrblController(stream, default_line_timeout_s=0.05)

        def fake_wait_ok(timeout_s=None) -> None:  # noqa: ANN001
            if not stream._responses:
                raise GrblSendError("等待 ok 超时")
            raw = stream.readline().decode().strip()
            if raw != "ok":
                raise GrblSendError(raw)

        controller.wait_ok = fake_wait_ok  # type: ignore[method-assign]
        sent, total = controller.send_program(
            "G1 X1\n$100=250\nG1 X2",
            streaming=True,
            rx_buffer_size=64,
        )
        self.assertEqual((sent, total), (3, 3))
        self.assertEqual(
            [w.decode("utf-8").strip() for w in stream.writes],
            ["G1 X1", "$100=250", "G1 X2"],
        )

    def test_resume_from_checkpoint_returns_remaining_lines(self) -> None:
        stream = _FakeStream(["ok", "error:2"])
        controller = GrblController(stream, default_line_timeout_s=0.05)

        def fake_wait_ok(timeout_s=None) -> None:  # noqa: ANN001
            if not stream._responses:
                raise GrblSendError("等待 ok 超时")
            raw = stream.readline().decode().strip()
            if raw == "ok":
                return
            raise GrblSendError(raw)

        controller.wait_ok = fake_wait_ok  # type: ignore[method-assign]
        with self.assertRaises(GrblSendError) as ctx:
            controller.send_program("G1 X1\nG1 X2\nG1 X3", streaming=False)
        self.assertEqual(ctx.exception.acked_count, 1)
        self.assertEqual(ctx.exception.failed_command, "G1 X2")
        self.assertTrue(controller.can_resume_from_checkpoint)
        self.assertEqual(controller.remaining_program_lines_from_checkpoint(), ["G1 X2", "G1 X3"])


if __name__ == "__main__":
    unittest.main()
