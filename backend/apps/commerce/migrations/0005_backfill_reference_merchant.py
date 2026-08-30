from django.db import migrations

REFERENCE_MERCHANT_ID = "reference-merchant"
REFERENCE_MERCHANT_NAME = "Reference Storefront"


def backfill_reference_merchant(apps, schema_editor):
    Merchant = apps.get_model('commerce', 'Merchant')
    Product = apps.get_model('commerce', 'Product')
    merchant, _ = Merchant.objects.get_or_create(
        merchant_id=REFERENCE_MERCHANT_ID,
        defaults={"name": REFERENCE_MERCHANT_NAME},
    )
    Product.objects.filter(merchant__isnull=True).update(merchant=merchant)


def noop_reverse(apps, schema_editor):
    # Deliberately not reversed: unsetting merchant on existing products
    # would silently discard real assignment data. If this migration
    # needs rolling back, do it by hand with full awareness of state.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('commerce', '0004_merchant_product_merchant'),
    ]
    operations = [
        migrations.RunPython(backfill_reference_merchant, noop_reverse),
    ]