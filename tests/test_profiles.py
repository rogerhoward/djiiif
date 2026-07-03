"""Tests for the typed Profile dataclass, profile resolution, and encoding."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from djiiif import IIIFObject, Profile, encode_identifier, resolve_profile


class FakeParent:
    def __init__(self, name, width=None, height=None):
        self.name = name
        self.width = width
        self.height = height


def test_profile_defaults_are_iiif_3():
    spec = Profile(host="http://server/").as_spec()
    assert spec == {
        "host": "http://server/",
        "region": "full",
        "size": "max",
        "rotation": "0",
        "quality": "default",
        "format": "jpg",
    }


def test_profile_mirror_prefixes_rotation():
    assert Profile(host="h", mirror=True).as_spec()["rotation"] == "!0"


def test_profile_mirror_does_not_double_prefix():
    assert Profile(host="h", rotation="!90", mirror=True).as_spec()["rotation"] == "!90"


def test_profile_upscale_prefixes_size():
    assert Profile(host="h", size="2000,", upscale=True).as_spec()["size"] == "^2000,"


def test_profile_upscale_does_not_double_prefix():
    assert Profile(host="h", size="^max", upscale=True).as_spec()["size"] == "^max"


@override_settings(IIIF_PROFILES={"p": Profile(host="http://server/", size="150,")})
def test_profile_instance_builds_url():
    obj = IIIFObject(FakeParent("file.jpg"))
    assert obj.p == "http://server/file.jpg/full/150,/0/default.jpg"


def test_resolve_profile_accepts_dict():
    spec = {"host": "h", "region": "full", "size": "max", "rotation": "0",
            "quality": "default", "format": "jpg"}
    assert resolve_profile(spec, FakeParent("f.jpg")) is spec


def test_resolve_profile_accepts_profile():
    assert resolve_profile(Profile(host="h"), FakeParent("f.jpg"))["host"] == "h"


def test_resolve_profile_calls_callable_returning_profile():
    resolved = resolve_profile(lambda parent: Profile(host="h"), FakeParent("f.jpg"))
    assert resolved["size"] == "max"


def test_resolve_profile_calls_callable_returning_dict():
    spec = {"host": "h", "region": "full", "size": "max", "rotation": "0",
            "quality": "default", "format": "jpg"}
    assert resolve_profile(lambda parent: spec, FakeParent("f.jpg")) is spec


def test_resolve_profile_rejects_bad_callable_return():
    with pytest.raises(ImproperlyConfigured):
        resolve_profile(lambda parent: "nope", FakeParent("f.jpg"))


def test_resolve_profile_rejects_unsupported_type():
    with pytest.raises(ImproperlyConfigured):
        resolve_profile("nope", FakeParent("f.jpg"))


def test_encode_identifier_encodes_reserved_characters():
    # Slashes, spaces, and query/fragment characters must all be encoded.
    assert encode_identifier("a b/c?d#e.jpg") == "a%20b%2Fc%3Fd%23e.jpg"


def test_encode_identifier_leaves_plain_names_untouched():
    assert encode_identifier("photo.jpg") == "photo.jpg"


@override_settings(
    IIIF_PROFILES={
        "thumbnail": {"host": "http://server/", "region": "full", "size": "150,",
                      "rotation": "0", "quality": "default", "format": "jpg"}
    }
)
def test_url_encodes_special_characters_in_name():
    obj = IIIFObject(FakeParent("my pics/a?b.jpg"))
    assert obj.thumbnail == "http://server/my%20pics%2Fa%3Fb.jpg/full/150,/0/default.jpg"


@override_settings(IIIF_PROFILES={})
def test_empty_profiles_does_not_crash():
    # Regression: with no profiles, info/identifier must be "" rather than raise.
    obj = IIIFObject(FakeParent("file.jpg"))
    assert obj.info == ""
    assert obj.identifier == ""
    assert obj.info_document is None
    assert obj.manifest is None
