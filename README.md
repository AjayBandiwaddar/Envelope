````markdown
# README.md

# Agent Action Firewall

> A task-scoped authorization gateway that allows AI agents to execute tools only within explicitly defined permissions.

## Overview

AI agents can now call APIs, tools, databases, and external services on behalf of users.

The security problem is not only:

> "Is this agent allowed to use this tool?"

It is:

> "Is this agent allowed to perform this exact action, on this exact resource, with these exact parameters, for this exact task, at this exact time?"

Agent Action Firewall is a proof-of-concept implementation of that control layer.

The system sits between an AI agent and its tools:

```text
AI Agent
    │
    │ proposes action
    ▼
┌──────────────────────────┐
│   Agent Action Firewall  │
│                          │
│ Authentication           │
│ Task authorization       │
│ Policy evaluation        │
│ Resource constraints     │
│ Parameter constraints    │
│ Rate limiting            │
│ Audit logging            │
└────────────┬─────────────┘
             │
        ALLOW│DENY
             │
             ▼
        Tool / API
````

The central security principle is:

> The LLM may propose an action. The deterministic policy engine decides whether it is allowed.

---

# Why This Exists

Traditional application authorization often gives software broad permissions.

For example:

```text
support-agent → can call refund_order()
```

For autonomous agents, that is too coarse.

A user may authorize:

```text
Refund order #8291
up to ₹5,000
within the next 30 minutes
```

The agent should therefore be able to:

```text
refund_order(8291, ₹3,000)
```

but not:

```text
refund_order(8291, ₹50,000)
refund_order(9999, ₹3,000)
delete_customer(123)
```

The firewall turns those constraints into deterministic authorization checks.

---

# Core Concept

Authorization is evaluated against:

```text
Agent
+
User
+
Task
+
Action
+
Tool
+
Resource
+
Parameters
+
Time
+
Policy
```

Conceptually:

```text
                    REQUEST
                       │
                       ▼
                 Authenticate
                       │
                       ▼
                Validate input
                       │
                       ▼
             Validate task authority
                       │
                       ▼
               Evaluate policy
                       │
                ┌──────┴──────┐
                │             │
              ALLOW         DENY
                │             │
                ▼             ▼
          Execute tool      Audit
                │
                ▼
              Audit
```

---

# Key Features

## Task-Scoped Authorization

Permissions are tied to a specific task rather than permanently granting broad agent privileges.

Example:

```text
Agent:
support-agent-01

Task:
task-001

Allowed action:
refund_order

Allowed resource:
order-8291

Maximum:
₹5,000

Expiration:
30 minutes
```

---

## Deterministic Policy Engine

The authorization decision is made by application logic.

The LLM does not decide:

```text
"this looks safe"
```

The system evaluates explicit rules.

---

## Least Privilege

Only the minimum required authority is granted.

```text
refund_order(order-8291, ₹3,000)
→ ALLOW

refund_order(order-8291, ₹8,000)
→ DENY

delete_customer(customer-123)
→ DENY
```

---

## Tool Gateway

Tools cannot be executed directly by the agent.

They must pass through the authorization boundary.

```text
Agent
  ↓
Tool request
  ↓
Authorization
  ↓
ALLOW
  ↓
Tool Gateway
  ↓
Tool
```

---

## Security Against Agent Abuse

The POC tests:

* privilege escalation
* resource substitution
* action substitution
* parameter manipulation
* expired authorization
* revoked authorization
* prompt injection
* tool poisoning
* unauthorized tools
* policy tampering
* confused-deputy scenarios
* authentication bypass
* fail-open behavior

---

## Auditability

Every authorization request produces an audit event containing relevant decision context.

Example:

```text
Agent:
support-agent-01

Task:
task-001

Action:
refund_order

Resource:
order-8291

Requested amount:
₹8,000

Decision:
DENY

Reason:
PARAMETER_LIMIT_EXCEEDED

