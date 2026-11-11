"""Synthetic tests: no household data, real Home Assistant API imports."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import ssl
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qs, urlsplit

from custom_components.aruba_instant_local.api import (
    ArubaClient, ArubaError, ArubaApiDisabled, ArubaAuthError, COMMANDS,
    number, normalize, table, validate_host,
)


def fixed(headers, rows):
    widths = [max(12, len(h) + 2, *(len(str(row[i])) + 2 for row in rows))
              for i, h in enumerate(headers)]
    line = lambda row: "".join(str(v).ljust(w) for v, w in zip(row, widths))
    return line(headers) + "\n" + line(["-" * (w - 2) for w in widths]) + "\n" + "\n".join(
        line(r) for r in rows) + "\n\nNumber of entries: " + str(len(rows))


OUTPUTS = {
    "show aps": fixed(
        ["Name", "IP Address", "Type", "Clients", "radio0 Channel", "radio1 Channel",
         "radio0 Utilization (%)", "radio1 Utilization (%)", "radio0 Noise Floor (dBm)",
         "radio1 Noise Floor (dBm)"],
        [["Floor one", "192.0.2.2*", "305(indoor)", "1", "36E", "6", "12", "5", "-93", "-88"]]),
    "show clients": fixed(
        ["Name", "IP Address", "MAC Address", "ESSID", "Access Point", "Channel",
         "Signal", "Speed (mbps)"],
        [["", "192.0.2.50", "02:00:00:00:00:01", "Test WiFi", "Floor one", "36E", "42(good)", "433"]]),
    "show network": fixed(
        ["ESSID", "Profile Name", "Clients", "Type", "Band", "Status", "Active", "Key Management"],
        [["Test WiFi", "Test profile", "1", "employee", "all", "Enabled", "Yes", "WPA2-AES"]]),
    "show version": "ArubaOS Version 8.13.3.0\nSerial Number: TESTSERIAL001\n",
    "show upgrade": "Upgrade in process : No\n",
}


class ParserTests(unittest.TestCase):
    def test_fixed_width_preserves_spaces_and_empty_name(self):
        rows = table(OUTPUTS["show clients"])
        self.assertEqual(rows[0]["Name"], "")
        self.assertEqual(rows[0]["ESSID"], "Test WiFi")

    def test_ansi_and_empty_table(self):
        self.assertEqual(table("\x1b[1mNo clients\x1b[0m"), [])

    def test_normalize_realistic_tables(self):
        data = normalize(OUTPUTS)
        self.assertEqual(data["aps"][0]["ip"], "192.0.2.2")
        self.assertTrue(data["aps"][0]["controller"])
        self.assertEqual(data["aps"][0]["noise_5g"], -93)
        self.assertEqual(data["clients"][0]["signal"], 42)
        self.assertEqual(data["clients"][0]["signal_quality"], "good")
        self.assertEqual(data["serial"], "TESTSERIAL001")
        self.assertTrue(data["ssids"][0]["active"])
        self.assertEqual(data["firmware"], "8.13.3.0")
        self.assertFalse(data["upgrade_in_progress"])

    def test_missing_ap_table_rejected(self):
        outputs = {**OUTPUTS, "show aps": "not supported"}
        with self.assertRaises(ArubaError):
            normalize(outputs)

    def test_upgrade_activity_and_missing_serial(self):
        data = normalize({**OUTPUTS, "show upgrade": "Upgrade in process: Yes",
                          "show version": "Version 8.13.3.0"})
        self.assertTrue(data["upgrade_in_progress"])
        self.assertIsNone(data["serial"])

    def test_number_handles_unknown(self):
        self.assertIsNone(number("N/A"))
        self.assertEqual(number("18.5(good)"), 18.5)

    def test_host_validation(self):
        for host in ("192.0.2.2", "controller.example.org", "2001:db8::1"):
            self.assertEqual(validate_host(host), host)
        for host in ("https://controller", "a\r\nPassword: bad", "host:4343", "../x",
                     "bad..example", "-invalid", "", "x" * 64 + ".org"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                validate_host(host)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.client = ArubaClient("192.0.2.2", 4343, "controller.example.org", "192.0.2.3",
                                  "synthetic-user", "synthetic-password")

    def request(self, method, path, data=None):
        if path == "/rest/login":
            return {"sid": "synthetic-token"}
        if path == "/rest/logout":
            return {}
        query = parse_qs(urlsplit(path).query)
        self.assertEqual(query["iap_ip_addr"], ["192.0.2.3"])
        self.assertEqual(query["sid"], ["synthetic-token"])
        return {"Status-code": 0, "Command output": OUTPUTS[query["cmd"][0]]}

    def test_fixed_commands_and_logout(self):
        with patch.object(self.client, "_request", side_effect=self.request) as mock:
            self.assertEqual(len(self.client.read()["aps"]), 1)
        self.assertEqual(mock.call_count, 7)
        self.assertEqual(mock.call_args.args[:2], ("POST", "/rest/logout"))
        commands = [parse_qs(urlsplit(c.args[1]).query)["cmd"][0]
                    for c in mock.call_args_list if c.args[0] == "GET"]
        self.assertEqual(tuple(commands), COMMANDS)

    def test_logout_after_command_failure(self):
        def fail(method, path, data=None):
            if method == "GET":
                raise ArubaError("sanitized")
            return self.request(method, path, data)
        with patch.object(self.client, "_request", side_effect=fail) as mock:
            with self.assertRaises(ArubaError):
                self.client.read()
        self.assertEqual(mock.call_args.args[1], "/rest/logout")

    def test_auth_failure_does_not_logout_without_session(self):
        with patch.object(self.client, "_request", return_value={}) as mock:
            with self.assertRaises(ArubaAuthError):
                self.client.read()
        self.assertEqual(mock.call_count, 1)

    def test_logout_failure_does_not_replace_success(self):
        def request(method, path, data=None):
            if path == "/rest/logout":
                raise ArubaError("logout failed")
            return self.request(method, path, data)
        with patch.object(self.client, "_request", side_effect=request):
            self.assertEqual(len(self.client.read()["ssids"]), 1)

    def test_certificate_verification_is_mandatory(self):
        self.assertEqual(self.client._context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(self.client._context.check_hostname)

    def test_socket_error_is_sanitized(self):
        with patch("socket.create_connection", side_effect=OSError("password=private")):
            with self.assertRaises(ArubaError) as cm:
                self.client._request("POST", "/rest/login", {})
        self.assertNotIn("private", str(cm.exception))

    def test_bounded_http_responses_and_disabled_api(self):
        for status, payload, error in [
            (401, b"{}", ArubaAuthError), (403, b"{}", ArubaAuthError),
            (503, b"REST API not enabled", ArubaApiDisabled),
            (500, b"private error", ArubaError), (200, b"not json", ArubaError),
            (200, b"[]", ArubaError), (200, b"x" * (1024 * 1024 + 1), ArubaError),
        ]:
            with self.subTest(status=status, error=error):
                raw = Mock()
                raw.__enter__ = Mock(return_value=raw)
                raw.__exit__ = Mock(return_value=False)
                sock = Mock()
                sock.__enter__ = Mock(return_value=sock)
                sock.__exit__ = Mock(return_value=False)
                response = Mock(status=status)
                response.read.return_value = payload
                with patch("socket.create_connection", return_value=raw), \
                     patch.object(self.client._context, "wrap_socket", return_value=sock), \
                     patch("http.client.HTTPResponse", return_value=response):
                    with self.assertRaises(error):
                        self.client._request("POST", "/rest/login", {"passwd": "secret"})
                self.assertEqual(sock.sendall.call_count, 1)


class NativeEntityTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = SimpleNamespace(
            entry=SimpleNamespace(entry_id="test_entry", title="Synthetic controller"),
            data=normalize(OUTPUTS), last_update_success=True)
        from custom_components.aruba_instant_local.sensor import ArubaCountSensor, ArubaClientSignalSensor
        from custom_components.aruba_instant_local.binary_sensor import ArubaSsidSensor
        self.count = ArubaCountSensor(self.coordinator, "clients", "Connected clients")
        self.signal = ArubaClientSignalSensor(self.coordinator, "02:00:00:00:00:01")
        self.ssid = ArubaSsidSensor(self.coordinator, "Test profile")

    def test_count_has_no_client_identifiers(self):
        self.assertEqual(self.count.native_value, 1)
        self.assertEqual(self.count.extra_state_attributes, {})

    def test_signal_is_opt_in_and_no_invented_unit(self):
        self.assertFalse(self.signal.entity_registry_enabled_default)
        self.assertIsNone(self.signal.native_unit_of_measurement)
        self.assertEqual(self.signal.native_value, 42)

    def test_disconnect_unavailable_not_zero(self):
        self.coordinator.data["clients"] = []
        self.assertFalse(self.signal.available)
        self.assertIsNone(self.signal.native_value)

    def test_profile_offline(self):
        self.assertTrue(self.ssid.is_on)
        self.coordinator.data["ssids"][0]["active"] = False
        self.assertFalse(self.ssid.is_on)
        self.coordinator.data["ssids"] = []
        self.assertFalse(self.ssid.available)

    def test_poll_failure_marks_entities_unavailable(self):
        self.coordinator.last_update_success = False
        self.assertFalse(self.count.available)
        self.assertFalse(self.signal.available)


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_config_flow_empty_form_and_sanitized_errors(self):
        from custom_components.aruba_instant_local.config_flow import ArubaConfigFlow
        flow = ArubaConfigFlow()
        flow.hass = Mock()
        flow.async_show_form = Mock(side_effect=lambda **kwargs: kwargs)
        self.assertEqual((await flow.async_step_user())["step_id"], "user")
        for error, key in [(ArubaAuthError(), "invalid_auth"), (ArubaApiDisabled(), "api_disabled"),
                           (ArubaError(), "cannot_connect"), (ValueError(), "invalid_input")]:
            with patch("custom_components.aruba_instant_local.config_flow.validate",
                       new=AsyncMock(side_effect=error)):
                result = await flow.async_step_user({"host": "192.0.2.2"})
            self.assertEqual(result["errors"], {"base": key})

    async def test_config_flow_success_uses_vendor_serial(self):
        from custom_components.aruba_instant_local.config_flow import ArubaConfigFlow
        flow = ArubaConfigFlow()
        flow.hass = Mock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = Mock()
        flow._async_abort_entries_match = Mock()
        flow.async_create_entry = Mock(side_effect=lambda **kwargs: kwargs)
        data = {"host": "192.0.2.2", "port": 4343}
        with patch("custom_components.aruba_instant_local.config_flow.validate",
                   new=AsyncMock(return_value=(data, {"serial": "TESTSERIAL001"}))):
            result = await flow.async_step_user(data)
        flow.async_set_unique_id.assert_awaited_once_with("TESTSERIAL001")
        self.assertEqual(result["data"], data)

    async def test_diagnostics_omit_sensitive_values(self):
        from custom_components.aruba_instant_local.diagnostics import async_get_config_entry_diagnostics
        entry = SimpleNamespace(runtime_data=SimpleNamespace(data=normalize(OUTPUTS),
                                                            last_update_success=True))
        result = await async_get_config_entry_diagnostics(None, entry)
        text = json.dumps(result)
        for private in ("Test WiFi", "192.0.2.", "02:00:00:00", "TESTSERIAL001", "password"):
            self.assertNotIn(private, text)


if __name__ == "__main__":
    unittest.main()
