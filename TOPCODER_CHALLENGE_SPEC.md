# Enterprise AI Customer Experience Resolution System: Gemini CX & Telco

> Working copy of the substantive challenge specification, converted from the 25-page Topcoder PDF for use during implementation. Website chrome, repeated page headers/footers, and other non-requirement page furniture are omitted. The challenge requirements below are preserved as the working reference.
>
> **Source:** Topcoder challenge page PDF, “Enterprise AI Customer Experience Resolution System: Gemini CX & Telco”.  
> **Important:** Any countdown shown in a saved PDF is historical. Check the live Topcoder page for the current deadline and rules.

## Working overview

- **Event / challenge type:** AI Exponential League Practical Qualification and Productionization Challenge; Rapid Development Match.
- **Prize amounts displayed on the challenge page:** 1st $300, 2nd $200, 3rd $100.
- **Core job:** Complete and productionize the supplied starter solution. Do not replace it with an unrelated application.
- **Technology direction:** Gemini / Google AI capabilities, Google Cloud deployment mapping, enterprise service adapters, controlled workflow orchestration, security, telemetry, automated evaluation and handover.
- **Data boundary:** Use only supplied or synthetic customer data. Do not connect to real customer records.
- **Review expectation:** Reviewers must be able to run the app, exercise the required scenarios, inspect evidence, run tests and understand how to maintain the solution.

## Quick implementation guardrails

1. Preserve the starter solution and its supplied enterprise integrations so reviewers can inspect them.
2. Use Gemini meaningfully in the actual request workflow. A mock-only submission, hardcoded scenario branches or a single model call without service integration is insufficient.
3. Enforce authentication, record ownership, authorization, confirmation and protected actions in deterministic application code, not by trusting the model.
4. Route enterprise calls through controlled tools/adapters; do not give Gemini unrestricted access to raw enterprise endpoints.
5. Ground customer-facing answers in validated enterprise responses. Never invent records, charges, outages, case numbers or successful outcomes.
6. Require explicit confirmation before consequential actions and prevent duplicate execution.
7. Make Live AI, Reviewer and Degraded Fallback modes clearly identifiable. Reviewer mode must still use real application workflows, controls, adapters and telemetry.
8. Record structured events and request-level traces with correlation IDs. Do not log secrets, tokens or unnecessary personal data.
9. Keep the solution runnable locally, configured through environment variables and free of active credentials in source control.
10. Document what remains incomplete. Do not claim a requirement is complete without code/test/evidence.

## Current work checklist

- [ ] Inspect the supplied ZIP and map the actual starter project structure.
- [ ] Run the existing starter locally and record the initial state.
- [ ] Map every requirement to an existing component, planned change, test and evidence.
- [ ] Complete Gemini integration and validate structured outputs.
- [ ] Complete or improve workflow/orchestration and state management.
- [ ] Enforce authentication, authorization and customer isolation.
- [ ] Complete modern enterprise API integrations and legacy telecom adapter.
- [ ] Implement at least one safely confirmed consequential action with duplicate protection.
- [ ] Implement failure handling, fallback and human escalation.
- [ ] Implement structured telemetry, traces and event-derived metrics.
- [ ] Implement both Live AI and Reviewer modes.
- [ ] Automate all eight mandatory evaluation scenarios and additional test cases.
- [ ] Prepare README, architecture diagram, deployment documentation, handover package and requirement-to-evidence matrix.
- [ ] Record a reproducible 3–5 minute demonstration and write a summary of changes.
- [ ] Re-run the full tests and verify the submitted repository from a clean setup.

---

## Challenge overview

Topcoder seeks a production-grade Enterprise AI Customer Experience Resolution System built on Google Cloud Platform (GCP) and Gemini Customer Experience (Gemini CX) architecture.

The participant acts as a Lead Forward Deployed Engineer (FDE), designing, building and deploying an end-to-end AI customer-support resolution engine for a telecommunications / communications service provider (CSP). The system must securely integrate with legacy backend services, including Billing, Network Diagnostics and Account Auth; provide robust agent/workflow orchestration; implement enterprise-grade security; and provide complete observability and telemetry.

**Objective:** Build a proof-of-concept (PoC) enterprise agentic solution able to handle complex customer scenarios such as subscriber authentication, broadband hardware diagnostics, billing disputes and automated escalation, using Gemini CX / Google Cloud AI frameworks.

