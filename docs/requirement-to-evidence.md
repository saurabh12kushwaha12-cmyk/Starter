# Requirement-to-evidence matrix

| Challenge area | Implementation | Test/evidence | Status in this repository |
|---|---|---|---|
| Gemini/live AI and degradation | `starter-solution/server.py` (`_gemini_intent`, `classify`) | `test_gemini_provider_failure_uses_explicit_degraded_mode`; live-mode credential configuration and demo required | Code implemented; live successful API call must be verified with a real key |
| Reviewer mode | Deterministic intent classifier, same downstream workflow/adapters/controls | Full unittest suite without paid access | Implemented |
| Protected account information | `require_session`, `authorized_account`, `_account` | plan inquiry, unauthenticated access, cross-customer access tests | Implemented |
| Billing integration/validation | `_billing` | billing success and malformed response tests | Implemented |
| Multi-system workflow | service-issue path combines profile, account, network, legacy | `test_multi_system_issue_calls_profile_account_network_and_legacy` | Implemented |
| Legacy XML adapter | `_legacy_status` validates XML, account/service identity, maps codes | success and malformed XML tests | Implemented |
| Consequential action confirmation | `handle_chat`, `confirm_action` | confirmation, cancellation, confirmation ownership, deduplication tests | Implemented for support-case creation |
| Failure handling/escalation | `ServiceError`, bounded timeout/retries, `_escalate` | case failure, malformed billing, malformed legacy, Gemini degradation tests | Implemented for supplied mock failure switches |
| Structured telemetry and traces | `emit`, `GET /traces/{traceId}` | schema/trace/redaction test | Implemented (JSONL local persistence) |
| Event-derived metrics | `get_metrics`, `GET /metrics` | metrics-changing test | Implemented (computed from local event log) |
| Eight scenario definitions | `scenarios/SCN-001.json` to `SCN-008.json` | resource integrity plus workflow tests for the eight scenario families | Implemented, run suite before submission |
| Architecture diagram | `docs/architecture.md` | reviewer inspection | Included |
| Google Cloud plan | `docs/gcp-deployment.md` | reviewer inspection | Plan included; no live GCP infrastructure provisioned |
| Customer handover | root README, architecture/deployment/demo docs | reviewer inspection | Included |
| Demo recording | Record the application with `docs/demo-script.md` | 3–5 minute screen recording | Must be recorded by participant |

## Commands used for reproducible local evidence

```bash
python3 -m unittest discover -s starter-solution/tests -v
```

Tests use synthetic data and start the mock API inside the test process. They do not require a live Gemini key. Before submission, also run the app manually in reviewer mode, then live mode with a valid private API credential, and capture a 3–5 minute recording. Do not mark the live Gemini success test complete unless it was actually exercised.
