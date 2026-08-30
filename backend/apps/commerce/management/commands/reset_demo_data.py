from django.core.management.base import BaseCommand
from django.db import transaction
from apps.commerce.models import (
    PurchaseIntent, Order, PurchaseMandate, SpendingEnvelope,
    EnvelopeDebit, EnvelopeStatus,
)
from apps.policies.models import Policy
from apps.audit.models import AuditEvent

DEMO_TASK_ID = "demo-buyer-task"


class Command(BaseCommand):
    help = (
        "Wipe per-purchase demo state (intents, orders, mandates, "
        "envelope debits, per-intent policies) back to a clean slate "
        "before a rehearsal or recording take. Leaves the demo agent, "
        "task, standing propose/list-products policies, catalog, and "
        "merchants untouched - only the per-run purchase history and "
        "one-off gated policies are removed. Envelope balances are "
        "reset to their max_amount_minor, ACTIVE, rather than deleted, "
        "so the same envelope_id stays usable across takes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--task-id", default=DEMO_TASK_ID,
            help=f"Which task's purchase history to wipe (default: {DEMO_TASK_ID}).",
        )
        parser.add_argument(
            "--include-audit", action="store_true",
            help="Also delete AuditEvent rows for this task. Off by "
                 "default - the audit trail is often part of what you "
                 "want to demo, so don't wipe it unless you specifically "
                 "want a fully empty audit page for this take.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print what would be deleted/reset without changing anything.",
        )

    def handle(self, *args, **options):
        task_id = options["task_id"]
        dry_run = options["dry_run"]
        include_audit = options["include_audit"]

        intents = PurchaseIntent.objects.filter(task__task_id=task_id)
        intent_ids = list(intents.values_list("intent_id", flat=True))

        mandate_count = PurchaseMandate.objects.filter(intent__in=intents).count()
        debit_count = EnvelopeDebit.objects.filter(intent__in=intents).count()
        order_count = Order.objects.filter(purchase_intent__in=intents).count()
        intent_count = intents.count()
        policy_qs = Policy.objects.filter(
            task_scope__task_id=task_id,
            tool_scope__tool_id__in=["create_order", "finalize_payment"],
        )
        policy_count = policy_qs.count()
        envelopes = SpendingEnvelope.objects.filter(agent__agent_id="demo-buyer-agent")
        audit_qs = AuditEvent.objects.filter(task_id=task_id) if include_audit else AuditEvent.objects.none()
        audit_count = audit_qs.count()

        self.stdout.write(f"Task: {task_id}")
        self.stdout.write(f"  PurchaseMandate to delete: {mandate_count}")
        self.stdout.write(f"  EnvelopeDebit to delete:   {debit_count}")
        self.stdout.write(f"  Order to delete:           {order_count}")
        self.stdout.write(f"  PurchaseIntent to delete:  {intent_count}")
        self.stdout.write(f"  Gated Policy to delete:    {policy_count}")
        self.stdout.write(f"  SpendingEnvelope to reset: {envelopes.count()}")
        if include_audit:
            self.stdout.write(f"  AuditEvent to delete:      {audit_count}")
        else:
            self.stdout.write("  AuditEvent: left untouched (pass --include-audit to wipe)")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run - nothing changed."))
            return

        with transaction.atomic():
            PurchaseMandate.objects.filter(intent__in=intents).delete()
            EnvelopeDebit.objects.filter(intent__in=intents).delete()
            Order.objects.filter(purchase_intent__in=intents).delete()
            policy_qs.delete()
            intents.delete()
            if include_audit:
                audit_qs.delete()
            for envelope in envelopes:
                envelope.remaining_amount_minor = envelope.max_amount_minor
                envelope.status = EnvelopeStatus.ACTIVE
                envelope.save(update_fields=["remaining_amount_minor", "status", "updated_at"])

        self.stdout.write(self.style.SUCCESS(
            f"Reset complete for task {task_id}: {intent_count} intents, "
            f"{order_count} orders, {mandate_count} mandates, {debit_count} "
            f"envelope debits, {policy_count} gated policies removed; "
            f"{envelopes.count()} envelope(s) restored to full balance."
        ))