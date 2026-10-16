# Google Cloud deployment mapping

This is a deployment plan, not a claim that a cloud environment has already been provisioned.

| Component | Suggested Google Cloud mapping | Required work before production |
|---|---|---|
| Python HTTP application | Cloud Run service | Container build, non-root user, health/readiness probes, request concurrency tuning |
| Gemini | Vertex AI Gemini where approved; current local adapter also supports Gemini API key REST | Use service identity/ADC or Secret Manager; verify model/location and enabled APIs |
| Synthetic enterprise dependencies | Keep as local mock services for judging; replace only with explicitly approved test adapters | Do not connect to real telecom customer records for this challenge |
| Configuration | Cloud Run environment variables | Separate non-secret settings from credentials |
| Secret material | Secret Manager + service identity | Never bake keys into image or repository; rotate credentials |
| Event/trace pipeline | Cloud Logging and Cloud Trace/OpenTelemetry export | Add structured logger/exporter, sampling, retention, and PII filtering |
| Escalation/action idempotency | Firestore or Cloud SQL transaction-backed record | Persist confirmations/idempotency and use atomic updates across instances |
| Operational metrics | Cloud Monitoring custom metrics/dashboards | Export counters/histograms from real events and define alerts |
| CI | GitHub Actions | Run unit/security tests, dependency/code scanning, build and deploy only from protected branch |

## Deployment checklist

1. Build a pinned, non-root container image and publish to Artifact Registry.
2. Deploy the application to Cloud Run with minimum necessary IAM permissions.
3. Keep mock services internal or sidecar-like for the challenge demonstration; production enterprise endpoints must use authenticated private connectivity.
4. Configure a health/readiness check and finite outbound timeouts. Keep action retries conservative; only GET requests are automatically retried by the current PoC.
5. Supply Gemini credentials through a managed secret or a dedicated service identity—not `GEMINI_API_KEY` committed into Git.
6. Replace in-memory sessions, pending confirmations, and completed-action cache with shared durable stores before scaling beyond one process/instance.
7. Export structured telemetry, traces, and operational metrics; redact personal data and secrets before export.
8. Set budget alerts, request/latency/error alerts, retention policies, and a rollback revision.
9. Run all eight scenarios against the deployed test environment before considering the deployment validated.

The provided app is intentionally runnable locally with Python's standard library. A reviewer can validate it without a Google Cloud account or paid reviewer access; live Gemini mode requires an approved API credential.
