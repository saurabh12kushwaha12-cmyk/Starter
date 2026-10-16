# Gemini CX & Telco — Productionized Challenge Submission

A runnable Python proof-of-capability for the Topcoder **Enterprise AI Customer Experience Resolution System: Gemini CX & Telco** challenge. It retains the supplied synthetic data, mock enterprise APIs, eight review scenarios, and original standard-library architecture while completing the main workflow, authorization, integration, failure, and telemetry gaps.

> **Safety:** All supplied users and account records are synthetic. Do not connect this challenge application to real subscriber records. Active credentials must never be committed to Git.

## Quick start

Requirements: Python 3.10+ (standard library only; no package installation needed).

Terminal 1 — mock enterprise services:

```bash
python3 mock-services/server.py
```

Terminal 2 — application:

```bash
AI_MODE=reviewer python3 starter-solution/server.py
```

Open `http://127.0.0.1:8080`.

Reviewer demo account:

- Username: `alex.morgan`
- Password: `ReviewerPass-1001`

Second synthetic customer (use to verify record isolation): `jordan.lee` / `ReviewerPass-1002`.

Synthetic operations user (required for cross-customer metrics, traces and escalation records): `support.agent` / `ReviewerPass-3001`. The operations endpoints reject customer-role and unauthenticated access.

## Run automated evaluation

From the repository root:

```bash
python3 -m unittest discover -s starter-solution/tests -v
```

The test suite starts a local mock-service instance, uses isolated temporary event/escalation logs, and covers the eight mandatory scenario families plus authentication, cross-customer denial, confirmation/idempotency, legacy XML normalization, malformed service responses, Gemini degradation, telemetry, and metrics. No external API key or paid access is needed for reviewer-mode tests.

## AI modes

- **Reviewer mode** (`AI_MODE=reviewer`): deterministic intent classification, but the same authenticated application workflow, mock enterprise APIs, validation, confirmation, case creation, escalation, events, traces, and metrics are exercised.
- **Live mode** (`AI_MODE=live`): uses the Gemini `generateContent` REST endpoint when `GEMINI_API_KEY` is supplied. Configure `GEMINI_MODEL` as needed. If Gemini is unavailable, the app records `gemini.failure` and enters an explicit degraded deterministic mode; the application still enforces authorization and action confirmation outside the model.

Copy `.env.example` values into your local shell or a private `.env` file; the standard library app does not automatically parse `.env` files. Use a current Gemini API key restricted to the Gemini API (or an authorization key from AI Studio); Google's current guidance says unrestricted standard keys are being rejected. Never expose API keys in screenshots, logs, client responses, or commits.

Example (bash):

```bash
export AI_MODE=live
export GEMINI_API_KEY='your-key-from-a-secret-store'
export GEMINI_MODEL='gemini-3.8-flash'
python3 starter-solution/server.py
```

The live model classifies and extracts a constrained intent only. It never receives the stored access token and cannot grant permissions or directly execute an enterprise action.

## Local API

- `GET /` — responsive conversation and operational console
- `GET /health` — app/mock-service health and AI-mode configuration
- `POST /auth/login` — authenticate against the supplied synthetic mock service
- `POST /chat` — classify a request and run guarded workflows
- `POST /confirm` — confirm or cancel the pending support-case action
- `GET /traces/{TRACE-ID}` — structured events for one request
- `GET /metrics` — metrics computed from the event log
- `GET /escalations` — recent synthetic escalation records

The application writes `starter-solution/events.jsonl` and `starter-solution/escalations.jsonl` by default. Set `EVENTS_FILE` and `ESCALATIONS_FILE` to override their paths.

## Implemented controls

- server-side sessions and expiry checks; no token is returned to the browser or sent to Gemini
- deterministic record ownership and role checks before account retrieval
- input size validation, structured provider output validation, sanitized telemetry
- controlled enterprise actions require explicit confirmation and use idempotency keys
- safe GET retries, bounded network timeouts, malformed response checks, legacy XML validation and error mapping
- escalation on unresolved integration failures without claiming false success
- request trace IDs, event-derived metrics, reviewer/live/degraded mode indications

## Architecture, evaluation evidence, deployment and demo

- [Architecture](docs/architecture.md)
- [Google Cloud deployment mapping](docs/gcp-deployment.md)
- [Requirement-to-evidence matrix](docs/requirement-to-evidence.md)
- [Three-to-five-minute demo script](docs/demo-script.md)
- [Known limitations](docs/known-gaps.md)
- [Developer handover and extension guide](docs/developer-handover.md)
- [Summary of changes](docs/changes-summary.md)
- Challenge reference: [TOPCODER_CHALLENGE_SPEC.md](TOPCODER_CHALLENGE_SPEC.md)

The Google Cloud items are a deployment mapping/plan, not a claim that a live GCP deployment has already been provisioned. Verify the test output and live Gemini configuration in your own environment before submitting.
