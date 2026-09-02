# Reference Merchant — Agentic Commerce with Cryptographic, Bounded Authorization

**Razorpay AI Buildathon 2026 — Track 1: AI Growth & Agentic Commerce**

> AI decides what it wants to buy. The merchant determines what is actually true and available. The authorization system determines what the agent is allowed to do. Razorpay determines the payment outcome. The system records the proof.

A live, working demonstration of an AI buyer agent purchasing real goods through a real Razorpay test-mode integration — with every action explainable, bounded, and gated, and every decision independently auditable.


![Architecture diagram](architecture.svg)

---

## Table of Contents

- [Problem & Interpretation](#problem--interpretation)
- [System Overview](#system-overview)
- [Purchase Flow](#purchase-flow)
- [Delegated Authorization: SpendingEnvelope](#delegated-authorization-spendingenvelope)
- [Security Guarantees](#security-guarantees)
- [Live Interfaces](#live-interfaces)
- [What We Don't Claim](#what-we-dont-claim)
- [Known Limitations](#known-limitations)
- [Tech Stack](#tech-stack)
- [Running It Locally](#running-it-locally)
- [Test Suite](#test-suite)
- [Repository History](#repository-history)
- [Credits](#credits)

---

## Problem & Interpretation

Track 1 asks for AI Growth & Agentic Commerce, with a stated bar: *"every money action explainable, bounded and gated. Show the audit trail and one failure handled gracefully."*

We chose to build **a merchant transactable by an AI buyer, end-to-end** — rather than a merchant-growth agent — because the harder and more track-relevant problem is proving an autonomous agent can be trusted with real payment authority at all, not just that it can recommend products.

## System Overview

| System | What it is |
|---|---|
| **1. Agent Action Firewall** | A deterministic, pre-existing ALLOW/DENY policy engine, extended with a cryptographic Purchase Mandate and a delegated-authority SpendingEnvelope layer |
| **2. Reference Merchant** | A real storefront with schema.org machine-readable product data and MCP tools for catalog discovery |
| **3. AI Buyer Agent** | A real Gemini-powered agent using a real MCP client, with a hard, non-bypassable human-confirmation gate and automated payment handoff |

## Purchase Flow

```
Search catalog (MCP: list_products)
  → Propose purchase intent (server-derived canonical price, never agent-supplied)
  → Product-fit confirmation (human may reject and force a new search)
  → Authorization (see below — envelope auto-confirm, or manual gate)
  → Cryptographic Purchase Mandate signed (Ed25519)
  → create_order (real Razorpay test-mode order)
  → Checkout (human payment — Razorpay requires this; not automatable even in test mode)
  → finalize_payment (verifies Razorpay signature, idempotent)
  → Live audit trail (re-verifies the mandate on every page load)
```

## Delegated Authorization: SpendingEnvelope

Modeled on NPCI's real **UPI Reserve Pay** / Single Block Multiple Debits policy (block funds once, up to ₹10,000, valid 90 days, one block per merchant — real published rules). Our version is additive to, never a replacement for, the manual confirmation gate:

- **Scope:** one envelope per agent + merchant (a real `Merchant` foreign-key relationship — not a hardcoded string — proven with a cross-merchant denial test).
- **Auto-confirm:** if an active, unexpired envelope has enough remaining balance for a proposed purchase, the system authorizes it automatically — no human click. If not, it falls back cleanly to the existing manual gate, with an explicit reason (no coverage vs. exhausted balance).
- **Concurrency safety:** the balance check-and-decrement is a single atomic conditional `UPDATE` (`WHERE remaining_amount_minor >= amount`), not a Python read-then-write — the same class of fix as `create_order`'s own concurrency hardening. Proven with a real multithreaded test (two real OS threads racing for a balance that can only cover one).
- **Hold → capture → release lifecycle:** auto-confirming a purchase places a `HELD` debit against the envelope. A successful payment **captures** the hold (permanent, no balance change). A failed payment (signature verification failure) **releases** it, atomically crediting the balance back — idempotent, so a double-release can never over-credit. This closes a real gap we found ourselves during testing: without it, an abandoned or failed checkout after auto-confirmation would permanently consume envelope balance for a purchase that never completed.
- **Structurally unreachable by the agent:** creating, extending, or revoking an envelope is never an MCP tool — verified by a test asserting no envelope-related tool exists in the registry, and that the firewall would deny it even if one were added without a matching policy.
- **Novelty over the real UPI Reserve Pay:** NPCI's block is centrally trusted and opaque; ours is independently, cryptographically verifiable via the same mandate pattern used for individual purchases.

## Security Guarantees

Live at [`/security-demo/`](http://127.0.0.1:8000/security-demo/) — four real attacks run through the actual authorization dispatch path, a fresh disposable agent/task/purchase created per run, nothing scripted:

1. **Skip Confirmation** — attempt `create_order` with no human confirmation → `DENY` / `POLICY_NOT_FOUND`.
2. **Unknown Parameter** — inject an undeclared parameter → `DENY` / `UNKNOWN_PARAMETER`.
3. **Tampered Mandate** — confirm normally, then edit the stored mandate payload directly in the database → Policy layer still says `ALLOW` (its scope genuinely matches), but the independent cryptographic mandate check inside `create_order` blocks it anyway → `MANDATE_VERIFICATION_FAILED`. Two independent layers; either one stops the attack.
4. **Tampered Amount Parameter** — attempt `create_order` with a forged `amount`/`currency` smuggled into the call → `DENY` / `UNKNOWN_PARAMETER`, proving the historical fix (amount is now server-derived only, never agent-supplied) is closed at the firewall layer, not just the handler layer.

Every scenario reports a **real, counted Razorpay invocation total** — proven zero on every denial, not inferred from an empty database.

Also live: [`/concurrency-demo/`](http://127.0.0.1:8000/concurrency-demo/) — fires three real concurrent purchase attempts against one envelope with balance for exactly one, live in the browser, and shows the database's atomic guarantee resolve the race in real time.

## Live Interfaces

| URL | What it shows |
|---|---|
| `/` | Storefront catalog |
| `/agent-console/` | **Type a prompt, watch the full agent pipeline run live** — search, propose, product-fit check, authorization (auto or manual), order, checkout, and audit — as a real-time staged pipeline, not a chat log |
| `/security-demo/` | Four live attacks against the real authorization path |
| `/concurrency-demo/` | The envelope's atomic concurrency guarantee, proven live |
| `/checkout/<order_id>/` | Real Razorpay test-mode checkout |
| `/checkout/<intent_id>/audit/` | Live decision timeline + live mandate re-verification |

## What We Don't Claim

- **Not full AP2 conformance.** The cryptographic mandate is a simplified, single-keypair Ed25519 analogue of AP2's Cart Mandate pattern — not the full W3C Verifiable Credential chain.
- **Not UCP.** Researched in depth (real spec, Jan 2026, Google+Shopify+retailers standard); deliberately not implemented, because our MCP server is stdio-only with no public network endpoint — declaring any transport in a UCP discovery profile would itself be a false claim.
- **Not "better than Razorpay's own Reserve Pay."** We don't know their production system's internals. The honest, specific claim: our authorization artifact is independently, cryptographically verifiable, rather than resting on a centrally-trusted bank ledger entry.
- **No tokenized/recurring payment instruments.** SpendingEnvelope pre-authorizes spending amount and scope, not a specific payment instrument — every purchase still requires a real human checkout interaction, because that's a genuine Razorpay/regulatory boundary, not an oversight.

## Known Limitations

- **Distributed-transaction gap (accepted, not fixed):** if the process crashes between Razorpay confirming an order and the local `razorpay_order_id` being saved, an orphaned Razorpay-side order could exist with no local record. No outbox/reconciliation system built — judged unnecessary for this POC.
- **Envelope hold release is not universal:** a successful payment captures the hold; a signature-verification failure releases it. Other `finalize_payment` error branches (e.g. `ORDER_NOT_FOUND`, `MANDATE_VERIFICATION_FAILED` at finalize time) do not currently release the hold, nor does a checkout silently abandoned with no callback at all. This mirrors `create_order`'s own accepted orphan-order gap in shape and severity.
- **No public mandate-verification endpoint** — deliberately deprioritized.
- **No growth-agent feature** was built as a separate artifact for Track 1's other allowed interpretation; the buyer's product-fit reasoning is the closest analogue.

## Tech Stack

- **Backend:** Django 5.2, SQLite (dev), pytest
- **Cryptography:** Ed25519 via the Python `cryptography` library
- **AI:** Google Gemini (`gemini-3.6-flash`) via Google AI Studio free tier, `google-genai` SDK with native MCP tool support
- **Payments:** Razorpay test-mode API
- **Frontend:** MDBootstrap storefront template (MIT licensed), vanilla JS for the Agent Console / Concurrency Demo pipelines (no framework — deliberately dependency-light for a hackathon timeline)

## Running It Locally

```bash
# 1. Clone and set up the virtual environment
git clone https://github.com/AjayBandiwaddar/razorpaybuildathon.git
cd razorpaybuildathon
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux
pip install -r backend/requirements.txt

# 2. Configure environment
# Copy .env.example to .env and fill in:
#   GEMINI_API_KEY, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, MANDATE_KEY_ID

cd backend
python manage.py generate_mandate_keys     # writes MANDATE_PRIVATE_KEY/PUBLIC_KEY/KEY_ID to .env
python manage.py migrate

# 3. Seed reference data
python manage.py seed_tools                # registers MCP tool definitions (self-healing — safe to rerun anytime)
python manage.py seed_products             # seeds the reference merchant + 6-product catalog
python manage.py seed_demo_agent           # creates the demo buyer agent + task
#   ⚠ This prints a fresh DEMO_AGENT_TOKEN every run — copy it into .env each time you rerun it.

# 4. Create a SpendingEnvelope for the demo agent (optional — manual confirmation works without one)
python manage.py create_envelope --agent-id demo-buyer-agent --merchant-id reference-merchant --max-amount-minor 6000000

# 5. Run the server
python manage.py runserver --noreload
#   ⚠ --noreload matters for /agent-console/ and /concurrency-demo/, which hold
#     in-memory run state that would split across two processes under the
#     autoreloader.

# 6. Try it
#   Storefront:         http://127.0.0.1:8000/
#   Agent Console:       http://127.0.0.1:8000/agent-console/
#   Security Demo:       http://127.0.0.1:8000/security-demo/
#   Concurrency Demo:    http://127.0.0.1:8000/concurrency-demo/

# Or drive the original CLI buyer agent directly:
cd ..
python agent/buyer.py "find me the best laptop under 60000 rupees with at least 16gb ram"
```

**Resetting demo state between takes/runs:**
```bash
python manage.py reset_demo_data --include-audit
```
Clears per-run purchase history (intents, orders, mandates, envelope debits, gated policies) and restores envelope balances to full — leaves the catalog, merchants, agents, and standing policies untouched.

**Free-tier Gemini rate limits:** the buyer agent spaces Gemini calls ~15s apart by default (`GEMINI_CALL_SPACING_SECONDS` in `.env`) to stay under the free tier's 5 requests/minute cap. Lower it if you've enabled billing.

## Test Suite

144 tests, all passing, run via `pytest` from `backend/`. Coverage includes:

- Full commerce flow (propose → confirm → order → payment) happy path and every documented denial path
- **Real concurrency tests** using `threading.Barrier` + real OS threads + `transaction=True` — for both `create_order` (proving exactly one of two simultaneous requests creates an order and calls the provider) and `SpendingEnvelope` (proving a balance covering only one of two simultaneous purchases is never overdrawn)
- Cross-merchant envelope denial (real second `Merchant` seeded only in tests)
- Envelope hold/capture/release lifecycle, including idempotent release and rejected double-capture
- Handler exception-safety (no internal error text leaks to the caller), quantity validation (explicitly excluding `bool`, a Python `int` subclass), and `finalize_payment` idempotency
- The three original security-demo scenarios plus the tampered-amount-parameter scenario, each asserting zero real provider calls on denial

## Repository History

This repository was created by cloning a pre-existing, independent project of mine (`agent-action-firewall`) with its **full real commit history intact** — not a fresh copy with fabricated history. A marker commit, `--- Buildathon work begins here (Track 1: AI Growth & Agentic Commerce) ---`, separates pre-existing work from buildathon work in the log. Annotated tags mark major milestones: `system-1-firewall`, `system-2-merchant`, `system-3-buyer-agent`.

We disclose this openly as a strength, not a limitation: it let buildathon time go entirely into the new, hard parts — cryptographic mandates, delegated authorization, and the live demo surfaces — rather than re-building tested infrastructure from scratch.

## Credits

- Storefront template: [MDBootstrap Ecommerce Template](https://github.com/mdbootstrap/Ecommerce-Template-Bootstrap) (MIT licensed)
- Payments: [Razorpay](https://razorpay.com) test-mode API
- AI: [Google Gemini](https://ai.google.dev) via Google AI Studio

## License

MIT — see [LICENSE](LICENSE).

---

*Built solo (Ajay + Claude as technical co-architect) for the Razorpay AI Buildathon 2026.*