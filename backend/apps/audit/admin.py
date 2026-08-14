from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = [
        "timestamp", "decision", "reason_code", "agent_id", "task_id", "action",
    ]
    list_filter = ["decision", "reason_code"]
    search_fields = ["request_id", "agent_id", "task_id", "policy_id"]
    readonly_fields = [f.name for f in AuditEvent._meta.fields]

    def has_change_permission(self, request, obj=None):
        # Audit records should not be editable through the admin - they
        # exist to explain what happened, not to be revised afterward.
        return False
