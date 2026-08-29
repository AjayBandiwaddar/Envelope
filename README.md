# Reference Merchant — Agentic Commerce with a Cryptographically Bound Firewall

**Razorpay AI Buildathon 2026 — Track 1: AI Growth & Agentic Commerce**

> An AI agent can genuinely shop and pay a real merchant, end to end — but it can never authorize its own spending. Every money-relevant step is checked by a deterministic authorization firewall, backed by a cryptographically signed proof of exactly what was approved, with every decision — allowed or denied — permanently recorded.

![Architecture diagram](architecture.svg)

---

## Table of Contents

- [The Problem](#the-problem)
- [Our Interpretation](#our-interpretation)
- [What's Built — Three Systems](#whats-built--three-systems)
- [The Purchase Flow](#the-purchase-flow)
- [Security Guarantees](#security-guarantees)
- [Live Failure Demonstrations](#live-failure-demonstrations)
- [What We Explicitly Do Not Claim](#what-we-explicitly-do-not-claim)
- [Known Limitations](#known-limitations)
- [Tech Stack](#tech-stack)
- [Running It Locally](#running-it-locally)
- [Test Suite](#test-suite)
- [Repository History](#repository-history)
- [Credits](#credits)

---

## The Problem

Razorpay's Track 1 asks for one of two things:

> *"Build an agent that grows revenue for a merchant on Razorpay test-mode APIs, **or** that makes a merchant transactable by an AI buyer end to end."*

with one non-negotiable bar, regardless of which path you pick:

> *"Every money action explainable, bounded and gated. Show the audit trail and one failure handled gracefully."*

The track's own "why now" cites NPCI's UAP and the live protocol race between AP2, ACP, and x402 — 2026 is the year every major platform is racing to define how AI agents should be allowed to spend money on a human's behalf. Razorpay itself already piloted exactly this with NPCI and Claude in February 2026, letting AI agents place UPI orders on Zomato, Swiggy, and Zepto under spending limits.

## Our Interpretation

We picked the harder path: **make a merchant transactable by an AI buyer, end to end** — not an upsell chatbot. This project is built on a pre-existing, independently developed project of ours, the **Agent Action Firewall**: a deterministic authorization gateway whose core principle — *"the AI agent may propose an action, but a deterministic authorization layer decides whether that exact action is permitted"* — is close to a direct match for the track's bar. We disclose this openly rather than presenting it as built from scratch (see [Repository History](#repository-history)): reusing tested, hardened infrastructure and spending the buildathon's time on the genuinely new parts — commerce logic, an AI buyer, and a cryptographic proof layer — is a deliberate engineering choice, not a shortcut.

## What's Built — Three Systems

| | System | What it does |
|---|---|---|
| 1 | **Agent Action Firewall** | Extended for commerce. Decides ALLOW/DENY for every action an agent proposes, with zero implicit-allow paths, and signs a cryptographic **Purchase Mandate** — a simplified, honest analogue of [AP2](https://github.com/google-agentic-commerce/AP2)'s Cart Mandate — at the moment a human confirms a purchase. |
| 2 | **Reference Merchant** | A real storefront (six laptops, real prices) exposing a genuine **MCP server** for agent discovery/purchase, plus `schema.org` structured data on every product page — a recognized vocabulary any commerce-literate agent could parse, not a bespoke API only our own agent understands. |
| 3 | **AI Buyer Agent** | `agent/buyer.py` — a real **MCP client** using Google Gemini (free tier) to parse a natural-language request, browse the real catalog, and drive the purchase. It can propose a purchase; it structurally **cannot** confirm one. |

## The Purchase Flow

1. **`propose_purchase_intent`** — the agent names a product and quantity. Price is looked up from the live database *right now* — never accepted from the agent.
2. **Human confirmation** — a hard stop, outside the agent's reach. `confirm_purchase_intent` is not an MCP tool; there is no callable action for the agent to authorize its own purchase with.
3. **`confirm_purchase_intent`** — writes the authorization `Policy` **and** signs the cryptographic `Mandate` for this exact transaction (product, quantity, amount, currency, expiry, nonce).
4. **`create_order`** — accepts only an `intent_id`. No amount or currency parameter exists to spoof. Firewall checks the Policy *and* the Mandate; only then is a real Razorpay test-mode order created — atomically, so two concurrent attempts can never create two orders or make two provider calls.
5. **Checkout** — a human completes payment via Razorpay Checkout. This is not a workaround: Razorpay requires a human-present payment step even in test mode, and we treat that as a second, independent consent layer rather than a limitation.
6. **`finalize_payment`** — independently verifies Razorpay's payment signature (idempotent — safe to call twice) and marks the order `PAID`.
7. **Audit trail** — every step above, ALLOW or DENY, is permanently recorded and viewable live at `/checkout/<intent_id>/audit/`, including a **live re-verification of the mandate signature on every page load** — not a cached status.

## Security Guarantees

- No implicit `ALLOW` anywhere in the policy engine — every path either matches an explicit rule or denies.
- Unknown parameters are always rejected outright, never silently ignored.
- The agent's credential never appears in any tool's callable schema.
- Confused-deputy protection: a task belonging to another agent is indistinguishable from one that doesn't exist.
- Prices are always server-derived; `create_order` has no amount/currency field to spoof at all.
- The cryptographic mandate is checked against **live database state**, not just its own signature — a validly signed mandate that no longer matches reality is rejected.
- Duplicate/concurrent order creation is prevented by a real database uniqueness constraint (portable across Postgres and SQLite) — proven with a genuine multithreaded concurrency test, not a mock.
- `finalize_payment` is idempotent; a handler exception anywhere is caught and never crashes the pipeline or leaks internal detail.
- Audit persistence is fail-closed: if the audit record can't be saved, the decision is downgraded to `DENY`.

## Live Failure Demonstrations

Available at **`/security-demo/`** — three real attacks, run through the actual code path with fresh disposable data every time, backed by a real invocation counter proving zero Razorpay calls on every denial:

| Attack | Result |
|---|---|
| Skip human confirmation, then `create_order` | `DENY — POLICY_NOT_FOUND` |
| `create_order` with an undeclared extra field | `DENY — UNKNOWN_PARAMETER` |
| Tamper a signed mandate's amount, then `create_order` | Policy layer says `ALLOW` — the independent mandate check blocks it anyway |

The third one is the centerpiece: two independent layers, either of which alone stops the attack. A standalone, rerunnable version also lives at `scripts/demo_tampered_mandate.py`.

## What We Explicitly Do Not Claim

- **Not AP2-conformant.** We sign one server-side payload per transaction; real AP2 chains three W3C Verifiable-Credential mandates signed by the user's own wallet.
- **No x402.** It's a stablecoin/crypto micropayment rail — doesn't fit an INR/Razorpay context, so we didn't bolt it on for coverage.
- **No UCP implementation.** We researched Google/Shopify's Universal Commerce Protocol in depth and deliberately skipped even its lightweight discovery profile — our MCP server only runs over local stdio, and publishing a discovery document pointing at a non-network-reachable service would itself be a false claim.
- **No nonce-based replay ledger.** The signed nonce exists for structural fidelity to the AP2 pattern; replay is actually prevented via the database's strict one-to-one `Order`↔`PurchaseIntent` relationship.

## Known Limitations

- MCP server is stdio-only, not publicly network-reachable.
- Single hardcoded merchant, six-SKU catalog, no multi-merchant support.
- No fulfillment/shipping concept — `Order` status stops at `PAID`/`FAILED`.
- The Razorpay-invocation counter used in the live security demo is disclosed, process-local, in-memory instrumentation — resets on restart, not a production metric.
- A narrow, documented distributed-transaction gap: a crash between Razorpay confirming an order and that ID being saved locally could theoretically orphan a provider-side order. Judged, based on testing, as not warranting full outbox/reconciliation infrastructure for this proof of concept.
- Automated tests run against SQLite; local development runs against PostgreSQL — deliberate (the concurrency fix uses a uniqueness constraint portable to both, not a Postgres-only lock), not an oversight.

## Tech Stack

Python · Django · PostgreSQL (dev) / SQLite (tests) · Redis · [Model Context Protocol](https://modelcontextprotocol.io) (real server *and* real client) · Ed25519 (`cryptography`) · Razorpay Test Mode · Google Gemini (`gemini-3.5-flash`, free tier) · Bootstrap/MDBootstrap (MIT-licensed template) · `schema.org` · pytest (125+ tests, including real multithreaded concurrency tests)

## Running It Locally

```bash
# Backend
cd backend
python manage.py migrate
python manage.py seed_tools
python manage.py seed_products
python manage.py generate_mandate_keys   # copy printed keys into .env
python manage.py seed_demo_agent         # copy printed token into .env
python manage.py runserver

# AI buyer agent (separate terminal)
python agent/buyer.py "Find me the best laptop under 60000 rupees with at least 16GB RAM"
```

Requires a `.env` at the repo root with `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `GEMINI_API_KEY`, `MANDATE_PRIVATE_KEY`, `MANDATE_PUBLIC_KEY`, `DEMO_AGENT_TOKEN` (all generated/printed by the commands above).

## Test Suite

```bash
cd backend
pytest
```

125+ tests: the core policy engine, adversarial/security tests (unknown parameters, prompt-injection resistance, confused-deputy protection, real MCP-protocol integration), purchase-mandate signing/tampering/wrong-intent tests, audit-linkage correctness, all three live failure scenarios, and hardening tests including a genuine two-thread concurrency race proven against a real database.

## Repository History

This repository was created by cloning our pre-existing [`agent-action-firewall`](https://github.com/AjayBandiwaddar/ai-firewall) project with its **full, real, dated commit history intact** — not copied and re-committed to fabricate the appearance of hackathon-period work. A single marker commit, `--- Buildathon work begins here (Track 1: AI Growth & Agentic Commerce) ---`, separates pre-existing work from buildathon work in the log itself. Three annotated tags mark each system's completion: `system-1-firewall`, `system-2-merchant`, `system-3-buyer-agent`.

## Credits

Storefront template adapted from [MDBootstrap's free Ecommerce Template](https://github.com/mdbootstrap/Ecommerce-Template-Bootstrap) (MIT licensed). Built by [Ajay Bandiwaddar](https://github.com/AjayBandiwaddar).