## Challenge goal

Complete and productionize the supplied customer-experience solution so that it can:

- Understand customer requests using Gemini.
- Ask relevant clarification questions.
- Manage conversation and workflow context.
- Coordinate agents, workflows and enterprise tools.
- Authenticate customers before accessing protected information.
- Enforce authorization outside the AI model.
- Integrate with modern and legacy enterprise systems.
- Produce responses grounded in verified enterprise data.
- Perform supported actions only after validation and confirmation.
- Handle AI and enterprise-service failures safely.
- Escalate unresolved requests with useful context.
- Generate structured logs, traces, events and operational metrics.
- Support repeatable automated evaluation.
- Provide a credible Google Cloud deployment approach.
- Enable another engineering team to understand and extend the solution.

The productionized solution is the practical evidence used to validate and rank competitors; building the solution is not the final business outcome of the challenge.

## Challenge scope and allowed approaches

The challenge combines:

- Existing codebase analysis
- Gemini integration and conversational AI
- Agentic architecture
- Workflow and tool orchestration
- Secure API implementation
- Authentication and authorization
- Enterprise integration and legacy-system adaptation
- Data pipelines
- Telemetry and observability
- Reliability engineering
- Automated testing
- Google Cloud deployment planning
- Technical handover

Participants may use a single controlled AI agent, multiple specialized agents, deterministic workflow orchestration, a hybrid AI/rules architecture, Google-supported agent frameworks or a custom implementation. Framework choice alone does not determine the score. The supplied starter solution must be improved rather than replaced with an unrelated implementation.

## Business scenario and known gaps

The telecommunications provider has separate enterprise systems for:

- Customer identity
- Customer profiles
- Accounts and subscriptions
- Billing information
- Product and service eligibility
- Network and service status
- Technical diagnostics
- Support-case management

The current AI-powered customer-experience implementation is not production-ready. Known gaps include:

- Incomplete Gemini integration
- Weak or incomplete agent orchestration
- Stubbed enterprise integrations
- Missing authorization controls
- Incomplete legacy-system handling
- Unsafe enterprise-action execution
- Limited failure handling
- Missing telemetry and traces
- Incomplete automated tests
- Limited deployment documentation

The resulting solution must be secure, reliable, observable and deployment-ready as a proof of capability.

**Data restriction:** This is a technical assessment environment. Use only supplied or synthetic customer data; do not connect to real customer records.

## Supplied starter package

The challenge starter package includes or is described as including:

- Partially implemented source code
- Basic customer interaction interface or conversation runner
- Initial Gemini integration or provider adapter
- Stubbed agent or workflow orchestration
- Mock authentication service
- Customer-profile service
- Account and subscription service
- Billing or service-information service
- Network-status or diagnostics service
- Case-management service
- Legacy telecom service
- Sample customer and account data
- Test users and roles
- Mandatory customer scenarios
- Failure-simulation controls
- API documentation and schemas
- Initial architecture documentation
- Known technical gaps
- Sample environment configuration

The same starter package, scenarios, test data and failure controls are provided to all competitors. Components may be refactored where necessary, but required workflows and supplied enterprise integrations must remain reviewable.

## Target users

### 1. Customer

The customer can ask account or service questions, report service issues, request technical assistance, review available service options, perform supported account/service actions and receive a verified resolution or escalation reference.

### 2. Customer support representative

An escalation should contain:

- Request summary
- Verified customer context
- Completed workflow steps
- Enterprise systems already accessed
- Retrieved evidence
- Failed tools or integrations
- Pending actions
- Recommended next step
- Request or trace identifier

### 3. Operations and engineering user

Operations and engineering users should be able to review workflow executions, agent/tool activity, integration performance, authentication/authorization events, failed requests, escalations, operational metrics and application health.

## Core user journey

1. Customer submits a natural-language request.
2. Gemini interprets the request and extracts relevant information.
3. The system asks for clarification if information is missing.
4. The customer authenticates before protected information or actions.
5. Deterministic authorization logic validates access.
6. The orchestrator selects the appropriate agent, workflow or enterprise tool.
7. Enterprise data is retrieved and normalized.
8. Returned information is validated.
9. A grounded response or proposed action is presented.
10. The customer confirms any consequential action.
11. The enterprise action is executed and verified.
12. The system returns a confirmed outcome or creates an escalation.
13. The complete execution is recorded through structured events and traces.
14. Operational metrics are updated from actual workflow activity.

