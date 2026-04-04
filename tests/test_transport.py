from __future__ import annotations

import unittest

from inkscape_wps.core.transport import parse_transport_target


class TestTransportTarget(unittest.TestCase):
    def test_parse_tcp_target(self) -> None:
        target = parse_transport_target("tcp://192.168.4.1:23")
        self.assertEqual(target.kind, "tcp")
        self.assertEqual(target.tcp_host, "192.168.4.1")
        self.assertEqual(target.tcp_port, 23)

    def test_parse_host_port_without_prefix(self) -> None:
        target = parse_transport_target("grbl.local:8023")
        self.assertEqual(target.kind, "tcp")
        self.assertEqual(target.tcp_host, "grbl.local")
        self.assertEqual(target.tcp_port, 8023)

    def test_parse_serial_target(self) -> None:
        target = parse_transport_target("/dev/ttyUSB0")
        self.assertEqual(target.kind, "serial")
        self.assertEqual(target.serial_port, "/dev/ttyUSB0")


if __name__ == "__main__":
    unittest.main()
