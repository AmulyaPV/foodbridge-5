"""Download Bootstrap into static/vendor so the site works with no internet afterwards."""
import urllib.request
from urllib.error import URLError

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

BOOTSTRAP_VERSION = "5.3.3"
BASE_URL = f"https://cdn.jsdelivr.net/npm/bootstrap@{BOOTSTRAP_VERSION}/dist"
FILES = {
    "bootstrap/css/bootstrap.min.css": f"{BASE_URL}/css/bootstrap.min.css",
    "bootstrap/js/bootstrap.bundle.min.js": f"{BASE_URL}/js/bootstrap.bundle.min.js",
}


class Command(BaseCommand):
    help = "Download Bootstrap into static/vendor (needs internet once)."

    def handle(self, *args, **options):
        target = settings.BASE_DIR / "static" / "vendor"
        for relative, url in FILES.items():
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.stdout.write(f"Downloading {url}")
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    destination.write_bytes(response.read())
            except (URLError, OSError) as error:
                raise CommandError(f"Could not download {url}: {error}")
        self.stdout.write(self.style.SUCCESS("Bootstrap saved to static/vendor. The site now works offline."))
