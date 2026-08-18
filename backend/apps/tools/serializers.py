"""Serializers for the Tools API (API_SPEC.md Section 13)."""

from rest_framework import serializers

from .models import Tool


class ToolCreateSerializer(serializers.Serializer):
    tool_id = serializers.SlugField(max_length=100)
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    service = serializers.CharField(required=False, allow_blank=True, default="")
    risk_level = serializers.ChoiceField(choices=["LOW", "MEDIUM", "HIGH"], default="LOW")
    input_schema = serializers.DictField(required=False, default=dict)

    def validate_tool_id(self, value):
        if Tool.objects.filter(tool_id=value).exists():
            raise serializers.ValidationError("A tool with this tool_id already exists.")
        return value

    def create(self, validated_data):
        return Tool.objects.create(**validated_data)


class ToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tool
        fields = ["tool_id", "name", "description", "service", "risk_level", "input_schema", "status"]
        read_only_fields = fields