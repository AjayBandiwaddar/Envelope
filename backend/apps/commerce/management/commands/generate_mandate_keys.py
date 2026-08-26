import base64
from django.core.management.base import BaseCommand
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


class Command(BaseCommand):
    help = "Generate an Ed25519 keypair for signing purchase mandates. Run once; store the printed values in .env."

    def handle(self, *args, **options):
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        self.stdout.write(self.style.WARNING(f"MANDATE_PRIVATE_KEY={base64.b64encode(private_bytes).decode()}"))
        self.stdout.write(self.style.SUCCESS(f"MANDATE_PUBLIC_KEY={base64.b64encode(public_bytes).decode()}"))
        self.stdout.write("Copy both lines into .env. The private key never leaves the server.")