"""
Registers the six default mock tools from apps.tools.handlers.DEFAULT_TOOLS.
Idempotent - safe to run multiple times (get_or_create).

Usage: python manage.py seed_tools
"""

from django.core.management.base import BaseCommand

from apps.tools.handlers import DEFAULT_TOOLS
from apps.tools.models import Tool


class Command(BaseCommand):
    help = "Register the six default mock tools (get_order, refund_order, cancel_order, get_customer, send_email, delete_customer)."

    def handle(self, *args, **options):
        created_count = 0
        for entry in DEFAULT_TOOLS:
            _, created = Tool.objects.get_or_create(
                tool_id=entry["tool_id"],
                defaults={
                    "name": entry["name"],
                    "service": entry["service"],
                    "risk_level": entry["risk_level"],
                },
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created tool: {entry['tool_id']}"))
            else:
                self.stdout.write(f"Tool already exists: {entry['tool_id']}")

        self.stdout.write(self.style.SUCCESS(f"Done. {created_count} new tool(s) created."))