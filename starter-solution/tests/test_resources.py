"""Functional, authorization, integration, failure-path and telemetry tests for the PoC."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
STARTER = ROOT / "starter-solution"
MOCK_PATH = ROOT / "mock-services" / "server.py"
sys.path.insert(0, str(STARTER))
import server as app  # noqa: E402

spec = importlib.util.spec_from_file_location("mock_services_server", MOCK_PATH)
mock = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mock)


class ChallengeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock_http = ThreadingHTTPServer(("127.0.0.1", 0), mock.H)
        cls.mock_http.daemon_threads = True
        cls.mock_thread = threading.Thread(target=cls.mock_http.serve_forever, daemon=True)
        cls.mock_thread.start()
        cls.api = f"http://127.0.0.1:{cls.mock_http.server_port}"
        cls.app_http = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.app_http.daemon_threads = True
        cls.app_thread = threading.Thread(target=cls.app_http.serve_forever, daemon=True)
        cls.app_thread.start()
        cls.app_url = f"http://127.0.0.1:{cls.app_http.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.app_http.shutdown()
        cls.app_http.server_close()
        cls.app_thread.join(timeout=2)
        cls.mock_http.shutdown()
        cls.mock_http.server_close()
        cls.mock_thread.join(timeout=2)

    def http_get(self, path, headers=None):
        request = urllib.request.Request(self.app_url + path, headers=headers or {}, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        app.API = self.api
        app.EVENTS_FILE = Path(self.tmp.name) / "events.jsonl"
        app.ESCALATIONS_FILE = Path(self.tmp.name) / "escalations.jsonl"
        app.AI_MODE = "reviewer"
        app.GEMINI_API_KEY = ""
        app.REQUEST_TIMEOUT = 0.75
        with app.STATE_LOCK:
            app.SESSIONS.clear()
            app.PENDING_ACTIONS.clear()
            app.COMPLETED_ACTIONS.clear()
            app.CONVERSATIONS.clear()
            app.TRACE_EVENTS.clear()
        mock.KEYS.clear()
        mock.CASES.clear()
        mock.TOKENS.clear()
        self.alex = app.login("alex.morgan", "ReviewerPass-1001")
        self.session = self.alex["sessionId"]

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, username="alex.morgan", password="ReviewerPass-1001"):
        return app.login(username, password)

    def test_http_security_headers_and_operations_route_permissions(self):
        status, headers, _ = self.http_get("/")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(headers.get("Referrer-Policy"), "no-referrer")
        self.assertIn("frame-ancestors 'none'", headers.get("Content-Security-Policy", ""))

        for path in ("/metrics", "/traces/TRACE-ABCDEF123456", "/escalations"):
            unauth_status, _, _ = self.http_get(path)
            self.assertEqual(unauth_status, 401, path)
            customer_status, _, _ = self.http_get(path, {"X-Session-ID": self.session})
            self.assertEqual(customer_status, 403, path)

        inquiry = app.handle_chat("What internet plan am I currently using?", self.session)
        support = self.login("support.agent", "ReviewerPass-3001")
        headers = {"X-Session-ID": support["sessionId"]}
        metrics_status, _, metrics_body = self.http_get("/metrics", headers)
        self.assertEqual(metrics_status, 200)
        self.assertGreaterEqual(json.loads(metrics_body)["totalRequests"], 1)
        trace_status, _, trace_body = self.http_get("/traces/" + inquiry["traceId"], headers)
        self.assertEqual(trace_status, 200)
        self.assertEqual(json.loads(trace_body)["traceId"], inquiry["traceId"])
        escalation_status, _, escalation_body = self.http_get("/escalations", headers)
        self.assertEqual(escalation_status, 200)
        self.assertIn("records", json.loads(escalation_body))

    def test_resource_package_has_eight_scenarios_and_parseable_json(self):
        for i in range(1, 9):
            scenario = json.loads((ROOT / "scenarios" / f"SCN-{i:03d}.json").read_text())
            self.assertEqual(scenario["scenarioId"], f"SCN-{i:03d}")
        for path in (ROOT / "sample-data").glob("*.json"):
            json.loads(path.read_text())
        for path in (ROOT / "schemas").glob("*.json"):
            json.loads(path.read_text())

    def test_login_rejects_wrong_password(self):
        with self.assertRaises(app.ServiceError):
            self.login(password="wrong")

    def test_auth_context_is_server_side_and_not_returned(self):
        self.assertIn("sessionId", self.alex)
        self.assertNotIn("accessToken", self.alex)
        self.assertNotIn("password", json.dumps(self.alex).lower())
        server_token = app.SESSIONS[self.session]["accessToken"]
        self.assertNotIn("synthetic-CUST-", server_token)
        self.assertIn(server_token, mock.TOKENS)

    def test_protected_account_query_requires_authentication(self):
        result = app.handle_chat("What plan am I using?", None)
        self.assertEqual(result["status"], "authentication_required")
        self.assertEqual(result["httpStatus"], 401)

    def test_plan_inquiry_is_grounded_in_account_api(self):
        result = app.handle_chat("What internet plan am I currently using?", self.session)
        self.assertNotIn("sessionId", result)
        self.assertEqual(result["status"], "resolved")
        self.assertIn("Fiber 500", result["answer"])
        self.assertEqual(result["sources"], ["account-service"])
        self.assertEqual(result["data"]["accountId"], "ACC-2001")
        events = app.get_trace(result["traceId"])["events"]
        self.assertTrue(any(e["eventType"] == "authorization.allowed" for e in events))

    def test_service_problem_takes_precedence_over_plan_keywords(self):
        problem = app._deterministic_intent("My internet plan is not working")
        self.assertEqual(problem["intent"], "service_issue")
        self.assertEqual(problem["serviceType"], "home-internet")
        inquiry = app._deterministic_intent("What internet plan am I currently using?")
        self.assertEqual(inquiry["intent"], "account_plan")
        mobile = app._deterministic_intent("My mobile service has no service")
        self.assertEqual(mobile["intent"], "service_issue")
        self.assertEqual(mobile["serviceType"], "mobile")

    def test_cross_customer_account_request_is_denied_before_fetch(self):
        result = app.handle_chat("What plan am I using on ACC-2002?", self.session)
        self.assertEqual(result["status"], "access_denied")
        self.assertNotIn("Mobile Unlimited", result["answer"])
        self.assertNotIn("ACC-2002", json.dumps(result.get("data")))
        denied = [e for e in app.TRACE_EVENTS[result["traceId"]] if e["eventType"] == "authorization.denied"]
        self.assertTrue(denied)

    def test_billing_answer_uses_billing_service(self):
        result = app.handle_chat("Show me my bill", self.session)
        self.assertEqual(result["status"], "resolved")
        self.assertIn("$84.99", result["answer"])
        self.assertEqual(result["sources"], ["billing-service"])

    def test_ambiguous_issue_asks_and_then_resumes(self):
        first = app.handle_chat("My service is not working.", self.session)
        self.assertEqual(first["status"], "clarification")
        self.assertIn("home internet or mobile", first["answer"])
        second = app.handle_chat("home internet", self.session)
        self.assertIn(second["status"], {"resolved", "escalated"})
        self.assertTrue(any(source in second.get("sources", []) for source in ("network-diagnostics", "legacy-service")))

    def test_legacy_status_asks_for_service_when_ambiguous(self):
        app.AI_MODE = "live"
        with patch.object(app, "_gemini_intent", return_value={
            "intent": "legacy_status", "accountId": None, "serviceType": None,
            "postalCode": None, "issueSummary": "Check subscriber status",
            "clarificationNeeded": False,
        }):
            result = app.handle_chat("Check subscriber status", self.session)
        self.assertEqual(result["status"], "clarification")
        self.assertIn("serviceType", result["missingFields"])
        self.assertIn("home internet or mobile", result["answer"].lower())

    def test_legacy_status_never_uses_a_different_service_type(self):
        with patch.object(app, "_legacy_status") as legacy_call:
            result = app.handle_chat("Check my mobile subscriber status", self.session)
        self.assertEqual(result["status"], "escalated")
        legacy_call.assert_not_called()

    def test_legacy_xml_response_is_normalized(self):
        result = app.handle_chat("Check my home internet legacy subscriber status", self.session)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["data"]["accountId"], "ACC-2001")
        self.assertEqual(result["data"]["serviceId"], "SVC-5001")
        self.assertEqual(result["data"]["errorCode"], "0")

    def test_case_requires_confirmation_then_creates_one(self):
        result = app.handle_chat("Create a support case for my internet issue", self.session)
        self.assertEqual(result["status"], "confirmation_required")
        self.assertFalse(mock.CASES)
        self.assertNotIn("action", result)
        self.assertNotIn(self.session, json.dumps(result))
        confirmation = app.confirm_action(self.session, result["confirmationId"], True)
        self.assertEqual(confirmation["status"], "resolved")
        self.assertIn("caseId", confirmation["data"])
        self.assertEqual(len(mock.CASES), 1)
        repeat = app.handle_chat("Create a support case for my internet issue", self.session)
        self.assertTrue(repeat.get("actionAlreadyCompleted"))
        self.assertEqual(repeat["data"], {"caseId": confirmation["data"]["caseId"], "status": "open"})
        repeat_json = json.dumps(repeat)
        self.assertNotIn(self.session, repeat_json)
        self.assertNotIn("idempotencyKey", repeat_json)
        self.assertNotIn("accessToken", repeat_json)
        self.assertEqual(len(mock.CASES), 1)

    def test_expired_confirmation_is_reissued_and_not_counted_as_pending(self):
        message = "Create a support case for my internet issue"
        first = app.handle_chat(message, self.session)
        self.assertEqual(first["status"], "confirmation_required")
        key = next(k for k, v in app.PENDING_ACTIONS.items() if v.get("sessionId") == self.session)
        app.PENDING_ACTIONS[key]["expiresAt"] = time.time() - 1
        self.assertEqual(app.get_metrics()["pendingConfirmations"], 0)

        second = app.handle_chat(message, self.session)
        self.assertEqual(second["status"], "confirmation_required")
        self.assertNotEqual(first["confirmationId"], second["confirmationId"])
        self.assertGreater(app.PENDING_ACTIONS[key]["expiresAt"], time.time())
        self.assertEqual(len(app.PENDING_ACTIONS), 1)

    def test_case_cancellation_does_not_execute(self):
        result = app.handle_chat("Open a ticket for my problem", self.session)
        self.assertEqual(result["status"], "confirmation_required")
        cancelled = app.confirm_action(self.session, result["confirmationId"], False)
        self.assertEqual(cancelled["status"], "cancelled")
        cancel_events = app.get_trace(cancelled["traceId"])["events"]
        cancelled_workflow = next(e for e in cancel_events if e["eventType"] == "workflow.cancelled")
        self.assertEqual(cancelled_workflow["status"], "success")
        self.assertEqual(len(mock.CASES), 0)

    def test_case_service_failure_escalates_without_false_success(self):
        result = app.handle_chat("Create a support case for an outage", self.session)
        with patch.dict(os.environ, {"MOCK_CASE_MODE": "unavailable"}):
            final = app.confirm_action(self.session, result["confirmationId"], True)
        self.assertEqual(final["status"], "escalated")
        self.assertNotIn("was created and verified", final["answer"])
        records = [json.loads(x) for x in app.ESCALATIONS_FILE.read_text().splitlines()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["traceId"], final["traceId"])
        encoded = json.dumps(final["escalation"])
        self.assertNotIn(self.session, encoded)
        self.assertIn("keyFingerprint", encoded)
        self.assertNotIn("idempotencyKey", records[0].get("pendingAction", {}))

    def test_malformed_billing_response_escalates(self):
        with patch.dict(os.environ, {"MOCK_BILLING_MODE": "malformed"}):
            result = app.handle_chat("Show my bill", self.session)
        self.assertEqual(result["status"], "escalated")
        self.assertNotIn("$0.00", result["answer"])

    def test_gemini_provider_failure_uses_explicit_degraded_mode(self):
        app.AI_MODE = "live"
        app.GEMINI_API_KEY = ""
        result = app.handle_chat("What plan am I using?", self.session)
        self.assertEqual(result["aiMode"], "degraded")
        self.assertEqual(result["status"], "resolved")
        trace = app.get_trace(result["traceId"])
        self.assertTrue(any(e["eventType"] == "gemini.failure" for e in trace["events"]))

    def test_event_schema_fields_trace_and_sanitization(self):
        result = app.handle_chat("What plan am I using?", self.session)
        trace = app.get_trace(result["traceId"])
        self.assertGreaterEqual(trace["eventCount"], 4)
        required = {"eventId", "traceId", "sessionId", "timestamp", "eventType", "component", "status"}
        for event in trace["events"]:
            self.assertTrue(required.issubset(event))
            self.assertEqual(event["traceId"], result["traceId"])
            self.assertNotEqual(event["sessionId"], self.session)
            self.assertIsInstance(event["timestamp"], str)
            self.assertIn(event["status"], {"success", "failure", "pending", "denied"})
            self.assertFalse(set(event) - required - {"durationMs", "metadata"})
            encoded = json.dumps(event).lower()
            self.assertNotIn("reviewerpass", encoded)
            self.assertNotIn("accesstoken", encoded)
            self.assertNotIn(self.session.lower(), encoded)
        authenticated_refs = {e["sessionId"] for e in trace["events"] if e["sessionId"].startswith("SESSION-")}
        self.assertEqual(len(authenticated_refs), 1)
        metrics = app.get_metrics()
        self.assertGreaterEqual(metrics["totalRequests"], 1)
        self.assertGreaterEqual(metrics["eventCount"], trace["eventCount"])

    def test_historical_trace_read_redacts_legacy_session_ids_and_sensitive_metadata(self):
        trace_id = "TRACE-ABCDEF123456"
        old_event = {
            "eventId": "EVT-LEGACY000001", "traceId": trace_id, "sessionId": self.session,
            "timestamp": "2026-10-16T00:00:00+00:00", "eventType": "request.received",
            "component": "starter-app", "status": "success",
            "metadata": {"api_key": "test-secret-key", "note": "safe"},
        }
        app.EVENTS_FILE.write_text(json.dumps(old_event) + "\n", encoding="utf-8")
        trace = app.get_trace(trace_id)
        self.assertNotEqual(trace["events"][0]["sessionId"], self.session)
        self.assertNotIn(self.session, json.dumps(trace))
        self.assertNotIn("test-secret-key", json.dumps(trace))
        self.assertNotIn("api_key", json.dumps(trace))

    def test_historical_escalations_are_redacted_on_read(self):
        legacy_record = {
            "escalationId": "ESC-LEGACY0001", "traceId": "TRACE-ABCDEF123456",
            "customerId": "CUST-1001",
            "requestSummary": "My password is OldSecret123; email alex.morgan@example.test",
            "completedSteps": ["request received"],
            "reason": "api_key=LegacyApiSecret",
            "errorSummary": "token=LegacyTokenSecret",
            "recommendedNextStep": "Review the sanitized record",
            "evidence": [{"eventType": "authentication.failed",
                           "metadata": {"sessionId": self.session, "api_key": "NestedSecret"}}],
        }
        app.ESCALATIONS_FILE.write_text(json.dumps(legacy_record) + "\n", encoding="utf-8")
        result = app.get_escalations()
        self.assertEqual(result["count"], 1)
        encoded = json.dumps(result)
        for secret in ("OldSecret123", "alex.morgan@example.test", "LegacyApiSecret",
                       "LegacyTokenSecret", "NestedSecret", self.session):
            self.assertNotIn(secret, encoded)

    def test_telemetry_schema_validation_rejects_invalid_trace_id(self):
        with self.assertRaises(ValueError):
            app.emit("request.received", "not-a-trace-id")

    def test_telemetry_schema_validation_rejects_invalid_status_and_duration(self):
        trace_id = app._new_trace()
        with self.assertRaises(ValueError):
            app.emit("workflow.cancelled", trace_id, "cancelled")
        with self.assertRaises(ValueError):
            app.emit("workflow.resolved", trace_id, "success", duration_ms=float("nan"))

    def test_gemini_prompt_redacts_credentials_and_omits_assistant_history(self):
        payload = {
            "candidates": [{"content": {"parts": [{"text": json.dumps({
                "intent": "billing", "accountId": None, "serviceType": None,
                "postalCode": None, "issueSummary": "Check my current bill",
                "clarificationNeeded": False,
            })}]}}],
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        captured = {}
        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = request.data.decode("utf-8")
            captured["headers"] = dict(request.header_items())
            return FakeResponse()

        history = [
            {"role": "user", "content": "My password is Secret123 and email is alex.morgan@example.test"},
            {"role": "assistant", "content": "Your private bill was $84.99 for account ACC-2001"},
        ]
        with patch.object(app, "GEMINI_API_KEY", "private-test-api-key"), \
             patch.object(app.urllib.request, "urlopen", side_effect=fake_urlopen):
            intent = app._gemini_intent(
                "Check bill; password is Secret456; api_key=XYZSECRET; email alex.morgan@example.test",
                history,
            )
        self.assertEqual(intent["intent"], "billing")
        self.assertNotIn("private-test-api-key", captured["url"])
        self.assertNotIn("Secret123", captured["body"])
        self.assertNotIn("Secret456", captured["body"])
        self.assertNotIn("XYZSECRET", captured["body"])
        self.assertNotIn("alex.morgan@example.test", captured["body"])
        self.assertNotIn("Your private bill was", captured["body"])
        self.assertIn("X-goog-api-key", captured["headers"])

    def test_request_limits_and_empty_input(self):
        with self.assertRaises(ValueError):
            app.handle_chat(" ", self.session)
        with self.assertRaises(ValueError):
            app.handle_chat("x" * (app.MAX_MESSAGE_CHARS + 1), self.session)

    def test_multi_system_issue_calls_profile_account_network_and_legacy(self):
        result = app.handle_chat("My home internet has been down since this morning", self.session)
        self.assertIn(result["status"], {"resolved", "escalated"})
        events = app.get_trace(result["traceId"])["events"]
        components = {e.get("component") for e in events if e.get("eventType") == "tool.invoked"}
        self.assertTrue({"customer-profile", "account-service", "network-diagnostics",
                          "device-diagnostics", "legacy-adapter"}.issubset(components))

    def test_malformed_legacy_xml_is_not_reported_as_success(self):
        with patch.dict(os.environ, {"MOCK_LEGACY_MODE": "malformed"}):
            result = app.handle_chat("Check my home internet legacy subscriber status", self.session)
        self.assertEqual(result["status"], "escalated")
        self.assertNotIn("subscriber status: service active", result["answer"].lower())
        events = app.get_trace(result["traceId"])["events"]
        self.assertTrue(any(e["eventType"] == "tool.failed" and e["component"] == "legacy-adapter"
                            for e in events))

    def test_legacy_adapter_rejects_wrong_content_type_and_traces_failure(self):
        original_request_raw = app.request_raw
        def fake_request_raw(method, path, **kwargs):
            if path == "/api/legacy/subscriber-status":
                return 200, b"<SubscriberStatusResponse/>", "application/json"
            return original_request_raw(method, path, **kwargs)
        with patch.object(app, "request_raw", side_effect=fake_request_raw):
            result = app.handle_chat("Check my home internet legacy subscriber status", self.session)
        self.assertEqual(result["status"], "escalated")
        events = app.get_trace(result["traceId"])["events"]
        self.assertTrue(any(e["eventType"] == "tool.failed"
                            and e["component"] == "legacy-adapter"
                            and e.get("metadata", {}).get("reason") == "invalid_legacy_content_type"
                            for e in events))

    def test_malformed_device_diagnostics_response_escalates_and_traces_failure(self):
        jordan = self.login("jordan.lee", "ReviewerPass-1002")
        with patch.dict(os.environ, {"MOCK_DIAGNOSTICS_MODE": "malformed"}):
            result = app.handle_chat("My mobile service is slow", jordan["sessionId"])
        self.assertEqual(result["status"], "escalated")
        events = app.get_trace(result["traceId"])["events"]
        self.assertTrue(any(e["eventType"] == "tool.failed" and e["component"] == "device-diagnostics"
                            for e in events))

    def test_expired_server_side_session_is_rejected(self):
        app.SESSIONS[self.session]["expiresAt"] = 0
        with self.assertRaises(app.ServiceError) as raised:
            app.handle_chat("What plan am I using?", self.session)
        self.assertEqual(raised.exception.status, 401)

    def test_confirmation_cannot_be_replayed_from_another_session(self):
        request = app.handle_chat("Create a support case for my internet issue", self.session)
        jordan = self.login("jordan.lee", "ReviewerPass-1002")
        with self.assertRaises(app.ServiceError) as raised:
            app.confirm_action(jordan["sessionId"], request["confirmationId"], True)
        self.assertEqual(raised.exception.status, 403)
        self.assertEqual(len(mock.CASES), 0)

    def test_metrics_reflect_real_workflow_events(self):
        before = app.get_metrics()["totalRequests"]
        app.handle_chat("What plan am I currently using?", self.session)
        after = app.get_metrics()["totalRequests"]
        self.assertEqual(after, before + 1)
        metrics = app.get_metrics()
        self.assertGreater(metrics["toolCallSuccessRate"], 0)
        self.assertGreater(metrics["averageRecordedDurationMs"], 0)
        self.assertGreater(metrics["averageWorkflowDurationMs"], 0)
        self.assertGreaterEqual(metrics["totalSessions"], 1)
        self.assertIn("workflow-orchestrator", metrics["agentUsage"])
        self.assertIn("account-service", metrics["toolUsage"])

    def test_call_json_records_malformed_json_as_a_tool_failure(self):
        trace_id = app._new_trace()
        headers = app._session_headers(app.SESSIONS[self.session])
        with patch.object(app, "request_raw", return_value=(200, b"not-json", "application/json")):
            with self.assertRaises(app.ServiceError) as raised:
                app.call_json("GET", "/api/accounts/ACC-2001", headers=headers,
                              trace_id=trace_id, session_id=self.session,
                              component="account-service")
        self.assertEqual(raised.exception.service, "account-service")
        events = app.get_trace(trace_id)["events"]
        self.assertTrue(any(e["eventType"] == "tool.failed"
                            and e["component"] == "account-service" for e in events))
        self.assertTrue(any(e["eventType"] == "tool.retry" for e in events))

    def test_mock_enterprise_api_rejects_missing_bearer_token(self):
        with self.assertRaises(app.ServiceError) as raised:
            app.call_json("GET", "/api/customers/CUST-1001", retry_get=False)
        self.assertEqual(raised.exception.status, 401)

    def test_mock_api_enforces_customer_ownership_independently(self):
        jordan = self.login("jordan.lee", "ReviewerPass-1002")
        token = app.SESSIONS[jordan["sessionId"]]["accessToken"]
        with self.assertRaises(app.ServiceError) as raised:
            app.call_json(
                "GET",
                "/api/accounts/ACC-2001",
                headers={"Authorization": "Bearer " + token},
                retry_get=False,
            )
        self.assertEqual(raised.exception.status, 403)

    def test_escalation_contains_context_systems_and_failed_tool_evidence(self):
        with patch.dict(os.environ, {"MOCK_BILLING_MODE": "malformed"}):
            result = app.handle_chat("Show my bill", self.session)
        self.assertEqual(result["status"], "escalated")
        record = result["escalation"]
        schema = json.loads((ROOT / "schemas" / "escalation-record.schema.json").read_text(encoding="utf-8"))
        self.assertTrue(set(schema["required"]).issubset(record))
        self.assertFalse(set(record) - set(schema["properties"]))
        for field in ("verifiedContext", "enterpriseSystemsAccessed", "evidence",
                      "failedTools", "errorSummary", "pendingAction"):
            self.assertIn(field, record)
        self.assertIn("billing-service", record["enterpriseSystemsAccessed"])
        self.assertTrue(any(e["eventType"] == "tool.failed" and e["component"] == "billing-service"
                            for e in app.get_trace(result["traceId"])["events"]))

    def test_billing_rejects_non_numeric_amount(self):
        with patch.object(app, "call_json", return_value={
            "accountId": "ACC-2001", "period": "2026-09",
            "total": "not-a-number", "items": []
        }):
            result = app.handle_chat("Show my bill", self.session)
        self.assertEqual(result["status"], "escalated")
        self.assertNotIn("$0.00", result["answer"])

    def test_billing_rejects_malformed_line_item_and_records_tool_failure(self):
        with patch.object(app, "call_json", return_value={
            "accountId": "ACC-2001", "period": "2026-09", "total": 84.99,
            "items": [{"description": "Fiber 500", "amount": "not-a-number"}]
        }):
            result = app.handle_chat("Show my bill", self.session)
        self.assertEqual(result["status"], "escalated")
        events = app.get_trace(result["traceId"])["events"]
        self.assertTrue(any(e["eventType"] == "tool.failed" and e["component"] == "billing-service"
                            for e in events))

    def test_device_diagnostics_unavailable_escalates_for_normal_network_status(self):
        jordan = self.login("jordan.lee", "ReviewerPass-1002")
        with patch.dict(os.environ, {"MOCK_DIAGNOSTICS_MODE": "unavailable"}):
            result = app.handle_chat("My mobile service is slow", jordan["sessionId"])
        self.assertEqual(result["status"], "escalated")
        self.assertIn("device-diagnostics", result["escalation"]["enterpriseSystemsAccessed"])
        self.assertTrue(any(x["component"] == "device-diagnostics"
                            for x in result["escalation"]["failedTools"]))
        self.assertNotIn("no device fault", result["answer"].lower())

    def test_device_diagnostic_fault_is_reported_with_verified_reference(self):
        jordan = self.login("jordan.lee", "ReviewerPass-1002")
        with patch.dict(os.environ, {"MOCK_DIAGNOSTICS_MODE": "fault"}):
            result = app.handle_chat("My mobile service is slow", jordan["sessionId"])
        self.assertEqual(result["status"], "resolved")
        self.assertIn("device diagnostics detected a fault", result["answer"].lower())
        self.assertRegex(result["data"]["diagnostics"]["diagnosticId"], r"^DIAG-[A-F0-9]{6}$")
        self.assertIn("device-diagnostics", result["sources"])

    def test_network_endpoint_denies_service_types_not_owned_by_customer(self):
        session = app.SESSIONS[self.session]
        with self.assertRaises(app.ServiceError) as raised:
            app._network("94105", session, app._new_trace(), "mobile")
        self.assertEqual(raised.exception.status, 403)

    def test_multi_system_legacy_failure_escalates_instead_of_claiming_health(self):
        jordan = self.login("jordan.lee", "ReviewerPass-1002")
        with patch.dict(os.environ, {"MOCK_LEGACY_MODE": "unavailable"}):
            result = app.handle_chat("My mobile service is slow", jordan["sessionId"])
        self.assertEqual(result["status"], "escalated")
        self.assertIn("could not fully verify", result["answer"].lower())
        self.assertIn("legacy-adapter", result["escalation"]["enterpriseSystemsAccessed"])
        self.assertTrue(result["escalation"]["failedTools"])

    def test_gemini_clarification_flag_is_honored(self):
        app.AI_MODE = "live"
        with patch.object(app, "_gemini_intent", return_value={
            "intent": "billing", "accountId": None, "serviceType": None,
            "issueSummary": "Show my bill", "clarificationNeeded": True
        }):
            result = app.handle_chat("Show my bill", self.session)
        self.assertEqual(result["status"], "clarification")
        self.assertIn("billingQuestion", result["missingFields"])

    def test_legacy_business_error_is_escalated(self):
        with patch.object(app, "_legacy_status", return_value={
            "accountId": "ACC-2001", "serviceId": "SVC-5001",
            "serviceStatus": "unknown", "networkStatus": "unknown",
            "errorCode": "503", "error": "legacy_unavailable"
        }):
            result = app.handle_chat("Check my home internet legacy subscriber status", self.session)
        self.assertEqual(result["status"], "escalated")
        self.assertIn("legacy_unavailable", result["answer"])

    def test_mock_case_api_idempotency_returns_existing_case(self):
        payload = {"customerId": "CUST-1001", "accountId": "ACC-2001",
                   "summary": "Synthetic test", "idempotencyKey": "test-idempotency-key"}
        token = app.SESSIONS[self.session]["accessToken"]
        headers = {"Authorization": "Bearer " + token}
        created = app.call_json("POST", "/api/support-cases", payload=payload,
                                headers=headers, retry_get=False)
        repeated = app.call_json("POST", "/api/support-cases", payload=payload,
                                 headers=headers, retry_get=False)
        self.assertEqual(created["caseId"], repeated["caseId"])
        self.assertEqual(len(mock.CASES), 1)

    def test_idempotency_key_cannot_be_reused_for_another_account(self):
        alex_token = app.SESSIONS[self.session]["accessToken"]
        headers = {"Authorization": "Bearer " + alex_token}
        key = "shared-test-key"
        app.call_json("POST", "/api/support-cases",
                      payload={"customerId": "CUST-1001", "accountId": "ACC-2001",
                               "summary": "Alex test", "idempotencyKey": key},
                      headers=headers, retry_get=False)
        jordan = self.login("jordan.lee", "ReviewerPass-1002")
        jordan_token = app.SESSIONS[jordan["sessionId"]]["accessToken"]
        with self.assertRaises(app.ServiceError) as raised:
            app.call_json("POST", "/api/support-cases",
                          payload={"customerId": "CUST-1002", "accountId": "ACC-2002",
                                   "summary": "Jordan test", "idempotencyKey": key},
                          headers={"Authorization": "Bearer " + jordan_token}, retry_get=False)
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(len(mock.CASES), 1)

    def test_mock_case_rejects_non_string_idempotency_key(self):
        token = app.SESSIONS[self.session]["accessToken"]
        with self.assertRaises(app.ServiceError) as raised:
            app.call_json("POST", "/api/support-cases",
                          payload={"customerId": "CUST-1001", "accountId": "ACC-2001",
                                   "summary": "Synthetic test", "idempotencyKey": ["bad", "key"]},
                          headers={"Authorization": "Bearer " + token}, retry_get=False)
        self.assertEqual(raised.exception.status, 400)
        self.assertEqual(mock.CASES, {})

    def test_logout_revokes_session_and_pending_confirmation(self):
        pending = app.handle_chat("Create a support case for my internet issue", self.session)
        self.assertEqual(pending["status"], "confirmation_required")
        result = app.logout_session(self.session)
        self.assertEqual(result["status"], "signed_out")
        self.assertNotIn(self.session, app.SESSIONS)
        self.assertFalse(any(p.get("sessionId") == self.session for p in app.PENDING_ACTIONS.values()))
        with self.assertRaises(app.ServiceError) as raised:
            app.handle_chat("What plan am I using?", self.session)
        self.assertEqual(raised.exception.status, 401)

    def test_operations_metrics_and_traces_are_support_agent_only(self):
        with self.assertRaises(app.ServiceError) as raised:
            app.require_operations_session(self.session)
        self.assertEqual(raised.exception.status, 403)
        support = self.login("support.agent", "ReviewerPass-3001")
        allowed = app.require_operations_session(support["sessionId"])
        self.assertEqual(allowed["customerId"], "AGENT-3001")

    def test_negative_case_request_never_creates_or_leaves_pending_action(self):
        request = app.handle_chat("Create a support case for my internet issue", self.session)
        self.assertEqual(request["status"], "confirmation_required")
        result = app.handle_chat("No, don't create a support case", self.session)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["intent"], "action_declined")
        self.assertIn("will not create", result["answer"].lower())
        self.assertEqual(mock.CASES, {})
        self.assertFalse(any(p.get("sessionId") == self.session for p in app.PENDING_ACTIONS.values()))

    def test_escalation_summary_redacts_secrets_and_common_pii(self):
        safe = app._safe_summary(
            "Contact alex.morgan@example.test phone +1-415-555-1212 token=abc-secret Bearer secret-token"
        )
        self.assertNotIn("alex.morgan@example.test", safe)
        self.assertNotIn("+1-415-555-1212", safe)
        self.assertNotIn("abc-secret", safe)
        self.assertNotIn("secret-token", safe)
        self.assertIn("[REDACTED_EMAIL]", safe)
        self.assertIn("[REDACTED_PHONE]", safe)


if __name__ == "__main__":
    unittest.main()
