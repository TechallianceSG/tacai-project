#!/usr/bin/env python3
"""Temporary TACAI public-test gateway.

Routes one public tunnel endpoint to the local TACAI pilot services.
This is intended only for short remote testing windows.
"""

from __future__ import annotations

import argparse
import http.client
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROUTES = [
    ("/useradmin", "127.0.0.1", 8006, "/useradmin"),
    ("/employeeadmin", "127.0.0.1", 8004, "/employeeadmin"),
    ("/masterdata", "127.0.0.1", 8007, "/masterdata"),
    ("/timesheet", "127.0.0.1", 8002, "/timesheet"),
    ("/expense", "127.0.0.1", 8003, "/expense"),
    ("/payroll", "127.0.0.1", 8001, "/payroll"),
    ("/tacpayroll", "127.0.0.1", 8015, "/tacpayroll"),
    ("/interviewready", "127.0.0.1", 8000, "/interviewready"),
    ("/vendorpayables", "127.0.0.1", 8008, "/vendorpayables"),
    ("/billing", "127.0.0.1", 8009, "/billing"),
    ("/customerbilling", "127.0.0.1", 8009, "/customerbilling"),
    ("/fileadmin", "127.0.0.1", 8011, "/fileadmin"),
    ("/portal", "127.0.0.1", 8005, "/portal"),
]
DEFAULT_TARGET = ("127.0.0.1", 8005, "/portal")

URL_REWRITES = [
    ("https://ai.tactokyo.com", "/portal"),
    ("http://127.0.0.1:8005", "/portal"),
    ("http://localhost:8005", "/portal"),
    ("http://192.168.0.27:8005", "/portal"),
    ("https://useradmin.tactokyo.com", "/useradmin"),
    ("http://127.0.0.1:8006", "/useradmin"),
    ("http://localhost:8006", "/useradmin"),
    ("http://192.168.0.27:8006", "/useradmin"),
    ("https://interview.tactokyo.com", "/interviewready"),
    ("http://127.0.0.1:8000", "/interviewready"),
    ("http://localhost:8000", "/interviewready"),
    ("http://192.168.0.27:8000", "/interviewready"),
    ("https://payroll.tactokyo.com", "/payroll"),
    ("http://127.0.0.1:8001", "/payroll"),
    ("http://localhost:8001", "/payroll"),
    ("http://192.168.0.27:8001", "/payroll"),
    ("https://tacpayroll.tactokyo.com", "/tacpayroll"),
    ("http://127.0.0.1:8015", "/tacpayroll"),
    ("http://localhost:8015", "/tacpayroll"),
    ("http://192.168.0.27:8015", "/tacpayroll"),
    ("https://employee.tactokyo.com", "/employeeadmin"),
    ("http://127.0.0.1:8004", "/employeeadmin"),
    ("http://localhost:8004", "/employeeadmin"),
    ("http://192.168.0.27:8004", "/employeeadmin"),
    ("https://masterdata.tactokyo.com", "/masterdata"),
    ("http://127.0.0.1:8007", "/masterdata"),
    ("http://localhost:8007", "/masterdata"),
    ("http://192.168.0.27:8007", "/masterdata"),
    ("https://timesheet.tactokyo.com", "/timesheet"),
    ("http://127.0.0.1:8002", "/timesheet"),
    ("http://localhost:8002", "/timesheet"),
    ("http://192.168.0.27:8002", "/timesheet"),
    ("https://expense.tactokyo.com", "/expense"),
    ("http://127.0.0.1:8003", "/expense"),
    ("http://localhost:8003", "/expense"),
    ("http://192.168.0.27:8003", "/expense"),
    ("https://vendor.tactokyo.com", "/vendorpayables"),
    ("https://vendorpayables.tactokyo.com", "/vendorpayables"),
    ("http://127.0.0.1:8008", "/vendorpayables"),
    ("http://localhost:8008", "/vendorpayables"),
    ("http://192.168.0.27:8008", "/vendorpayables"),
    ("https://billing.tactokyo.com", "/billing"),
    ("https://customerbilling.tactokyo.com", "/billing"),
    ("http://127.0.0.1:8009", "/billing"),
    ("http://localhost:8009", "/billing"),
    ("http://192.168.0.27:8009", "/billing"),
    ("https://fileadmin.tactokyo.com", "/fileadmin"),
    ("http://127.0.0.1:8011", "/fileadmin"),
    ("http://localhost:8011", "/fileadmin"),
    ("http://192.168.0.27:8011", "/fileadmin"),
]


