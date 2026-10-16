# Known limitations and production follow-up

This is a synthetic-data proof-of-capability designed for the challenge's local evaluation—not a production telco service.

1. **Live Gemini verification:** The REST integration is implemented, but a successful live call must be tested with the participant's own approved credential. No API key is included in the repository.
2. **In-memory state:** Sessions, pending confirmations, and deduplication cache are process-local. A production/multi-instance deployment needs durable shared storage and transaction-safe idempotency.
3. **Local telemetry:** Events and escalations are JSONL files. Production needs managed log/trace/metric export, rotation, retention, monitoring alerts, and access control.
4. **Synthetic authentication:** The mock login is only for the supplied test accounts. It is not a real identity provider or production credential lifecycle.
5. **Operational hardening:** Add rate limiting, CSRF protections for any cookie-based deployment, stronger HTTP security headers, dependency/image scanning, and a production-grade reverse proxy before exposing outside a trusted test environment.
6. **Action scope:** The sample implements support-case creation as the consequential action. Other account/service changes are not implemented and must not be represented as available.
7. **Google Cloud:** Deployment mapping is documented, but this repository does not provision Cloud Run, Vertex AI, Cloud Logging, Cloud Trace, Firestore, Cloud SQL, Secret Manager, or Monitoring resources.
8. **Evaluation evidence:** Run the suite in the final checkout, validate live Gemini separately, and record the required 3–5 minute demo before submission. Never claim tests or deployment that have not been run.
