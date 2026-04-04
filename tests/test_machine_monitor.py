from __future__ import annotations

import unittest

from inkscape_wps.core.machine_monitor import MachineMonitor


class TestMachineMonitor(unittest.TestCase):
    def test_apply_status_fields_updates_runtime_snapshot(self) -> None:
        monitor = MachineMonitor()
        snap = monitor.apply_status_fields(
            {
                "state": "Idle",
                "mpos": "1.000,2.000,3.000",
                "wpos": "0.100,0.200,0.300",
                "wco": "0.900,1.800,2.700",
                "pn": "XYZ",
                "fs": "1500,8000",
                "ov": "110,100,95",
                "bf": "15,252",
            }
        )
        self.assertEqual(snap.state, "IDLE")
        self.assertEqual(snap.mpos, (1.0, 2.0, 3.0))
        self.assertEqual(snap.wpos, (0.1, 0.2, 0.3))
        self.assertEqual(snap.wco, (0.9, 1.8, 2.7))
        self.assertEqual(snap.limit_pins, "XYZ")
        self.assertEqual(snap.feed_rate, 1500.0)
        self.assertEqual(snap.spindle_rpm, 8000.0)
        self.assertEqual(snap.ov_feed, 110)
        self.assertEqual(snap.ov_rapid, 100)
        self.assertEqual(snap.ov_spindle, 95)
        self.assertEqual(snap.planner_free, 15)
        self.assertEqual(snap.rx_free, 252)

    def test_alarm_message_is_humanized(self) -> None:
        monitor = MachineMonitor()
        snap = monitor.apply_alarm_or_error("ALARM:2")
        self.assertEqual(snap.state, "ALARM")
        self.assertIn("软限位", snap.last_alarm)


if __name__ == "__main__":
    unittest.main()
