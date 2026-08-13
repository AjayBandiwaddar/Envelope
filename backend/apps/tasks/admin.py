from django.contrib import admin

from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["task_id", "agent", "user_id", "status", "expires_at"]
    list_filter = ["status"]
    search_fields = ["task_id", "agent__agent_id", "user_id"]
    readonly_fields = ["issued_at", "created_at", "updated_at"]
