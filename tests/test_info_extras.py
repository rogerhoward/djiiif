"""Tests for IIIF_INFO enrichment of the generated info.json."""

import json

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, override_settings

from djiiif import (
    IIIFObject,
    InfoExtras,
    build_info_document,
    resolve_info,
)
from djiiif import views


class FakeParent:
    def __init__(self, name, width=None, height=None):
        self.name = name
        self.width = width
        self.height = height


DICT_PROFILES = {
    "thumbnail": {"host": "http://server/", "region": "full", "size": "150,",
                  "rotation": "0", "quality": "default", "format": "jpg"},
}

FULL_EXTRAS = {
    "sizes": [{"width": 500, "height": 375}],
    "tiles": [{"width": 512, "scaleFactors": [1, 2, 4]}],
    "max_width": 5000,
    "max_height": 4000,
    "max_area": 20_000_000,
    "rights": "http://creativecommons.org/licenses/by/4.0/",
    "preferred_formats": ["webp", "jpg"],
    "extra_qualities": ["color", "gray"],
    "extra_formats": ["webp"],
    "extra_features": ["mirroring"],
}


# --- build_info_document emission (v3) ---------------------------------------

def test_v3_emits_all_keys_with_spec_casing():
    doc = build_info_document("http://s/img", 4000, 3000, extras=FULL_EXTRAS)
    assert doc["sizes"] == [{"width": 500, "height": 375}]
    assert doc["tiles"] == [{"width": 512, "scaleFactors": [1, 2, 4]}]
    assert doc["maxWidth"] == 5000
    assert doc["maxHeight"] == 4000
    assert doc["maxArea"] == 20_000_000
    assert doc["rights"] == "http://creativecommons.org/licenses/by/4.0/"
    assert doc["preferredFormats"] == ["webp", "jpg"]
    assert doc["extraQualities"] == ["color", "gray"]
    assert doc["extraFormats"] == ["webp"]
    assert doc["extraFeatures"] == ["mirroring"]


def test_v3_key_order_is_spec_conventional():
    doc = build_info_document("http://s/img", 4000, 3000, extras=FULL_EXTRAS)
    keys = list(doc)
    # Base fields first, then sizes/tiles/limits/rights/extras in spec grouping.
    assert keys.index("height") < keys.index("sizes") < keys.index("tiles")
    assert keys.index("tiles") < keys.index("maxWidth") < keys.index("rights")
    assert keys.index("rights") < keys.index("preferredFormats")


def test_v3_composition_with_auth():
    auth = {"id": "http://s/probe", "type": "AuthProbeService2"}
    doc = build_info_document("http://s/img", 1, 1, auth=auth, extras={"max_width": 100})
    assert doc["maxWidth"] == 100
    assert doc["service"] == [auth]


# --- v2 behavior -------------------------------------------------------------

def test_v2_emits_sizes_and_tiles():
    doc = build_info_document(
        "http://s/img", 1, 1, version=2,
        extras={"sizes": [{"width": 100, "height": 100}], "tiles": [{"width": 256}]},
    )
    assert doc["sizes"] == [{"width": 100, "height": 100}]
    assert doc["tiles"] == [{"width": 256}]


def test_v2_rejects_v3_only_key():
    with pytest.raises(ImproperlyConfigured):
        build_info_document("http://s/img", 1, 1, version=2, extras={"max_width": 100})


# --- byte-identical regression pins ------------------------------------------

def test_v3_byte_identical_without_extras():
    with_default = build_info_document("http://s/img", 4000, 3000)
    with_empty = build_info_document("http://s/img", 4000, 3000, extras={})
    assert with_default == with_empty
    assert list(with_default) == [
        "@context", "id", "type", "protocol", "profile", "width", "height",
    ]


def test_v2_byte_identical_without_extras():
    doc = build_info_document("http://s/img", 4000, 3000, version=2)
    assert list(doc) == ["@context", "@id", "protocol", "profile", "width", "height"]


# --- resolve_info / key normalization ----------------------------------------

def test_resolve_info_camel_and_snake_accepted():
    with override_settings(IIIF_INFO={"maxWidth": 10, "preferred_formats": ["jpg"]}):
        assert resolve_info(FakeParent("p")) == {"max_width": 10, "preferred_formats": ["jpg"]}


def test_resolve_info_conflicting_duplicate_rejected():
    with override_settings(IIIF_INFO={"max_width": 10, "maxWidth": 20}):
        with pytest.raises(ImproperlyConfigured):
            resolve_info(FakeParent("p"))


def test_resolve_info_unknown_key_rejected():
    with override_settings(IIIF_INFO={"bogus": 1}):
        with pytest.raises(ImproperlyConfigured):
            resolve_info(FakeParent("p"))


def test_resolve_info_dataclass():
    with override_settings(IIIF_INFO=InfoExtras(max_area=100, rights="http://x/r")):
        assert resolve_info(FakeParent("p")) == {"max_area": 100, "rights": "http://x/r"}


def test_resolve_info_callable_receives_parent():
    def per_image(parent):
        w = parent.width
        return {"sizes": [{"width": w, "height": w}]}

    with override_settings(IIIF_INFO=per_image):
        assert resolve_info(FakeParent("p", width=64)) == {"sizes": [{"width": 64, "height": 64}]}


def test_resolve_info_callable_returning_none():
    with override_settings(IIIF_INFO=lambda parent: None):
        assert resolve_info(FakeParent("p")) == {}


def test_resolve_info_unset():
    assert resolve_info(FakeParent("p")) == {}


def test_resolve_info_bad_type_raises():
    with override_settings(IIIF_INFO=["not", "a", "dict"]):
        with pytest.raises(ImproperlyConfigured):
            resolve_info(FakeParent("p"))


# --- IIIFObject.info_document threading --------------------------------------

@override_settings(IIIF_PROFILES=DICT_PROFILES, IIIF_INFO={"max_width": 8000})
def test_info_document_threads_extras():
    doc = IIIFObject(FakeParent("uploads/pic.jpg", 4000, 3000)).info_document
    assert doc["maxWidth"] == 8000


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_info_document_unset_unchanged():
    doc = IIIFObject(FakeParent("uploads/pic.jpg", 4000, 3000)).info_document
    assert "maxWidth" not in doc


# --- serve_info_json threading (str-name callable contract) ------------------

class FakeFile:
    def close(self):
        pass


@pytest.fixture
def rf():
    return RequestFactory()


def _patch_dimensions(monkeypatch):
    monkeypatch.setattr(views.default_storage, "open", lambda name: FakeFile())
    monkeypatch.setattr(views, "get_image_dimensions", lambda image: (4000, 3000))


def _info_by_name(parent):
    # On the view path, parent is the decoded storage name (a str).
    assert isinstance(parent, str)
    return {"rights": f"http://rights/{parent}"}


@override_settings(IIIF_INFO=_info_by_name)
def test_serve_info_json_threads_extras_with_name(monkeypatch, rf):
    _patch_dimensions(monkeypatch)
    response = views.serve_info_json(rf.get("/iiif/photo.jpg/info.json"), "photo.jpg")
    body = json.loads(response.content)
    assert body["rights"] == "http://rights/photo.jpg"
