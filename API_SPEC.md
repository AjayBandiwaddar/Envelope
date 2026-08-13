````markdown
# API_SPEC.md

# Agent Action Firewall — API Specification

## 1. Purpose

This document defines the HTTP API contract for the Agent Action Firewall POC.

The API is divided into:

1. Administrative APIs
2. Agent/task APIs
3. Authorization APIs
4. Tool APIs
5. Audit APIs
6. Health/metrics APIs

The frontend, tests, and future agent integrations must use these contracts instead of depending on internal Django implementation details.

---

# 2. API Conventions

## Base URL

Local development:

    http://localhost:8000/api

All endpoints must be versioned in the future.

For the POC, `/api/` is sufficient.

---

## Content Type

Requests and responses use:

    application/json

unless explicitly stated otherwise.

---

## JSON Naming

Use `snake_case`.

Example:

```json
{
  "agent_id": "support-agent-01",
  "task_id": "task-001"
}
````

Do not mix camelCase and snake_case.

---

# 3. Authentication

The POC must distinguish between:

### Admin/API client requests

Used for:

* creating agents
* creating tasks
* creating policies
* registering tools
* viewing audit data

### Agent execution requests

Used for:

* requesting authorization
* invoking tools

Do not rely on a user-submitted `agent_id` as proof of identity.

The authenticated identity must be established separately.

---

# 4. Development Authentication

For the Week 1 POC, authentication may use a simple bearer-token mechanism.

Example:

```http
Authorization: Bearer <token>
```

The exact token implementation is internal.

The API must reject missing or invalid credentials for protected endpoints.

Never hard-code real credentials.

---

# 5. Common Response Structure

Successful responses may use:

```json
{
  "data": {},
  "request_id": "req-001"
}
```

Errors should use:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request",
    "details": {}
  },
  "request_id": "req-001"
}
```

`request_id` should be present whenever possible.

---

# 6. HTTP Status Codes

Use standard status codes.

```text
200 OK
201 Created
400 Bad Request
401 Unauthorized
403 Forbidden
404 Not Found
409 Conflict
429 Too Many Requests
500 Internal Server Error
503 Service Unavailable
```

Authorization DENY is different from HTTP authentication failure.

A validly authenticated agent may receive:

```text
200
decision = DENY
```

because the request was successfully evaluated and rejected by policy.

Authentication failure should normally use:

```text
401
```

Use these HTTP semantics consistently:

```text
401 = authentication failure
403 = authenticated caller lacks required administrative/API permission
200 + decision = DENY = authorization was successfully evaluated and rejected
400 = malformed or schema-invalid request
```

Unknown agents, disabled agents, unknown tasks, expired tasks, unknown tools,
disabled tools, and policy mismatches are authorization outcomes for an
authenticated authorization request and should return `200` with
`decision = DENY` and a stable reason code.

---

# 7. Agents API

## 7.1 Create Agent

Endpoint:

```http
POST /api/agents/
```

Request:

```json
{
  "name": "Customer Support Agent",
  "description": "Handles customer support workflows"
}
```

Server generates:

```text
agent_id
```

Response:

```json
{
  "data": {
    "agent_id": "support-agent-01",
    "name": "Customer Support Agent",
    "description": "Handles customer support workflows",
    "status": "ACTIVE",
    "created_at": "2026-08-13T10:00:00Z"
  },
  "request_id": "req-001"
}
```

Status:

```text
201
```

---

## 7.2 List Agents

Endpoint:

```http
GET /api/agents/
```

Response:

```json
{
  "data": [
    {
      "agent_id": "support-agent-01",
      "name": "Customer Support Agent",
      "status": "ACTIVE",
      "created_at": "2026-08-13T10:00:00Z"
    }
  ],
  "request_id": "req-002"
}
```

---

## 7.3 Get Agent

Endpoint:

```http
GET /api/agents/{agent_id}/
```

