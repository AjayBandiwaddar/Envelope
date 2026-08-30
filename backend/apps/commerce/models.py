from django.db import models


class Merchant(models.Model):
    """
    A registered commerce counterparty. Deliberately minimal - this
    exists so 'per-merchant' authorization scopes (SpendingEnvelope) are
    a real foreign-key relationship, not a hardcoded string constant.
    The reference storefront has exactly one Merchant row in normal
    operation; a second is seeded only in tests, to prove cross-merchant
    envelope denial is a real, checked invariant.
    """
    merchant_id = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["merchant_id"]

    def __str__(self) -> str:
        return self.merchant_id


class Product(models.Model):
    product_id = models.SlugField(max_length=100, unique=True)
    merchant = models.ForeignKey(
        Merchant, on_delete=models.PROTECT, related_name="products",
        help_text="Which merchant this product belongs to. Nullable only until migration 0006 makes it required, after 0005 backfills existing rows.",
    )
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True, default="")
    description = models.TextField(blank=True, default="")
    price_minor = models.PositiveIntegerField(
        help_text="Price in minor units. Never trust an agent-supplied price - this is the canonical value."
    )
    currency = models.CharField(max_length=3, default="INR")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product_id"]

    def __str__(self) -> str:
        return self.product_id


class PurchaseIntentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    AUTHORIZED = "AUTHORIZED", "Authorized"
    DENIED = "DENIED", "Denied"
    COMPLETED = "COMPLETED", "Completed"
    ABANDONED = "ABANDONED", "Abandoned"


class PurchaseIntent(models.Model):
    """
    Cheap, ungated bookkeeping: "the agent wants to buy X." No money
    moves and no inventory is touched here - this exists purely so a
    Policy has something real to be scoped to (resource_type
    'purchase_intent') before an Order is ever created.
    """
    intent_id = models.SlugField(max_length=100, unique=True)
    task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, related_name="purchase_intents")
    agent_id = models.CharField(max_length=100)
    user_id = models.CharField(max_length=100, blank=True, default="")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="purchase_intents")
    quantity = models.PositiveIntegerField(default=1)
    canonical_amount_minor = models.PositiveIntegerField(
        help_text="quantity * Product.price_minor at proposal time, computed server-side."
    )
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20, choices=PurchaseIntentStatus.choices, default=PurchaseIntentStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["task", "status"])]

    def __str__(self) -> str:
        return self.intent_id


class OrderStatus(models.TextChoices):
    CREATED = "CREATED", "Created"
    PAID = "PAID", "Paid"
    FAILED = "FAILED", "Failed"
    DENIED = "DENIED", "Denied"
    ABANDONED = "ABANDONED", "Abandoned"


class Order(models.Model):
    """
    The authoritative transaction record. Deliberately has no ungated
    creation path - an Order only exists as the direct effect of a
    successful authorization on the create_order action, scoped to one
    PurchaseIntent. There is no separate "reserve inventory" step that
    happens before that check.
    """
    order_id = models.SlugField(max_length=100, unique=True)
    purchase_intent = models.OneToOneField(PurchaseIntent, on_delete=models.PROTECT, related_name="order")
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.CREATED)
    amount_minor = models.PositiveIntegerField()
    currency = models.CharField(max_length=3)
    razorpay_order_id = models.CharField(max_length=100, blank=True, default="")
    razorpay_payment_id = models.CharField(max_length=100, blank=True, default="")
    pending_signature = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.order_id


class PurchaseMandate(models.Model):
    """
    A cryptographically signed, tamper-evident proof of exactly what was
    authorized for one purchase intent - structurally modeled on AP2's
    Cart Mandate pattern (Google's open agent-payments protocol, which
    uses signed mandates as portable proof of user-authorized purchases),
    using a simplified single-keypair Ed25519 signature rather than AP2's
    full W3C Verifiable Credential chain. This is a second, independent
    proof layer on top of the Policy engine, not a replacement for it:
    Policy answers "is this action permitted now"; the mandate answers
    "can we prove, independent of trusting our own database, exactly
    what was authorized, and that nothing about it has changed since."
    """
    mandate_id = models.SlugField(max_length=100, unique=True)
    intent = models.OneToOneField(PurchaseIntent, on_delete=models.PROTECT, related_name="mandate")
    payload = models.JSONField()
    signature = models.CharField(max_length=200)
    public_key_id = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.mandate_id

class EnvelopeStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    EXPIRED = "EXPIRED", "Expired"
    REVOKED = "REVOKED", "Revoked"


class SpendingEnvelope(models.Model):
    """
    Delegated spending authority: "this agent may spend up to X with this
    merchant until Y, without a human confirming every single purchase."
    Modeled on NPCI's real UPI Reserve Pay (single block, multiple
    debits), with one deliberate difference: this block is our own
    independently verifiable domain object, not a request to a bank.

    Creation/modification of this row is NEVER exposed as an MCP tool -
    the agent can propose and buy, but only a human/system-level action
    can create, extend, or revoke delegated spending authority. Each
    individual purchase still produces its own separate PurchaseMandate
    via the unchanged confirm_purchase_intent - this model only decides
    whether that confirmation happens automatically or falls back to
    the existing manual human-confirm gate.
    """
    envelope_id = models.SlugField(max_length=100, unique=True)
    agent = models.ForeignKey("agents.Agent", on_delete=models.PROTECT, related_name="spending_envelopes")
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name="spending_envelopes")
    max_amount_minor = models.PositiveIntegerField()
    remaining_amount_minor = models.PositiveIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20, choices=EnvelopeStatus.choices, default=EnvelopeStatus.ACTIVE)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["agent", "merchant", "status"])]

    def __str__(self) -> str:
        return self.envelope_id

class EnvelopeDebitStatus(models.TextChoices):
    HELD = "HELD", "Held"
    CAPTURED = "CAPTURED", "Captured"
    RELEASED = "RELEASED", "Released"


class EnvelopeDebit(models.Model):
    """
    Tracks one envelope hold against one purchase intent, through its
    full lifecycle - mirrors the standard auth/capture/release pattern
    used by real card payment processors, applied here to our own
    SpendingEnvelope balance rather than a bank's.

    HELD: balance was decremented at auto-confirm time (this is what
    actually prevents overspend - the decrement itself, not this row).
    CAPTURED: the purchase completed successfully (finalize_payment
    succeeded) - the hold becomes permanent, no balance change.
    RELEASED: the purchase failed or was explicitly abandoned before
    completing - the held amount is atomically credited back to the
    envelope, exactly once (status=HELD in the WHERE clause prevents
    a double-release from over-crediting).

    A HELD row that never transitions to either CAPTURED or RELEASED
    (e.g. a checkout silently abandoned with no failure callback at
    all) is a documented residual gap, not solved by a sweep/timeout
    job in this POC - see docs.
    """
    envelope = models.ForeignKey(SpendingEnvelope, on_delete=models.PROTECT, related_name="debits")
    intent = models.OneToOneField(PurchaseIntent, on_delete=models.PROTECT, related_name="envelope_debit")
    amount_minor = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=EnvelopeDebitStatus.choices, default=EnvelopeDebitStatus.HELD)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.envelope.envelope_id}:{self.intent.intent_id}:{self.status}"