---

## Functional requirements

### 1. Gemini and conversational AI

Gemini must be used meaningfully in the required customer workflows. Possible uses include intent classification, entity extraction, request interpretation, clarification-question generation, workflow planning, agent routing, tool selection, enterprise-information synthesis, grounded response generation and escalation summarization.

The solution must document:

- Gemini model or service used
- Where the model is invoked
- Purpose of every model invocation
- Context supplied to the model
- Prompt or agent instructions
- Structured output definitions
- Output validation
- Safety controls
- Failure behavior
- Decisions enforced outside the model

Authentication, authorization, record ownership, confirmation and protected business actions must be enforced through deterministic application logic. Fixed responses or hardcoded scenario branches alone do not qualify.

### 2. Agent architecture and orchestration

Allowed approaches include a primary orchestrator with specialized agents, a controlled tool-using agent, multiple cooperating agents, a deterministic workflow with AI-assisted steps or a hybrid architecture.

The implementation must demonstrate:

- Clear agent/component responsibilities
- Controlled tool access
- Conversation and workflow state management
- Routing and delegation logic
- Validation before tool execution
- Loop prevention
- Completion and termination conditions
- Timeout and error handling
- Human review and escalation points

If multiple agents are used, explain why each agent is needed, what information it can access, which tools it may execute, how context is transferred, how conflicting results are handled, how unnecessary calls are avoided and how completion is determined. More agents do not automatically earn a higher score; the architecture must be appropriate, controlled, reliable and maintainable.

### 3. Customer authentication and authorization

Authenticate customers before accessing protected information or executing protected actions. The implementation must:

- Use the supplied authentication service or an approved equivalent
- Maintain authentication state appropriately
- Handle invalid and expired authentication
- Prevent one customer from accessing another customer's records
- Enforce record ownership or role permissions
- Restrict tools according to authenticated user and workflow state
- Validate model-generated tool parameters
- Record authentication and authorization events
- Protect credentials and tokens from the AI model
- Avoid sensitive authentication information in logs and traces

The AI model must never be the sole authority granting access. Simulated authentication is acceptable because the data is synthetic, but the flow and enforcement must be technically meaningful.

### 4. Enterprise and legacy-system integration

Integrate with the supplied enterprise services and legacy telecom service. The integration layer must handle:

- Request validation
- Response validation
- Data normalization
- Enterprise authentication
- Error-code mapping
- Timeouts
- Safe and limited retries
- Missing or partial data
- Malformed responses
- Rate limits
- Duplicate requests
- Failed enterprise operations

Access enterprise systems through controlled tools, services or adapters. Gemini must not have unrestricted access to raw enterprise endpoints.

#### Legacy telecom adapter

The supplied legacy service may include XML requests/responses, inconsistent field names, legacy status codes, unusual error codes, missing optional fields, slow responses, intermittent failures and older authentication behavior.

The adapter must:

- Communicate with the legacy interface
- Validate the returned response
- Convert the response into a consistent internal model
- Map legacy errors into application-level errors
- Prevent raw legacy-system behavior from leaking into the AI/customer layers
- Produce useful diagnostic events without exposing protected data

The legacy service must not be bypassed or replaced with hardcoded results.

### 5. Grounded and trustworthy responses

Customer-facing responses must be grounded in customer input and verified enterprise information. Distinguish between customer-provided information, retrieved enterprise information, AI-generated interpretation, assumptions, recommendations, confirmed actions and unverified information.

The system must not:

- Invent customer or account records
- Generate unsupported charges, plans, outages, cases or reference numbers
- Present assumptions as verified facts
- Claim that a tool was called when it was not
- Report a failed action as successful
- Replace unavailable data with fabricated values
- Hide materially conflicting enterprise information

When information is unavailable or unclear, ask for clarification, provide a qualified response, use an approved fallback or escalate.

### 6. Clarification and context management