Example:

```http
GET /api/agents/support-agent-01/
```

Response:

```json
{
  "data": {
    "agent_id": "support-agent-01",
    "name": "Customer Support Agent",
    "description": "Handles customer support workflows",
    "status": "ACTIVE",
    "created_at": "2026-08-13T10:00:00Z"
  },
  "request_id": "req-003"
}
```

---

## 7.4 Disable Agent

Endpoint:

```http
POST /api/agents/{agent_id}/disable/
```

Response:

```json
{
  "data": {
    "agent_id": "support-agent-01",
    "status": "DISABLED"
  },
  "request_id": "req-004"
}
```

Disabled agents cannot execute tools.

---

# 8. Tasks API

## 8.1 Create Task

Endpoint:

```http
POST /api/tasks/
```

Request:

```json
{
  "agent_id": "support-agent-01",
  "user_id": "user-001",
  "description": "Refund order #8291 up to ₹5,000"
}
```

Response:

```json
{
  "data": {
    "task_id": "task-001",
    "agent_id": "support-agent-01",
    "user_id": "user-001",
    "description": "Refund order #8291 up to ₹5,000",
    "status": "ACTIVE",
    "created_at": "2026-08-13T10:05:00Z"
  },
  "request_id": "req-005"
}
```

Status:

```text
201
```

---

## 8.2 Get Task

Endpoint:

```http
GET /api/tasks/{task_id}/
```

Response:

```json
{
  "data": {
    "task_id": "task-001",
    "agent_id": "support-agent-01",
    "user_id": "user-001",
    "description": "Refund order #8291 up to ₹5,000",
    "status": "ACTIVE",
    "created_at": "2026-08-13T10:05:00Z",
    "expires_at": "2026-08-13T10:35:00Z"
  },
  "request_id": "req-006"
}
```

---

## 8.3 Revoke Task

Endpoint:

```http
POST /api/tasks/{task_id}/revoke/
```

Response:

```json
{
  "data": {
    "task_id": "task-001",
    "status": "REVOKED"
  },
  "request_id": "req-007"
}
```

All future requests using this task must be denied.

---

# 9. Policies API

## 9.1 Create Policy

Endpoint:

```http
POST /api/policies/
```

Request:

```json
{
  "name": "Support Refund Policy",
  "description": "Allows support agent to refund a specific order",
  "agent_scope": {
    "agent_id": "support-agent-01"
  },
  "user_scope": {
    "user_id": "user-001"
  },
  "task_scope": {
    "task_id": "task-001"
  },
  "tool_scope": {
    "tool": "tool-refund-001"
  },
  "allowed_actions": [
    "refund_order"
  ],
  "resource_scope": {
    "type": "order",
    "mode": "EXACT",
    "ids": [
      "8291"
    ]
  },
  "constraints": {
    "amount": {
      "operator": "LTE",
      "value": 5000
    },
    "currency": {
      "operator": "EQ",
      "value": "INR"
    }
  }
}
```

Response:

```json
{
  "data": {
    "policy_id": "policy-refund-001",
    "name": "Support Refund Policy",
    "status": "ACTIVE"
  },
  "request_id": "req-008"
}
```

Status:

```text
201
```

---

## 9.2 List Policies

Endpoint:

```http
GET /api/policies/
```

Optional filters:

```text
?agent_id=support-agent-01
?task_id=task-001
?status=ACTIVE
```

Response:

```json
{
  "data": [
    {
      "policy_id": "policy-refund-001",
      "name": "Support Refund Policy",
      "status": "ACTIVE",
      "agent_id": "support-agent-01",
      "task_id": "task-001"
    }
  ],
  "request_id": "req-009"
}
```

---

## 9.3 Get Policy

Endpoint:

```http
GET /api/policies/{policy_id}/
```

Response returns the complete policy definition.

---

## 9.4 Revoke Policy

Endpoint:

