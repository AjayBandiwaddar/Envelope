import pytest
from django.utils import timezone
from datetime import timedelta
from apps.agents.models import Agent, AgentStatus
from apps.tasks.models import Task, TaskStatus
from apps.tools.models import Tool
from apps.commerce.models import Product, PurchaseIntent, PurchaseIntentStatus
from apps.commerce.authorization import confirm_purchase_intent


@pytest.fixture
def create_order_tool(db):
    return Tool.objects.create(
        tool_id="create_order", name="Create Order",
        input_schema={"intent_id": {}},
    )


@pytest.fixture
def finalize_payment_tool(db):
    return Tool.objects.create(
        tool_id="finalize_payment", name="Finalize Payment",
        input_schema={"intent_id": {}, "razorpay_order_id": {}, "razorpay_payment_id": {}, "razorpay_signature": {}},
    )


@pytest.fixture
def mandate_test_product(db):
    return Product.objects.create(
        product_id="test-laptop", name="Test Laptop", category="laptops",
        price_minor=5799900, currency="INR",
    )


@pytest.fixture
def confirmed_purchase_intent(db, create_order_tool, finalize_payment_tool, mandate_test_product):
    agent = Agent.objects.create(agent_id="test-mandate-agent", name="Test Agent", status=AgentStatus.ACTIVE)
    task = Task.objects.create(
        task_id="test-mandate-task", agent=agent, user_id="test-user",
        status=TaskStatus.ACTIVE, expires_at=timezone.now() + timedelta(minutes=30),
    )
    intent = PurchaseIntent.objects.create(
        intent_id="test-mandate-intent", task=task, agent_id=agent.agent_id, user_id=task.user_id,
        product=mandate_test_product, quantity=1,
        canonical_amount_minor=mandate_test_product.price_minor, currency=mandate_test_product.currency,
        status=PurchaseIntentStatus.PENDING,
    )
    confirm_purchase_intent(intent.intent_id)
    intent.refresh_from_db()
    return intent
@pytest.fixture
def propose_intent_tool(db):
    return Tool.objects.get_or_create(
        tool_id="propose_purchase_intent",
        defaults={"name": "Propose Purchase Intent", "input_schema": {"task_id": {}, "product_id": {}, "quantity": {}}},
    )[0]


@pytest.fixture
def security_demo_tools(db, create_order_tool, finalize_payment_tool, propose_intent_tool):
    pass


@pytest.fixture
def agent_task_with_propose_policy(db, propose_intent_tool):
    from apps.policies.models import Policy, PolicyEffect, ResourceScopeMode

    agent = Agent.objects.create(agent_id="audit-link-agent", name="Audit Link Agent", status=AgentStatus.ACTIVE)
    raw_token = agent.issue_token()
    task = Task.objects.create(
        task_id="audit-link-task", agent=agent, user_id="audit-link-user",
        status=TaskStatus.ACTIVE, expires_at=timezone.now() + timedelta(minutes=30),
    )
    Policy.objects.create(
        policy_id="policy-audit-link-propose",
        name="Standing: propose purchase intent (audit link test)",
        effect=PolicyEffect.ALLOW,
        agent_scope=agent,
        task_scope=task,
        tool_scope=propose_intent_tool,
        allowed_actions=["propose_purchase_intent"],
        resource_mode=ResourceScopeMode.NONE,
    )
    return agent, task, raw_token