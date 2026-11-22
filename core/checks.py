from django.conf import settings
from django.core.checks import Warning, register


@register()
def bootstrap_is_bundled(app_configs, **kwargs):
    path = settings.BASE_DIR / "static" / "vendor" / "bootstrap" / "css" / "bootstrap.min.css"
    if path.exists():
        return []
    return [
        Warning(
            "Bootstrap is not bundled locally yet, so pages load it from a CDN (internet needed).",
            hint="Run `python manage.py fetch_vendor` once while online. After that the site works fully offline.",
            id="core.W001",
        )
    ]
