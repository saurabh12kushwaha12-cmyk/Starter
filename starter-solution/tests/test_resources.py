"""Functional, authorization, integration, failure-path and telemetry tests for the PoC."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
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

    @classmethod
    def tearDownClass(cls):
        cls.mock_http.shutdown()
        cls.mock_http.server_close()
        cls.mock_thread.join(timeout=2)

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
        self.alex = app.login("alex.morgan", "ReviewerPass-1001")
        self.session = self.alex["sessionId"]

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, username="alex.morgan", password="ReviewerPass-1001"):
        return app.login(username, password)

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

    def test_protected_account_query_requires_authentication(self):
        result = app.handle_chat("What plan am I using?", None)
        self.assertEqual(result["status"], "authentication_required")
        self.assertEqual(result["httpStatus"], 401)

    def test_plan_inquiry_is_grounded_in_account_api(self):
        result = app.handle_chat("What internet plan am I currently using?", self.session)
        self.assertEqual(result["status"], "resolved")
        self.assertIn("Fiber 500", result["answer"])
        self.assertEqual(result["sources"], ["account-service"])
        self.assertEqual(result["data"]["accountId"], "ACC-2001")

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

    def test_legacy_xml_response_is_normalized(self):
        result = app.handle_chat("Check my legacy subscriber status", self.session)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["data"]["accountId"], "ACC-2001")
        self.assertEqual(result["data"]["serviceId"], "SVC-5001")
        self.assertEqual(result["data"]["errorCode"], "0")

    def test_case_requires_confirmation_then_creates_one(self):
        result = app.handle_chat("Create a support case for my internet issue", self.session)
        self.assertEqual(result["status"], "confirmation_required")
        self.assertFalse(mock.CASES)
        confirmation = app.confirm_action(self.session, result["confirmationId"], True)
        self.assertEqual(confirmation["status"], "resolved")
        self.assertIn("caseId", confirmation["data"])
        self.assertEqual(len(mock.CASES), 1)
        repeat = app.handle_chat("Create a support case for my internet issue", self.session)
        self.assertTrue(repeat.get("actionAlreadyCompleted"))
        self.assertEqual(len(mock.CASES), 1)

    def test_case_cancellation_does_not_execute(self):
        result = app.handle_chat("Open a ticket for my problem", self.session)
        self.assertEqual(result["status"], "confirmation_required")
        cancelled = app.confirm_action(self.session, result["confirmationId"], False)
        self.assertEqual(cancelled["status"], "cancelled")
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
            encoded = json.dumps(event).lower()
            self.assertNotIn("reviewerpass", encoded)
            self.assertNotIn("accesstoken", encoded)
        metrics = app.get_metrics()
        self.assertGreaterEqual(metrics["totalRequests"], 1)
        self.assertGreaterEqual(metrics["eventCount"], trace["eventCount"])

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
        self.assertTrue({"customer-profile", "account-service", "network-diagnostics", "legacy-adapter"}.issubset(components))

    def test_malformed_legacy_xml_is_not_reported_as_success(self):
        with patch.dict(os.environ, {"MOCK_LEGACY_MODE": "malformed"}):
            result = app.handle_chat("Check my legacy subscriber status", self.session)
        self.assertEqual(result["status"], "escalated")
        self.assertNotIn("subscriber status: service active", result["answer"].lower())

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

    def test_mock_enterprise_api_rejects_missing_bearer_token(self):
        with self.assertRaises(app.ServiceError) as raised:
            app.call_json("GET", "/api/customers/CUST-1001", retry_get=False)
        self.assertEqual(raised.exception.status, 401)

    def test_mock_api_enforces_customer_ownership_independently(self):
        with self.assertRaises(app.ServiceError) as raised:
            app.call_json(
                "GET",
                "/api/accounts/ACC-2001",
                headers={"Authorization": "Bearer synthetic-CUST-1002"},
                retry_get=False,
            )
        self.assertEqual(raised.exception.status, 403)

    def test_escalation_contains_context_systems_and_failed_tool_evidence(self):
        with patch.dict(os.environ, {"MOCK_BILLING_MODE": "malformed"}):
            result = app.handle_chat("Show my bill", self.session)
        self.assertEqual(result["status"], "escalated")
        record = result["escalation"]
        for field in ("verifiedContext", "enterpriseSystemsAccessed", "evidence",
                      "failedTools", "errorSummary", "pendingAction"):
            self.assertIn(field, record)
        self.assertIn("billing-service", record["enterpriseSystemsAccessed"])

    def test_billing_rejects_non_numeric_amount(self):
        with patch.object(app, "call_json", return_value={
            "accountId": "ACC-2001", "total": "not-a-number", "items": []
        }):
            result = app.handle_chat("Show my bill", self.session)
        self.assertEqual(result["status"], "escalated")
        self.assertNotIn("$0.00", result["answer"])

    def test_multi_system_legacy_failure_escalates_instead_of_claiming_health(self):
        jordan = self.login("jordan.lee", "ReviewerPass-1002")
        with patch.dict(os.environ, {"MOCK_LEGACY_MODE": "unavailable"}):
            result = app.handle_chat("My mobile service is slow", jordan["sessionId"])
        self.assertEqual(result["status"], "escalated")
        self.assertIn("could not verify", result["answer"].lower())
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
            result = app.handle_chat("Check my legacy subscriber status", self.session)
        self.assertEqual(result["status"], "escalated")
        self.assertIn("legacy_unavailable", result["answer"])

    def test_mock_case_api_idempotency_returns_existing_case(self):
        payload = {"customerId": "CUST-1001", "accountId": "ACC-2001",
                   "summary": "Synthetic test", "idempotencyKey": "test-idempotency-key"}
        headers = {"Authorization": "Bearer synthetic-CUST-1001"}
        created = app.call_json("POST", "/api/support-cases", payload=payload,
                                headers=headers, retry_get=False)
        repeated = app.call_json("POST", "/api/support-cases", payload=payload,
                                 headers=headers, retry_get=False)
        self.assertEqual(created["caseId"], repeated["caseId"])
        self.assertEqual(len(mock.CASES), 1)


if __name__ == "__main__":
    unittest.main()
