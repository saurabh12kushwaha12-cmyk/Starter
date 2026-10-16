# Gemini CX & Telco — Productionized Challenge Submission

## Vercel mobile web application

The repository now includes a Next.js web interface in `app/` alongside the original Python challenge implementation. The original solution is preserved on the `archive/main-before-vercel` branch; ongoing web-app work is on `main`.

### Deploy and configure

The Vercel project is linked to this GitHub repository and deploys from `main`. Configure these server-only environment variables in Vercel Project Settings:

- `DATABASE_URL`: connected to the dedicated `starter-app-isolated` Neon branch. Do not expose this variable to browser code.
- `AI_MODE=live`
- `GEMINI_MODEL=gemini-3.8-flash`
- `GEMINI_API_KEY`: add the private key in Vercel's encrypted environment-variable settings. Do not put it in GitHub, this file, screenshots, or chat messages.

After changing environment variables, trigger a redeployment so the new deployment receives them. Gemini is optional for reviewer-mode behavior; the app falls back to deterministic classification when the key is missing or the provider fails.

### Web app capabilities

- Responsive mobile-first login and customer support workspace.
- Synthetic demo accounts: `alex.morgan / ReviewerPass-1001`, `jordan.lee / ReviewerPass-1002`, and `support.agent / ReviewerPass-3001`.
- Server-side session token hashing, an HTTP-only cookie, role checks, customer data isolation, request tracing, and a Neon-backed audit trail.
- Bill, usage, plan, network troubleshooting and support-case workflows. Case creation requires an explicit confirmation and is protected by a database idempotency key.
- The support-agent role alone can view aggregated operations counts and sanitized events.

All accounts and service details are synthetic. This is a challenge test application, not a live telecom subscriber system.

### Web API smoke checks

- `GET /api/health` — runtime, Neon connectivity, AI mode and key-presence status (never returns secrets).
- `POST /api/auth/login` — establishes an HTTP-only session.
- `GET /api/auth/me` — validates the current session.
- `POST /api/chat` — intent routing and guarded customer workflow.
- `POST /api/confirm` — confirm or cancel the pending support-case action.
- `GET /api/ops` — role-restricted aggregated operations data.

The original Python test suite remains available with `python3 -m unittest discover -s starter-solution/tests -v`. The Vercel version is a new web runtime and should also be exercised through the deployed mobile UI after its Neon and Gemini environment configuration is complete.


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
- `GET /traces/{TRACE-ID}` — structured events for one request (**support-agent session required**)
- `GET /metrics` — metrics computed from the event log (**support-agent session required**)
- `GET /escalations` — recent synthetic escalation records (**support-agent session required**)

Send the active application session in the `X-Session-ID` header for these three operations endpoints. Their traces contain a stable, hashed session reference—not the actual session ID used to authenticate. Never share an application session ID.

The application writes `starter-solution/events.jsonl` and `starter-solution/escalations.jsonl` by default. Set `EVENTS_FILE` and `ESCALATIONS_FILE` to override their paths.

## Implemented controls

- server-side sessions and expiry checks; no token is returned to the browser or sent to Gemini
- deterministic record ownership and role checks before account retrieval
- input size validation, structured provider output validation, sanitized telemetry
- controlled enterprise actions require explicit confirmation and use idempotency keys
- safe GET retries, bounded network timeouts, malformed response checks, legacy XML validation and error mapping
- escalation on unresolved integration failures without claiming false success
- request trace IDs, event-derived metrics, reviewer/live/degraded mode indications
- hashed session references in telemetry; operational trace/metrics/escalation routes restricted to the synthetic support-agent role
- local CSP and browser security headers; response bodies do not echo the application session ID or internal action idempotency key

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
