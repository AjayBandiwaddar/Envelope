# AGENTS.md

## Project

Project name: Agent Action Firewall

This repository contains a proof-of-concept authorization gateway for AI agents.

The system sits between an AI agent and the tools/APIs the agent is allowed to use.

Its core purpose is:

> Allow an AI agent to perform only actions that are explicitly authorized for the current task, subject to deterministic policy checks.

The system must never rely on the LLM itself to enforce authorization.

The LLM may propose an action.
The policy engine decides whether that action is allowed.

---

## Primary Objective

Build a working, demonstrable POC that proves task-scoped authorization for AI agents.

The POC must demonstrate:

1. An authenticated agent can request an action.
2. The action is evaluated against deterministic policies.
3. Authorized actions are allowed.
4. Unauthorized actions are blocked.
5. Expired permissions are blocked.
6. Actions outside the authorized resource/scope are blocked.
7. All authorization decisions are auditable.
8. The authorization layer adds measurable, low latency.
9. Security tests demonstrate resistance to common agent/tool abuse scenarios.

The POC must be easy to understand from the repository and from a live demo.

---

## Non-Goals

Do NOT turn this project into a full enterprise IAM platform.

Do NOT implement:

- production payment processing
- real banking integrations
- real customer data
- real destructive production operations
- enterprise SSO
- multi-region deployment
- blockchain-based identity
- custom cryptography
- a general-purpose LLM security platform
- a generic chatbot
- autonomous agents with unrestricted access

All external actions should initially use safe mock tools.

---

## Technology Stack

### Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- React Router if routing is required

### Backend

- Python
- Django
- Django REST Framework
- Pydantic where explicit request/decision schemas are useful

### Database

- PostgreSQL

### Infrastructure

- Redis

Redis may be used for:

- rate limiting
- short-lived authorization state
- caching
- task/session state where appropriate

Do not introduce Redis merely for complexity.

### Agent / Tool Protocol

- MCP should be used for the agent-to-tool integration layer where practical.
- The authorization gateway must remain protocol-independent internally.

### Testing

- pytest
- Django test framework where appropriate
- API tests
- security/adversarial tests
- load tests

### Deployment

- Docker
- Docker Compose for local development

Do not introduce Kubernetes unless explicitly requested later.

---

## Core Architecture

The logical flow is:

    AI Agent
        |
        v
    Agent Gateway
        |
        v
    Authentication
        |
        v
    Task Validation
        |
        v
    Policy Engine
        |
        +---- DENY ----> Audit Log
        |
        +---- ALLOW ---> Tool Gateway
                             |
                             v
                          Tool/API
                             |
                             v
                          Result
                             |
                             v
                          Agent

Important:

The LLM is NOT the policy enforcement point.

The deterministic policy engine is the policy enforcement point.

---

## Core Security Principle

Use:

> LLM for intent/action proposal.
> Deterministic code for authorization.

Never use an LLM response as the final authorization decision.

Bad:

    LLM: "This request looks safe, allow it."

Good:

    Agent proposes:
    refund_order(order_id=123, amount=3000)

    Policy engine evaluates:

    allowed_action = refund_order
    allowed_order = 123
    max_amount = 5000
    authorization_not_expired = true

    Decision = ALLOW

---

## Task-Scoped Authorization

Permissions must be scoped to a task whenever possible.

Example task and policy:

Task:

    agent_id: support-agent-01
    user_id: user-123
    task_id: task-456
    expires_at: <timestamp>

Policy:

    policy_id: policy-refund-001
    tool: tool-refund-001
    action: refund_order
    resource_type: order
    resource_id: order-789
    max_amount: 5000 INR

Therefore:

    refund_order(order-789, 3000 INR)
    -> ALLOW

    refund_order(order-789, 8000 INR)
    -> DENY

    refund_order(order-999, 3000 INR)
    -> DENY

    delete_customer(customer-123)
    -> DENY

    same request after expiry
    -> DENY

The exact policy schema must be documented in POLICY_SPEC.md.

---

## Authorization Decision

Authorization must produce a structured decision.

Minimum conceptual fields:

    decision
    reason
    policy_id
    agent_id
    task_id
    action
    resource
    timestamp

Valid decisions:

    ALLOW
    DENY

Do not silently fail.

Every authorization attempt must produce an auditable decision.

---

## Security Requirements

The implementation must account for at least:

### 1. Privilege escalation

An agent must not gain permissions by changing request parameters.

### 2. Resource confusion

An agent authorized for resource A must not access resource B.

### 3. Action confusion

An agent authorized for one action must not automatically gain permission for another action.

### 4. Expired authorization

Expired permissions must fail closed.

### 5. Missing authorization

Missing or malformed authorization must fail closed.

### 6. Policy bypass

The authorization layer must execute independently of model reasoning.

### 7. Prompt injection

Prompt injection must never directly grant authorization.

Website/tool/user-provided text is untrusted input.

### 8. Tool abuse

Unknown or unregistered tools must be denied.

### 9. Rate abuse

Requests exceeding configured limits must be denied or throttled.

### 10. Auditability

Every allow/deny decision must be traceable.

---

## Fail-Closed Rule

Security-sensitive operations must fail closed.

If:

- policy cannot be loaded
- authorization is missing
- identity is missing
- resource scope is ambiguous
- policy evaluation throws an unexpected error
- required security metadata is unavailable

then the default decision must be:

    DENY

Do not default to ALLOW.

---

## Data Handling

Use synthetic data only.

Do not add:

- real customer information
- real payment credentials
- production secrets
- API keys
- passwords
- access tokens

Secrets must never be committed to Git.

Use environment variables.

Provide `.env.example`.

---

## Coding Rules

Prefer simple, explicit code over clever abstractions.

