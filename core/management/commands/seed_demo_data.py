from django.core.management.base import BaseCommand
import subprocess
import sys

class Command(BaseCommand):
    help = "Seeds standard demo data into the active database."

    def handle(self, *args, **options):
        self.stdout.write("Running seed_demo.py...")
        import seed_demo
        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
