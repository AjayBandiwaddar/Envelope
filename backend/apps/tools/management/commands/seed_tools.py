"""
Registers the six default mock tools from apps.tools.handlers.DEFAULT_TOOLS.
Idempotent and self-healing - safe to run multiple times. Existing
Tool rows are refreshed to match DEFAULT_TOOLS on every run (update_or_create),
so a stale input_schema left over from an old code version can never
silently persist after a fresh seed.

Usage: python manage.py seed_tools
"""

from django.core.management.base import BaseCommand

from apps.tools.handlers import DEFAULT_TOOLS
from apps.tools.models import Tool


class Command(BaseCommand):
    help = "Register the six default mock tools (get_order, refund_order, cancel_order, get_customer, send_email, delete_customer)."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        for entry in DEFAULT_TOOLS:
            defaults = {
                "name": entry["name"],
                "service": entry["service"],
                "risk_level": entry["risk_level"],
                "input_schema": entry.get("input_schema", {}),
            }
            tool, created = Tool.objects.update_or_create(
                tool_id=entry["tool_id"],
                defaults=defaults,
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created tool: {entry['tool_id']}"))
            else:
                updated_count += 1
                self.stdout.write(f"Tool already exists, refreshed to match DEFAULT_TOOLS: {entry['tool_id']}")
        self.stdout.write(self.style.SUCCESS(
            f"Done. {created_count} new tool(s) created, {updated_count} existing tool(s) refreshed."
        ))