Policy:
policy-refund-001
```

---

# Example

## Task

User asks:

```text
Refund order #8291 for up to ₹5,000.
```

The system creates task-scoped authority:

```json
{
  "task_id": "task-001",
  "agent_id": "support-agent-01",
  "action": "refund_order",
  "resource": {
    "type": "order",
    "id": "8291"
  },
  "constraints": {
    "max_amount": 5000,
    "currency": "INR"
  }
}
```

## Valid request

```json
{
  "action": "refund_order",
  "resource": {
    "type": "order",
    "id": "8291"
  },
  "parameters": {
    "amount": 3000,
    "currency": "INR"
  }
}
```

Result:

```text
ALLOW
```

The mock tool executes.

---

## Unauthorized request

```json
{
  "action": "refund_order",
  "resource": {
    "type": "order",
    "id": "8291"
  },
  "parameters": {
    "amount": 8000,
    "currency": "INR"
  }
}
```

Result:

```text
DENY
```

The tool does not execute.

---

# Security Principle

The project deliberately separates:

```text
AI reasoning
```

from:

```text
authorization enforcement
```

An agent can be manipulated by:

* prompt injection
* malicious tool output
* untrusted documents
* malicious webpages
* misleading user content

The firewall does not assume the agent is trustworthy.

Even if the agent proposes:

```text
refund_order(8291, 100000)
```

the deterministic policy engine independently evaluates the request.

---

# Architecture

```text
                         React Dashboard
                                │
                                ▼
                         Django REST API
                                │
                 ┌──────────────┼──────────────┐
                 │              │              │
                 ▼              ▼              ▼
             Agents          Tasks          Policies
                 │              │              │
                 └──────────────┼──────────────┘
                                ▼
                       Authorization Service
                                │
                                ▼
                         Deterministic
                         Policy Engine
                                │
                         ┌──────┴──────┐
                         │             │
                       ALLOW         DENY
                         │             │
                         ▼             ▼
                    Tool Gateway     Audit
                         │
                         ▼
                    Mock Tools
```

Infrastructure:

```text
React
   ↓
Django
   ├── PostgreSQL
   └── Redis
```

MCP integration is used where practical for realistic agent-to-tool communication.

---

# Technology Stack

## Frontend

* React
* TypeScript
* Vite
* Tailwind CSS

## Backend

* Python
* Django
* Django REST Framework
* Pydantic where useful

## Database

* PostgreSQL

## Infrastructure

* Redis
* Docker
* Docker Compose

## Agent Tooling

* MCP-compatible integration
* Mock tool services

## Testing

* pytest
* Django tests
* API tests
* security tests
* adversarial tests
* load tests

---

# Repository Structure

```text
agent-action-firewall/
│
├── AGENTS.md
├── README.md
├── PRODUCT_SPEC.md
├── ARCHITECTURE.md
├── THREAT_MODEL.md
├── POLICY_SPEC.md
├── API_SPEC.md
├── TEST_PLAN.md
├── BENCHMARK_PLAN.md
│
├── backend/
├── frontend/
├── tests/
│
├── benchmarks/
│
├── docker-compose.yml
└── .env.example
```

The specification files define the source of truth for the project.

---

# Local Setup

## Requirements

Install:

```text
Python 3.12+
Node.js 20+
Docker
Docker Compose
Git
```

---

## Clone

```bash
git clone <repository-url>
cd agent-action-firewall
```

---

## Environment

Create:

```bash
cp .env.example .env
```

Never commit `.env`.

---

## Start Infrastructure

```bash
docker compose up -d postgres redis
```

---

## Backend

Create the Python virtual environment:

```bash
python -m venv .venv
```

Activate it.

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r backend/requirements.txt
```

Run migrations:

```bash
python backend/manage.py migrate
```

Start Django:

```bash
python backend/manage.py runserver
```

---

## Frontend

```bash
cd frontend
npm install
npm run dev
```

The React development server should be available at:

```text
http://localhost:5173
```

The Django API should be available at:

```text
http://localhost:8000
```

---

# Running Tests

From the repository root:

```bash
pytest
```

Run security tests:

```bash
pytest tests/security/
```

Run API/integration tests:

```bash
pytest tests/api/ tests/integration/
```

The final CI pipeline should run the complete functional and security test suite.

---

# Running the Demo

The primary demo should follow this sequence:

```text
1. Register support-agent-01.

2. Create task:
   "Refund order #8291 up to ₹5,000."

3. Create the corresponding task-scoped policy.

4. Execute:
   refund_order(8291, ₹3,000)

   → ALLOW

5. Execute:
   refund_order(8291, ₹8,000)

   → DENY

6. Execute:
   refund_order(9999, ₹3,000)

   → DENY

7. Execute:
   delete_customer(123)

   → DENY

8. Open audit dashboard.

9. Show all authorization decisions.

10. Run security test suite.
```

