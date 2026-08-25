from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.agents.models import Agent, AgentStatus
from apps.tasks.models import Task, TaskStatus
from apps.policies.models import Policy, PolicyEffect, ResourceScopeMode
from apps.tools.models import Tool


class Command(BaseCommand):
    help = "Create/refresh the fixed demo buyer agent+task used by the storefront's 'Buy with AI Agent' button."

    def handle(self, *args, **options):
        agent, _ = Agent.objects.get_or_create(
            agent_id="demo-buyer-agent",
            defaults={"name": "Demo Buyer Agent", "status": AgentStatus.ACTIVE},
        )
        raw_token = agent.issue_token()

        task, _ = Task.objects.update_or_create(
            task_id="demo-buyer-task",
            defaults={
                "agent": agent,
                "user_id": "demo-user",
                "status": TaskStatus.ACTIVE,
                "expires_at": timezone.now() + timedelta(days=30),
            },
        )

        Policy.objects.get_or_create(
            policy_id=f"policy-{task.task_id}-propose-intent",
            defaults={
                "name": "Standing: propose purchase intent (demo agent)",
                "effect": PolicyEffect.ALLOW,
                "agent_scope": agent,
                "task_scope": task,
                "tool_scope": Tool.objects.get(tool_id="propose_purchase_intent"),
                "allowed_actions": ["propose_purchase_intent"],
                "resource_mode": ResourceScopeMode.NONE,
            },
        )

        self.stdout.write(self.style.SUCCESS("Demo agent/task ready."))
        self.stdout.write(self.style.WARNING(f"DEMO_AGENT_TOKEN={raw_token}"))
        self.stdout.write("Copy that line into your .env file (repo root), replacing any previous value.")