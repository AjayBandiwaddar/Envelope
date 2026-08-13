from django.contrib import admin

from .models import Policy


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ["policy_id", "effect", "status", "agent_scope", "task_scope", "tool_scope"]
    list_filter = ["status", "effect"]
    search_fields = ["policy_id", "name"]