def pct_encode_url(value: str) -> str:
    return value.replace(":", "%3A").replace("/", "%2F")


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def resolve_target(path: str) -> tuple[str, int, str, str]:
    for prefix, host, port, public_prefix in ROUTES:
        if path == prefix or path.startswith(prefix + "/"):
            stripped = path[len(prefix):] or "/"
            return host, port, stripped, public_prefix
    host, port, public_prefix = DEFAULT_TARGET
    return host, port, path, public_prefix


def rewrite_text(text: str, public_prefix: str) -> str:
    for old, new in URL_REWRITES:
        text = text.replace(old, new)

    encoded_rewrites = [
        ("https%3A%2F%2Fai.tactokyo.com", "%2Fportal"),
        ("http%3A%2F%2F127.0.0.1%3A8005", "%2Fportal"),
        ("http%3A%2F%2Flocalhost%3A8005", "%2Fportal"),
        ("https%3A%2F%2Fuseradmin.tactokyo.com", "%2Fuseradmin"),
        ("http%3A%2F%2F127.0.0.1%3A8006", "%2Fuseradmin"),
        ("http%3A%2F%2Flocalhost%3A8006", "%2Fuseradmin"),
        ("https%3A%2F%2Finterview.tactokyo.com", "%2Finterviewready"),
        ("http%3A%2F%2F127.0.0.1%3A8000", "%2Finterviewready"),
        ("http%3A%2F%2Flocalhost%3A8000", "%2Finterviewready"),
        ("https%3A%2F%2Fpayroll.tactokyo.com", "%2Fpayroll"),
        ("http%3A%2F%2F127.0.0.1%3A8001", "%2Fpayroll"),
        ("http%3A%2F%2Flocalhost%3A8001", "%2Fpayroll"),
        ("https%3A%2F%2Femployee.tactokyo.com", "%2Femployeeadmin"),
        ("http%3A%2F%2F127.0.0.1%3A8004", "%2Femployeeadmin"),
        ("http%3A%2F%2Flocalhost%3A8004", "%2Femployeeadmin"),
        ("https%3A%2F%2Fmasterdata.tactokyo.com", "%2Fmasterdata"),
        ("http%3A%2F%2F127.0.0.1%3A8007", "%2Fmasterdata"),
        ("http%3A%2F%2Flocalhost%3A8007", "%2Fmasterdata"),
        ("https%3A%2F%2Ftimesheet.tactokyo.com", "%2Ftimesheet"),
        ("http%3A%2F%2F127.0.0.1%3A8002", "%2Ftimesheet"),
        ("http%3A%2F%2Flocalhost%3A8002", "%2Ftimesheet"),
        ("https%3A%2F%2Fexpense.tactokyo.com", "%2Fexpense"),
        ("http%3A%2F%2F127.0.0.1%3A8003", "%2Fexpense"),
        ("http%3A%2F%2Flocalhost%3A8003", "%2Fexpense"),
        ("http%3A%2F%2F127.0.0.1%3A8008", "%2Fvendorpayables"),
        ("http%3A%2F%2Flocalhost%3A8008", "%2Fvendorpayables"),
        ("http%3A%2F%2F127.0.0.1%3A8009", "%2Fbilling"),
        ("http%3A%2F%2Flocalhost%3A8009", "%2Fbilling"),
        ("https%3A%2F%2Ffileadmin.tactokyo.com", "%2Ffileadmin"),
        ("http%3A%2F%2F127.0.0.1%3A8011", "%2Ffileadmin"),
        ("http%3A%2F%2Flocalhost%3A8011", "%2Ffileadmin"),
    ]
    encoded_rewrites.extend((pct_encode_url(old), pct_encode_url(new)) for old, new in URL_REWRITES)
    for old, new in encoded_rewrites:
        text = text.replace(old, new)

    # Rewrite root-relative links/forms/assets in module pages so they stay under their prefix.
    if public_prefix != "/portal":
        text = re.sub(r'((?:href|src|action)=")/(?!/)', rf'\1{public_prefix}/', text)
        text = re.sub(r"((?:href|src|action)=')/(?!/)", rf"\1{public_prefix}/", text)
    else:
        text = re.sub(r'((?:href|src|action)=")/(?!/)', r'\1/portal/', text)
        text = re.sub(r"((?:href|src|action)=')/(?!/)", r"\1/portal/", text)

    known_prefixes = (
        "/portal",
        "/useradmin",
        "/employeeadmin",
        "/masterdata",
        "/timesheet",
        "/expense",
        "/payroll",
        "/tacpayroll",
        "/interviewready",
        "/vendorpayables",
        "/billing",
        "/customerbilling",
        "/fileadmin",
    )
    for prefix in known_prefixes:
        if prefix == public_prefix:
            continue
        text = text.replace(f'="{public_prefix}{prefix}', f'="{prefix}')
        text = text.replace(f"='{public_prefix}{prefix}", f"='{prefix}")
    return text


