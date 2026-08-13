# SPEC_REVIEW.md

# Agent Action Firewall — Specification Cross-Verification

Performed before any Day 1 implementation, per `CODEX_EXECUTION_PLAN.md` Section 3.

---

## 1. Specifications Reviewed

Read in full:

- `AGENTS.md`
- `PRODUCT_SPEC.md`
- `ARCHITECTURE.md`
- `POLICY_SPEC.md`
- `API_SPEC.md`
- `BENCHMARK_PLAN.md`
- `README.md`
- `CODEX_EXECUTION_PLAN.md`

**Not reviewed — not present in the repository:**

- `THREAT_MODEL.md`
- `TEST_PLAN.md`

Both files are treated as authoritative source-of-truth documents by `AGENTS.md`, `ARCHITECTURE.md`, `PRODUCT_SPEC.md`, `README.md`, and `CODEX_EXECUTION_PLAN.md`, and `THREAT_MODEL.md` is ranked **#3 in the specification hierarchy** (above `POLICY_SPEC.md`, `ARCHITECTURE.md`, and `API_SPEC.md`). Their absence is the single largest gap in this review — see Section 8.

## Repository / Git State

No existing repository, `.git` directory, or prior application code was found in the working environment. This is a clean start; nothing to preserve or avoid overwriting. Repository scaffolding has **not** been created in this turn, per the instruction not to begin Day 1.

---

## 2. Contradictions Found

### 2.1 Missing `tasks` Django app in `AGENTS.md`

`AGENTS.md` → "Backend Structure" lists Django apps as:

    agents / authorization / policies / tools / audit

It does **not** list a `tasks` app, even though `AGENTS.md`'s own "Core Architecture" and "Task-Scoped Authorization" sections describe tasks as a first-class concept with their own lifecycle.

`ARCHITECTURE.md` §6–7 explicitly defines a `tasks` app with its own responsibilities (task creation, status, lifecycle, expiration, revocation, agent/user binding), and `CODEX_EXECUTION_PLAN.md` Day 1 §5 explicitly requires, "at minimum," `agents, tasks, policies, authorization, tools, audit`.

**Resolution:** Include a dedicated `tasks` app. `AGENTS.md`'s list is read as non-exhaustive/incomplete rather than a deliberate exclusion — `ARCHITECTURE.md` and `CODEX_EXECUTION_PLAN.md` agree with each other and are more specific on this exact point, and omitting a `tasks` app would contradict the Task Store design (`ARCHITECTURE.md` §5.8) and the Task/Policy field-ownership split described below. This does not touch a security guarantee, so it's resolved without escalation.

### 2.2 Inconsistent authorization reason-code sets across documents

Three different documents define overlapping but non-identical sets of machine-readable codes for the same concepts:

- `ARCHITECTURE.md` §17 (illustrative, non-exhaustive): `INVALID_AGENT, TASK_NOT_FOUND, TASK_EXPIRED, ACTION_NOT_ALLOWED, RESOURCE_NOT_ALLOWED, PARAMETER_VIOLATION, TOOL_NOT_REGISTERED, RATE_LIMIT_EXCEEDED, POLICY_EVALUATION_ERROR`
- `POLICY_SPEC.md` §25 (explicitly "minimum set" for authorization *decisions*): a larger, more granular set — e.g. `RESOURCE_TYPE_NOT_ALLOWED` / `RESOURCE_ID_NOT_ALLOWED` instead of `RESOURCE_NOT_ALLOWED`; `REQUIRED_PARAMETER_MISSING` / `PARAMETER_SCHEMA_INVALID` / `PARAMETER_LIMIT_EXCEEDED` / `PARAMETER_VALUE_NOT_ALLOWED` instead of `PARAMETER_VIOLATION`; plus `AGENT_DISABLED`, `TASK_NOT_ACTIVE`, `TASK_REVOKED`, `POLICY_NOT_FOUND`, `POLICY_DISABLED`, `POLICY_REVOKED`, `USER_SCOPE_MISMATCH`, `TOOL_DISABLED`, `EXPLICIT_DENY`.
- `API_SPEC.md` §25 (explicitly HTTP/API-layer *error* codes, a different concept): `VALIDATION_ERROR, AUTHENTICATION_REQUIRED, INVALID_CREDENTIALS, INVALID_AGENT, AGENT_DISABLED, TASK_NOT_FOUND, TASK_EXPIRED, TASK_REVOKED, POLICY_NOT_FOUND, POLICY_INVALID, TOOL_NOT_FOUND, TOOL_DISABLED, AUTHORIZATION_DENIED, RATE_LIMIT_EXCEEDED, INTERNAL_ERROR, SERVICE_UNAVAILABLE` — note `TOOL_NOT_FOUND` here vs. `TOOL_NOT_REGISTERED` in `POLICY_SPEC.md`.

