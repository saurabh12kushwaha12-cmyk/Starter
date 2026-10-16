# Starter Solution

This folder contains the application implementation and its automated tests.

For the full setup and operating instructions, start at the repository-root [README](../README.md). From the repository root, start the synthetic enterprise services first:

```bash
python3 mock-services/server.py
```

Then start the app in a second terminal:

```bash
AI_MODE=reviewer python3 starter-solution/server.py
```

Open `http://127.0.0.1:8080`.

Run the test suite from the repository root:

```bash
python3 -m unittest discover -s starter-solution/tests -v
```

This is a local challenge proof-of-capability, not a production telecom service. Use synthetic records only. The root README, developer handover and known-gaps documents describe implemented flows and remaining Live AI/cloud/demo work.
