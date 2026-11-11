"""Verified-TLS Aruba Instant REST client. No controller configuration writes."""
from __future__ import annotations
import http.client
import ipaddress
import json
import re
import socket
import ssl
from urllib.parse import urlencode

MAX_RESPONSE = 1024 * 1024
COMMANDS = ("show aps", "show clients", "show network", "show version", "show upgrade")


class ArubaError(Exception):
    """Sanitized communication error."""


class ArubaAuthError(ArubaError):
    """Credentials rejected."""


class ArubaApiDisabled(ArubaError):
    """REST API must be enabled by the controller administrator."""


def validate_host(host: str) -> str:
    host = host.strip()
    if not host or len(host) > 253:
        raise ValueError("Invalid host")
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", host):
        raise ValueError("Invalid host")
    if any(not part or len(part) > 63 or part.startswith("-") or part.endswith("-")
           for part in host.split(".")):
        raise ValueError("Invalid host")
    return host.lower()


def table(text: str) -> list[dict[str, str]]:
    lines = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text).replace("\r", "").splitlines()
    for index, line in enumerate(lines):
        starts = [m.start() for m in re.finditer(r"-{2,}", line)]
        if len(starts) < 3 or index == 0:
            continue
        ends = starts[1:] + [None]
        names = [lines[index - 1][a:b].strip() for a, b in zip(starts, ends)]
        rows = []
        for row in lines[index + 1:]:
            if not row.strip() or row.startswith(("Number of", "Info timestamp")):
                break
            rows.append(dict(zip(names, [row[a:b].strip().strip('"')
                                        for a, b in zip(starts, ends)])))
        return rows
    return []


def number(value: str | None) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match[0]) if match else None


def normalize(outputs: dict[str, str]) -> dict:
    aps = []
    for row in table(outputs["show aps"]):
        aps.append({
            "name": row.get("Name", ""),
            "ip": row.get("IP Address", "").rstrip("*"),
            "controller": "*" in row.get("IP Address", ""),
            "model": row.get("Type", ""),
            "clients": number(row.get("Clients")),
            "channel_5g": row.get("radio0 Channel"),
            "channel_24g": row.get("radio1 Channel"),
            "utilization_5g": number(row.get("radio0 Utilization (%)")),
            "utilization_24g": number(row.get("radio1 Utilization (%)")),
            "noise_5g": number(row.get("radio0 Noise Floor (dBm)")),
            "noise_24g": number(row.get("radio1 Noise Floor (dBm)")),
        })
    ssids = [{
        "name": r.get("ESSID", ""), "profile": r.get("Profile Name", ""),
        "clients": number(r.get("Clients")), "type": r.get("Type"),
        "bands": r.get("Band"), "enabled": r.get("Status") == "Enabled",
        "active": r.get("Active") == "Yes", "security": r.get("Key Management"),
    } for r in table(outputs["show network"])]
    clients = []
    for row in table(outputs["show clients"]):
        quality = re.search(r"\(([^)]+)\)", row.get("Signal", ""))
        clients.append({
            "name": row.get("Name", ""), "ip": row.get("IP Address"),
            "mac": row.get("MAC Address", "").lower(), "ssid": row.get("ESSID"),
            "ap": row.get("Access Point"), "channel": row.get("Channel"),
            "signal": number(row.get("Signal")),
            "signal_quality": quality[1] if quality else None,
            "speed_mbps": number(row.get("Speed (mbps)")),
        })
    version = re.search(r"Version\s+([\w.]+)", outputs["show version"])
    serial = re.search(r"Serial\s*(?:Number|#|Num)?\s*[:=]\s*([A-Za-z0-9-]+)",
                       outputs["show version"], re.I)
    if not aps or not any(ap["name"] and ap["ip"] for ap in aps):
        raise ArubaError("Unsupported access point table")
    return {
        "aps": aps, "ssids": ssids, "clients": clients,
        "serial": serial[1] if serial else None,
        "firmware": version[1] if version else None,
        "upgrade_in_progress": bool(re.search(r"Upgrade in process\s*:\s*Yes",
                                              outputs["show upgrade"], re.I)),
    }


class ArubaClient:
    """Executor-only client; bounded responses and short-lived sessions."""

    def __init__(self, host: str, port: int, tls_name: str, ap_address: str,
                 username: str, password: str) -> None:
        self.host = validate_host(host)
        if not 1 <= port <= 65535:
            raise ValueError("Invalid port")
        self.port = port
        self.tls_name = validate_host(tls_name or host)
        self.ap_address = validate_host(ap_address)
        self._username = username
        self._password = password
        self._context = ssl.create_default_context()

    def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        body = json.dumps(data).encode("utf-8") if data is not None else b""
        host_header = "[" + self.tls_name + "]" if ":" in self.tls_name else self.tls_name
        headers = (f"{method} {path} HTTP/1.1\r\nHost: {host_header}\r\n"
                   "Accept: application/json\r\nContent-Type: application/json\r\n"
                   f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode("ascii")
        try:
            with socket.create_connection((self.host, self.port), timeout=10) as raw:
                with self._context.wrap_socket(raw, server_hostname=self.tls_name) as sock:
                    # Some firmware resets header and body sent in separate writes.
                    sock.sendall(headers + body)
                    response = http.client.HTTPResponse(sock)
                    response.begin()
                    status = response.status
                    payload = response.read(MAX_RESPONSE + 1)
                    response.close()
        except ssl.SSLCertVerificationError:
            raise ArubaError("TLS certificate verification failed") from None
        except (OSError, ssl.SSLError, http.client.HTTPException):
            raise ArubaError("Local controller connection failed") from None
        if len(payload) > MAX_RESPONSE:
            raise ArubaError("Controller response too large")
        if b"not enabled" in payload.lower():
            raise ArubaApiDisabled("REST API is disabled")
        if status in (401, 403):
            raise ArubaAuthError("Authentication rejected")
        if status != 200:
            raise ArubaError("Controller request failed")
        try:
            result = json.loads(payload)
        except (ValueError, UnicodeError):
            raise ArubaError("Invalid controller response") from None
        if not isinstance(result, dict):
            raise ArubaError("Invalid controller response")
        return result

    def read(self) -> dict:
        sid = None
        try:
            login = self._request("POST", "/rest/login",
                                  {"user": self._username, "passwd": self._password})
            sid = login.get("sid")
            if not isinstance(sid, str) or not sid:
                raise ArubaAuthError("Authentication rejected")
            outputs = {}
            for command in COMMANDS:
                query = urlencode({"iap_ip_addr": self.ap_address, "cmd": command, "sid": sid})
                result = self._request("GET", "/rest/show-cmd?" + query)
                if result.get("Status-code") not in (0, None) or result.get("Status") == "Failed":
                    raise ArubaError("Controller read command rejected")
                output = result.get("Command output")
                if not isinstance(output, str):
                    raise ArubaError("Unsupported controller response")
                outputs[command] = output
            return normalize(outputs)
        finally:
            if sid:
                try:
                    self._request("POST", "/rest/logout", {"sid": sid})
                except ArubaError:
                    pass
