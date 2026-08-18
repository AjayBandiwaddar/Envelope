"""Serializers for the Audit API (API_SPEC.md Section 16-17). Read-only."""

from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    event_id = serializers.IntegerField(source="id", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "event_id", "timestamp", "request_id", "agent_id", "user_id", "task_id",
            "tool_id", "action", "resource_type", "resource_id", "decision",
            "reason_code", "reason", "policy_id", "latency_ms",
        ]
        read_only_fields = fields