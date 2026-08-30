from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta
import uuid
from apps.agents.models import Agent
from apps.commerce.models import Merchant, SpendingEnvelope, EnvelopeStatus


class Command(BaseCommand):
    help = (
        "Create a SpendingEnvelope (delegated spending authority) for an "
        "agent+merchant. Deliberately a management command, not an MCP "
        "tool or API endpoint the agent can reach - envelope creation is "
        "a human/operator action only."
    )

    def add_arguments(self, parser):
        parser.add_argument("--agent-id", required=True)
        parser.add_argument("--merchant-id", required=True)
        parser.add_argument("--max-amount-minor", type=int, required=True)
        parser.add_argument("--currency", default="INR")
        parser.add_argument("--expires-in-days", type=int, default=90,
                             help="Matches NPCI UPI Reserve Pay's real 90-day cap by default.")

    def handle(self, *args, **options):
        try:
            agent = Agent.objects.get(agent_id=options["agent_id"])
        except Agent.DoesNotExist:
            raise CommandError(f"No agent with agent_id={options['agent_id']!r}")
        try:
            merchant = Merchant.objects.get(merchant_id=options["merchant_id"])
        except Merchant.DoesNotExist:
            raise CommandError(f"No merchant with merchant_id={options['merchant_id']!r}")

        envelope = SpendingEnvelope.objects.create(
            envelope_id=f"envelope-{uuid.uuid4().hex[:12]}",
            agent=agent, merchant=merchant,
            max_amount_minor=options["max_amount_minor"],
            remaining_amount_minor=options["max_amount_minor"],
            currency=options["currency"],
            status=EnvelopeStatus.ACTIVE,
            expires_at=timezone.now() + timedelta(days=options["expires_in_days"]),
        )
        self.stdout.write(self.style.SUCCESS(
            f"Created envelope {envelope.envelope_id}: agent={agent.agent_id} "
            f"merchant={merchant.merchant_id} max={envelope.max_amount_minor} "
            f"{envelope.currency}, expires {envelope.expires_at.date()}"
        ))