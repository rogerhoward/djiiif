"""Tests for the IIIF Content State API 1.0 helpers and .iiif.content_state."""

import pytest
from django.template import Context, Template
from django.test import override_settings

from djiiif import (
    IIIFObject,
    build_content_state,
    decode_content_state,
    encode_content_state,
)
from djiiif.templatetags.iiiftags import NotAnIIIFField
from djiiif.templatetags.iiiftags import iiif_content_state as content_state_tag


class FakeParent:
    """Minimal stand-in for an IIIFFieldFile (content_state does no file I/O)."""

    def __init__(self, name):
        self.name = name


DICT_PROFILES = {
    "thumbnail": {"host": "http://server/", "region": "full", "size": "150,",
                  "rotation": "0", "quality": "default", "format": "jpg"},
}


# The canonical worked example published in Content State API 1.0 §6 — a Canvas
# region within a Manifest, and its exact encoded form. Pinning to it verifies
# byte-for-byte interop with the spec (and any conforming viewer).
SPEC_STATE = {
    "id": "https://example.org/object1/canvas7#xywh=1000,2000,1000,2000",
    "type": "Canvas",
    "partOf": [{"id": "https://example.org/object1/manifest", "type": "Manifest"}],
}
SPEC_ENCODED = (
    "JTdCJTIyaWQlMjIlM0ElMjJodHRwcyUzQSUyRiUyRmV4YW1wbGUub3JnJTJGb2JqZWN0MSUyRmNh"
    "bnZhczclMjN4eXdoJTNEMTAwMCUyQzIwMDAlMkMxMDAwJTJDMjAwMCUyMiUyQyUyMnR5cGUlMjIl"
    "M0ElMjJDYW52YXMlMjIlMkMlMjJwYXJ0T2YlMjIlM0ElNUIlN0IlMjJpZCUyMiUzQSUyMmh0dHBz"
    "JTNBJTJGJTJGZXhhbXBsZS5vcmclMkZvYmplY3QxJTJGbWFuaWZlc3QlMjIlMkMlMjJ0eXBlJTIy"
    "JTNBJTIyTWFuaWZlc3QlMjIlN0QlNUQlN0Q"
)


# --- encode/decode primitives ------------------------------------------------

def test_encode_matches_spec_worked_example():
    assert encode_content_state(SPEC_STATE) == SPEC_ENCODED


def test_decode_matches_spec_worked_example():
    assert decode_content_state(SPEC_ENCODED) == SPEC_STATE


def test_encode_strips_padding():
    encoded = encode_content_state(SPEC_STATE)
    assert "=" not in encoded


def test_dict_round_trip():
    state = {"id": "https://example.org/m", "type": "Manifest"}
    assert decode_content_state(encode_content_state(state)) == state


def test_bare_uri_string_round_trip():
    # A non-JSON payload (the spec's trivial manifest-URI form) survives verbatim.
    uri = "https://example.org/object1/manifest"
    assert decode_content_state(encode_content_state(uri)) == uri


# --- build_content_state -----------------------------------------------------

def test_build_manifest_only_target():
    assert build_content_state("https://example.org/m") == {
        "id": "https://example.org/m",
        "type": "Manifest",
    }


def test_build_canvas_target_has_part_of():
    state = build_content_state("https://example.org/m", canvas_id="https://example.org/c1")
    assert state == {
        "id": "https://example.org/c1",
        "type": "Canvas",
        "partOf": [{"id": "https://example.org/m", "type": "Manifest"}],
    }


def test_build_xywh_string_and_tuple_produce_same_fragment():
    from_string = build_content_state(
        "https://example.org/m", canvas_id="https://example.org/c1", xywh="1000,2000,1000,2000"
    )
    from_tuple = build_content_state(
        "https://example.org/m", canvas_id="https://example.org/c1", xywh=(1000, 2000, 1000, 2000)
    )
    assert from_string["id"] == "https://example.org/c1#xywh=1000,2000,1000,2000"
    assert from_string == from_tuple


def test_build_xywh_ignored_without_canvas():
    # A whole-Manifest target has no canvas to attach a region to.
    assert build_content_state("https://example.org/m", xywh="0,0,1,1") == {
        "id": "https://example.org/m",
        "type": "Manifest",
    }


# --- IIIFObject.content_state ------------------------------------------------

@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_content_state_uris_match_manifest():
    obj = IIIFObject(FakeParent("uploads/pic.jpg"))
    state = obj.content_state(encoded=False)
    manifest_id = state["partOf"][0]["id"]
    assert state["id"] == "http://server/uploads%2Fpic.jpg/canvas/1"
    assert manifest_id == "http://server/uploads%2Fpic.jpg/manifest"


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_content_state_with_region():
    obj = IIIFObject(FakeParent("uploads/pic.jpg"))
    state = obj.content_state(xywh="10,20,30,40", encoded=False)
    assert state["id"] == "http://server/uploads%2Fpic.jpg/canvas/1#xywh=10,20,30,40"


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_content_state_encoded_decodes_back_to_dict():
    obj = IIIFObject(FakeParent("uploads/pic.jpg"))
    encoded = obj.content_state(xywh="10,20,30,40")
    assert isinstance(encoded, str) and "=" not in encoded
    assert decode_content_state(encoded) == obj.content_state(xywh="10,20,30,40", encoded=False)


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_content_state_empty_field_returns_empty_string():
    assert IIIFObject(FakeParent("")).content_state() == ""


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_content_state_empty_field_dict_form_returns_none():
    assert IIIFObject(FakeParent("")).content_state(encoded=False) is None


# --- template tag ------------------------------------------------------------

@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_tag_returns_encoded_state():
    obj = IIIFObject(FakeParent("uploads/pic.jpg"))
    parent = type("P", (), {"iiif": obj})()
    result = content_state_tag(parent, xywh="10,20,30,40")
    assert decode_content_state(result)["id"].endswith("#xywh=10,20,30,40")


def test_tag_raises_for_non_iiif_field():
    with pytest.raises(NotAnIIIFField):
        content_state_tag(object())


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_tag_renders_in_template():
    obj = IIIFObject(FakeParent("uploads/pic.jpg"))
    parent = type("P", (), {"iiif": obj})()
    template = Template("{% load iiiftags %}{% iiif_content_state asset xywh='10,20,30,40' %}")
    rendered = template.render(Context({"asset": parent}))
    assert decode_content_state(rendered)["id"].endswith("#xywh=10,20,30,40")
