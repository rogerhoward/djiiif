"""Django system checks that validate ``settings.IIIF_PROFILES`` at startup.

Registered by :class:`djiiif.apps.DjiiifConfig`. Only statically-inspectable
entries are validated: callable profiles are skipped because their real shape is
only known once invoked with a field file.
"""

from django.conf import settings
from django.core.checks import Error, Warning, register

from djiiif import PROFILE_KEYS, Profile


@register()
def check_iiif_profiles(app_configs, **kwargs):
    """Validate the structure of ``settings.IIIF_PROFILES``.

    Args:
        app_configs: The app configs being checked (unused; the setting is
            global).
        **kwargs: Extra keyword arguments passed by Django's check framework.

    Returns:
        A list of ``django.core.checks`` messages — empty when the setting is
        well-formed.
    """
    messages = []
    profiles = getattr(settings, "IIIF_PROFILES", None)

    if profiles is None:
        messages.append(
            Warning(
                "IIIF_PROFILES is not defined; djiiif fields will expose no profile URLs.",
                hint="Define IIIF_PROFILES in your settings.",
                id="djiiif.W001",
            )
        )
        return messages

    if not isinstance(profiles, dict):
        messages.append(
            Error(
                "IIIF_PROFILES must be a dict mapping profile names to specs, got "
                f"{type(profiles).__name__}.",
                id="djiiif.E001",
            )
        )
        return messages

    for name, profile in profiles.items():
        # A Profile is always complete; a callable can only be checked at call
        # time, so both are considered valid here.
        if isinstance(profile, Profile) or callable(profile):
            continue

        if not isinstance(profile, dict):
            messages.append(
                Error(
                    f"IIIF profile '{name}' must be a dict, Profile, or callable, got "
                    f"{type(profile).__name__}.",
                    id="djiiif.E002",
                )
            )
            continue

        missing = [key for key in PROFILE_KEYS if key not in profile]
        if missing:
            messages.append(
                Error(
                    f"IIIF profile '{name}' is missing required key(s): {missing}.",
                    hint=f"Every dict profile needs: {list(PROFILE_KEYS)}.",
                    id="djiiif.E003",
                )
            )

    return messages
