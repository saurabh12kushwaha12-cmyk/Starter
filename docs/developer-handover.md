# Engineering handover

## Business problem and supported scope

This project is a local proof-of-capability for the Topcoder Gemini CX & Telco challenge. It demonstrates how a synthetic telecom customer request can be interpreted, authenticated, authorized, routed through enterprise adapters, answered from verified data, confirmed before a consequential action, and traced through success or escalation. It is not a production telecom service and must never be connected to real subscriber records.

Supported demonstrations are plan inquiry, bill lookup, service-scoped network status, device diagnostics, legacy subscriber status, and support-case creation. A case is not sent until explicit confirmation. Other service/account changes are not implemented.

## Component responsibilities

| Component | Responsibility |
|---|---|
| `starter-solution/server.py` | HTTP interface, server-side sessions, Gemini/reviewer classifier, request orchestration, policy/ownership checks, adapter validation, confirmation, escalation, telemetry and metrics |
| `mock-services/server.py` | Synthetic enterprise API; bearer token validation; customer/account/service-type ownership; service-scoped outage lookup; device diagnostics; idempotent support-case endpoint; failure switches |
| `sample-data/` | Synthetic identity, account, bill and outage records |
| `scenarios/` | Eight challenge scenario definitions |
| `schemas/` | Event, escalation and other payload schemas |
| `starter-solution/tests/test_resources.py` | Integration, authorization, failure, data-validation, telemetry and workflow test suite |
| `docs/architecture.md` | Trust boundaries, control flow and persistence model |
| `docs/requirement-to-evidence.md` | Requirement-to-implementation/test/limitation mapping |

The primary orchestration is a deterministic Python workflow with a Gemini intent/entity-classification step in Live AI mode. Reviewer mode changes the classifier only; it does not bypass authentication, adapters, ownership checks, confirmation, event logging or escalation. The design intentionally avoids giving the model direct API credentials or unrestricted tool access.

## Local run and test

From the repository root, start two terminals:

```bash
python3 mock-services/server.py
```

```bash
AI_MODE=reviewer python3 starter-solution/server.py
```

Open `http://127.0.0.1:8080`. For ordinary customer demonstrations, use the synthetic customer account. For cross-customer operations metrics, request traces and escalation records, sign in with the synthetic support agent shown in the README. Operations routes reject unauthenticated users and sessions without the `support-agent` role.

Run all automated tests:

```bash
python3 -m unittest discover -s starter-solution/tests -v
```

The test fixture starts an isolated local instance of the mock API and writes events/escalations to temporary files. No external Gemini key is required for Reviewer mode.

## How to add an enterprise tool

1. Add the smallest focused adapter in `starter-solution/server.py`. Use `request_raw` or `call_json`, finite timeouts, a server-side bearer token from the authenticated session, and a distinct component name.
2. Validate response identity and every field needed for a customer-facing answer. Reject malformed types, unexpected record IDs, non-finite numeric values and partial data that cannot support a safe answer.
3. Enforce user role, customer ownership and workflow state in application code before making the call. Never rely on Gemini output as an authorization decision.
4. Emit `tool.invoked`, `tool.completed` and `tool.failed` events. Include only necessary sanitized metadata and preserve the request's trace ID.
5. Map documented upstream errors to `ServiceError`. Retry idempotent reads in a bounded way. The current implementation permits one retry for support-case creation only when the idempotency key is present; other consequential writes must not retry automatically.
6. Add success, unauthorized access, malformed response, timeout/unavailable service and redaction tests. Update `api-contracts/enterprise-api.yaml`, architecture, README and the evidence matrix.
7. Extend `mock-services/server.py` with synthetic data, bearer checks, ownership checks and explicit failure simulation so the flow remains reproducible offline.

## How to change orchestration safely

The supported deterministic routing is centralized in `_deterministic_intent`, with Gemini structured classification in `_gemini_intent` and provider fallback in `classify`. The customer workflow is dispatched in `handle_chat`; service-issue workflows validate the profile/account, query the postal-code plus owned service type, run a device diagnostic, and normalize the legacy XML status. Controlled case execution is isolated in `confirm_action`. Keep policy checks outside the model. For new intents, define accepted structured fields, ask for any missing information, preserve context, route only to a narrowly scoped adapter, and define explicit terminal outcomes. Add a bounded clarification/confirmation lifecycle so requests cannot loop forever.

Do not add speculative agent calls just to increase the agent count. If a specialized agent is added, document its responsibility, allowed context/tools, input/output schema, timeouts, stop conditions and tests. No model component should receive stored access tokens, API keys or unrestricted enterprise endpoint access.

## Inspect traces and troubleshoot

Operations endpoints require the `X-Session-ID` header from an active `support-agent` application session:

- `GET /metrics` — event-derived operational metrics.
- `GET /traces/{TRACE-ID}` — the correlated events for a request.
- `GET /escalations` — the latest escalation records with context and failure evidence.
- `GET /health` — app/mock dependency status and configured AI mode.

Look for `request.received`, `agent.invoked`, `intent.classified`, `tool.invoked`, `tool.completed` or `integration.failure`, and the final workflow event. Inspect the failed component and error summary before considering any retry. For an action with an unverified outcome, check its idempotency key and the downstream case record before repeating it.

Common local issues:
- Mock API unavailable: make sure terminal 1 is running and `MOCK_API_BASE` points to it.
- Sign-in fails: use one of the supplied synthetic accounts and check `MOCK_AUTH_MODE`.
- Legacy/billing/case failure: return the corresponding `MOCK_*_MODE` setting to `success` after the demonstration.
- Live AI falls back: check the model name, key permissions, outbound connectivity and quota. The code records a provider-failure event and retains deterministic security controls.
- Metrics/traces return 403: sign in as `support.agent`; customer roles are not allowed to inspect cross-customer operations data.

## Security and production roadmap

- Continue to use only synthetic records; do not connect these mocks to real subscribers.
- Store credentials in a secret manager or identity mechanism; never commit them.
- Before production, replace process-local sessions, confirmation state and completed-action cache with durable shared storage and atomic idempotency; move JSONL telemetry to managed logging/tracing and metrics storage.
- Add CSRF protection if changing to cookies, rate limits, stricter security headers, input/rate controls, dependency and container scanning, log retention/access policies and managed identity.
- Build a pinned non-root container, deploy behind appropriate private networking, configure health checks, least-privilege IAM, timeouts, alerts, budget limits and a verified rollback runbook.
- Validate a real successful Gemini request in a controlled account, run the full suite from a clean checkout, exercise every mandatory scenario and record the requested 3–5 minute demonstration. Do not claim cloud deployment or Live AI success until actually performed.