**Resolution:** Per the specification hierarchy, `POLICY_SPEC.md` (#4) outranks `ARCHITECTURE.md` (#5) and `API_SPEC.md` (#6). `POLICY_SPEC.md §25` is adopted as the canonical, exhaustive set of **authorization decision `reason_code` values** (used in `AuthorizationDecision` / audit events / `POST /api/authorize/` responses). `API_SPEC.md §25`'s list is kept as a separate, smaller set of **HTTP/API-level `error.code` values** (malformed requests, missing auth, internal errors) used only in the `error` envelope for non-authorization failures — these two code spaces are not meant to be merged, and `ARCHITECTURE.md`'s list is treated as illustrative shorthand, superseded by `POLICY_SPEC.md` wherever they diverge.

### 2.3 No genuine contradiction found regarding decision-only `/api/authorize/`

Worth calling out explicitly because it easily could have been a contradiction: `PRODUCT_SPEC.md §7.5`, `ARCHITECTURE.md §5.5/§17.14/§8`, and `API_SPEC.md §10/§14` all consistently agree that `POST /api/authorize/` is decision-only and never executes a tool, and that a separate internal Tool Gateway performs execution only after ALLOW **and** after the required audit record is persisted. All three documents use near-identical wording, suggesting this point was already deliberately reconciled across documents. No action needed beyond preserving this invariant in implementation.

### 2.4 No genuine contradiction found regarding Task vs. Policy field ownership

`PRODUCT_SPEC.md §7.2`, `ARCHITECTURE.md §5.8/§12`, and `POLICY_SPEC.md §3/§8` all consistently state: Task owns agent/user binding, lifecycle, expiration, and revocation; Policy owns allowed tools/actions/resources/parameter constraints and explicit allow/deny effect. Like 2.3, this looks like a deliberately reconciled point. Adopted as-is.

---

## 3. Ambiguities Found

1. **Authentication mechanism for admin vs. agent identity is under-specified.** `API_SPEC.md §3–4` distinguishes "Admin/API client" from "Agent execution" callers and says the API "must reject missing or invalid credentials," and that bearer tokens "may" be used, but no document specifies: how an agent obtains a token, whether admin and agent tokens are the same credential type, or how a token maps to a specific `agent_id` (so that a caller cannot simply assert an arbitrary `agent_id` in the request body).
   **Resolution/assumption:** Implement a minimal token model — one static, per-agent bearer token issued at agent-creation time (visible once, stored hashed), used to authenticate `POST /api/authorize/` and cryptographically bind the caller to a specific `agent_id` (the token determines identity; the request body's `agent_id` is validated against it rather than trusted). Administrative endpoints (agents/tasks/policies/tools CRUD) use Django's own authenticated-user/session or a separate admin API key. This satisfies `API_SPEC.md §26`'s explicit warning not to trust a client-supplied `agent_id` without authenticating and validating it.

2. **Rate limiting thresholds are never specified.** `AGENTS.md`, `POLICY_SPEC.md §41`, and `ARCHITECTURE.md §5.10` all require rate limiting via Redis and a `RATE_LIMIT_EXCEEDED` outcome, but no numeric limit (per agent, per IP, per endpoint) is given anywhere.
   **Resolution/assumption:** Implement a configurable per-agent request-rate limit (e.g. an environment-variable default, generous enough not to interfere with the benchmark's throughput tests) with the actual number documented in `.env.example` and `ARCHITECTURE.md`/`POLICY_SPEC.md` once chosen. Not a Day 1 blocker.

3. **MCP SDK/transport is unspecified.** `ARCHITECTURE.md §13` and `PRODUCT_SPEC.md §14` describe the MCP integration only conceptually ("MCP-compatible interface," "may depend on MCP SDK used").
   **Resolution/assumption:** Use the official Python `mcp` SDK to expose the registered mock tools as MCP tools, with the MCP layer calling into the same central `authorize()` service used by the REST path (no duplicated policy logic), consistent with `API_SPEC.md §15`. This is an Implementation-Order item 10 (mid-week), not a Day 1 concern.

4. **The `/api/internal/tools/{tool_id}/execute/` endpoint in `API_SPEC.md §14` is explicitly called "conceptual" and is stated to "not be publicly exposed," but Django alone doesn't provide network-level isolation for a URL that is technically registered in the same URLconf as public endpoints.**
   **Resolution/assumption:** Rather than registering this as a reachable HTTP endpoint at all, implement tool execution as an internal, non-HTTP Python service call (`tool_gateway.execute(...)`) invoked directly by the authorization/view layer after a persisted ALLOW decision. This is a stricter reading of "must not expose a direct unauthenticated execution path" (`ARCHITECTURE.md §5.5`, `PRODUCT_SPEC.md §7.5`) than the conceptual HTTP endpoint sketched in `API_SPEC.md`, and removes an entire class of "was this internal endpoint accidentally reachable" risk. If a real HTTP boundary is later needed (e.g. a genuinely separate tool-execution service), it should require a separate internal-only credential distinct from any agent or admin token.

5. **Policy versioning is explicitly optional** (`POLICY_SPEC.md §33`: "Week 1 may use a simple updated policy model rather than full immutable policy versioning"). **Resolution:** Use simple mutable policy rows with `updated_at` and an audit record of the change for Week 1; do not build versioning unless a specific requirement emerges.

---

## 4. Architecture Concerns

1. **Benchmark dataset size vs. Week-1 scope tension.** `BENCHMARK_PLAN.md §7` recommends a "minimum" synthetic dataset of 100 agents / 10,000 users / 100,000 tasks / 100,000 policies / 1,000,000 resources for the *final* benchmark, which is a nontrivial data-generation and infrastructure-sizing effort on its own. This sits in tension with `AGENTS.md`'s and `CODEX_EXECUTION_PLAN.md §6`'s explicit "avoid unnecessary complexity / prefer simple architecture" philosophy for a 7-day solo POC. `BENCHMARK_PLAN.md §7` itself says "The POC may start smaller during development," so this is not a contradiction, but it is a real execution-risk if attempted at full scale before Day 6–7. **Interpretation adopted:** use a small dataset for all development-time (Day 1–5) testing and iterate up to a larger dataset only for the final Day 6/7 benchmark, explicitly reporting whatever scale was actually achieved rather than reproducing the full suggested minimum if time-constrained.

2. **10,000 RPS target is aggressive for a synchronous Django/WSGI + PostgreSQL + Redis stack on unknown local hardware**, especially once the fail-closed audit-before-execute requirement (`ARCHITECTURE.md §5.5`, `API_SPEC.md §10.2/§14`) is honored, since that makes a synchronous database write part of the critical path for every request. `BENCHMARK_PLAN.md` is well-hedged about this already (§28, §29, §37, §40 all explicitly forbid inventing or overclaiming the number and require reporting the actual measured result), so this is not a contradiction — it's flagged here only so the eventual benchmark report is not treated as a failure if it lands well below 10K RPS. Per Rule 15 (non-negotiable security rules) and `BENCHMARK_PLAN.md §32/§40.9`, the audit-before-execute requirement must **not** be relaxed to hit a higher throughput number.

3. **Policy caching vs. security-correctness tension is already well-resolved in the docs.** `ARCHITECTURE.md §19` allows caching read-heavy policy/task metadata but requires "explicit expiration and invalidation rules," and `POLICY_SPEC.md §42` says "if cache consistency cannot be guaranteed, prefer the authoritative database state." **Interpretation:** treat Redis caching of policy/task state as a pure performance optimization to be added later (if at all) once correctness is proven against PostgreSQL directly; do not let caching correctness become a Week-1 dependency for the authorization decision to be correct.

---

## 5. Security Concerns

1. **No document specifies token issuance/rotation/storage details** beyond "may use a simple bearer-token mechanism" (`API_SPEC.md §4`). For a project whose portfolio thesis is specifically about AI-agent security, storing tokens in plaintext or using a trivially guessable identity mechanism would undercut that thesis. Addressed by the assumption in Section 3.1 above (hashed storage, token-determines-identity rather than client-asserted `agent_id`).

2. **Fail-closed-on-audit-failure is a strong, cross-document requirement** (`ARCHITECTURE.md §5.5/§20`, `API_SPEC.md §14`, `PRODUCT_SPEC.md §7.5`) and is treated here as non-negotiable per `CODEX_EXECUTION_PLAN.md` Rule 13/14. This will be implemented as: authorization decision → write audit record synchronously → only on successful persistence does an ALLOW proceed to tool execution. This is called out explicitly because it is easy to accidentally weaken (e.g., by making audit writes "best effort" or asynchronous) while chasing benchmark numbers, which Rule 15 explicitly forbids.

3. **Absence of `THREAT_MODEL.md` means this review cannot verify** whether all threats the team intends to defend against are actually covered by `PRODUCT_SPEC.md §10`'s and `README.md`'s threat lists (privilege escalation, resource/action substitution, parameter manipulation, expired/revoked auth, unknown tools, missing identity, prompt injection, replay/tool poisoning, confused-deputy, fail-open). These lists are consistent with each other, but a dedicated threat model might identify additional threats (e.g., timing side-channels on policy evaluation, agent enumeration via error-message differences, audit-log tampering) not currently reflected anywhere. Flagged as an unresolved gap in Section 8.

---

## 6. Performance Concerns

Covered substantively in Section 4.2 above. Summary: the p50 < 20ms / p95 < 100ms targets and the 100→10,000 RPS experiment ladder are explicitly documented as targets/experiments rather than guarantees throughout `BENCHMARK_PLAN.md`, and the specs are internally consistent and appropriately hedged on this point. No contradiction; the only risk is in execution (see Section 4), not in the specification itself.

---

## 7. Recommended Resolutions (Summary)

| # | Issue | Resolution |
|---|---|---|
| 1 | Missing `tasks` app in `AGENTS.md` | Include dedicated `tasks` app (per `ARCHITECTURE.md` + `CODEX_EXECUTION_PLAN.md`) |
| 2 | Reason-code set mismatch | `POLICY_SPEC.md §25` is canonical for authorization `reason_code`; `API_SPEC.md §25` is a separate, smaller HTTP `error.code` space |
| 3 | Auth/token mechanism unspecified | Per-agent hashed bearer token issued at agent creation; token determines identity, not the request body |
| 4 | Rate-limit thresholds unspecified | Configurable env-driven default; document once chosen; not a Day 1 blocker |
| 5 | MCP SDK unspecified | Official Python `mcp` SDK; MCP layer calls the same central `authorize()` service |
| 6 | Internal tool-execution endpoint's isolation | Implement as an internal Python call, not a reachable HTTP endpoint, for Week 1 |
| 7 | Policy versioning | Simple mutable rows + audit trail; no versioning system in Week 1 |
| 8 | Full benchmark dataset size vs. Week-1 timeline | Small dataset through Day 5; scale up only for the final Day 6/7 benchmark; report whatever is actually achieved |
| 9 | 10K RPS target vs. fail-closed audit requirement | Audit-before-execute is never relaxed to hit a throughput number; report the real ceiling |

---

## 8. Requirements Requiring Explicit Human Decision (Unresolved)

1. **`THREAT_MODEL.md` and `TEST_PLAN.md` are missing from the uploaded files but are treated as authoritative, and `THREAT_MODEL.md` outranks `POLICY_SPEC.md`, `ARCHITECTURE.md`, and `API_SPEC.md` in the specification hierarchy.** I cannot verify whether the security assumptions built into the other documents (fail-closed rules, threat coverage list, trust boundaries) match an actual threat model that hasn't been shared, and I cannot verify `TEST_PLAN.md`'s specific expected test cases against the architecture. This is exactly the kind of "irreversible ambiguity" `CODEX_EXECUTION_PLAN.md §24` says warrants asking rather than guessing, since a missing or different threat model could materially change security requirements.
   **Ask:** Do these two files exist and should they be uploaded before Day 1 proceeds, or should Day 1 proceed using the threat coverage described in `PRODUCT_SPEC.md §10`, `README.md` ("Security Against Agent Abuse," "Security Limitations"), and `AGENTS.md`'s "Security Requirements"/"Fail-Closed Rule" sections as a stand-in, with `THREAT_MODEL.md`/`TEST_PLAN.md` to be authored as part of the implementation once their absence is confirmed intentional?

No other issue found rose to the "ask before proceeding" bar — items 1–9 above were resolved using the specification hierarchy and the safest reasonable interpretation, per `CODEX_EXECUTION_PLAN.md §4/§23`.

---

## 9. Final Implementation Interpretation for the POC

- **Stack, apps, and repo layout:** as described in `ARCHITECTURE.md §6–7`, with the `tasks` app included alongside `agents`, `policies`, `authorization`, `tools`, `audit`.
- **Authorization is the security-critical core**, implemented as a layered, dependency-free (no Django ORM, no HTTP, no LLM) deterministic engine per `ARCHITECTURE.md §5.4/§10`, exercised through `authorization_service.authorize(...)` and tested in isolation for both correctness and benchmarking.
- **`POST /api/authorize/` is decision-only**; tool execution is a distinct internal code path invoked only after a persisted ALLOW.
- **Default-deny, fail-closed everywhere**, matching `AGENTS.md`'s Fail-Closed Rule, `PRODUCT_SPEC.md §12`, `POLICY_SPEC.md §22`, and `ARCHITECTURE.md §20/§27` verbatim.
- **Reason codes:** `POLICY_SPEC.md §25`'s set for authorization decisions; `API_SPEC.md §25`'s set for HTTP/API errors, as two distinct namespaces.
- **Auth:** hashed per-agent bearer tokens for `/api/authorize/`; separate admin credential for administrative CRUD endpoints.
- **Benchmark dataset:** small during development, scaled up only for the final reported benchmark; all throughput/latency claims will state the actual measured result, never an assumed or target number, per `BENCHMARK_PLAN.md §37/§40`.
- **THREAT_MODEL.md / TEST_PLAN.md gap:** flagged to the developer (Section 8) rather than silently invented. Implementation of Day 1 scaffolding can proceed without them since Day 1 is foundational (no security-sensitive logic yet), but security-sensitive work in later days should not proceed past this gap without a decision from the developer.

---

## 10. What Was *Not* Done in This Turn

- No specification file was modified.
- No application code was written.
- No repository, Django project, or React project was scaffolded.
- No dependencies were installed.
- No Git repository was initialized and no commits were made.
- No benchmark or security-test results were produced or invented.
