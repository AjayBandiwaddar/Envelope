from django.contrib import admin

from .models import Tool


@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = ["tool_id", "name", "service", "risk_level", "status"]
    list_filter = ["status", "risk_level"]
    search_fields = ["tool_id", "name"]