The entire demonstration should be understandable within a few minutes.

---

# Performance Benchmark

The primary benchmark is the deterministic authorization gateway.

We measure:

```text
RPS
p50 latency
p95 latency
p99 latency
error rate
CPU
memory
database utilization
Redis utilization
```

Target experiments:

```text
100 RPS
1,000 RPS
5,000 RPS
10,000 RPS
```

The 10K RPS number is an experimental target.

The repository must contain the reproducible benchmark configuration before any performance claim is made.

Never claim:

```text
10K RPS
```

unless actual testing demonstrates it.

---

# Security Benchmark

The POC should measure:

```text
unauthorized actions attempted
unauthorized actions blocked
unauthorized actions executed
```

Target for the defined attack suite:

```text
unauthorized actions executed = 0
```

Also measure:

```text
audit coverage
false denial rate
authorization latency
```

---

# What This Project Is NOT

This repository is not:

* a production IAM platform
* a complete AI security product
* a generic LLM firewall
* a chatbot
* a replacement for enterprise identity systems
* a guarantee against all prompt injection
* a guarantee against compromised infrastructure

It is a focused POC demonstrating:

> Task-scoped authorization for AI-agent tool execution.

---

# Security Limitations

The POC cannot guarantee protection against:

* compromised administrators
* compromised servers
* vulnerabilities inside tools
* incorrectly defined policies
* perfect user-intent interpretation
* every possible prompt-injection technique
* every distributed-system race condition

These limitations are documented in `THREAT_MODEL.md`.

---

# Design Principles

## 1. LLMs propose, deterministic systems authorize.

## 2. Default decision is DENY.

## 3. Tool execution requires explicit authorization.

## 4. Permissions should be as narrow and short-lived as practical.

## 5. Every authorization attempt should be auditable.

## 6. Security failures must fail closed.

## 7. Frontend checks are never security controls.

## 8. Performance claims require reproducible benchmarks.

## 9. Security claims require reproducible tests.

## 10. Simplicity is preferred over unnecessary infrastructure.

---

# Project Status

Current status:

```text
Specification / POC development
```

The initial milestone is:

```text
Functional task-scoped authorization
+
MCP/tool integration
+
Security test suite
+
Audit dashboard
+
Performance benchmark
```

---

# Week 1 Definition of Done

At the end of the first development week, the project should be able to demonstrate:

```text
[ ] Register an AI agent
[ ] Create a task
[ ] Define task-scoped authorization
[ ] Register tools
[ ] Evaluate authorization deterministically
[ ] Execute authorized tools
[ ] Block unauthorized tools
[ ] Enforce resource restrictions
[ ] Enforce parameter limits
[ ] Enforce expiration
[ ] Enforce revocation
[ ] Record audit events
[ ] Test prompt-injection-driven escalation
[ ] Test privilege escalation
[ ] Test policy tampering
[ ] Test fail-closed behavior
[ ] Run end-to-end demonstration
[ ] Run performance benchmark
```

The boxes above represent requirements, not completed implementation status. They
should only be checked after the corresponding functionality and tests actually
pass.

---

# Future Direction

Potential future capabilities:

```text
Agent identity
Delegated authority
Capability tokens
Human approval workflows
Risk-based authorization
Multi-agent delegation
Agent reputation
External policy engines
Distributed authorization
Cryptographically verifiable execution
Additional agent protocols
```

These are intentionally outside the initial POC.

---

# Portfolio Positioning

Use a precise description:

> Built a task-scoped authorization gateway for AI agents that enforces least-privilege tool access, deterministic policy constraints, auditability, and security controls across MCP/API tool execution.

The project should be evaluated primarily through:

```text
Architecture
Security model
Authorization correctness
Adversarial testing
MCP integration
Performance measurements
```

Not by the number of UI screens or AI features.

---

# Core Thesis

AI agents are moving from generating information to taking actions.

Once agents can:

```text
send
modify
purchase
refund
delete
deploy
approve
```

authorization becomes a fundamentally important control layer.

Agent Action Firewall explores one narrow question:

> How do we give an AI agent enough authority to complete a task without giving it more authority than the task requires?

The answer implemented by this project is:

```text
Task-scoped authority
+
Deterministic policy enforcement
+
Least privilege
+
Tool isolation
+
Auditability
+
Adversarial testing
```

```
```
