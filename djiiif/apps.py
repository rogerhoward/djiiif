"""App configuration for djiiif."""

from django.apps import AppConfig


class DjiiifConfig(AppConfig):
    """Registers djiiif's system checks once the app registry is ready."""

    name = "djiiif"

    def ready(self):
        """Import the checks module so its ``@register`` decorator runs."""
        from djiiif import checks  # noqa: F401  (import registers the check)
