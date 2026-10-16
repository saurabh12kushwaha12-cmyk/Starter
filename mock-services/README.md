# Mock Enterprise Services

Run from the repository root:

```bash
python3 mock-services/server.py
```

The mock API listens on `127.0.0.1:8090` by default. It reads only the supplied synthetic JSON records. It is a challenge/test dependency, not a production telecom API.

## Authentication

- `GET /health` and `POST /api/auth/login` do not require a bearer token.
- All customer/account/billing/network/diagnostics/case/legacy endpoints require `Authorization: Bearer <synthetic-token>`.
- The login endpoint issues random, short-lived opaque bearer tokens; the application keeps them server-side and never writes them into traces. Successful mock tokens expire after 3,600 seconds; `MOCK_AUTH_MODE=expired` simulates an already-expired token.
- Customer tokens can access only their own customer, account, bill, postal-code network status and services. When `serviceType` is supplied to the network endpoint, the type must belong to that customer's account. The synthetic support-agent role can access records across customers, subject to action validation.
- Support-case creation validates customer/account ownership and summary limits. Repeated idempotency keys return the previously created case rather than creating a duplicate.

## Failure simulation

Set these environment variables before starting the mock server:

- `MOCK_AUTH_MODE=normal|expired|unavailable`
- `MOCK_LEGACY_MODE=success|timeout|unavailable|malformed`
- `MOCK_CASE_MODE=success|unavailable`
- `MOCK_BILLING_MODE=success|unavailable|malformed`
- `MOCK_DIAGNOSTICS_MODE=success|fault|inconclusive|unavailable|malformed`

Only synthetic identities and data are supported. Do not add real customer information or secrets.
