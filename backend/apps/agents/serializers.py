"""Serializers for the Agents API (API_SPEC.md Section 7)."""

from django.utils.text import slugify
from rest_framework import serializers

from .models import Agent


class AgentCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def create(self, validated_data):
        agent_id = self._generate_agent_id(validated_data["name"])
        agent = Agent.objects.create(
            agent_id=agent_id,
            name=validated_data["name"],
            description=validated_data.get("description", ""),
        )
        return agent

    @staticmethod
    def _generate_agent_id(name: str) -> str:
        base = slugify(name) or "agent"
        candidate = base
        suffix = 1
        while Agent.objects.filter(agent_id=candidate).exists():
            suffix += 1
            candidate = f"{base}-{suffix:02d}"
        return candidate


class AgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agent
        fields = ["agent_id", "name", "description", "status", "created_at"]
        read_only_fields = fields