The solution must identify incomplete or ambiguous requests. It must determine what information is missing, ask a relevant and specific question, preserve previously supplied information, resume the workflow after clarification, avoid asking for information already provided, avoid unsupported assumptions and avoid calling protected or consequential tools prematurely. Generic requests for “more information” receive limited credit when the missing information can be identified precisely.

### 7. Controlled enterprise action

Support at least one consequential enterprise action. Examples include creating a support case, scheduling technical assistance, submitting a service-change request, updating an account preference or requesting a supported plan change.

Before completing the action, the solution must:

1. Authenticate the customer.
2. Verify authorization.
3. Validate the requested action and parameters.
4. Present an understandable action summary.
5. Obtain explicit customer confirmation.
6. Execute the controlled enterprise tool.
7. Validate the backend response.
8. Report success only after confirmed execution.
9. Return a valid reference identifier where applicable.
10. Record the action and result.
11. Prevent accidental duplicate execution.

A proposed or recommended action must not be shown as completed.

### 8. Failure handling and human escalation

Safely handle Gemini provider failure, enterprise API failure, network timeout, rate limit, invalid/expired authentication, unauthorized requests, missing/conflicting enterprise data, malformed responses, failed enterprise actions, duplicate action requests and internal processing failures.

The implementation must detect and classify failures, preserve relevant workflow state, avoid fabricating outcomes, retry only when safe and appropriate, limit retry attempts, prevent duplicate consequential actions, provide a clear customer-facing explanation, use documented fallbacks where available, escalate when safe completion is impossible and record failures in logs, traces and metrics.

An escalation record must include:

- Customer request summary
- Available verified context
- Completed workflow steps
- Enterprise systems accessed
- Relevant evidence
- Failed tools or integrations
- Error summary
- Pending action
- Recommended next step
- Request or trace identifier

A receiving representative should be able to continue without making the customer repeat the entire interaction.

### 9. Data pipeline, telemetry and observability

Produce structured events for important workflow activity, as applicable:

- Session started
- Request received
- Intent classified
- Clarification requested
- Authentication attempted
- Authentication succeeded or failed
- Authorization allowed or denied
- Agent invoked
- Tool invoked
- Tool completed or failed
- Retry performed
- Confirmation requested
- Confirmation received
- Enterprise action completed
- Escalation created
- Workflow resolved
- Workflow failed

Each event must contain a correlation or trace identifier.

#### Telemetry pipeline

The telemetry pipeline must accept structured application events, validate event formats, associate events with a request/session, support request-level investigation and operational metrics, handle invalid events safely and avoid unnecessary sensitive-data storage.

#### Workflow trace

Reviewers must be able to inspect the trace identifier, workflow steps, agents/components invoked, enterprise tools called, sanitized input/output summaries, execution duration, success/failure status, retry/fallback events, authorization decisions, confirmation events, final outcome and escalation reason.

Passwords, tokens, secrets, unnecessary personal data and protected model instructions must not appear in traces.

#### Operational view

Show metrics generated from actual application events, such as total sessions, resolution rate, escalation rate, failure rate, average workflow duration, tool-call success rate, failures by integration, authentication failures, authorization denials, agent/tool usage, retry frequency, Gemini latency/failures and human handoff rate. Static or manually entered monitoring data does not satisfy this requirement.

---

## Mandatory evaluation scenarios

Every submission is reviewed using the same scenarios, test users, data and failure conditions.

### 1. Grounded customer inquiry
A customer asks for protected account, subscription, billing or service information. Authenticate the customer, retrieve the correct authorized record, normalize the enterprise response and return a grounded answer.

### 2. Ambiguous request
A customer gives insufficient information. Identify the missing information, ask a specific clarification question, preserve context and continue after clarification.

### 3. Multi-system issue resolution
A reported issue requires multiple enterprise systems. Coordinate the required agents/tools, preserve context, reconcile returned information and resolve or safely escalate.

### 4. Protected enterprise action
An authenticated customer requests a supported action. Validate, authorize, summarize, confirm, execute, verify and record the action, while preventing duplicate execution.

### 5. Unauthorized access attempt
An authenticated customer attempts to access another customer's record. Deny access through deterministic authorization, avoid retrieving or exposing the protected record and record the denial.

### 6. Legacy-system request
A request needs the supplied legacy telecom service. Call the service, process its legacy format, normalize the response, map errors and use the result in the customer workflow.

