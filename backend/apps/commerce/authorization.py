from __future__ import annotations
from django.db import transaction
from apps.commerce.models import PurchaseIntent, PurchaseIntentStatus
from apps.policies.models import Policy, PolicyEffect, ResourceScopeMode
from apps.tools.models import Tool

# finalize_payment isn't built yet (see the Checkout-based redesign) - only
# create_order exists as a real Tool right now. Add "finalize_payment" here
# once that tool is seeded.
GATED_PURCHASE_TOOLS = ("create_order", "finalize_payment")


def confirm_purchase_intent(intent_id: str) -> list[Policy]:
    """
    Called only after the user has explicitly confirmed the purchase -
    never the agent, never automatic. Writes the actual authorization
    boundary for this purchase: one Policy per gated tool
    (create_order, initiate_payment), each scoped EXACT to this
    PurchaseIntent's id, each capping amount at the intent's
    server-computed canonical_amount_minor. Two policies, not one,
    because Policy.tool_scope is a single foreign key - one row can't
    cover two different tools even though both represent the same
    authorization decision. initiate_payment re-checking its own policy
    later (rather than trusting create_order's success) is what gives
    you replay protection at the payment step for free.
    """
    intent = PurchaseIntent.objects.select_related("task", "task__agent").get(intent_id=intent_id)
    if intent.status != PurchaseIntentStatus.PENDING:
        raise ValueError(f"Cannot confirm a purchase intent in status {intent.status}.")

    tool_constraints: dict[str, dict] = {
        "create_order": {
            "amount": {"operator": "LTE", "value": intent.canonical_amount_minor},
            "currency": {"operator": "EQ", "value": intent.currency},
        },
        # No amount/currency constraint here - the amount was already
        # locked in at create_order. This step only verifies a payment
        # signature for this exact, already-scoped purchase intent.
        "finalize_payment": {},
    }
    with transaction.atomic():
        policies = []
        for tool_id in GATED_PURCHASE_TOOLS:
            tool = Tool.objects.get(tool_id=tool_id)
            policies.append(
                Policy.objects.create(
                    policy_id=f"policy-{intent.intent_id}-{tool_id}",
                    name=f"Confirmed purchase: {intent.intent_id} ({tool_id})",
                    effect=PolicyEffect.ALLOW,
                    agent_scope=intent.task.agent,
                    task_scope=intent.task,
                    tool_scope=tool,
                    allowed_actions=[tool_id],
                    resource_type="purchase_intent",
                    resource_mode=ResourceScopeMode.EXACT,
                    resource_ids=[intent.intent_id],
                    constraints=tool_constraints[tool_id],
                )
            )
        intent.status = PurchaseIntentStatus.AUTHORIZED
        intent.save(update_fields=["status", "updated_at"])
    return policies