```http
POST /api/policies/{policy_id}/revoke/
```

Response:

```json
{
  "data": {
    "policy_id": "policy-refund-001",
    "status": "REVOKED"
  },
  "request_id": "req-010"
}
```

---

# 10. Authorization API

This is the most important endpoint in the system.

`POST /api/authorize/` is decision-only. It evaluates the exact authenticated
request and returns ALLOW or DENY. It never executes a tool.

## 10.1 Evaluate Authorization

Endpoint:

```http
POST /api/authorize/
```

Request:

```json
{
  "agent_id": "support-agent-01",
  "user_id": "user-001",
  "task_id": "task-001",
  "tool": "tool-refund-001",
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

---

## 10.2 ALLOW Response

Status:

```text
200
```

Response:

```json
{
  "data": {
    "decision": "ALLOW",
    "reason_code": "AUTHORIZED",
    "reason": "Request satisfies task authorization",
    "policy_id": "policy-refund-001",
    "request_id": "req-011"
  }
}
```

The tool may only execute through the internal Tool Gateway after this
successful decision and after the required audit record can be persisted.

---

## 10.3 DENY Response

Status:

```text
200
```

Response:

```json
{
  "data": {
    "decision": "DENY",
    "reason_code": "PARAMETER_LIMIT_EXCEEDED",
    "reason": "Requested amount exceeds the authorized maximum",
    "policy_id": "policy-refund-001",
    "request_id": "req-012"
  }
}
```

The tool must NOT execute.

---

# 11. Authorization Request Validation

The endpoint must reject malformed requests.

Required:

```text
agent_id
task_id
tool
action
```

Resource may be required depending on the registered tool schema.

Parameters must satisfy the registered tool schema.

---

# 12. Authorization Error Cases

## Missing agent identity

HTTP:

```text
401
```

---

## Unknown agent

HTTP:

```text
200
```

Decision:

```json
{
  "decision": "DENY",
  "reason_code": "INVALID_AGENT"
}
```

---

## Disabled agent

HTTP:

```text
200
```

Decision:

```json
{
  "decision": "DENY",
  "reason_code": "AGENT_DISABLED"
}
```

---

## Unknown task

HTTP:

```text
200
```

Decision:

```json
{
  "decision": "DENY",
  "reason_code": "TASK_NOT_FOUND"
}
```

---

## Expired task

HTTP:

```text
200
```

Decision:

```json
{
  "decision": "DENY",
  "reason_code": "TASK_EXPIRED"
}
```

---

# 13. Tools API

## 13.1 Register Tool

Endpoint:

```http
POST /api/tools/
```

Request:

```json
{
  "tool_id": "tool-refund-001",
  "name": "refund_order",
  "description": "Refund an order",
  "service": "order-service",
  "risk_level": "HIGH",
  "input_schema": {
    "type": "object",
    "properties": {
      "order_id": {
        "type": "string"
      },
      "amount": {
        "type": "number"
      },
      "currency": {
        "type": "string"
      }
    },
    "required": [
      "order_id",
      "amount",
      "currency"
    ],
    "additionalProperties": false
  }
}
```

Response:

```json
{
  "data": {
    "tool_id": "tool-refund-001",
    "name": "refund_order",
    "status": "ENABLED"
  },
  "request_id": "req-013"
}
```

---

## 13.2 List Tools

Endpoint:

```http
GET /api/tools/
```

Response:

```json
{
  "data": [
    {
      "tool_id": "tool-refund-001",
      "name": "refund_order",
      "service": "order-service",
      "risk_level": "HIGH",
      "status": "ENABLED"
    }
  ],
  "request_id": "req-014"
}
```

---

## 13.3 Get Tool

Endpoint:

```http
GET /api/tools/{tool_id}/
```

Response includes:

* tool metadata
* input schema
* risk level
* status

---

## 13.4 Disable Tool

Endpoint:

```http
POST /api/tools/{tool_id}/disable/
```

A disabled tool cannot execute.

---

# 14. Tool Execution API

The internal tool execution interface is separate from public authorization.

Conceptual endpoint:

```http
POST /api/internal/tools/{tool_id}/execute/
```

This endpoint must NOT be publicly exposed to agents or the frontend. It is an
internal backend boundary used by the Tool Gateway after authorization succeeds.

Terminology:

```text
tool_id = unique registered tool identifier
tool = reference to a registered tool, normally by tool_id
action = operation requested on that tool
service = optional metadata/grouping field
```

Request should include the authorization decision or an internally trusted execution context.

Example:

```json
{
  "request_id": "req-011",
  "authorization": {
    "decision": "ALLOW",
    "policy_id": "policy-refund-001"
  },
  "arguments": {
    "order_id": "8291",
    "amount": 3000,
    "currency": "INR"
  }
}
```

The tool gateway should reject execution if:

```text
decision != ALLOW
```

or if the execution context cannot be trusted.

Security-sensitive tool execution must also fail closed if the required audit
record for the authorization decision cannot be persisted.

---

# 15. MCP Integration API

The exact MCP transport implementation may depend on the MCP SDK used.

The internal authorization boundary must remain:

```text
MCP Request
    ↓
