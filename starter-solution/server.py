"""Productionized starter for the Gemini CX/Telco Topcoder challenge.

Uses only Python's standard library. Synthetic services are served by mock-services/server.py.
Authentication, authorization, action confirmation, and idempotency are deterministic app logic;
Gemini is an interpretation aid and never grants permissions.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API = os.getenv("MOCK_API_BASE", "http://127.0.0.1:8090").rstrip("/")
APP_PORT = int(os.getenv("APP_PORT", "8080"))
AI_MODE = os.getenv("AI_MODE", "reviewer").strip().lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "3"))
EVENTS_FILE = Path(os.getenv("EVENTS_FILE", str(Path(__file__).with_name("events.jsonl"))))
ESCALATIONS_FILE = Path(os.getenv("ESCALATIONS_FILE", str(Path(__file__).with_name("escalations.jsonl"))))
MAX_REQUEST_BYTES = 16_384
MAX_MESSAGE_CHARS = 2_000

WRITE_LOCK = threading.Lock()
STATE_LOCK = threading.RLock()
SESSIONS: dict[str, dict[str, Any]] = {}
PENDING_ACTIONS: dict[str, dict[str, Any]] = {}
COMPLETED_ACTIONS: dict[str, dict[str, Any]] = {}
CONVERSATIONS: dict[str, dict[str, Any]] = {}
TRACE_EVENTS: dict[str, list[dict[str, Any]]] = {}


class ServiceError(Exception):
    def __init__(self, service: str, message: str, status: int | None = None):
        super().__init__(message)
        self.service = service
        self.status = status
        self.safe_message = message


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _safe_summary(value: Any, limit: int = 300) -> str:
    """Keep enough context for support while redacting common secret/PII patterns."""
    summary = "".join(ch for ch in str(value) if ch.isprintable())[:max(limit * 2, limit)]
    summary = re.sub(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+", r"\1 [REDACTED]", summary)
    summary = re.sub(
        r"(?i)\b(api[_ -]?key|password|token|secret|authorization|credential)\b"
        r"(?:\s+is)?\s*[:=]?\s+[^\s,;]+",
        r"\1=[REDACTED]", summary)
    summary = re.sub(r"(?i)\b(api[_ -]?key|password|token|secret|authorization|credential)\s*[:=]\s*[^\s,;]+",
                     r"\1=[REDACTED]", summary)
    summary = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED_EMAIL]", summary, flags=re.I)
    summary = re.sub(r"(?<!\w)\+?\d[\d ().-]{8,}\d(?!\w)", "[REDACTED_PHONE]", summary)
    return summary[:limit]


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Remove secrets and sanitize metadata before it reaches logs or traces."""
    if not metadata:
        return {}
    sensitive_fragments = (
        "password", "token", "authorization", "api_key", "apikey", "secret",
        "credential", "testpassword", "email", "sessionid", "session_id",
    )
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
        if any(fragment.replace("_", "") in normalized_key for fragment in sensitive_fragments):
            continue
        if isinstance(value, dict):
            safe[key] = _safe_metadata(value)
        elif isinstance(value, str):
            safe[key] = _safe_summary(value, 240)
        elif isinstance(value, (int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, list):
            safe[key] = [_safe_metadata(x) if isinstance(x, dict) else _safe_summary(x, 240) if isinstance(x, str) else x
                         for x in value[:20]]
    return safe


def _telemetry_session_ref(session_id: str) -> str:
    """Return a stable, non-authenticating reference; never publish the bearer session ID."""
    if not session_id or session_id in {"system", "anonymous"}:
        return session_id or "anonymous"
    return "SESSION-" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12].upper()