def rewrite_location(value: str, public_prefix: str) -> str:
    for old, new in URL_REWRITES:
        if value.startswith(old):
            value = new + value[len(old):]
        value = value.replace(old, new)

    encoded_rewrites = [
        ("https%3A%2F%2Fai.tactokyo.com", "%2Fportal"),
        ("http%3A%2F%2F127.0.0.1%3A8005", "%2Fportal"),
        ("http%3A%2F%2Flocalhost%3A8005", "%2Fportal"),
        ("https%3A%2F%2Fuseradmin.tactokyo.com", "%2Fuseradmin"),
        ("http%3A%2F%2F127.0.0.1%3A8006", "%2Fuseradmin"),
        ("http%3A%2F%2Flocalhost%3A8006", "%2Fuseradmin"),
        ("https%3A%2F%2Finterview.tactokyo.com", "%2Finterviewready"),
        ("http%3A%2F%2F127.0.0.1%3A8000", "%2Finterviewready"),
        ("http%3A%2F%2Flocalhost%3A8000", "%2Finterviewready"),
        ("https%3A%2F%2Fpayroll.tactokyo.com", "%2Fpayroll"),
        ("http%3A%2F%2F127.0.0.1%3A8001", "%2Fpayroll"),
        ("http%3A%2F%2Flocalhost%3A8001", "%2Fpayroll"),
        ("https%3A%2F%2Femployee.tactokyo.com", "%2Femployeeadmin"),
        ("http%3A%2F%2F127.0.0.1%3A8004", "%2Femployeeadmin"),
        ("http%3A%2F%2Flocalhost%3A8004", "%2Femployeeadmin"),
        ("https%3A%2F%2Fmasterdata.tactokyo.com", "%2Fmasterdata"),
        ("http%3A%2F%2F127.0.0.1%3A8007", "%2Fmasterdata"),
        ("http%3A%2F%2Flocalhost%3A8007", "%2Fmasterdata"),
        ("https%3A%2F%2Ftimesheet.tactokyo.com", "%2Ftimesheet"),
        ("http%3A%2F%2F127.0.0.1%3A8002", "%2Ftimesheet"),
        ("http%3A%2F%2Flocalhost%3A8002", "%2Ftimesheet"),
        ("https%3A%2F%2Fexpense.tactokyo.com", "%2Fexpense"),
        ("http%3A%2F%2F127.0.0.1%3A8003", "%2Fexpense"),
        ("http%3A%2F%2Flocalhost%3A8003", "%2Fexpense"),
        ("https%3A%2F%2Fvendor.tactokyo.com", "%2Fvendorpayables"),
        ("https%3A%2F%2Fvendorpayables.tactokyo.com", "%2Fvendorpayables"),
        ("http%3A%2F%2F127.0.0.1%3A8008", "%2Fvendorpayables"),
        ("http%3A%2F%2Flocalhost%3A8008", "%2Fvendorpayables"),
        ("https%3A%2F%2Fbilling.tactokyo.com", "%2Fbilling"),
        ("https%3A%2F%2Fcustomerbilling.tactokyo.com", "%2Fbilling"),
        ("http%3A%2F%2F127.0.0.1%3A8009", "%2Fbilling"),
        ("http%3A%2F%2Flocalhost%3A8009", "%2Fbilling"),
        ("https%3A%2F%2Ffileadmin.tactokyo.com", "%2Ffileadmin"),
        ("http%3A%2F%2F127.0.0.1%3A8011", "%2Ffileadmin"),
        ("http%3A%2F%2Flocalhost%3A8011", "%2Ffileadmin"),
    ]
    encoded_rewrites.extend((pct_encode_url(old), pct_encode_url(new)) for old, new in URL_REWRITES)
    for old, new in encoded_rewrites:
        value = value.replace(old, new)

    known_prefixes = (
        "/portal",
        "/useradmin",
        "/employeeadmin",
        "/masterdata",
        "/timesheet",
        "/expense",
        "/payroll",
        "/tacpayroll",
        "/interviewready",
        "/vendorpayables",
        "/billing",
        "/customerbilling",
        "/fileadmin",
    )
    if value.startswith("/") and not value.startswith(known_prefixes):
        return public_prefix + value
    return value