Validate
    ↓
Authenticate
    ↓
Authorize
    ↓
Tool Execution
```

Do not duplicate policy logic inside each MCP tool.

All MCP tools must use the central authorization service.

---

# 16. Audit API

## 16.1 List Audit Events

Endpoint:

```http
GET /api/audit-events/
```

Optional filters:

```text
?agent_id=support-agent-01
?task_id=task-001
?decision=DENY
?action=refund_order
?reason_code=PARAMETER_LIMIT_EXCEEDED
```

Response:

```json
{
  "data": [
    {
      "event_id": "audit-001",
      "timestamp": "2026-08-13T10:10:00Z",
      "request_id": "req-012",
      "agent_id": "support-agent-01",
      "user_id": "user-001",
      "task_id": "task-001",
      "tool": "tool-refund-001",
      "action": "refund_order",
      "resource": {
        "type": "order",
        "id": "8291"
      },
      "decision": "DENY",
      "reason_code": "PARAMETER_LIMIT_EXCEEDED",
      "policy_id": "policy-refund-001",
      "latency_ms": 7
    }
  ],
  "request_id": "req-015"
}
```

---

# 17. Audit Event Detail

Endpoint:

```http
GET /api/audit-events/{event_id}/
```

Returns the complete event record subject to data-minimization rules.

Do not expose secrets or credentials.

---

# 18. Health API

## 18.1 Health Check

Endpoint:

```http
GET /api/health/
```

Response:

```json
{
  "status": "ok"
}
```

---

# 19. Readiness API

Endpoint:

```http
GET /api/ready/
```

Response should verify required dependencies.

Example:

```json
{
  "status": "ready",
  "dependencies": {
    "database": "ok",
    "redis": "ok"
  }
}
```

If a required dependency is unavailable:

```text
503
```

---

# 20. Metrics API

Endpoint:

```http
GET /api/metrics/
```

The API may expose application metrics for the dashboard.

Minimum conceptual metrics:

```text
authorization_requests_total
authorization_allows_total
authorization_denies_total
authorization_errors_total
authorization_latency_ms
tool_execution_total
tool_execution_failures_total
```

Exact Prometheus exposition may be added later.

Do not expose secrets.

---

# 21. Pagination

List endpoints should support pagination once data volume grows.

Preferred query parameters:

```text
?page=1
&page_size=50
```

Maximum page size:

```text
100
```

Do not allow unlimited result sets.

---

# 22. Filtering

Filtering must be deterministic and server-side.

Example:

```http
GET /api/audit-events/?decision=DENY
```

Supported filters should be explicitly documented.

Do not create dynamic SQL filters directly from arbitrary user input.

Use validated ORM query parameters.

---

# 23. Idempotency

Administrative creation endpoints may optionally accept:

```http
Idempotency-Key: <unique-key>
```

This is useful for:

* policy creation
* task creation
* other state-changing requests

Week 1 may implement this only if duplicate creation becomes a real issue.

Do not add unnecessary complexity before the core POC works.

---

# 24. Request IDs

Every incoming request should receive or generate a request ID.

Header:

```http
X-Request-ID: req-001
```

If the client supplies one, validate and propagate it.

If absent, generate one.

The request ID must appear in:

* response
* logs
* audit event

---

# 25. Error Codes

Use stable machine-readable error codes.

Minimum API errors:

```text
VALIDATION_ERROR
AUTHENTICATION_REQUIRED
INVALID_CREDENTIALS
INVALID_AGENT
AGENT_DISABLED
TASK_NOT_FOUND
TASK_EXPIRED
TASK_REVOKED
POLICY_NOT_FOUND
POLICY_INVALID
TOOL_NOT_FOUND
TOOL_DISABLED
AUTHORIZATION_DENIED
RATE_LIMIT_EXCEEDED
INTERNAL_ERROR
SERVICE_UNAVAILABLE
```

Authorization denial should additionally provide a policy reason code as specified in POLICY_SPEC.md.

---

# 26. Security Requirements

All protected endpoints must enforce backend authorization.

Never assume:

```text
React UI
```

is trusted.

Never allow:

```text
POST /api/authorize/
```

to grant itself permissions.

Never accept:

```text
is_admin: true
```

or similar client-controlled privilege indicators.

Never trust:

```text
agent_id
user_id
policy_id
```

without authenticating and validating their relationship.

---

# 27. CORS

Development may allow the local React origin.

Example:

```text
http://localhost:5173
```

Production CORS configuration must be explicit.

Do not use unrestricted:

```text
*
```

for authenticated application endpoints unless there is a documented reason.

---

# 28. Request Size Limits

Limit request body size.

This prevents oversized payloads from being used as a trivial denial-of-service vector.

The POC should define a reasonable maximum, for example:

```text
1 MB
```

Adjust only when required.

---

# 29. Tool Parameter Validation

Every registered tool must have an explicit input schema.

Example:

```json
{
  "type": "object",
  "properties": {
    "order_id": {
      "type": "string"
    },
    "amount": {
      "type": "number",
      "minimum": 0
    },
    "currency": {
      "type": "string"
    }
  },
  "required": [
    "order_id",
    "amount",
    "currency"
  ],
  "additionalProperties": false
}
```

The request must pass schema validation before policy evaluation of parameters.

---

# 30. Authorization vs HTTP Authentication

These concepts must remain separate.

### Authentication

Question:

> Who is making this request?

Failure:

```text
401
```

### Authorization

Question:

> Is this authenticated requester allowed to perform this exact action?

Failure:

```text
200
decision = DENY
```

or another documented authorization-specific response where appropriate.

Do not collapse these concepts.

---

# 31. Authorization Response Must Not Leak Policy Secrets

A denial reason should be useful but should not expose internal security configuration unnecessarily.

Good:

```text
Requested refund exceeds authorized maximum.
```

Avoid:

```text
Our hidden policy policy-refund-001 has condition
amount <= 5000 and hidden admin override token = ...
```

The frontend may receive a safe human-readable explanation and stable reason code.

---

# 32. API Acceptance Tests

The following requests must work as documented.

### Valid request

```text
POST /api/authorize/
refund_order(8291, 3000)
→ ALLOW
```

### Excessive amount

```text
POST /api/authorize/
refund_order(8291, 8000)
→ DENY
```

### Wrong resource

```text
POST /api/authorize/
refund_order(9999, 3000)
→ DENY
```

### Wrong action

```text
POST /api/authorize/
delete_customer(123)
→ DENY
```

### Expired task

```text
POST /api/authorize/
expired task
→ DENY
```

### Unknown tool

```text
POST /api/authorize/
unknown_tool(...)
→ DENY
```

### Missing credentials

```text
POST /api/authorize/
without authentication
→ 401
```

### Policy failure

Simulated policy engine/database failure:

```text
POST /api/authorize/
→ DENY
→ no tool execution
→ audit event
```

---

# 33. Example End-to-End API Flow

## Step 1 — Create agent

```http
POST /api/agents/
```

Returns:

```text
support-agent-01
```

---

## Step 2 — Create task

```http
POST /api/tasks/
```

Returns:

```text
task-001
```

---

## Step 3 — Create policy

```http
POST /api/policies/
```

Policy allows:

```text
refund_order
order 8291
amount <= 5000 INR
```

---

## Step 4 — Agent requests authorization

```http
POST /api/authorize/
```

Request:

```json
{
  "agent_id": "support-agent-01",
  "user_id": "user-001",
  "task_id": "task-001",
  "tool": "tool-refund-001",
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

Response:

```json
{
  "data": {
    "decision": "ALLOW",
    "reason_code": "AUTHORIZED",
    "policy_id": "policy-refund-001",
    "request_id": "req-100"
  }
}
```

---

## Step 5 — Tool executes

Only after ALLOW.

The mock tool processes the request.

---

## Step 6 — Audit recorded

Audit event contains:

```text
agent
task
action
resource
decision
reason
policy
latency
timestamp
```

---

## Step 7 — Agent attempts escalation

Request:

```json
{
  "agent_id": "support-agent-01",
  "user_id": "user-001",
  "task_id": "task-001",
  "tool": "tool-refund-001",
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

Response:

```json
{
  "data": {
    "decision": "DENY",
    "reason_code": "PARAMETER_LIMIT_EXCEEDED",
    "policy_id": "policy-refund-001",
    "request_id": "req-101"
  }
}
```

The tool must not execute.

---

# 34. API Design Principle

The API must enforce this boundary:

```text
Agent
  ↓
Authenticated Request
  ↓
Authorization API
  ↓
Deterministic Decision
  ↓
Tool Gateway
```

Never:

```text
Agent
  ↓
Tool directly
```

Never:

```text
Frontend
  ↓
Tool directly
```

Never:

```text
LLM
  ↓
Tool directly
```

---

# 35. Future API Extensions

The following are intentionally deferred:

```text
API versioning
organization/workspace hierarchy
OAuth/OIDC integration
JWT-based delegated authority
cryptographic capability tokens
policy simulation endpoint
policy dry-run mode
human approval endpoint
webhooks
external policy engines
distributed authorization
multi-region APIs
billing APIs
```

These should not be implemented in Week 1 unless required by the core demonstration.

---

# 36. API Completion Criteria

The API is considered complete for the Week 1 POC when:

```text
[ ] Agents can be created
[ ] Tasks can be created
[ ] Policies can be created
[ ] Tools can be registered
[ ] Authorization can be evaluated
[ ] ALLOW is returned for valid requests
[ ] DENY is returned for invalid requests
[ ] Tool execution occurs only after ALLOW
[ ] Audit events are generated
[ ] Expired tasks are rejected
[ ] Wrong resources are rejected
[ ] Wrong actions are rejected
[ ] Parameter violations are rejected
[ ] Unknown tools are rejected
[ ] Missing authentication is rejected
[ ] API errors use stable codes
[ ] Request IDs are propagated
[ ] Health endpoint works
[ ] Tests cover the documented contracts
```

# 37. Final API Contract Rule

The most important contract is:

```text
POST /api/authorize/
```

must never mean:

> "Ask the AI whether this action is safe."

It means:

> "Evaluate this exact authenticated action against the current deterministic authorization state and return ALLOW or DENY."

```
```