### 7. Enterprise-service failure
A required service fails, times out or returns incomplete information. Avoid false success, apply safe retry behavior, preserve state and escalate where necessary.

### 8. Gemini provider failure
Gemini becomes unavailable. Detect failure, preserve the active request, maintain deterministic security controls, enter a documented fallback/degraded mode and record the failure.

---

## Google technology expectations

The primary AI workflow must demonstrate practical use of Gemini or another Google AI capability identified in the challenge package.

Document the Google services used, Gemini integration, agent/orchestration approach, identity/authentication design, enterprise-integration approach, logging/telemetry approach, Google Cloud deployment architecture, security considerations and production-deployment changes required.

If direct access to a particular Gemini Customer Experience product is unavailable, explain how the implemented solution maps to the intended Google customer-experience environment. Merely mentioning Google products without working implementation or credible technical mapping receives limited credit.

## Live AI and reviewer modes

### Live AI mode

Provide a functional Gemini integration, including model integration code, configuration instructions, prompt/agent instructions, structured output validation, failure handling, execution evidence and a recorded demonstration. Do not include active credentials.

### Reviewer mode

Provide a deterministic, cached, recorded or mock reviewer mode for all mandatory scenarios. Reviewer mode must still exercise the real user workflow, authentication/authorization, application services, integration adapters, validation, controlled-action logic, failure handling, telemetry pipeline and trace generation. It must not be disconnected static screens or predefined final responses.

Clearly identify whether the solution is in Live AI mode, Reviewer mode or Degraded Fallback mode. Reviewer mode does not replace mandatory live AI implementation.

## Solution depth: insufficient versus valid

The following are not sufficient:

- Static chatbot demonstration
- Hardcoded responses
- Single model call without enterprise integration
- Architecture documents without working implementation
- UI that does not exercise supplied APIs
- Static telemetry or manually entered metrics
- Mock-only implementation without live Gemini integration
- Replacement application that bypasses the starter solution
- Recorded demonstration reviewers cannot reproduce

A valid submission must demonstrate meaningful Gemini usage, controlled agent/workflow orchestration, authentication and deterministic authorization, modern and legacy enterprise integration, grounded responses, protected enterprise-action handling, failure recovery and escalation, structured events and request-level traces, event-derived operational metrics, repeatable tests, deployment preparation and customer-team handover.

## Technology expectations

The stack may be extended or adjusted where justified. The final solution must be:

- Runnable locally
- Reviewable without private participant assistance
- Maintainable and documented
- Secure with synthetic customer data
- Transparent about AI-generated versus enterprise-sourced information
- Configurable through environment variables
- Free from hardcoded active credentials
- Capable of running mandatory scenarios without paid reviewer access
- Prepared for Google Cloud deployment

A browser interface is recommended, but visual design is not the primary focus. A functional conversation runner with appropriate engineering and operational views may also be acceptable.

---

## Deliverables

### 1. Productionized starter solution

Must include Gemini integration, agent/workflow orchestration, authentication/authorization, enterprise API integrations, legacy telecom adapter, grounded response handling, controlled enterprise action, failure/escalation handling, telemetry pipeline, workflow trace, operational monitoring and Live AI/Reviewer modes.

### 2. Source code

Clean, modular, documented and easy to run.

### 3. Automated tests or evaluation runner

Tests must cover:

- Successful inquiry
- Clarification
- Authentication success and failure
- Authorization enforcement
- Cross-customer access denial
- Controlled-action confirmation
- Successful and failed enterprise actions
- Duplicate-action protection
- Legacy-response normalization
- Enterprise timeout or malformed response
- Gemini provider failure
- Escalation creation
- Telemetry-event generation

### 4. README

Explain local setup, environment configuration, Live AI mode, Reviewer mode, mandatory scenario execution, test execution, Gemini integration, agent orchestration, enterprise integrations, security controls, telemetry/traces and known limitations.

### 5. Architecture diagram

Show the customer interaction layer, Gemini integration, agents/orchestrator, authentication/authorization, enterprise tool layer, legacy adapter, data stores, telemetry pipeline, trace/monitoring views and deployment boundaries.

### 6. Deployment documentation

