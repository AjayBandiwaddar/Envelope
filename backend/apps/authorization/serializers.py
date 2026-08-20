"""Request/response serializers for POST /api/authorize/ (API_SPEC.md Section 10)."""

from rest_framework import serializers


class ResourceSerializer(serializers.Serializer):
    type = serializers.CharField(required=False, allow_blank=True, default="")
    id = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)


class AuthorizeRequestSerializer(serializers.Serializer):
    """
    Per API_SPEC.md Section 11: agent_id, task_id, tool, and action are
    required. `agent_id` is accepted in the body (matching the documented
    request shape) but is NEVER trusted as identity - the view validates
    it against the authenticated caller before use (API_SPEC.md Section
    26 / docs/SPEC_REVIEW.md Section 3.1).
    """

    agent_id = serializers.CharField()
    user_id = serializers.CharField(required=False, allow_blank=True, default="")
    task_id = serializers.CharField()
    tool = serializers.CharField()
    action = serializers.CharField()
    resource = ResourceSerializer(required=False)
    parameters = serializers.DictField(required=False, default=dict)