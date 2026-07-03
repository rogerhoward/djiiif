"""Tests for the IIIF_PROFILES system check."""

from django.test import override_settings

from djiiif import Profile
from djiiif.checks import check_iiif_profiles

GOOD_DICT = {"host": "h", "region": "full", "size": "max", "rotation": "0",
             "quality": "default", "format": "jpg"}


@override_settings(IIIF_PROFILES={"thumb": GOOD_DICT})
def test_valid_dict_profile_passes():
    assert check_iiif_profiles(None) == []


@override_settings(IIIF_PROFILES={"a": Profile(host="h"), "b": lambda parent: GOOD_DICT})
def test_profile_instance_and_callable_pass():
    assert check_iiif_profiles(None) == []


@override_settings(IIIF_PROFILES=None)
def test_missing_profiles_warns():
    messages = check_iiif_profiles(None)
    assert [m.id for m in messages] == ["djiiif.W001"]


@override_settings(IIIF_PROFILES=["not", "a", "dict"])
def test_non_dict_setting_errors():
    messages = check_iiif_profiles(None)
    assert [m.id for m in messages] == ["djiiif.E001"]


@override_settings(IIIF_PROFILES={"bad": "not a spec"})
def test_unsupported_profile_type_errors():
    messages = check_iiif_profiles(None)
    assert [m.id for m in messages] == ["djiiif.E002"]


@override_settings(IIIF_PROFILES={"partial": {"host": "h", "region": "full"}})
def test_dict_missing_keys_errors():
    messages = check_iiif_profiles(None)
    assert len(messages) == 1
    assert messages[0].id == "djiiif.E003"
    assert "size" in messages[0].msg
