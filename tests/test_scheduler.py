import unittest
from unittest.mock import patch

from app.main import should_run_now, build_default_options, resolve_printer_target, discover_printers


class SchedulerTests(unittest.TestCase):
    def test_should_run_now_for_daily_schedule(self):
        options = {
            "schedule_enabled": True,
            "schedule_type": "daily",
            "schedule_hour": 8,
            "last_run": "2024-01-01T07:00:00",
        }
        now = "2024-01-01T08:00:00"
        self.assertTrue(should_run_now(options, now))

    def test_should_not_run_for_wrong_hour(self):
        options = {
            "schedule_enabled": True,
            "schedule_type": "daily",
            "schedule_hour": 8,
            "last_run": "2024-01-01T07:00:00",
        }
        now = "2024-01-01T07:59:00"
        self.assertFalse(should_run_now(options, now))

    def test_default_options_include_schedule(self):
        options = build_default_options()
        self.assertTrue(options["schedule_enabled"] is False)
        self.assertEqual(options["schedule_type"], "daily")
        self.assertEqual(options["schedule_hour"], 8)

    def test_resolve_printer_target_uses_configured_values(self):
        options = {
            "printer_name": "Office Printer",
            "printer_host": "192.168.1.50",
            "printer_uri": "ipp://192.168.1.50/ipp/print",
        }
        self.assertEqual(resolve_printer_target(options)["name"], "Office Printer")
        self.assertEqual(resolve_printer_target(options)["host"], "192.168.1.50")

    def test_discover_printers_uses_probe_results(self):
        options = {"printer_name": "", "printer_host": "", "printer_uri": ""}
        with patch("app.main.probe_printer_host", return_value={"name": "Office Printer", "host": "192.168.1.50", "uri": "ipp://192.168.1.50/ipp/print"}):
            with patch("app.main.get_candidate_hosts", return_value=["192.168.1.50"]):
                discovered = discover_printers(options)
        self.assertEqual(discovered[0]["name"], "Office Printer")
        self.assertEqual(discovered[0]["host"], "192.168.1.50")


if __name__ == "__main__":
    unittest.main()
