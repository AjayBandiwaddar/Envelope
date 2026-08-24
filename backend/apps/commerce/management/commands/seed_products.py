from django.core.management.base import BaseCommand
from apps.commerce.models import Product

DEFAULT_PRODUCTS = [
    {"product_id": "laptop-apex-16", "name": "Apex 16", "category": "laptops",
     "description": "16GB RAM, 512GB SSD, 15.6-inch display.", "price_minor": 5799900, "currency": "INR"},
    {"product_id": "laptop-apex-8", "name": "Apex 8", "category": "laptops",
     "description": "8GB RAM, 256GB SSD, 14-inch display.", "price_minor": 3999900, "currency": "INR"},
    {"product_id": "laptop-voyager-16", "name": "Voyager 16", "category": "laptops",
     "description": "16GB RAM, 1TB SSD, 16-inch display, dedicated GPU.", "price_minor": 7499900, "currency": "INR"},
    {"product_id": "laptop-voyager-32", "name": "Voyager 32", "category": "laptops",
     "description": "32GB RAM, 1TB SSD, 16-inch display, dedicated GPU.", "price_minor": 9999900, "currency": "INR"},
    {"product_id": "laptop-compact-8", "name": "Compact 8", "category": "laptops",
     "description": "8GB RAM, 256GB SSD, 13-inch ultralight.", "price_minor": 4499900, "currency": "INR"},
    {"product_id": "laptop-compact-16", "name": "Compact 16", "category": "laptops",
     "description": "16GB RAM, 512GB SSD, 13-inch ultralight.", "price_minor": 5499900, "currency": "INR"},
]


class Command(BaseCommand):
    help = "Register the reference merchant's catalog (six laptops)."

    def handle(self, *args, **options):
        created_count = 0
        for entry in DEFAULT_PRODUCTS:
            _, created = Product.objects.get_or_create(
                product_id=entry["product_id"],
                defaults={k: v for k, v in entry.items() if k != "product_id"},
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created product: {entry['product_id']}"))
            else:
                self.stdout.write(f"Product already exists: {entry['product_id']}")
        self.stdout.write(self.style.SUCCESS(f"Done. {created_count} new product(s) created."))