def rewrite_set_cookie(value: str) -> str:
    # Browser will reject Domain=.tactokyo.com on a temporary tunnel host.
    value = re.sub(r";\s*Domain=[^;]+", "", value, flags=re.IGNORECASE)
    # Local HTTP tunnel tests may not accept Secure cookies. Public HTTPS tunnels can still use them,
    # but stripping Secure makes the temporary gateway work over either HTTP or HTTPS.
    value = re.sub(r";\s*Secure", "", value, flags=re.IGNORECASE)
    return value


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()

    def do_DELETE(self) -> None:
        self._proxy()

    def do_HEAD(self) -> None:
        self._proxy(send_body=False)

    def _proxy(self, send_body: bool = True) -> None:
        parsed = urlsplit(self.path)
        host, port, upstream_path, public_prefix = resolve_target(parsed.path)
        if parsed.query:
            upstream_path = f"{upstream_path}?{parsed.query}"

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(content_length) if content_length else None

        headers = {}
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in HOP_BY_HOP_HEADERS or lower == "host":
                continue
            headers[key] = value
        headers["Host"] = f"{host}:{port}"
        headers["X-Forwarded-Host"] = self.headers.get("Host", "")
        headers["X-Forwarded-Proto"] = "https" if self.headers.get("X-Forwarded-Proto") == "https" else "http"

        # Browser-based remote tests send Origin/Referer for form POSTs using the
        # temporary public tunnel host. The local apps intentionally reject unknown
        # origins, so normalize those headers to the upstream local service origin
        # while this gateway remains the explicit trust boundary for the test window.
        upstream_origin = f"http://{host}:{port}"
        if "Origin" in headers:
            headers["Origin"] = upstream_origin
        if "Referer" in headers:
            headers["Referer"] = upstream_origin + upstream_path

        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            conn.request(self.command, upstream_path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
        except Exception as exc:  # pragma: no cover - operator-facing temporary tool
            message = f"Temporary gateway could not reach {host}:{port}: {exc}\n".encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            if send_body:
                self.wfile.write(message)
            return
        finally:
            conn.close()

        response_headers = resp.getheaders()
        content_type = dict((k.lower(), v) for k, v in response_headers).get("content-type", "")
        if any(kind in content_type for kind in ("text/html", "text/css", "application/javascript", "text/javascript", "application/json")):
            try:
                data = rewrite_text(data.decode("utf-8"), public_prefix).encode("utf-8")
            except UnicodeDecodeError:
                pass

        self.send_response(resp.status, resp.reason)
        for key, value in response_headers:
            lower = key.lower()
            if lower in HOP_BY_HOP_HEADERS or lower == "content-length":
                continue
            if lower == "location":
                value = rewrite_location(value, public_prefix)
            elif lower == "set-cookie":
                value = rewrite_set_cookie(value)
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Temporary TACAI public-test gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), GatewayHandler)
    print(f"TACAI temporary gateway listening on http://{args.host}:{args.port}")
    print("Routes: /portal -> 8005, /useradmin -> 8006, /timesheet -> 8002, /expense -> 8003")
    server.serve_forever()


if __name__ == "__main__":
    main()
