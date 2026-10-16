"""Synthetic enterprise API services for the Topcoder Gemini CX challenge.

Every data/action endpoint requires a synthetic bearer token. The mock is for
local challenge evaluation only and must never contain real subscriber data.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parents[1]


def load(name: str):
    return json.loads((BASE / "sample-data" / name).read_text(encoding="utf-8"))


CUSTOMERS = load("customers.json")["customers"]
ACCOUNTS = load("accounts.json")["accounts"]
BILLING = load("billing.json")["billing"]
OUTAGES = load("network-status.json")["outages"]
CASES: dict[str, dict] = {}
KEYS: dict[str, str] = {}
MOCK_LOCK = threading.RLock()


def find(items, key, value):
    return next((item for item in items if item.get(key) == value), None)


def account_for_customer(customer_id: str):
    return find(ACCOUNTS, "customerId", customer_id)


def xml_error(code: str) -> bytes:
    return (
        "<SubscriberStatusResponse><ACCT_NO></ACCT_NO><SVC_NO></SVC_NO>"
        "<SVC_STAT></SVC_STAT><NET_STAT></NET_STAT><ERR_CD>"
        + code
        + "</ERR_CD><RESP_TS>2026-10-16T00:00:00Z</RESP_TS></SubscriberStatusResponse>"
    ).encode("utf-8")


class H(BaseHTTPRequestHandler):
    server_version = "GeminiCXMockServices/1.0"

    def js(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self) -> bytes:
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = -1
        if size < 0 or size > 16384:
            raise ValueError("invalid_body_size")
        return self.rfile.read(size) if size else b"{}"

    def json_body(self) -> dict:
        try:
            data = json.loads(self.body().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_json") from exc
        if not isinstance(data, dict):
            raise ValueError("json_object_required")
        return data

    def principal(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header[7:].strip()
        if not token.startswith("synthetic-"):
            return None
        customer_id = token.removeprefix("synthetic-")
        return find(CUSTOMERS, "customerId", customer_id)

    def require_principal(self):
        principal = self.principal()
        if principal is None:
            self.js(401, {"error": "bearer_authentication_required"})
            return None
        return principal

    @staticmethod
    def is_support(principal) -> bool:
        return "support-agent" in principal.get("roles", [])

    def may_access_account(self, principal, account_id: str) -> bool:
        account = find(ACCOUNTS, "accountId", account_id)
        if not account:
            return False
        return self.is_support(principal) or account.get("customerId") == principal.get("customerId")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        parts = path.strip("/").split("/")

        if path == "/health":
            return self.js(200, {"status": "ok"})
        if len(parts) == 2 and parts == ["api", "customers"]:
            return self.js(404, {"error": "not_found"})
        if len(parts) == 3 and parts[:2] == ["api", "customers"]:
            principal = self.require_principal()
            if principal is None:
                return
            requested_id = parts[2]
            if not self.is_support(principal) and requested_id != principal["customerId"]:
                return self.js(403, {"error": "access_denied"})
            customer = find(CUSTOMERS, "customerId", requested_id)
            if not customer:
                return self.js(404, {"error": "not_found"})
            safe = {k: v for k, v in customer.items() if k not in {"testPassword", "username", "email"}}
            return self.js(200, safe)

        if len(parts) == 3 and parts[:2] == ["api", "accounts"]:
            principal = self.require_principal()
            if principal is None:
                return
            account_id = parts[2]
            if not self.may_access_account(principal, account_id):
                return self.js(403, {"error": "access_denied"})
            account = find(ACCOUNTS, "accountId", account_id)
            return self.js(200, account)

        if len(parts) == 4 and parts[:2] == ["api", "accounts"] and parts[3] == "billing":
            principal = self.require_principal()
            if principal is None:
                return
            account_id = parts[2]
            if not self.may_access_account(principal, account_id):
                return self.js(403, {"error": "access_denied"})
            mode = os.getenv("MOCK_BILLING_MODE", "success")
            if mode == "unavailable":
                return self.js(503, {"error": "billing_unavailable"})
            if mode == "malformed":
                return self.js(200, {"unexpected": True})
            bill = find(BILLING, "accountId", account_id)
            return self.js(200, bill) if bill else self.js(404, {"error": "not_found"})

        if path == "/api/network/outages":
            principal = self.require_principal()
            if principal is None:
                return
            postal_code = parse_qs(parsed.query).get("postalCode", [""])[0]
            if not self.is_support(principal) and postal_code != principal.get("postalCode"):
                return self.js(403, {"error": "access_denied"})
            outage = find(OUTAGES, "postalCode", postal_code)
            return self.js(200, outage or {"postalCode": postal_code, "status": "unknown"})

        return self.js(404, {"error": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/auth/login":
                mode = os.getenv("MOCK_AUTH_MODE", "normal")
                if mode == "unavailable":
                    return self.js(503, {"error": "auth_unavailable"})
                data = self.json_body()
                customer = next(
                    (c for c in CUSTOMERS
                     if c.get("username") == data.get("username")
                     and c.get("testPassword") == data.get("password")),
                    None,
                )
                if not customer:
                    return self.js(401, {"error": "invalid_credentials"})
                return self.js(200, {
                    "accessToken": "expired" if mode == "expired" else "synthetic-" + customer["customerId"],
                    "customerId": customer["customerId"],
                    "accountId": customer.get("accountId"),
                    "roles": customer["roles"],
                    "expiresIn": 0 if mode == "expired" else 3600,
                })

            principal = self.require_principal()
            if principal is None:
                return

            if path == "/api/support-cases":
                if os.getenv("MOCK_CASE_MODE", "success") == "unavailable":
                    return self.js(503, {"error": "case_unavailable"})
                data = self.json_body()
                key = data.get("idempotencyKey")
                account_id = data.get("accountId")
                customer_id = data.get("customerId")
                if not key:
                    return self.js(400, {"error": "idempotency_key_required"})
                if not self.may_access_account(principal, str(account_id or "")):
                    return self.js(403, {"error": "access_denied"})
                account = find(ACCOUNTS, "accountId", account_id)
                if account is None or account.get("customerId") != customer_id:
                    return self.js(403, {"error": "customer_account_mismatch"})
                if not isinstance(data.get("summary"), str) or not data["summary"].strip() or len(data["summary"]) > 240:
                    return self.js(400, {"error": "valid_summary_required"})
                with MOCK_LOCK:
                    if key in KEYS:
                        prior = CASES.get(KEYS[key])
                        if prior is None:
                            return self.js(503, {"error": "idempotency_record_inconsistent"})
                        return self.js(200, prior)
                    case_id = "CASE-" + uuid.uuid4().hex[:8].upper()
                    KEYS[key] = case_id
                    CASES[case_id] = {
                        "caseId": case_id,
                        "status": "open",
                        "customerId": customer_id,
                        "accountId": account_id,
                        "summary": data["summary"][:240],
                        "idempotencyKey": key,
                    }
                    return self.js(201, CASES[case_id])

            if path == "/api/diagnostics":
                data = self.json_body()
                service_id = data.get("serviceId")
                account = account_for_customer(principal["customerId"])
                owned = any(s.get("serviceId") == service_id for s in (account or {}).get("services", []))
                if not self.is_support(principal) and not owned:
                    return self.js(403, {"error": "access_denied"})
                if not service_id:
                    return self.js(400, {"error": "service_id_required"})
                return self.js(200, {
                    "diagnosticId": "DIAG-" + uuid.uuid4().hex[:6].upper(),
                    "serviceId": service_id,
                    "result": "no_device_fault_detected",
                })

            if path == "/api/legacy/subscriber-status":
                mode = os.getenv("MOCK_LEGACY_MODE", "success")
                if mode == "timeout":
                    time.sleep(8)
                if mode == "unavailable":
                    return self.js(503, {"error": "legacy_unavailable"})
                try:
                    root = ET.fromstring(self.body())
                    account_id = root.findtext("AccountNumber") or ""
                    service_id = root.findtext("ServiceNumber") or ""
                except (ET.ParseError, ValueError):
                    return self.js(400, {"error": "malformed_xml_request"})
                if not self.may_access_account(principal, account_id):
                    return self.js(403, {"error": "access_denied"})
                account = find(ACCOUNTS, "accountId", account_id)
                valid_service = account and any(s.get("serviceId") == service_id for s in account.get("services", []))
                if not valid_service:
                    raw = xml_error("102")
                elif mode == "malformed":
                    raw = b"<SubscriberStatusResponse><BROKEN>"
                else:
                    code = "0"
                    raw = (
                        "<SubscriberStatusResponse><ACCT_NO>" + account_id
                        + "</ACCT_NO><SVC_NO>" + service_id
                        + "</SVC_NO><SVC_STAT>A</SVC_STAT><NET_STAT>DEGRADED</NET_STAT>"
                        + "<ERR_CD>" + code + "</ERR_CD><RESP_TS>2026-10-16T00:00:00Z</RESP_TS></SubscriberStatusResponse>"
                    ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/xml")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return

            return self.js(404, {"error": "not_found"})
        except ValueError as exc:
            return self.js(400, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, fmt, *args):
        # Do not log Authorization headers, passwords, or request bodies.
        return


if __name__ == "__main__":
    port = int(os.getenv("MOCK_PORT", "8090"))
    print("Mock services on http://localhost:" + str(port), flush=True)
    ThreadingHTTPServer((os.getenv("MOCK_HOST", "127.0.0.1"), port), H).serve_forever()
