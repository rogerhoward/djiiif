"""Tests for the optional IIIF Authorization Flow 2.0 integration."""

from types import SimpleNamespace

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from djiiif import (
    AccessService,
    IIIFObject,
    LogoutService,
    ProbeService,
    TokenService,
    build_info_document,
    build_manifest,
    resolve_auth,
)


class FakeParent:
    def __init__(self, name, width=None, height=None, instance=None):
        self.name = name
        self.width = width
        self.height = height
        self.instance = instance


DICT_PROFILES = {
    "thumbnail": {"host": "http://server/", "region": "full", "size": "150,",
                  "rotation": "0", "quality": "default", "format": "jpg"},
}

PROBE = ProbeService(
    id="https://auth.example/probe",
    access=AccessService(
        id="https://auth.example/login",
        profile="active",
        label="Log in",
        heading="Restricted",
        note="Use your account",
        confirm_label="Continue",
        token=TokenService(id="https://auth.example/token"),
        logout=LogoutService(id="https://auth.example/logout", label="Log out"),
    ),
)

PROBE_DICT = {
    "id": "https://auth.example/probe",
    "type": "AuthProbeService2",
    "service": [
        {
            "id": "https://auth.example/login",
            "type": "AuthAccessService2",
            "profile": "active",
            "label": {"none": ["Log in"]},
            "heading": {"none": ["Restricted"]},
            "note": {"none": ["Use your account"]},
            "confirmLabel": {"none": ["Continue"]},
            "service": [
                {"id": "https://auth.example/token", "type": "AuthAccessTokenService2"},
                {"id": "https://auth.example/logout", "type": "AuthLogoutService2",
                 "label": {"none": ["Log out"]}},
            ],
        }
    ],
}


# --- typed helper serialization -------------------------------------------------

def test_probe_service_full_nesting():
    assert PROBE.as_dict() == PROBE_DICT


def test_probe_service_bare():
    assert ProbeService(id="p").as_dict() == {"id": "p", "type": "AuthProbeService2"}


def test_token_service():
    assert TokenService(id="t").as_dict() == {"id": "t", "type": "AuthAccessTokenService2"}


def test_logout_service_with_and_without_label():
    assert LogoutService(id="l").as_dict() == {"id": "l", "type": "AuthLogoutService2"}
    assert LogoutService(id="l", label="Bye").as_dict() == {
        "id": "l", "type": "AuthLogoutService2", "label": {"none": ["Bye"]}
    }


def test_access_service_minimal_external():
    assert AccessService(id="a", profile="external").as_dict() == {
        "id": "a", "type": "AuthAccessService2", "profile": "external"
    }


def test_language_map_accepts_list_and_passthrough_dict():
    assert AccessService(id="a", label=["X", "Y"]).as_dict()["label"] == {"none": ["X", "Y"]}
    assert AccessService(id="a", label={"en": ["Z"]}).as_dict()["label"] == {"en": ["Z"]}


# --- resolve_auth ---------------------------------------------------------------

def test_resolve_auth_none_when_unset():
    assert resolve_auth(FakeParent("f.jpg")) is None


@override_settings(IIIF_AUTH=PROBE)
def test_resolve_auth_probe_service():
    assert resolve_auth(FakeParent("f.jpg")) == PROBE_DICT


@override_settings(IIIF_AUTH={"id": "x", "type": "AuthProbeService2"})
def test_resolve_auth_dict_passthrough():
    assert resolve_auth(FakeParent("f.jpg")) == {"id": "x", "type": "AuthProbeService2"}


@override_settings(IIIF_AUTH=lambda parent: PROBE)
def test_resolve_auth_callable_returning_probe():
    assert resolve_auth(FakeParent("f.jpg")) == PROBE_DICT


@override_settings(IIIF_AUTH=lambda parent: None)
def test_resolve_auth_callable_returning_none():
    assert resolve_auth(FakeParent("f.jpg")) is None


@override_settings(IIIF_AUTH=12345)
def test_resolve_auth_bad_type_raises():
    with pytest.raises(ImproperlyConfigured):
        resolve_auth(FakeParent("f.jpg"))


# --- emission in documents ------------------------------------------------------

@override_settings(IIIF_PROFILES=DICT_PROFILES, IIIF_AUTH=PROBE)
def test_info_document_includes_auth_service():
    doc = IIIFObject(FakeParent("f.jpg", width=10, height=10)).info_document
    assert doc["service"] == [PROBE_DICT]


@override_settings(IIIF_PROFILES=DICT_PROFILES, IIIF_AUTH=PROBE)
def test_manifest_attaches_auth_to_image_body():
    body = IIIFObject(FakeParent("f.jpg", width=10, height=10)).manifest[
        "items"][0]["items"][0]["items"][0]["body"]
    assert body["service"][0]["type"] == "ImageService3"
    assert body["service"][-1] == PROBE_DICT


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_documents_have_no_auth_when_unset():
    obj = IIIFObject(FakeParent("f.jpg", width=10, height=10))
    assert "service" not in obj.info_document
    body = obj.manifest["items"][0]["items"][0]["items"][0]["body"]
    assert len(body["service"]) == 1  # only the image service


def _auth_for(parent):
    return None if parent.instance.public else PROBE


@override_settings(IIIF_PROFILES=DICT_PROFILES, IIIF_AUTH=_auth_for)
def test_per_image_callable_public_vs_restricted():
    public = IIIFObject(FakeParent("f.jpg", 10, 10, instance=SimpleNamespace(public=True)))
    assert "service" not in public.info_document

    restricted = IIIFObject(FakeParent("g.jpg", 10, 10, instance=SimpleNamespace(public=False)))
    assert restricted.info_document["service"] == [PROBE_DICT]


# --- version guard --------------------------------------------------------------

@override_settings(IIIF_PROFILES=DICT_PROFILES, IIIF_AUTH=PROBE, IIIF_IMAGE_API_VERSION=2)
def test_auth_with_api_v2_raises_in_info_document():
    with pytest.raises(ImproperlyConfigured):
        IIIFObject(FakeParent("f.jpg", width=10, height=10)).info_document


@override_settings(IIIF_PROFILES=DICT_PROFILES, IIIF_AUTH=PROBE, IIIF_IMAGE_API_VERSION=2)
def test_auth_with_api_v2_raises_in_manifest():
    with pytest.raises(ImproperlyConfigured):
        IIIFObject(FakeParent("f.jpg", width=10, height=10)).manifest


def test_build_helpers_reject_auth_at_v2():
    with pytest.raises(ImproperlyConfigured):
        build_info_document("http://s/x", 10, 10, version=2, auth=PROBE_DICT)
    with pytest.raises(ImproperlyConfigured):
        build_manifest("http://s/x", 10, 10, label="x", version=2, auth=PROBE_DICT)
