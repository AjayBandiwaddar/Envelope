from django.db import models


class Product(models.Model):
    product_id = models.SlugField(max_length=100, unique=True)
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