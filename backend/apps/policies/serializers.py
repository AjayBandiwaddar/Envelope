"""
Serializers for the Policies API (API_SPEC.md Section 9).

The create-policy request shape uses nested scope objects
(agent_scope.agent_id, task_scope.task_id, tool_scope.tool,
user_scope.user_id, resource_scope.{type,mode,ids}) per API_SPEC.md
Section 9.1's example. This serializer accepts that nested shape and
flattens it onto the Policy model's flat fields.
"""

from django.utils.text import slugify
from rest_framework import serializers

from apps.agents.models import Agent
from apps.tasks.models import Task
from apps.tools.models import Tool

from .models import Policy, PolicyEffect, ResourceScopeMode


class ResourceScopeInputSerializer(serializers.Serializer):
    type = serializers.CharField(required=False, allow_blank=True, default="")
    mode = serializers.ChoiceField(choices=["EXACT", "ANY", "NONE"], default="NONE")
    ids = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class ConstraintInputSerializer(serializers.Serializer):
    operator = serializers.ChoiceField(choices=["LTE", "GTE", "EQ", "IN", "BOOL_EQ"])
    value = serializers.JSONField()


class PolicyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    effect = serializers.ChoiceField(choices=["ALLOW", "DENY"], default="ALLOW")

    agent_scope = serializers.DictField()
    user_scope = serializers.DictField(required=False, default=dict)
    task_scope = serializers.DictField()
    tool_scope = serializers.DictField()

    allowed_actions = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    resource_scope = ResourceScopeInputSerializer(required=False)
    constraints = serializers.DictField(required=False, default=dict)
    priority = serializers.IntegerField(required=False, default=0)

    def validate_agent_scope(self, value):
        agent_id = value.get("agent_id")
        if not agent_id or not Agent.objects.filter(agent_id=agent_id).exists():
            raise serializers.ValidationError("agent_scope.agent_id must reference an existing agent.")
        return value

    def validate_task_scope(self, value):
        task_id = value.get("task_id")
        if not task_id or not Task.objects.filter(task_id=task_id).exists():
            raise serializers.ValidationError("task_scope.task_id must reference an existing task.")
        return value

    def validate_tool_scope(self, value):
        tool_id = value.get("tool")
        if not tool_id or not Tool.objects.filter(tool_id=tool_id).exists():
            raise serializers.ValidationError("tool_scope.tool must reference an existing tool.")
        return value

    def validate_constraints(self, value):
        for name, spec in value.items():
            constraint_serializer = ConstraintInputSerializer(data=spec)
            constraint_serializer.is_valid(raise_exception=True)
        return value

    def create(self, validated_data):
        agent = Agent.objects.get(agent_id=validated_data["agent_scope"]["agent_id"])
        task = Task.objects.get(task_id=validated_data["task_scope"]["task_id"])
        tool = Tool.objects.get(tool_id=validated_data["tool_scope"]["tool"])
        resource_scope = validated_data.get("resource_scope") or {}
        user_scope = validated_data.get("user_scope") or {}

        policy_id = self._generate_policy_id(validated_data["name"])

        return Policy.objects.create(
            policy_id=policy_id,
            name=validated_data["name"],
            description=validated_data.get("description", ""),
            effect=validated_data.get("effect", PolicyEffect.ALLOW),
            agent_scope=agent,
            user_scope=user_scope.get("user_id", ""),
            task_scope=task,
            tool_scope=tool,
            allowed_actions=validated_data["allowed_actions"],
            resource_type=resource_scope.get("type", ""),
            resource_mode=resource_scope.get("mode", ResourceScopeMode.NONE),
            resource_ids=resource_scope.get("ids", []),
            constraints=validated_data.get("constraints", {}),
            priority=validated_data.get("priority", 0),
        )

    @staticmethod
    def _generate_policy_id(name: str) -> str:
        base = slugify(name) or "policy"
        candidate = base
        suffix = 1
        while Policy.objects.filter(policy_id=candidate).exists():
            suffix += 1
            candidate = f"{base}-{suffix:02d}"
        return candidate


class PolicySerializer(serializers.ModelSerializer):
    agent_id = serializers.CharField(source="agent_scope.agent_id", read_only=True)
    task_id = serializers.CharField(source="task_scope.task_id", read_only=True)
    tool_id = serializers.CharField(source="tool_scope.tool_id", read_only=True)

    class Meta:
        model = Policy
        fields = [
            "policy_id", "name", "description", "status", "effect",
            "agent_id", "task_id", "tool_id", "allowed_actions",
            "resource_type", "resource_mode", "resource_ids", "constraints",
            "priority",
        ]
        read_only_fields = fields