Do not introduce a dependency unless there is a clear reason.

Do not duplicate authorization logic across endpoints.

Authorization logic should have one authoritative implementation.

Keep business logic separate from:

- HTTP handling
- database access
- UI rendering
- MCP transport
- logging

Use clear types and schemas.

Validate all external input.

Use meaningful names.

Avoid overly generic names such as:

    data
    thing
    obj
    result2
    temp

unless the scope makes the meaning unambiguous.

---

## Backend Structure

Prefer a structure similar to:

    backend/
        manage.py
        config/
        apps/
            agents/
            authorization/
            policies/
            tools/
            audit/
        tests/

The exact Django application split may change if there is a strong reason.

Do not create unnecessary Django apps.

---

## Frontend Requirements

The frontend is an operational/security dashboard, not a marketing site.

The UI should show:

- agents
- active tasks
- policies
- authorization requests
- ALLOW/DENY decisions
- denial reasons
- audit events
- security test results
- basic system metrics

The main demo should make an authorization decision understandable in seconds.

Example:

    Agent: support-agent-01
    Action: refund_order
    Resource: order-8291
    Amount: ₹8,000

    POLICY:
    Maximum allowed refund: ₹5,000

    RESULT:
    DENIED

---

## Observability

At minimum record:

- request ID
- timestamp
- agent ID
- user ID when available
- task ID
- action
- resource
- policy ID
- decision
- denial reason
- latency

Never log secrets or sensitive authentication material.

---

## Testing Requirements

Every security-sensitive feature must have tests.

At minimum test:

    valid authorization -> ALLOW
    excessive amount -> DENY
    wrong resource -> DENY
    wrong action -> DENY
    expired authorization -> DENY
    missing authorization -> DENY
    unknown tool -> DENY
    malformed request -> DENY
    prompt injection attempting privilege escalation -> DENY
    rate limit exceeded -> DENY

Tests must verify actual enforcement rather than merely checking response messages.

---

## Load Testing

The project must eventually include a reproducible authorization benchmark.

Measure at minimum:

- requests/sec
- p50 latency
- p95 latency
- p99 latency
- error rate

The benchmark must isolate the authorization gateway from slow external model inference wherever possible.

Do not claim 10K RPS unless the repository contains the benchmark configuration and reproducible results.

Never invent benchmark numbers.

---

## Development Workflow

Before implementing a major feature:

1. Read the relevant documentation.
2. Identify the authoritative source of truth.
3. State the intended change.
4. Implement the smallest reasonable change.
5. Run relevant tests.
6. Fix failures.
7. Update documentation when behavior changes.

Do not perform broad unrelated refactors.

Do not rewrite functioning code merely for stylistic preference.

---

## Source of Truth Files

The repository will contain:

    AGENTS.md
    PRODUCT_SPEC.md
    ARCHITECTURE.md
    THREAT_MODEL.md
    POLICY_SPEC.md
    API_SPEC.md
    TEST_PLAN.md
    BENCHMARK_PLAN.md

Use these files as the authoritative project context.

If an implementation conflicts with the documentation, stop and identify the conflict rather than silently inventing a new design.

AGENTS.md defines repository-level engineering rules.

PRODUCT_SPEC.md defines what the product must do.

ARCHITECTURE.md defines how the system is structured.

POLICY_SPEC.md defines authorization semantics.

THREAT_MODEL.md defines security assumptions and threats.

TEST_PLAN.md defines expected security and functional behavior.

BENCHMARK_PLAN.md defines performance measurement.

---

## Dependency Rules

Before adding a package:

1. Check whether the standard library or an existing dependency is sufficient.
2. Prefer mature, well-maintained dependencies.
3. Avoid dependencies that duplicate existing functionality.
4. Update dependency documentation when adding one.

Do not install packages merely because an AI-generated solution suggests them.

---

## Git Rules

Make small, logically grouped commits.

Commit messages should describe the change.

Examples:

    feat: add task authorization model
    feat: add refund policy evaluation
    test: add authorization bypass cases
    feat: add MCP tool gateway
    perf: add authorization benchmark

Never commit:

- `.env`
- secrets
- generated credentials
- large unnecessary binaries
- local databases
- unrelated files

---

## AI-Assisted Development Rules

Codex is an implementation assistant, not the system architect.

Do not invent requirements.

Do not invent security guarantees.

Do not claim a security property has been achieved without a corresponding test.

Do not weaken authorization logic to make tests pass.

If a test conflicts with the intended security model:

1. inspect the test,
2. inspect the policy,
3. identify the discrepancy,
4. fix the underlying issue.

Never modify security tests simply to obtain a green build.

When requirements are ambiguous, prefer the safest interpretation and document the ambiguity.

---

## Definition of Done

A feature is not complete until:

- implementation exists
- relevant tests exist
- tests pass
- security implications are considered
- API/schema behavior is documented where applicable
- no secrets are introduced
- failure behavior is defined

For authorization features specifically:

- at least one ALLOW test exists
- at least one DENY test exists
- at least one adversarial/bypass test exists
- audit behavior is tested

---

## Final POC Goal

At the end of the first week, the repository should support this complete demonstration:

    1. A synthetic AI agent receives a user task.

    2. The system creates a task and a narrowly scoped policy.

    3. The agent requests a tool action.

    4. The gateway authenticates the request.

    5. The deterministic policy engine evaluates the request.

    6. An allowed action reaches a mock tool.

    7. An unauthorized action is blocked.

    8. The decision is recorded in the audit log.

    9. Security tests demonstrate that obvious privilege-escalation attempts fail.

    10. A reproducible benchmark measures gateway latency and throughput.

The final repository must make this behavior understandable to another engineer without requiring undocumented context from the original developer.