Cover local/containerized execution, health checks, environment configuration, timeout/retry settings, persistence approach, Google Cloud deployment mapping, scaling/performance, security, cost and recovery/rollback.

### 7. Customer-team handover package

Explain the business problem, architecture, agent/component responsibilities, key design decisions, security approach, how to add a tool/integration, how to modify orchestration, how to inspect traces, how to diagnose failures, known limitations and recommended production roadmap.

### 8. Demo video

Recommended duration: 3–5 minutes. Show a grounded inquiry, clarification handling, protected enterprise action, authorization enforcement, legacy-system processing, simulated service failure and escalation, workflow traces and metrics, Live AI or evidence of live Gemini integration, Reviewer mode and key design decisions.

### 9. Requirement-to-evidence matrix

The repository must map each challenge requirement to implementation and review evidence. Suggested columns:

| Requirement | Implemented Capability | Code or Component Location | Supporting Test | Reviewer Scenario | Execution Evidence | Coverage Status | Known Limitation |
|---|---|---|---|---|---|---|---|
| Requirement text | Capability details | File/component path | Test name | Scenario ID | Log/trace/demo reference | Complete/Partial/Not started | Limitation or none |

### 10. Summary of changes

Identify starter components retained, components completed, components refactored, security issues fixed, integrations implemented, reliability improvements, observability improvements and remaining limitations.

---

## Evaluation criteria (100%)

| Category | Weight | Main areas reviewed |
|---|---:|---|
| Gemini and Conversational AI | 15% | Meaningful Gemini use, request understanding, context, clarification, grounded responses, structured output validation and provider failure handling |
| Agent Architecture and Orchestration | 15% | Appropriate design, responsibilities, routing/delegation, tool permissions, state management, loop prevention, termination and human escalation |
| Enterprise and Legacy Integration | 15% | APIs, contract validation, data normalization, legacy adapter, error mapping, timeout/retry handling, boundaries and maintainability |
| Secure APIs, Authentication and Authorization | 15% | Authentication, authorization, customer isolation, tool-level controls, parameter validation, confirmation, duplicate protection, secrets and auditability |
| Mandatory Customer Scenarios | 10% | End-to-end completion, business correctness, state preservation, verified outcomes and appropriate escalation |
| Data Pipelines, Telemetry and Observability | 10% | Structured events, correlation identifiers, request traces, event-derived metrics, diagnostic usefulness and sensitive-data protection |
| Reliability and Troubleshooting | 10% | Enterprise/Gemini failures, timeout/retry behavior, state preservation, duplicate protection, fallback and escalation quality |
| Testing and Software Quality | 5% | Functional, security, integration and failure tests; organization, validation and maintainability |
| Deployment and Customer-Team Enablement | 5% | Reproducible setup, Google Cloud mapping, documentation, handover and production recommendations |
| **Total** | **100%** | |

## Success definition

A successful submission allows an evaluator to:

- Run the productionized starter solution.
- Execute all mandatory scenarios.
- Verify meaningful Gemini usage.
- Inspect controlled agent/workflow orchestration.
- Confirm authentication and customer isolation.
- Verify protected enterprise-action controls.
- Exercise the legacy telecom integration.
- Confirm responses are grounded in enterprise data.
- Simulate Gemini and enterprise-service failures.
- Review escalation records.
- Inspect request-level traces.
- Review event-derived operational metrics.
- Run the automated tests.
- Review the Google Cloud deployment approach.
- Understand how the solution can be maintained and extended.

## Challenge resources and metadata

The challenge page says resources are provided in the challenge forums by the Copilot. It lists Final Review, Community Review Board, Approval and User Sign-Off; Standard Terms 2026 and Useable Code Rules; and tools/resources including the Topcoder Extension for VS Code and Topcoder Templates repository.

## Implementation notes for this repository

- This file is a working reference derived from the supplied challenge PDF; check the live Topcoder page for current schedule, legal terms and any updated forum instructions.
- The challenge requires a persistence approach to be documented, but this specification does not explicitly require creating a new Neon database. Inspect the starter project before deciding whether a database or schema changes are needed.
- Keep the original challenge starter code and this reference together in source control so the implementation can be traced back to requirements.
- Update the checklist above as work is completed, and link actual paths, test names and evidence in the requirement-to-evidence matrix.
