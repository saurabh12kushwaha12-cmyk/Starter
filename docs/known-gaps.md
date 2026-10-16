# Known Starter Gaps
1. Keyword routing replaces live Gemini integration.
2. Authentication is not wired into the starter workflow.
3. Account lookup is hardcoded and lacks ownership enforcement.
4. Tool permissions and model-output validation are absent.
5. Case creation, confirmation, and idempotency are not implemented in the starter.
6. Legacy XML is returned without normalization.
7. Retry, timeout, rate-limit, malformed-response, and escalation behavior is incomplete.
8. Logging is minimal; traces, redaction, and metrics are incomplete.
9. Automated tests cover only package integrity.
10. Google Cloud deployment assets and production hardening are absent.
