"""
Serializers for the Tasks API (API_SPEC.md Section 8).

API_SPEC.md Section 8.1's create-task example request does not show an
expires_at field, but the Task model requires one. Documented
assumption (per docs/SPEC_REVIEW.md and AGENTS.md's "document the
ambiguity" instruction): expires_at defaults to
settings.DEFAULT_TASK_DURATION_MINUTES from now, unless the caller
explicitly supplies one. Section 8.1's response also shows the task as
immediately "ACTIVE" on creation, not "PENDING" - so status defaults to
ACTIVE here rather than the model's own default.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from apps.agents.models import Agent

from .models import Task, TaskStatus


class TaskCreateSerializer(serializers.Serializer):
    agent_id = serializers.CharField()
    user_id = serializers.CharField(required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    expires_at = serializers.DateTimeField(required=False, allow_null=True, default=None)

    def validate_agent_id(self, value):
        if not Agent.objects.filter(agent_id=value).exists():
            raise serializers.ValidationError("Unknown agent_id.")
        return value

    def create(self, validated_data):
        agent = Agent.objects.get(agent_id=validated_data["agent_id"])
        expires_at = validated_data.get("expires_at") or (
            timezone.now() + timedelta(minutes=settings.DEFAULT_TASK_DURATION_MINUTES)
        )
        task_id = self._generate_task_id()
        return Task.objects.create(
            task_id=task_id,
            agent=agent,
            user_id=validated_data.get("user_id", ""),
            description=validated_data.get("description", ""),
            status=TaskStatus.ACTIVE,
            expires_at=expires_at,
        )

    @staticmethod
    def _generate_task_id() -> str:
        base = "task"
        suffix = 1
        candidate = f"{base}-{suffix:03d}"
        while Task.objects.filter(task_id=candidate).exists():
            suffix += 1
            candidate = f"{base}-{suffix:03d}"
        return candidate


class TaskSerializer(serializers.ModelSerializer):
    agent_id = serializers.CharField(source="agent.agent_id", read_only=True)

    class Meta:
        model = Task
        fields = [
            "task_id", "agent_id", "user_id", "description", "status",
            "created_at", "issued_at", "expires_at",
        ]
        read_only_fields = fields