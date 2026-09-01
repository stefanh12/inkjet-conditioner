import io
import os
import tempfile
import unittest
from unittest.mock import patch

from app.main import BONJOUR_PRINTER_SERVICE_TYPES, apply_environment_overrides, build_app, build_setup_page, is_setup_complete, save_uploaded_document, should_run_now, build_default_options, resolve_printer_target, discover_printers, discover_mdns_printers, get_webui_port, main


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
            with patch("app.main.get_candidate_hosts", return_value=["192.168.1.50"]), patch("app.main.discover_mdns_printers", return_value=[]):
                discovered = discover_printers(options)
        self.assertEqual(discovered[0]["name"], "Office Printer")
        self.assertEqual(discovered[0]["host"], "192.168.1.50")

    def test_mdns_discovery_returns_no_printers_without_zeroconf(self):
        with patch("app.main.Zeroconf", None):
            self.assertEqual(discover_mdns_printers(), [])

    def test_bonjour_discovery_includes_common_printer_service_types(self):
        self.assertIn("_ipp._tcp.local.", BONJOUR_PRINTER_SERVICE_TYPES)
        self.assertIn("_printer._tcp.local.", BONJOUR_PRINTER_SERVICE_TYPES)
        self.assertIn("_pdl-datastream._tcp.local.", BONJOUR_PRINTER_SERVICE_TYPES)

    def test_default_webui_port_is_8000(self):
        self.assertEqual(get_webui_port({"WEBUI_PORT": ""}), 8000)

    def test_web_ui_requires_configured_credentials(self):
        with patch.dict(os.environ, {"WEBUI_USERNAME": "admin", "WEBUI_PASSWORD": "test-password"}, clear=False):
            client = build_app().test_client()
            self.assertEqual(client.get("/", follow_redirects=False).status_code, 302)
            self.assertEqual(client.get("/healthz").status_code, 200)
            self.assertIn(b"Welcome back.", client.get("/login").data)
            response = client.post("/login", data={"username": "admin", "password": "test-password"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Keep your ink moving.", response.data)

    def test_startup_requires_web_ui_password(self):
        with patch.dict(os.environ, {"WEBUI_PASSWORD": ""}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "WEBUI_PASSWORD must be set"):
                main()

    def test_saving_setup_does_not_print(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"OPTIONS_PATH": os.path.join(temp_dir, "options.json"), "WEBUI_PASSWORD": "test-password"}, clear=False), patch("app.main.discover_printers", return_value=[]), patch("app.main.print_document") as print_mock:
            client = build_app().test_client()
            client.post("/login", data={"username": "admin", "password": "test-password"})
            response = client.post("/api/setup", data={"printer_name": "Office Printer", "action": "save"})

        self.assertEqual(response.get_json()["action"], "save")
        self.assertIsNone(response.get_json()["result"])
        print_mock.assert_not_called()

    def test_environment_override_webui_port_is_used(self):
        self.assertEqual(get_webui_port({"WEBUI_PORT": "8081"}), 8081)

    def test_environment_overrides_are_applied_to_runtime_options(self):
        with patch.dict(os.environ, {
            "PRINTER_NAME": "Unraid Printer",
            "PRINTER_HOST": "192.168.50.12",
            "PRINTER_URI": "ipp://192.168.50.12/ipp/print",
            "SCHEDULE_ENABLED": "true",
            "SCHEDULE_TYPE": "weekly",
            "SCHEDULE_HOUR": "9",
            "SCHEDULE_WEEKDAY": "friday",
        }, clear=False):
            options = apply_environment_overrides(build_default_options())

        self.assertEqual(options["printer_name"], "Unraid Printer")
        self.assertEqual(options["printer_host"], "192.168.50.12")
        self.assertEqual(options["schedule_enabled"], True)
        self.assertEqual(options["schedule_type"], "weekly")
        self.assertEqual(options["schedule_hour"], 9)
        self.assertEqual(options["schedule_weekday"], "friday")

    def test_default_options_mark_setup_as_incomplete(self):
        options = build_default_options()
        self.assertFalse(is_setup_complete(options))

    def test_saved_ui_config_wins_over_environment_defaults(self):
        options = {"printer_host": "10.0.0.42"}
        with patch.dict(os.environ, {"PRINTER_HOST": "192.168.50.200"}, clear=False):
            merged = apply_environment_overrides(options)
        self.assertEqual(merged["printer_host"], "10.0.0.42")

    def test_setup_page_contains_printer_form_and_autodiscovery_list(self):
        options = {
            "printer_name": "",
            "printer_host": "",
            "printer_uri": "",
            "discovered_printers": [{"name": "Office Printer", "model": "HP OfficeJet Pro", "host": "192.168.1.50", "uri": "ipp://192.168.1.50/ipp/print"}],
        }
        page = build_setup_page(options)
        self.assertIn("Office Printer", page)
        self.assertIn("HP OfficeJet Pro", page)
        self.assertIn("Keep your ink moving.", page)
        self.assertIn("Save and print test page", page)

    def test_uploaded_document_is_saved_to_persistent_uploads_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            saved_path = save_uploaded_document(io.BytesIO(b"%PDF-1.4\n"), "sample.pdf", temp_dir)
            self.assertTrue(os.path.exists(saved_path))
            self.assertTrue(saved_path.endswith("sample.pdf"))


if __name__ == "__main__":
    unittest.main()