def emit(event_type: str, trace_id: str, status: str = "success", *, session_id: str = "system",
         component: str = "starter-app", duration_ms: float | None = None,
         metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {
        "eventId": "EVT-" + uuid.uuid4().hex[:12],
        "traceId": trace_id,
        "sessionId": _telemetry_session_ref(session_id),
        "timestamp": utcnow(),
        "eventType": event_type,
        "component": component,
        "status": status if status in {"success", "failure", "pending", "denied"} else "failure",
    }
    if duration_ms is not None:
        event["durationMs"] = max(0, round(float(duration_ms), 2))
    clean_metadata = _safe_metadata(metadata)
    if clean_metadata:
        event["metadata"] = clean_metadata
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    with WRITE_LOCK:
        EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with EVENTS_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        TRACE_EVENTS.setdefault(trace_id, []).append(event)
    return event


def request_raw(method: str, path: str, *, payload: dict[str, Any] | None = None,
                headers: dict[str, str] | None = None, timeout: float | None = None,
                content_type: str = "application/json") -> tuple[int, bytes, str]:
    body = None
    req_headers = {"Accept": "application/json"}
    req_headers.update(headers or {})
    if content_type == "application/xml":
        req_headers.setdefault("Content-Type", "application/xml")
    if payload is not None:
        if content_type == "application/xml":
            body = payload.get("_xml", "").encode("utf-8")
        else:
            body = json.dumps(payload).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(API + path, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout or REQUEST_TIMEOUT) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            message = json.loads(raw.decode("utf-8")).get("error", f"HTTP {exc.code}")
        except Exception:
            message = f"HTTP {exc.code}"
        raise ServiceError(path.split("/")[2] if len(path.split("/")) > 2 else "enterprise", str(message), exc.code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ServiceError(path.split("/")[2] if len(path.split("/")) > 2 else "enterprise", "service_unavailable") from exc


def call_json(method: str, path: str, *, payload: dict[str, Any] | None = None,
              headers: dict[str, str] | None = None, retry_get: bool = True,
              trace_id: str | None = None, session_id: str = "system",
              component: str = "enterprise-integration") -> dict[str, Any]:
    """Call a mock enterprise endpoint with bounded retries for read-only requests only."""
    attempts = 2 if method == "GET" and retry_get else 1
    last_error: ServiceError | None = None
    for attempt in range(attempts):
        if attempt > 0 and trace_id:
            emit("tool.retry", trace_id, "pending", session_id=session_id, component=component,
                 metadata={"path": path, "attempt": attempt + 1})
        try:
            status, raw, _ = request_raw(method, path, payload=payload, headers=headers)
            data = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(data, dict):
                raise ServiceError(path, "malformed_response", status)
            return data
        except ServiceError as exc:
            last_error = exc
            if attempt + 1 >= attempts or (exc.status is not None and exc.status < 500):
                break
            time.sleep(0.05 * (attempt + 1))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ServiceError(path, "malformed_response") from exc
    assert last_error is not None
    if trace_id:
        emit("tool.failed", trace_id, "failure", session_id=session_id, component=component,
             metadata={"reason": last_error.safe_message, "path": path, "httpStatus": last_error.status})
    raise last_error


def _new_trace() -> str:
    return "TRACE-" + uuid.uuid4().hex[:12].upper()


def login(username: str, password: str) -> dict[str, Any]:
    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        raise ValueError("username_and_password_required")
    result = call_json("POST", "/api/auth/login", payload={"username": username, "password": password}, retry_get=False)
    token = result.get("accessToken")
    customer_id = result.get("customerId")
    roles = result.get("roles", [])
    expires_in = result.get("expiresIn", 0)
    if not token or not customer_id or not isinstance(roles, list) or int(expires_in or 0) <= 0:
        raise ServiceError("authentication", "invalid_or_expired_authentication", 401)
    session_id = secrets.token_urlsafe(24)
    session = {
        "sessionId": session_id,
        "customerId": str(customer_id),
        "accountId": result.get("accountId"),
        "roles": [str(x) for x in roles],
        "accessToken": str(token),  # server-side only; never exposed to model/UI/logs
        "expiresAt": time.time() + int(expires_in),
        "postalCode": None,
        "displayName": None,
        "pendingClarification": None,
    }
    with STATE_LOCK:
        SESSIONS[session_id] = session
        CONVERSATIONS[session_id] = {"messages": [], "lastTraceId": None}
    return {"sessionId": session_id, "customerId": session["customerId"], "accountId": session["accountId"], "roles": session["roles"]}


def require_session(session_id: str | None, trace_id: str) -> dict[str, Any]:
    if not session_id:
        emit("authentication.required", trace_id, "denied", metadata={"reason": "session_missing"})
        raise ServiceError("authentication", "authentication_required", 401)
    with STATE_LOCK:
        session = SESSIONS.get(session_id)
        if not session:
            emit("authentication.failed", trace_id, "denied", session_id=session_id, metadata={"reason": "session_invalid"})
            raise ServiceError("authentication", "invalid_or_expired_session", 401)
        if session["expiresAt"] <= time.time():
            del SESSIONS[session_id]
            emit("authentication.failed", trace_id, "denied", session_id=session_id, metadata={"reason": "session_expired"})
            raise ServiceError("authentication", "invalid_or_expired_session", 401)
        return session


def logout_session(session_id: str) -> dict[str, Any]:
    """Revoke an application session and discard its unfinished confirmations."""
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id_required")
    trace_id = _new_trace()
    with STATE_LOCK:
        session = SESSIONS.pop(session_id, None)
        CONVERSATIONS.pop(session_id, None)
        for key, pending in list(PENDING_ACTIONS.items()):
            if pending.get("sessionId") == session_id and pending.get("state", "pending") != "executing":
                PENDING_ACTIONS.pop(key, None)
    emit("session.ended", trace_id, "success" if session else "denied",
         session_id=session_id if session else "anonymous",
         metadata={"reason": "user_logout" if session else "session_not_active"})
    return {"status": "signed_out", "traceId": trace_id}


def _is_support(session: dict[str, Any]) -> bool:
    return "support-agent" in session.get("roles", [])


def _session_headers(session: dict[str, Any]) -> dict[str, str]:
    token = session.get("accessToken")
    if not isinstance(token, str) or not token:
        raise ServiceError("authentication", "invalid_or_expired_authentication", 401)
    return {"Authorization": "Bearer " + token}


def require_operations_session(session_id: str | None) -> dict[str, Any]:
    trace_id = _new_trace()
    session = require_session(session_id, trace_id)
    if not _is_support(session):
        emit("authorization.denied", trace_id, "denied", session_id=session["sessionId"],
             metadata={"reason": "operations_role_required"})
        raise ServiceError("authorization", "operations_access_denied", 403)
    return session


def authorized_account(session: dict[str, Any], requested_account: str | None, trace_id: str) -> str:
    requested_account = requested_account or session.get("accountId")
    if not requested_account:
        raise ServiceError("authorization", "account_id_required", 400)
    if not _is_support(session) and requested_account != session.get("accountId"):
        emit("authorization.denied", trace_id, "denied", session_id=session["sessionId"],
             metadata={"requestedAccount": requested_account, "reason": "record_ownership_mismatch"})
        raise ServiceError("authorization", "access_denied", 403)
    emit("authorization.allowed", trace_id, session_id=session["sessionId"], component="authorization",
         metadata={"scope": "account", "role": "support-agent" if _is_support(session) else "customer"})
    return str(requested_account)


def _profile(session: dict[str, Any], trace_id: str) -> dict[str, Any]:
    emit("tool.invoked", trace_id, "pending", session_id=session["sessionId"], component="customer-profile")
    data = call_json("GET", "/api/customers/" + urllib.parse.quote(session["customerId"], safe=""),
                     headers=_session_headers(session), trace_id=trace_id, session_id=session["sessionId"], component="customer-profile")
    # Keep only the fields required by business logic; synthetic auth attributes are never propagated.
    safe = {"customerId": data.get("customerId"), "name": data.get("name"), "postalCode": data.get("postalCode"), "accountId": data.get("accountId")}
    if safe["customerId"] != session.get("customerId"):
        raise ServiceError("customer-profile", "profile_identity_mismatch", 403)
    if not safe["customerId"]:
        raise ServiceError("customer-profile", "malformed_profile")
    session["postalCode"] = safe.get("postalCode")
    session["displayName"] = safe.get("name")
    emit("tool.completed", trace_id, session_id=session["sessionId"], component="customer-profile", metadata={"fields": [k for k, v in safe.items() if v is not None]})
    return safe


def _account(session: dict[str, Any], account_id: str, trace_id: str) -> dict[str, Any]:
    emit("tool.invoked", trace_id, "pending", session_id=session["sessionId"], component="account-service", metadata={"accountId": account_id})
    data = call_json("GET", "/api/accounts/" + urllib.parse.quote(account_id, safe=""),
                     headers=_session_headers(session), trace_id=trace_id, session_id=session["sessionId"], component="account-service")
    if not _is_support(session) and data.get("customerId") != session.get("customerId"):
        emit("authorization.denied", trace_id, "denied", session_id=session["sessionId"], metadata={"reason": "account_owner_mismatch"})
        raise ServiceError("authorization", "access_denied", 403)
    if data.get("accountId") != account_id:
        raise ServiceError("account-service", "malformed_account_response")
    emit("tool.completed", trace_id, session_id=session["sessionId"], component="account-service", metadata={"accountId": account_id})
    return data


def _billing(account_id: str, session: dict[str, Any], trace_id: str) -> dict[str, Any]:
    emit("tool.invoked", trace_id, "pending", session_id=session["sessionId"], component="billing-service", metadata={"accountId": account_id})
    data = call_json("GET", f"/api/accounts/{urllib.parse.quote(account_id, safe='')}/billing",
                     headers=_session_headers(session), trace_id=trace_id, session_id=session["sessionId"], component="billing-service")
    total = data.get("total")
    if (data.get("accountId") != account_id or not isinstance(total, (int, float))
            or isinstance(total, bool) or not math.isfinite(float(total)) or total < 0
            or not isinstance(data.get("items"), list)):
        raise ServiceError("billing-service", "malformed_response")
    emit("tool.completed", trace_id, session_id=session["sessionId"], component="billing-service", metadata={"accountId": account_id})
    return data


def _network(postal_code: str, session: dict[str, Any], trace_id: str) -> dict[str, Any]:
    emit("tool.invoked", trace_id, "pending", session_id=session["sessionId"], component="network-diagnostics")
    query = urllib.parse.urlencode({"postalCode": postal_code})
    data = call_json("GET", "/api/network/outages?" + query,
                     headers=_session_headers(session), trace_id=trace_id, session_id=session["sessionId"], component="network-diagnostics")
    if data.get("postalCode") != postal_code or "status" not in data:
        raise ServiceError("network-diagnostics", "malformed_response")
    emit("tool.completed", trace_id, session_id=session["sessionId"], component="network-diagnostics", metadata={"status": data.get("status")})
    return data


def _legacy_status(account_id: str, service_id: str, session: dict[str, Any], trace_id: str) -> dict[str, Any]:
    emit("tool.invoked", trace_id, "pending", session_id=session["sessionId"], component="legacy-adapter", metadata={"accountId": account_id})
    root = ET.Element("SubscriberStatusRequest")
    ET.SubElement(root, "AccountNumber").text = account_id
    ET.SubElement(root, "ServiceNumber").text = service_id
    xml_body = ET.tostring(root, encoding="unicode")
    status, raw, content_type = request_raw("POST", "/api/legacy/subscriber-status", payload={"_xml": xml_body},
                                            headers=_session_headers(session), content_type="application/xml")
    try:
        data = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ServiceError("legacy-service", "malformed_legacy_response", status) from exc
    normalized = {
        "accountId": data.findtext("ACCT_NO"),
        "serviceId": data.findtext("SVC_NO"),
        "serviceStatus": data.findtext("SVC_STAT") or "unknown",
        "networkStatus": data.findtext("NET_STAT") or "unknown",
        "errorCode": data.findtext("ERR_CD") or "900",
        "responseTimestamp": data.findtext("RESP_TS"),
    }
    if normalized["accountId"] != account_id or normalized["serviceId"] != service_id:
        raise ServiceError("legacy-service", "legacy_response_identity_mismatch")
    code = normalized["errorCode"]
    if code != "0":
        labels = {"101": "account_not_found", "102": "service_not_found", "205": "legacy_auth_rejected", "301": "legacy_required_field_missing", "429": "legacy_rate_limited", "503": "legacy_unavailable", "900": "legacy_unknown_error"}
        normalized["error"] = labels.get(code, "legacy_error")
    emit("tool.completed" if code == "0" else "tool.failed", trace_id,
         "success" if code == "0" else "failure", session_id=session["sessionId"], component="legacy-adapter",
         metadata={"errorCode": code, "serviceStatus": normalized["serviceStatus"], "networkStatus": normalized["networkStatus"]})
    return normalized


def _gemini_intent(message: str, prior_messages: list[dict[str, str]]) -> dict[str, Any]:
    """Call Gemini REST; return a strictly validated intent object. Raises ServiceError on failure."""
    if not GEMINI_API_KEY:
        raise ServiceError("gemini", "gemini_api_key_missing")
    prompt = {
        "systemInstruction": {"parts": [{"text": (
            "You classify synthetic telecom customer-support messages. Return only one JSON object with keys "
            "intent, accountId, serviceType, postalCode, issueSummary, clarificationNeeded. "
            "intent must be one of account_plan, billing, service_issue, legacy_status, create_case, other. "
            "Do not authorize users, claim tools ran, invent data, or execute actions. accountId is only an extraction "
            "from explicit user text; if not explicitly provided return null. serviceType is home-internet, mobile, or null. "
            "clarificationNeeded is a boolean. issueSummary is a concise string."
        )}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps({
            "message": _safe_summary(message, MAX_MESSAGE_CHARS),
            "recent_context": [
                {"role": item.get("role", "user"),
                 "content": _safe_summary(item.get("content", ""), 300)}
                for item in prior_messages[-6:] if item.get("role") == "user"
            ],
        }, ensure_ascii=False)}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    # Send the API key in a header rather than the URL so it is less likely to appear in URL logs.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(GEMINI_MODEL, safe='')}:generateContent"
    req = urllib.request.Request(url, data=json.dumps(prompt).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
                                 method="POST")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=float(os.getenv("GEMINI_TIMEOUT", "8"))) as response:
            response_data = json.loads(response.read())
        raw_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw_text)
    except Exception as exc:
        raise ServiceError("gemini", "gemini_provider_failure") from exc
    allowed = {"account_plan", "billing", "service_issue", "legacy_status", "create_case", "other"}
    if not isinstance(parsed, dict) or parsed.get("intent") not in allowed:
        raise ServiceError("gemini", "invalid_model_output")
    service_type = parsed.get("serviceType")
    if service_type not in {None, "home-internet", "mobile"}:
        service_type = None
    account_id = parsed.get("accountId")
    if account_id is not None and (not isinstance(account_id, str) or not re.fullmatch(r"ACC-[0-9]{4}", account_id)):
        account_id = None
    result = {
        "intent": parsed["intent"],
        "accountId": account_id,
        "serviceType": service_type,
        "postalCode": parsed.get("postalCode") if isinstance(parsed.get("postalCode"), str) and re.fullmatch(r"\d{5}", parsed.get("postalCode")) else None,
        "issueSummary": _safe_summary(parsed.get("issueSummary") or message, 240),
        "clarificationNeeded": parsed.get("clarificationNeeded") is True,
    }
    result["_model"] = GEMINI_MODEL
    result["_durationMs"] = (time.monotonic() - started) * 1000
    return result


def _negates_support_case(message: str) -> bool:
    """Detect clear negative intent so either classifier cannot create a case against the user's wording."""
    return bool(
        re.search(r"\b(?:do not|don't|dont|never|no need to|avoid|cancel|stop)\b.{0,50}\b(?:create|open|raise|submit|file|want|need)\b.{0,35}\b(?:support\s+case|case|ticket)\b", message, re.I)
        or re.search(r"\b(?:no|not)\s+(?:support\s+)?(?:case|ticket)\b", message, re.I)
    )


def _deterministic_intent(message: str) -> dict[str, Any]:
    """Deterministic reviewer/degraded classifier; actions still go through real tools and controls."""
    text = message.lower()
    acc_match = re.search(r"\bACC-[0-9]{4}\b", message, re.I)
    account_id = acc_match.group(0).upper() if acc_match else None
    service = "home-internet" if any(x in text for x in ("internet", "broadband", "wifi", "wi-fi", "router")) else None
    if any(x in text for x in ("bill", "billing", "charge", "invoice", "amount due")):
        intent = "billing"
    elif any(x in text for x in ("create a case", "create support", "support case", "open a ticket", "raise a ticket", "create ticket")):
        intent = "create_case"
    elif any(x in text for x in ("legacy", "subscriber status", "line status", "service status")):
        intent = "legacy_status"
    elif any(x in text for x in ("plan", "subscription", "currently using", "my package")):
        intent = "account_plan"
    elif any(x in text for x in ("not working", "not working", "unavailable", "down", "no connection", "slow", "outage", "disconnect")):
        intent = "service_issue"
    elif text.strip() in {"internet", "home internet", "mobile", "home broadband", "wifi", "wi-fi"}:
        intent = "service_issue"
    else:
        intent = "other"
    service_type = "mobile" if "mobile" in text and service is None else service
    return {"intent": intent, "accountId": account_id, "serviceType": service_type,
            "postalCode": None, "issueSummary": message.strip()[:300], "clarificationNeeded": False}


def classify(message: str, session_id: str, trace_id: str) -> tuple[dict[str, Any], str]:
    mode = AI_MODE
    with STATE_LOCK:
        history = list(CONVERSATIONS.get(session_id, {}).get("messages", []))
    if mode == "live":
        try:
            data = _gemini_intent(message, history)
            emit("gemini.completed", trace_id, session_id=session_id, component="gemini", duration_ms=data.pop("_durationMs", None), metadata={"model": data.pop("_model", GEMINI_MODEL), "intent": data.get("intent")})
            return data, "live"
        except ServiceError as exc:
            emit("gemini.failure", trace_id, "failure", session_id=session_id, component="gemini", metadata={"reason": exc.safe_message})
            return _deterministic_intent(message), "degraded"
    return _deterministic_intent(message), "reviewer"


def _escalate(trace_id: str, session_id: str, request_summary: str, reason: str,
              completed_steps: list[str], next_step: str, customer_id: str | None = None,
              pending_action: dict[str, Any] | None = None) -> dict[str, Any]:
    events = get_trace(trace_id).get("events", [])
    accessed = []
    failed = []
    evidence = []
    for event in events:
        event_type = event.get("eventType")
        event_metadata = event.get("metadata", {})
        component = event_metadata.get("service") if event_type in {"workflow.failed", "integration.failure"} else event.get("component")
        if event_type in {"tool.invoked", "tool.completed", "tool.failed", "action.failed", "integration.failure"} and component:
            if component not in accessed:
                accessed.append(component)
        if event_type in {"tool.failed", "action.failed", "integration.failure"} or (
            event_type == "workflow.failed" and event.get("status") == "failure"
        ):
            failed.append({"component": component or "unknown", "eventType": event_type,
                           "status": event.get("status", "failure"),
                           "metadata": event_metadata})
        if event_type in {"tool.completed", "tool.failed", "integration.failure", "authorization.denied",
                          "confirmation.received", "action.failed", "gemini.failure"}:
            evidence.append({"eventId": event.get("eventId"), "eventType": event_type,
                             "component": component, "status": event.get("status"),
                             "metadata": event.get("metadata", {})})
    record = {
        "escalationId": "ESC-" + uuid.uuid4().hex[:10].upper(),
        "traceId": trace_id,
        "customerId": customer_id,
        "requestSummary": _safe_summary(request_summary, 300),
        "verifiedContext": {"customerId": customer_id, "authenticatedSession": bool(session_id and session_id not in {"system", "anonymous"})},
        "completedSteps": list(dict.fromkeys(completed_steps + [
            f"{event.get('component')} completed" for event in events
            if event.get("eventType") == "tool.completed" and event.get("component")
        ]))[:30],
        "enterpriseSystemsAccessed": accessed[:20],
        "evidence": evidence[-30:],
        "failedTools": failed[-20:],
        "errorSummary": _safe_summary(reason, 240),
        "reason": _safe_summary(reason, 240),
        "pendingAction": _safe_metadata(pending_action) if pending_action else None,
        "recommendedNextStep": _safe_summary(next_step, 240),
        "createdAt": utcnow(),
    }
    with WRITE_LOCK:
        ESCALATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with ESCALATIONS_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    emit("escalation.created", trace_id, "pending", session_id=session_id, component="escalation",
         metadata={"escalationId": record["escalationId"], "reason": reason,
                   "failedToolCount": len(failed), "systemsAccessed": accessed})
    return record


def _respond(answer: str, trace_id: str, session: dict[str, Any] | None, *, status: str = "resolved",
             sources: list[str] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"traceId": trace_id, "answer": answer, "status": status,
                              "aiMode": "reviewer", "sources": sources or []}
    if session:
        result["sessionId"] = session["sessionId"]
    if extra:
        result.update(extra)
    return result


def handle_chat(message: str, session_id: str | None) -> dict[str, Any]:
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message_required")
    if len(message) > MAX_MESSAGE_CHARS:
        raise ValueError("message_too_long")
    message = message.strip()
    workflow_started = time.monotonic()
    trace_id = _new_trace()
    emit("request.received", trace_id, metadata={"messageLength": len(message)})
    session: dict[str, Any] | None = None
    if session_id:
        session = require_session(session_id, trace_id)
    # Resume the same service-issue workflow after a clarification reply.
    original_message = message
    if session:
        prior = session.get("pendingClarification")
        if prior:
            message = prior + " " + message
            session["pendingClarification"] = None
    intent, actual_mode = classify(message, session_id or "anonymous", trace_id)
    emit("agent.invoked", trace_id, session_id=session_id or "anonymous", component="intent-classifier",
         metadata={"mode": actual_mode, "intent": intent["intent"]})
    emit("agent.invoked", trace_id, session_id=session_id or "anonymous", component="workflow-orchestrator",
         metadata={"intent": intent["intent"]})
    emit("intent.classified", trace_id, session_id=session_id or "anonymous", metadata={"intent": intent["intent"], "aiMode": actual_mode})
    if session:
        with STATE_LOCK:
            conv = CONVERSATIONS.setdefault(session_id, {"messages": [], "lastTraceId": None})
            conv["messages"].append({"role": "user", "content": original_message[:300]})
            conv["lastTraceId"] = trace_id
            conv["messages"] = conv["messages"][-12:]
    result = _respond("", trace_id, session, status="resolved", extra={"intent": intent["intent"], "aiMode": actual_mode})
    action_rejected = intent["intent"] == "create_case" and _negates_support_case(original_message)

    if action_rejected:
        if session:
            with STATE_LOCK:
                for key, pending_action in list(PENDING_ACTIONS.items()):
                    if pending_action.get("sessionId") == session_id and pending_action.get("state", "pending") == "pending":
                        PENDING_ACTIONS.pop(key, None)
                        emit("action.cancelled", trace_id, session_id=session_id, component="case-management",
                             metadata={"reason": "customer_declined_case"})
        result.update(answer="Understood. I will not create a support case.", status="resolved", intent="action_declined")
    elif intent["intent"] == "other":
        if session:
            session["pendingClarification"] = original_message
        result.update(answer="I can help with your plan, bill, internet/mobile service issue, subscriber status, or support case. Which of these would you like to work on?", status="clarification")
        emit("clarification.requested", trace_id, "pending", session_id=session_id or "anonymous", metadata={"field": "intent"})
    elif intent.get("clarificationNeeded") or (intent["intent"] == "service_issue" and not intent.get("serviceType")):
        missing_field = "details"
        if intent["intent"] == "service_issue" and not intent.get("serviceType"):
            question = "Which service is affected: home internet or mobile?"
            missing_field = "serviceType"
        elif intent["intent"] == "billing":
            question = "Are you checking the current bill amount, or is there a particular charge you want support to review? This demo can verify the current bill and escalate a dispute."
            missing_field = "billingQuestion"
        elif intent["intent"] == "create_case":
            question = "What issue summary should I include in the support case?"
            missing_field = "issueSummary"
        elif intent["intent"] == "legacy_status":
            question = "Which service do you want checked: home internet or mobile?"
            missing_field = "serviceType"
        else:
            question = "Could you provide the specific detail needed to check your request?"
        if session:
            session["pendingClarification"] = original_message
        result.update(answer=question, status="clarification", missingFields=[missing_field])
        emit("clarification.requested", trace_id, "pending", session_id=session_id or "anonymous", metadata={"field": missing_field})
    else:
        # Protected intents must have authenticated context before any account/API access.
        if not session:
            emit("authentication.required", trace_id, "denied", metadata={"intent": intent["intent"]})
            result.update(answer="Please sign in before I access account or service information.", status="authentication_required", httpStatus=401)
        else:
            try:
                account_id = authorized_account(session, intent.get("accountId"), trace_id)
                if intent["intent"] == "account_plan":
                    account = _account(session, account_id, trace_id)
                    plan = account.get("plan")
                    if not isinstance(plan, dict) or not plan.get("name"):
                        raise ServiceError("account-service", "plan_information_unavailable")
                    result.update(answer=f"Your current plan is {plan['name']} (account {account_id}). This information came from the account service.", status="resolved", sources=["account-service"], data={"accountId": account_id, "plan": plan})
                elif intent["intent"] == "billing":
                    data = _billing(account_id, session, trace_id)
                    result.update(answer=f"Your bill for {data.get('period', 'the listed period')} is ${float(data['total']):.2f}. The amount is from the billing service; line items are available in the returned data.", status="resolved", sources=["billing-service"], data=data)
                elif intent["intent"] == "legacy_status":
                    account = _account(session, account_id, trace_id)
                    services = account.get("services") or []
                    service_id = next((s.get("serviceId") for s in services if s.get("serviceId")), None)
                    if not service_id:
                        raise ServiceError("account-service", "service_id_unavailable")
                    legacy = _legacy_status(account_id, service_id, session, trace_id)
                    if legacy.get("error"):
                        escalation = _escalate(
                            trace_id, session["sessionId"], original_message, str(legacy["error"]),
                            ["customer authenticated", "account ownership verified", "legacy response normalized"],
                            "Support should inspect the legacy response/error code and verify subscriber status before giving a definitive answer.",
                            session["customerId"])
                        result.update(
                            answer=f"The legacy subscriber service returned {legacy['error']}. I could not verify the status, so I escalated the request.",
                            status="escalated", sources=["account-service", "legacy-service"], data=legacy, escalation=escalation)
                    else:
                        result.update(answer=f"Legacy subscriber status: service {legacy['serviceStatus']}; network status {legacy['networkStatus']}.", status="resolved", sources=["legacy-service"], data=legacy)
                elif intent["intent"] == "service_issue":
                    profile = _profile(session, trace_id)
                    # profile ownership is tied to the authenticated identity, never to model text.
                    if profile.get("accountId") != session.get("accountId") and not _is_support(session):
                        raise ServiceError("authorization", "access_denied", 403)
                    account = _account(session, account_id, trace_id)
                    postal = profile.get("postalCode")
                    network = _network(str(postal), session, trace_id) if postal else {"status": "unknown", "postalCode": None}
                    services = account.get("services") or []
                    service_id = next((s.get("serviceId") for s in services if s.get("type") == intent.get("serviceType")), None)
                    legacy = None
                    legacy_error: ServiceError | None = None
                    if service_id:
                        try:
                            legacy = _legacy_status(account_id, service_id, session, trace_id)
                        except ServiceError as legacy_exc:
                            legacy_error = legacy_exc
                            emit("tool.failed", trace_id, "failure", session_id=session["sessionId"], component="legacy-adapter",
                                 metadata={"reason": legacy_exc.safe_message})
                    if network.get("status") in {"degraded", "outage", "down"}:
                        answer = f"The network service reports {network['status']} for postal code {postal}."
                        if network.get("incidentId"):
                            answer += f" Incident: {network['incidentId']}."
                        if legacy_error or (legacy and legacy.get("error")):
                            answer += " The legacy check was not fully verified, so support may need to follow up."
                        result.update(answer=answer, status="resolved",
                                      sources=["customer-profile", "account-service", "network-diagnostics"] + (["legacy-service"] if legacy or legacy_error else []),
                                      data={"network": network, "legacy": legacy})
                    elif legacy_error or (legacy and legacy.get("error")):
                        reason = legacy_error.safe_message if legacy_error else str(legacy.get("error"))
                        escalation = _escalate(
                            trace_id, session["sessionId"], original_message, reason,
                            ["customer authenticated", "customer profile verified", "account service queried", "network status queried"],
                            "Support should inspect the legacy telecom integration and continue only after verifying subscriber status.",
                            session["customerId"])
                        result.update(
                            answer="I could not verify the subscriber status because a required legacy check failed. I have escalated the request rather than treating the service as healthy.",
                            status="escalated", sources=["customer-profile", "account-service", "network-diagnostics", "legacy-service"],
                            data={"network": network, "legacy": legacy}, escalation=escalation)
                    else:
                        answer = "The available network and legacy checks did not confirm a current outage. I can create a support case if you confirm."
                        result.update(answer=answer, status="resolved",
                                      sources=["customer-profile", "account-service", "network-diagnostics"] + (["legacy-service"] if legacy else []),
                                      data={"network": network, "legacy": legacy})
                elif intent["intent"] == "create_case":
                    # A request may be explicit, but no consequential call occurs before confirmation.
                    pending_key = session_id + ":" + hashlib.sha256((account_id + "|" + re.sub(r"\s+", " ", original_message.lower())).encode()).hexdigest()[:24]
                    with STATE_LOCK:
                        done = COMPLETED_ACTIONS.get(pending_key)
                        pending = PENDING_ACTIONS.get(pending_key)
                        if not done and not pending:
                            summary = _safe_summary(intent.get("issueSummary") or original_message, 240)
                            confirmation_id = "CONF-" + uuid.uuid4().hex[:10].upper()
                            action = {"type": "create_support_case", "accountId": account_id, "customerId": session["customerId"], "summary": summary[:240], "idempotencyKey": pending_key}
                            pending = {"confirmationId": confirmation_id, "sessionId": session_id, "action": action,
                                       "summary": f"I will create a support case for account {account_id}: {summary[:200]}. Please confirm before I submit it.",
                                       "traceId": trace_id, "expiresAt": time.time() + 600, "state": "pending"}
                            PENDING_ACTIONS[pending_key] = pending
                    if done:
                        result.update(answer="This support case was already created. I will not create a duplicate.", status="resolved", data=done, sources=["case-management"], actionAlreadyCompleted=True)
                    elif pending:
                        if pending.get("state") == "executing":
                            result.update(answer="This support-case request is already being processed. Please wait for its outcome.", status="pending")
                        else:
                            emit("confirmation.requested", trace_id, "pending", session_id=session_id, metadata={"actionType": "create_support_case"})
                            result.update(answer=pending["summary"], status="confirmation_required", confirmationId=pending["confirmationId"], action=pending["action"])
                else:
                    result.update(answer="I could not map that request to a supported workflow. Please rephrase or ask for support.", status="clarification")
            except ServiceError as exc:
                status_code = exc.status or (403 if exc.service == "authorization" else 503)
                emit("integration.failure", trace_id, "denied" if status_code in {401, 403} else "failure", session_id=session["sessionId"], component=exc.service, metadata={"reason": exc.safe_message, "httpStatus": status_code})
                if status_code >= 500 or exc.service not in {"authorization", "authentication"}:
                    escalation = _escalate(trace_id, session["sessionId"], original_message, exc.safe_message, ["request received", "intent classified"], "Support representative should inspect the trace and verify the affected integration.", session["customerId"])
                    result.update(answer="I could not safely complete this request because a required service did not return a verifiable result. I recorded an escalation for support.", status="escalated", escalation=escalation, httpStatus=status_code)
                else:
                    result.update(answer="I cannot access that record or action with this session.", status="access_denied" if status_code == 403 else "authentication_required", httpStatus=status_code)
            except Exception:
                emit("workflow.failed", trace_id, "failure", session_id=session["sessionId"],
                     metadata={"service": "application", "reason": "internal_processing_failure"})
                escalation = _escalate(
                    trace_id, session["sessionId"], original_message, "internal_processing_failure",
                    ["request received", "intent classified"],
                    "Support should inspect the sanitized trace and retry only after the root cause is understood.",
                    session["customerId"])
                result.update(answer="An internal processing issue prevented safe completion. The request was escalated for review.",
                              status="escalated", escalation=escalation)
    result["aiMode"] = actual_mode
    final_status = result.get("status")
    if final_status == "resolved":
        final_event, final_state = "workflow.resolved", "success"
    elif final_status == "escalated":
        final_event, final_state = "workflow.escalated", "pending"
    elif final_status == "clarification":
        final_event, final_state = "workflow.clarification", "pending"
    elif final_status in {"confirmation_required", "pending"}:
        final_event, final_state = "workflow.pending_confirmation", "pending"
    elif final_status == "cancelled":
        final_event, final_state = "workflow.cancelled", "success"
    else:
        final_event, final_state = "workflow.failed", "failure"
    emit(final_event, trace_id, final_state,
         session_id=session_id or "anonymous", duration_ms=(time.monotonic() - workflow_started) * 1000,
         metadata={"intent": intent["intent"], "status": final_status})
    if session:
        with STATE_LOCK:
            CONVERSATIONS.setdefault(session_id, {"messages": [], "lastTraceId": None})["messages"].append({"role": "assistant", "content": str(result.get("answer", ""))[:300]})
    return result


def confirm_action(session_id: str, confirmation_id: str, confirmed: bool) -> dict[str, Any]:
    workflow_started = time.monotonic()
    trace_id = _new_trace()
    session = require_session(session_id, trace_id)
    emit("request.received", trace_id, session_id=session_id, metadata={"requestType": "action_confirmation"})
    with STATE_LOCK:
        match = next(((key, value) for key, value in PENDING_ACTIONS.items()
                      if value.get("confirmationId") == confirmation_id), None)
    if not match:
        raise ServiceError("case-management", "confirmation_not_found_or_expired", 404)
    action_key, pending = match
    if pending["sessionId"] != session_id:
        emit("authorization.denied", trace_id, "denied", session_id=session_id, metadata={"reason": "confirmation_owner_mismatch"})
        raise ServiceError("authorization", "confirmation_access_denied", 403)
    account_id = authorized_account(session, pending["action"].get("accountId"), trace_id) if confirmed else None
    if confirmed and account_id != pending["action"].get("accountId"):
        raise ServiceError("authorization", "access_denied", 403)
    with STATE_LOCK:
        current = PENDING_ACTIONS.get(action_key)
        if current is not pending:
            completed = COMPLETED_ACTIONS.get(action_key)
            if completed:
                return {"traceId": trace_id, "status": "resolved",
                        "answer": f"Support case {completed['caseId']} was already created and verified.",
                        "data": completed, "sources": ["case-management"], "aiMode": "reviewer"}
            raise ServiceError("case-management", "confirmation_not_found_or_expired", 404)
        if pending["expiresAt"] <= time.time():
            PENDING_ACTIONS.pop(action_key, None)
            raise ServiceError("case-management", "confirmation_expired", 410)
        if pending.get("state", "pending") == "executing":
            raise ServiceError("case-management", "action_already_in_progress", 409)
        if confirmed:
            pending["state"] = "executing"
        else:
            PENDING_ACTIONS.pop(action_key, None)
    emit("confirmation.received", trace_id, session_id=session_id, metadata={"confirmed": bool(confirmed)})
    if not confirmed:
        emit("action.cancelled", trace_id, session_id=session_id, component="case-management", metadata={"actionType": "create_support_case"})
        emit("workflow.cancelled", trace_id, "cancelled", session_id=session_id,
             duration_ms=(time.monotonic() - workflow_started) * 1000, metadata={"status": "cancelled"})
        return {"traceId": trace_id, "status": "cancelled", "answer": "No support case was created.", "aiMode": "reviewer"}
    action = pending["action"]
    try:
        payload = {"customerId": session["customerId"], "accountId": account_id,
                   "summary": action["summary"], "idempotencyKey": action_key}
        emit("tool.invoked", trace_id, "pending", session_id=session_id, component="case-management", metadata={"accountId": account_id})
        created = call_json("POST", "/api/support-cases", payload=payload, headers=_session_headers(session), retry_get=False,
                            trace_id=trace_id, session_id=session_id, component="case-management")
        case_id = created.get("caseId")
        if not case_id or created.get("status") != "open":
            raise ServiceError("case-management", "unverified_action_result")
        with STATE_LOCK:
            COMPLETED_ACTIONS[action_key] = {"caseId": case_id, "status": created["status"], "accountId": account_id}
            PENDING_ACTIONS.pop(action_key, None)
        emit("action.completed", trace_id, session_id=session_id, component="case-management", metadata={"caseId": case_id, "accountId": account_id})
        emit("workflow.resolved", trace_id, session_id=session_id, duration_ms=(time.monotonic() - workflow_started) * 1000, metadata={"status": "resolved", "actionType": "create_support_case"})
        return {"traceId": trace_id, "status": "resolved", "answer": f"Support case {case_id} was created and verified.", "data": {"caseId": case_id, "status": created["status"]}, "sources": ["case-management"], "aiMode": "reviewer"}
    except ServiceError as exc:
        emit("action.failed", trace_id, "failure", session_id=session_id, component="case-management", metadata={"reason": exc.safe_message})
        escalation = _escalate(trace_id, session_id, action["summary"], exc.safe_message,
                               ["customer authenticated", "authorization verified", "customer confirmation received"],
                               "Inspect the case-management service and verify the idempotency key before any retry.",
                               session["customerId"],
                               pending_action={"type": "create_support_case", "accountId": account_id,
                                               "idempotencyKey": action_key, "summary": action["summary"],
                                               "executionOutcome": "unverified"})
        with STATE_LOCK:
            PENDING_ACTIONS.pop(action_key, None)
        emit("workflow.escalated", trace_id, "pending", session_id=session_id, metadata={"reason": exc.safe_message})
        return {"traceId": trace_id, "status": "escalated", "answer": "The case-management service did not confirm creation, so I have not reported success. The request was escalated.", "escalation": escalation, "aiMode": "reviewer"}
    except Exception:
        emit("action.failed", trace_id, "failure", session_id=session_id, component="case-management",
             metadata={"reason": "internal_processing_failure"})
        with STATE_LOCK:
            PENDING_ACTIONS.pop(action_key, None)
        escalation = _escalate(
            trace_id, session_id, action["summary"], "internal_processing_failure",
            ["customer authenticated", "authorization verified", "customer confirmation received"],
            "Inspect the case-management trace and verify the idempotency key before retrying.",
            session["customerId"],
            pending_action={"type": "create_support_case", "accountId": account_id,
                            "idempotencyKey": action_key, "summary": action["summary"],
                            "executionOutcome": "unverified"})
        emit("workflow.escalated", trace_id, "pending", session_id=session_id,
             metadata={"reason": "internal_processing_failure"})
        return {"traceId": trace_id, "status": "escalated",
                "answer": "An internal processing issue prevented verification of the support case. The request was escalated and must be checked before retrying.",
                "escalation": escalation, "aiMode": "reviewer"}


def get_trace(trace_id: str) -> dict[str, Any]:
    with STATE_LOCK:
        events = list(TRACE_EVENTS.get(trace_id, []))
    if not events and EVENTS_FILE.exists():
        try:
            with EVENTS_FILE.open(encoding="utf-8") as handle:
                events = [json.loads(line) for line in handle if line.strip() and json.loads(line).get("traceId") == trace_id]
            # Older local log files may predate session-reference hashing. Redact on read as well.
            for event in events:
                raw_session = event.get("sessionId")
                if isinstance(raw_session, str) and raw_session not in {"system", "anonymous"}:
                    if not re.fullmatch(r"SESSION-[A-F0-9]{12}", raw_session):
                        event["sessionId"] = _telemetry_session_ref(raw_session)
                event["metadata"] = _safe_metadata(event.get("metadata", {}))
        except (OSError, json.JSONDecodeError):
            events = []
    return {"traceId": trace_id, "events": events, "eventCount": len(events)}


def get_metrics() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if EVENTS_FILE.exists():
        try:
            with EVENTS_FILE.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            pass
    traces: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        traces.setdefault(row.get("traceId", "unknown"), []).append(row)
    terminal = [ev for ev in rows if ev.get("eventType") in {
        "workflow.resolved", "workflow.failed", "workflow.escalated", "workflow.cancelled"
    }]
    terminal_traces = {ev.get("traceId") for ev in terminal if ev.get("traceId")}
    resolved_traces = {ev.get("traceId") for ev in terminal
                       if ev.get("eventType") == "workflow.resolved"
                       and ev.get("metadata", {}).get("status") == "resolved"}
    escalated_traces = {ev.get("traceId") for ev in terminal if ev.get("eventType") == "workflow.escalated"}
    failed_traces = {ev.get("traceId") for ev in terminal if ev.get("eventType") == "workflow.failed"}
    cancelled_traces = {ev.get("traceId") for ev in terminal if ev.get("eventType") == "workflow.cancelled"}
    terminal_count = max(1, len(terminal_traces))
    workflow_durations = [ev.get("durationMs") for ev in terminal if isinstance(ev.get("durationMs"), (int, float))]
    gemini_events = [ev for ev in rows if ev.get("eventType") in {"gemini.completed", "gemini.failure"}]
    gemini_durations = [ev.get("durationMs") for ev in gemini_events if isinstance(ev.get("durationMs"), (int, float))]
    tool_events = [ev for ev in rows if ev.get("eventType") in {"tool.completed", "tool.failed"}]
    tool_usage: dict[str, int] = {}
    agent_usage: dict[str, int] = {}
    failures_by_integration: dict[str, int] = {}
    for ev in rows:
        event_type = ev.get("eventType")
        component = str(ev.get("component") or ev.get("metadata", {}).get("service") or "unknown")
        if event_type == "tool.invoked":
            tool_usage[component] = tool_usage.get(component, 0) + 1
        if event_type == "agent.invoked":
            agent_usage[component] = agent_usage.get(component, 0) + 1
        if event_type in {"tool.failed", "action.failed", "integration.failure"}:
            failures_by_integration[component] = failures_by_integration.get(component, 0) + 1
    with STATE_LOCK:
        pending_confirmation_count = sum(item.get("state", "pending") == "pending" for item in PENDING_ACTIONS.values())
        executing_action_count = sum(item.get("state") == "executing" for item in PENDING_ACTIONS.values())
    sessions = {ev.get("sessionId") for ev in rows
                if ev.get("sessionId") and ev.get("sessionId") not in {"anonymous", "system"}}
    return {
        "totalRequests": len({ev.get("traceId") for ev in rows if ev.get("eventType") == "request.received"}),
        "totalSessions": len(sessions),
        "resolvedRequests": len(resolved_traces), "escalatedRequests": len(escalated_traces),
        "failedRequests": len(failed_traces), "cancelledRequests": len(cancelled_traces),
        "clarificationRequests": sum(ev.get("eventType") == "clarification.requested" for ev in rows),
        "pendingConfirmations": pending_confirmation_count, "actionsInProgress": executing_action_count,
        "resolutionRate": round(len(resolved_traces) / terminal_count * 100, 2),
        "escalationRate": round(len(escalated_traces) / terminal_count * 100, 2),
        "humanHandoffRate": round(len(escalated_traces) / terminal_count * 100, 2),
        "failureRate": round(len(failed_traces) / terminal_count * 100, 2),
        "toolCallSuccessRate": round(sum(ev.get("eventType") == "tool.completed" for ev in tool_events) / max(1, len(tool_events)) * 100, 2),
        "toolUsage": tool_usage, "agentUsage": agent_usage,
        "failuresByIntegration": failures_by_integration,
        "authenticationFailures": sum(ev.get("eventType") == "authentication.failed" for ev in rows),
        "authorizationDenials": sum(ev.get("eventType") == "authorization.denied" for ev in rows),
        "geminiFailures": sum(ev.get("eventType") == "gemini.failure" for ev in rows),
        "averageGeminiLatencyMs": round(sum(gemini_durations) / len(gemini_durations), 2) if gemini_durations else 0,
        "retryEvents": sum(ev.get("eventType") == "tool.retry" for ev in rows),
        "eventCount": len(rows), "traceCount": len(traces),
        "averageWorkflowDurationMs": round(sum(workflow_durations) / len(workflow_durations), 2) if workflow_durations else 0,
        "averageRecordedDurationMs": round(sum(workflow_durations) / len(workflow_durations), 2) if workflow_durations else 0,
    }


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gemini CX • Telco Resolution</title>
<style>
:root{color-scheme:dark;--bg:#07111f;--panel:#0f1e30;--panel2:#152940;--line:#29445d;--ink:#eef6ff;--muted:#9db3c9;--teal:#49d5c1;--blue:#61b9ff;--danger:#ff9292}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top right,#163a4b 0,transparent 40%),var(--bg);color:var(--ink);font:15px/1.5 Inter,system-ui,Segoe UI,Arial,sans-serif}.wrap{max-width:1180px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:24px}.eyebrow{color:var(--teal);font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase}.sub{color:var(--muted)}h1{font-size:clamp(26px,4vw,40px);line-height:1.1;margin:6px 0 10px}.tag{border:1px solid #477386;border-radius:999px;padding:5px 10px;color:#b2d7e6;font-size:12px}.layout{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(270px,.8fr);gap:16px}.panel{background:linear-gradient(160deg,rgba(21,41,64,.97),rgba(12,27,45,.97));border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 14px 40px #0002}.panel h2{font-size:17px;margin:0 0 14px}.row{display:flex;gap:8px;flex-wrap:wrap}input,textarea,select,button{font:inherit;border-radius:10px;border:1px solid #36516a;background:#091728;color:var(--ink);padding:11px 12px}input,textarea,select{width:100%}button{cursor:pointer;background:var(--teal);color:#06231f;font-weight:800;border-color:transparent}button.secondary{background:#1e3850;color:var(--ink);border-color:#43627b}button:disabled{opacity:.5;cursor:not-allowed}.login-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.chatlog{height:350px;overflow:auto;display:flex;flex-direction:column;gap:10px;padding:10px 0}.bubble{white-space:pre-wrap;padding:12px 14px;border-radius:13px;max-width:92%;overflow-wrap:anywhere}.user{align-self:flex-end;background:#15433f;border:1px solid #24665f}.bot{align-self:flex-start;background:#0a1a2b;border:1px solid #29445d}.meta{font-size:11px;color:var(--muted);margin-top:6px}.composer{display:grid;grid-template-columns:1fr auto;gap:8px}.status{display:inline-flex;align-items:center;gap:6px;border:1px solid #36516a;border-radius:999px;padding:5px 10px;font-size:12px;color:#b7d0e4}.dot{height:7px;width:7px;border-radius:50%;background:var(--teal)}.stats{display:grid;grid-template-columns:1fr 1fr;gap:8px}.stat{background:#091728;border:1px solid #223b54;border-radius:12px;padding:12px}.num{font-size:23px;font-weight:800;color:var(--teal)}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#071321;border:1px solid #233b53;border-radius:10px;padding:12px;max-height:300px;overflow:auto;font-size:12px}.muted-small{font-size:12px;color:var(--muted)}.divider{height:1px;background:var(--line);margin:16px 0}.hidden{display:none}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}.pill{display:inline-block;border-radius:7px;padding:3px 8px;background:#173f49;color:#b4fff0;font-size:12px}@media(max-width:840px){.layout{grid-template-columns:1fr}.wrap{padding:14px}.chatlog{height:300px}.top{align-items:flex-start;flex-direction:column}}
</style></head><body><main class="wrap">
<header class="top"><div><div class="eyebrow">Enterprise AI • Customer experience</div><h1>Resolution Console</h1><div class="sub">Gemini-assisted telco support with guarded actions, mock enterprise integrations and traceable outcomes.</div></div><span class="tag" id="modeTag">Reviewer mode</span></header>
<div class="layout"><section class="panel"><div class="row" style="justify-content:space-between;align-items:center"><h2>Customer conversation</h2><span class="status"><span class="dot"></span><span id="authStatus">Signed out</span></span></div>
<div class="login-grid"><input id="username" aria-label="Username" value="alex.morgan" autocomplete="username"><input id="password" aria-label="Password" value="ReviewerPass-1001" type="password" autocomplete="current-password"><button id="loginBtn" onclick="signIn()">Sign in</button><button class="secondary" onclick="signOut()">Sign out</button></div>
<p class="muted-small">Synthetic demo users only: customer alex.morgan / ReviewerPass-1001; customer jordan.lee / ReviewerPass-1002; operations support.agent / ReviewerPass-3001. Operational metrics, traces and escalations are visible only to the support-agent role.</p>
<div class="divider"></div><div id="chatlog" class="chatlog"><div class="bubble bot">Welcome. Sign in, then ask about your plan, bill, connectivity, subscriber status, or a support case.</div></div>
<div class="composer"><textarea id="message" rows="2" maxlength="2000" placeholder="Describe the issue…" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMessage()}"></textarea><button onclick="sendMessage()">Send</button></div>
<div class="muted-small" style="margin-top:8px">Action requests are not submitted until explicit confirmation. All customer/account data is synthetic.</div></section>
<aside class="panel"><h2>Operations & evidence</h2><div class="row"><span class="status" id="healthStatus">Checking health…</span><span class="status" id="geminiStatus">AI mode</span></div><div class="divider"></div><p class="muted-small" id="opsAccess">Sign in as the synthetic support agent to view cross-customer metrics and traces.</p><div class="stats">
<div class="stat"><div class="muted-small">Requests</div><div class="num" id="mRequests">0</div></div>
<div class="stat"><div class="muted-small">Sessions</div><div class="num" id="mSessions">0</div></div>
<div class="stat"><div class="muted-small">Resolved</div><div class="num" id="mResolved">0</div></div>
<div class="stat"><div class="muted-small">Resolution rate</div><div class="num" id="mResolutionRate">0%</div></div>
<div class="stat"><div class="muted-small">Human handoffs</div><div class="num" id="mEscalated">0</div></div>
<div class="stat"><div class="muted-small">Failures</div><div class="num" id="mFailures">0</div></div>
<div class="stat"><div class="muted-small">Tool success</div><div class="num" id="mToolSuccess">0%</div></div>
<div class="stat"><div class="muted-small">Gemini latency</div><div class="num" id="mGeminiLatency">0 ms</div></div>
<div class="stat"><div class="muted-small">Pending confirmations</div><div class="num" id="mPending">0</div></div>
<div class="stat"><div class="muted-small">Clarifications</div><div class="num" id="mClarifications">0</div></div>
<div class="stat"><div class="muted-small">Retries</div><div class="num" id="mRetries">0</div></div>
<div class="stat"><div class="muted-small">Events</div><div class="num" id="mEvents">0</div></div>
</div><div class="divider"></div><div class="row"><button class="secondary" onclick="refreshMetrics()">Refresh metrics</button><button class="secondary" onclick="showLastTrace()">Last trace</button></div><pre id="evidence">Run a conversation to generate trace evidence.</pre><div class="muted-small">Metrics and traces are generated from application events—not static demo numbers.</div></aside></div></main>
<script>
let sessionId=null,lastTrace=null,pendingConfirmation=null;
const $=id=>document.getElementById(id);
function addBubble(text,who='bot',meta=''){const b=document.createElement('div');b.className='bubble '+who;b.textContent=text;const wrap=document.createElement('div');wrap.appendChild(b);if(meta){const m=document.createElement('div');m.className='meta';m.textContent=meta;wrap.appendChild(m)}$('chatlog').appendChild(wrap);$('chatlog').scrollTop=$('chatlog').scrollHeight;}
function renderResult(d){lastTrace=d.traceId||lastTrace;if(d.aiMode)$('modeTag').textContent=(d.aiMode==='live'?'Live Gemini':d.aiMode==='degraded'?'Degraded fallback':'Reviewer mode');addBubble(d.answer||JSON.stringify(d),'bot',`Status: ${d.status||'unknown'} · Trace: ${d.traceId||'n/a'}`);if(d.confirmationId){pendingConfirmation=d.confirmationId;const actions=document.createElement('div');actions.className='actions';for(const [label,value] of [['Confirm action',true],['Cancel action',false]]){const btn=document.createElement('button');btn.className=value?'':'secondary';btn.textContent=label;btn.onclick=()=>confirmAction(value);actions.appendChild(btn)}$('chatlog').appendChild(actions)}$('evidence').textContent=JSON.stringify({status:d.status,traceId:d.traceId,sources:d.sources||[],data:d.data||null,escalation:d.escalation||null},null,2);refreshMetrics();}
function clearMetrics(){for(const id of ['mRequests','mSessions','mResolved','mResolutionRate','mEscalated','mFailures','mToolSuccess','mGeminiLatency','mPending','mClarifications','mRetries','mEvents'])$(id).textContent=(id==='mResolutionRate'||id==='mToolSuccess')?'0%':id==='mGeminiLatency'?'0 ms':'0';}
function resetSessionView(){lastTrace=null;pendingConfirmation=null;$('evidence').textContent='Sign in and run a conversation to generate authorized evidence.';$('chatlog').innerHTML='<div class="bubble bot">Welcome. Sign in, then ask about your plan, bill, connectivity, subscriber status, or a support case.</div>';clearMetrics();$('opsAccess').textContent='Sign in as the synthetic support agent to view cross-customer metrics and traces.';$('modeTag').textContent='Reviewer mode';}
async function signIn(){const b=$('loginBtn');b.disabled=true;const previous=sessionId;sessionId=null;pendingConfirmation=null;resetSessionView();$('authStatus').textContent='Signed out';if(previous){try{await fetch('/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sessionId:previous})})}catch(e){}}try{const r=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('username').value,password:$('password').value})});const d=await r.json();if(!r.ok)throw new Error(d.error||'Sign in failed');sessionId=d.sessionId;$('authStatus').textContent=d.customerId+' · '+d.roles.join(', ');addBubble('Signed in as '+d.customerId+'. Account context is held server-side.','bot');await refreshMetrics();}catch(e){addBubble('Sign-in failed: '+e.message,'bot')}finally{b.disabled=false}}
async function signOut(){const previous=sessionId;sessionId=null;resetSessionView();$('authStatus').textContent='Signed out';addBubble('Signed out. Protected actions require sign-in.','bot');if(previous){try{const r=await fetch('/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sessionId:previous})});if(!r.ok)addBubble('Server-side session revocation could not be confirmed.','bot')}catch(e){addBubble('Local sign-out completed; server session revocation could not be confirmed.','bot')}}}
async function sendMessage(){const message=$('message').value.trim();if(!message)return; $('message').value='';addBubble(message,'user');try{const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,sessionId})});const d=await r.json();renderResult(d)}catch(e){addBubble('Request failed. Check whether both local servers are running.','bot')}}
async function confirmAction(confirmed){if(!sessionId||!pendingConfirmation)return;try{const r=await fetch('/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sessionId,confirmationId:pendingConfirmation,confirmed})});const d=await r.json();pendingConfirmation=null;renderResult(d)}catch(e){addBubble('Could not confirm the action.','bot')}}
async function refreshMetrics(){try{const h=await fetch('/health').then(r=>r.json());$('healthStatus').textContent='App '+h.status+' · Mock API '+h.mockApi;$('geminiStatus').textContent=h.aiMode;if(!sessionId){clearMetrics();$('evidence').textContent='Sign in as support.agent to view cross-customer metrics, traces and escalation records.';$('opsAccess').textContent='Sign in as the synthetic support agent to view cross-customer metrics and traces.';return}const mr=await fetch('/metrics',{headers:{'X-Session-ID':sessionId}});if(!mr.ok){clearMetrics();lastTrace=null;$('evidence').textContent='Detailed traces and operational metrics are restricted to the support-agent role.';$('opsAccess').textContent='Operational telemetry is restricted to the support-agent role. Use support.agent for the operations view.';return}const m=await mr.json();$('opsAccess').textContent='Authorized operations view: live metrics from application events.';$('mRequests').textContent=m.totalRequests||0;$('mSessions').textContent=m.totalSessions||0;$('mResolved').textContent=m.resolvedRequests||0;$('mResolutionRate').textContent=(m.resolutionRate||0)+'%';$('mEscalated').textContent=m.escalatedRequests||0;$('mFailures').textContent=m.failedRequests||0;$('mToolSuccess').textContent=(m.toolCallSuccessRate||0)+'%';$('mGeminiLatency').textContent=(m.averageGeminiLatencyMs||0)+' ms';$('mPending').textContent=m.pendingConfirmations||0;$('mClarifications').textContent=m.clarificationRequests||0;$('mRetries').textContent=m.retryEvents||0;$('mEvents').textContent=m.eventCount||0;}catch(e){$('healthStatus').textContent='Health check failed';clearMetrics();$('evidence').textContent='Operational telemetry is unavailable.'}}
async function showLastTrace(){if(!lastTrace){$('evidence').textContent='No trace yet. Send a request first.';return}if(!sessionId){$('evidence').textContent='Sign in as support.agent to view request traces.';return}try{const r=await fetch('/traces/'+encodeURIComponent(lastTrace),{headers:{'X-Session-ID':sessionId}});const d=await r.json();$('evidence').textContent=JSON.stringify(d,null,2)}catch(e){$('evidence').textContent='Could not load trace.'}}
refreshMetrics();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "GeminiCXStarter/1.0"

    def _send(self, code: int, payload: Any, content_type: str = "application/json") -> None:
        body = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if "charset=" not in content_type else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid_content_length") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request_body_too_large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_json") from exc
        if not isinstance(data, dict):
            raise ValueError("json_object_required")
        return data

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            return self._send(200, HTML, "text/html")
        if path == "/health":
            mock_status = "unknown"
            try:
                call_json("GET", "/health", retry_get=False)
                mock_status = "ok"
            except ServiceError:
                mock_status = "unavailable"
            return self._send(200, {"status": "ok", "mockApi": mock_status, "aiMode": AI_MODE if AI_MODE in {"live", "reviewer"} else "reviewer", "geminiConfigured": bool(GEMINI_API_KEY)})
        if path == "/metrics":
            try:
                require_operations_session(self.headers.get("X-Session-ID"))
            except ServiceError as exc:
                return self._send(exc.status or 403, {"error": exc.safe_message})
            return self._send(200, get_metrics())
        if path.startswith("/traces/"):
            try:
                require_operations_session(self.headers.get("X-Session-ID"))
            except ServiceError as exc:
                return self._send(exc.status or 403, {"error": exc.safe_message})
            trace_id = path.rsplit("/", 1)[-1]
            if not re.fullmatch(r"TRACE-[A-F0-9]{8,24}", trace_id):
                return self._send(400, {"error": "invalid_trace_id"})
            trace = get_trace(trace_id)
            return self._send(200 if trace["eventCount"] else 404, trace)
        if path == "/escalations":
            try:
                require_operations_session(self.headers.get("X-Session-ID"))
            except ServiceError as exc:
                return self._send(exc.status or 403, {"error": exc.safe_message})
            records = []
            try:
                with ESCALATIONS_FILE.open(encoding="utf-8") as handle:
                    records = [json.loads(line) for line in handle if line.strip()]
            except FileNotFoundError:
                pass
            return self._send(200, {"records": records[-100:], "count": len(records)})
        return self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        try:
            body = self._json_body()
            if path == "/auth/login":
                trace = _new_trace()
                emit("authentication.attempted", trace, metadata={"credentialType": "username_password"})
                try:
                    user = login(body.get("username"), body.get("password"))
                    emit("session.started", trace, session_id=user["sessionId"],
                         metadata={"customerId": user["customerId"], "roles": user["roles"]})
                    emit("authentication.succeeded", trace, session_id=user["sessionId"],
                         metadata={"customerId": user["customerId"], "roles": user["roles"]})
                    return self._send(200, user)
                except ServiceError as exc:
                    emit("authentication.failed", trace, "denied", metadata={"reason": exc.safe_message})
                    status = exc.status or 401
                    return self._send(status, {"error": exc.safe_message})
            if path == "/auth/logout":
                session_id = body.get("sessionId")
                if not isinstance(session_id, str):
                    return self._send(400, {"error": "sessionId_required"})
                return self._send(200, logout_session(session_id))
            if path == "/chat":
                try:
                    result = handle_chat(body.get("message"), body.get("sessionId"))
                    code = int(result.pop("httpStatus", 200))
                    return self._send(code, result)
                except ServiceError as exc:
                    return self._send(exc.status or 503, {"error": exc.safe_message})
            if path == "/confirm":
                session_id, confirmation_id, confirmed = body.get("sessionId"), body.get("confirmationId"), body.get("confirmed")
                if not isinstance(session_id, str) or not isinstance(confirmation_id, str) or not isinstance(confirmed, bool):
                    return self._send(400, {"error": "sessionId_confirmationId_and_boolean_confirmed_required"})
                try:
                    return self._send(200, confirm_action(session_id, confirmation_id, confirmed))
                except ServiceError as exc:
                    return self._send(exc.status or 503, {"error": exc.safe_message})
            return self._send(404, {"error": "not_found"})
        except ValueError as exc:
            return self._send(400, {"error": str(exc)})
        except Exception:
            # Never send stack traces, tokens, prompts, or internal paths to the client.
            return self._send(500, {"error": "internal_error", "message": "The request could not be processed safely."})

    def log_message(self, fmt: str, *args: Any) -> None:
        # HTTP access logs omit request bodies and credentials by design.
        return


def main() -> None:
    server = ThreadingHTTPServer((os.getenv("APP_HOST", "127.0.0.1"), APP_PORT), Handler)
    server.daemon_threads = True
    print(f"Gemini CX Resolution Console: http://127.0.0.1:{APP_PORT} (AI_MODE={AI_MODE})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
