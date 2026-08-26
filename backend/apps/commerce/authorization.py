from __future__ import annotations
from django.db import transaction
from apps.commerce.models import PurchaseIntent, PurchaseIntentStatus
from apps.policies.models import Policy, PolicyEffect, ResourceScopeMode
from apps.tools.models import Tool

GATED_PURCHASE_TOOLS = ("create_order", "finalize_payment")


def confirm_purchase_intent(intent_id: str) -> list[Policy]:
    """
    Called only after the user has explicitly confirmed the purchase -
    never the agent, never automatic. Writes the actual authorization
    boundary for this purchase: one Policy per gated tool (create_order,
    finalize_payment), each scoped EXACT to this PurchaseIntent's id.
    Two policies, not one, because Policy.tool_scope is a single foreign
    key - one row can't cover two different tools even though both
    represent the same authorization decision. Neither policy needs an
    amount/currency constraint: neither tool accepts those as
    parameters, so the EXACT resource_scope binding to one already-priced
    intent_id is what actually enforces the ceiling. finalize_payment
    re-checking its own policy (rather than trusting create_order's
    success) is what gives you replay protection at the payment step
    for free.
    """
    intent = PurchaseIntent.objects.select_related("task", "task__agent").get(intent_id=intent_id)
    if intent.status != PurchaseIntentStatus.PENDING:
        raise ValueError(f"Cannot confirm a purchase intent in status {intent.status}.")

    # Neither tool accepts amount/currency as a parameter anymore (Option
    # A: create_order derives them entirely from the confirmed intent, and
    # finalize_payment never took them). No constraint dict is needed for
    # either - the real ceiling is the EXACT resource_scope below, which
    # only ever matches this one already-priced intent_id. There is no
    # amount parameter left for a tampered value to travel through.
    tool_constraints: dict[str, dict] = {
        "create_order": {},
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