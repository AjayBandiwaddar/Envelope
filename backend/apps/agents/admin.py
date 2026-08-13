from django.contrib import admin

from .models import Agent


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ["agent_id", "name", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["agent_id", "name"]
    readonly_fields = ["token_hash", "created_at", "updated_at"]
