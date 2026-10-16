# 3–5 minute demonstration script

Use only supplied synthetic reviewer accounts. Start the mock service and app as shown in the root README. Keep API keys and environment secrets off-screen.

1. **Overview (20–30 sec):** Open the Resolution Console, point out Reviewer mode, the health indicator, and event-derived metrics.
2. **Grounded inquiry (30 sec):** Sign in as `alex.morgan`, ask “What internet plan am I currently using?”, and show the `Fiber 500` answer and account-service source.
3. **Clarification and multi-system path (45 sec):** Ask “My service is not working.”, answer “home internet”, and show the network/legacy integration result.
4. **Protected action (45 sec):** Ask to create a support case. Show that no case is created before confirmation, then confirm and show the verified case ID. Repeat the exact request to demonstrate duplicate prevention.
5. **Authorization boundary (30 sec):** Ask for `ACC-2002` while signed in as Alex and show access denied without returning Jordan’s account data.
6. **Failure/escalation (45 sec):** In a separate terminal, restart the mock service with `MOCK_CASE_MODE=unavailable` (or set it before launch), request and confirm a case, and show that the app escalates rather than claiming success. Restore normal mode afterwards.
7. **Trace and metrics (30 sec):** Open the last trace and refresh metrics. Show correlation ID, tool/authorization events, and metrics changing from actual runs.
8. **Automated tests (20–30 sec):** Show `python3 -m unittest discover -s starter-solution/tests -v` passing.

If live Gemini is configured and has actually succeeded, demonstrate it and show `Live Gemini`. Otherwise state honestly that the demonstration used Reviewer mode or degraded fallback; do not describe reviewer output as a live model call.
