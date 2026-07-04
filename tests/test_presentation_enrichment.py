"""Tests for Presentation 3.0 enrichment: descriptors, multi-image, collections."""

import json
from datetime import datetime, timezone

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.test import RequestFactory, override_settings

from djiiif import (
    IIIFObject,
    build_collection,
    build_manifest,
    build_multi_manifest,
    resolve_manifest_descriptors,
)
from djiiif import views


class FakeParent:
    """Minimal stand-in for an IIIFFieldFile."""

    def __init__(self, name, width=None, height=None):
        self.name = name
        self.width = width
        self.height = height


DICT_PROFILES = {
    "thumbnail": {"host": "http://server/", "region": "full", "size": "150,",
                  "rotation": "0", "quality": "default", "format": "jpg"},
}


# --- Piece 1: descriptive properties -----------------------------------------

def test_manifest_byte_identical_without_descriptors():
    # The regression pin: no descriptors -> exactly the historical key set/order.
    manifest = build_manifest("http://server/pic.jpg", 100, 200, label="pic.jpg")
    assert list(manifest) == ["@context", "id", "type", "label", "items"]
    assert list(manifest["items"][0]) == ["id", "type", "width", "height", "items"]


def test_descriptors_emitted_and_coerced():
    manifest = build_manifest(
        "http://server/pic.jpg",
        100,
        200,
        label="pic.jpg",
        metadata=[("Title", "A photo"), {"label": {"en": ["Date"]}, "value": {"en": ["1900"]}}],
        summary="A summary",
        required_statement=("Attribution", "Example Institution"),
        rights="http://creativecommons.org/licenses/by/4.0/",
        nav_date=datetime(1900, 1, 1, tzinfo=timezone.utc),
        thumbnail="http://server/thumb.jpg",
    )
    assert manifest["metadata"] == [
        {"label": {"none": ["Title"]}, "value": {"none": ["A photo"]}},
        {"label": {"en": ["Date"]}, "value": {"en": ["1900"]}},
    ]
    assert manifest["summary"] == {"none": ["A summary"]}
    assert manifest["requiredStatement"] == {
        "label": {"none": ["Attribution"]},
        "value": {"none": ["Example Institution"]},
    }
    assert manifest["rights"] == "http://creativecommons.org/licenses/by/4.0/"
    assert manifest["navDate"] == "1900-01-01T00:00:00+00:00"
    assert manifest["thumbnail"] == [{"id": "http://server/thumb.jpg", "type": "Image"}]
    # Descriptive properties sit between label and items.
    keys = list(manifest)
    assert keys[3] == "label" and keys[-1] == "items"


def test_unknown_descriptor_key_raises():
    with pytest.raises(ImproperlyConfigured):
        build_manifest("http://server/pic.jpg", 100, 200, label="x", metdata=[])


def test_preformed_required_statement_and_thumbnail_passthrough():
    # Already-formed dict / list values pass through the coercion unchanged.
    statement = {"label": {"en": ["Rights"]}, "value": {"en": ["CC0"]}}
    thumbnail = [{"id": "http://server/t.jpg", "type": "Image", "width": 100}]
    manifest = build_manifest(
        "http://server/pic.jpg",
        100,
        200,
        label="x",
        required_statement=statement,
        thumbnail=thumbnail,
    )
    assert manifest["requiredStatement"] == statement
    assert manifest["thumbnail"] == thumbnail


# --- IIIF_MANIFEST_DESCRIPTORS resolution ------------------------------------

def _descriptor_hook(parent):
    return {"rights": "http://example.org/rights", "summary": parent.name}


@override_settings(IIIF_PROFILES=DICT_PROFILES, IIIF_MANIFEST_DESCRIPTORS=_descriptor_hook)
def test_iiifobject_manifest_threads_descriptors():
    manifest = IIIFObject(FakeParent("uploads/pic.jpg", 400, 300)).manifest
    assert manifest["rights"] == "http://example.org/rights"
    assert manifest["summary"] == {"none": ["uploads/pic.jpg"]}


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_iiifobject_manifest_unset_descriptors_unchanged():
    manifest = IIIFObject(FakeParent("uploads/pic.jpg", 400, 300)).manifest
    assert "rights" not in manifest and "summary" not in manifest


def test_resolve_descriptors_dict_form():
    with override_settings(IIIF_MANIFEST_DESCRIPTORS={"rights": "http://x/r"}):
        assert resolve_manifest_descriptors(FakeParent("p")) == {"rights": "http://x/r"}


def test_resolve_descriptors_callable_returning_none():
    with override_settings(IIIF_MANIFEST_DESCRIPTORS=lambda parent: None):
        assert resolve_manifest_descriptors(FakeParent("p")) == {}


def test_resolve_descriptors_unset():
    assert resolve_manifest_descriptors(FakeParent("p")) == {}


def test_resolve_descriptors_bad_type_raises():
    with override_settings(IIIF_MANIFEST_DESCRIPTORS=lambda parent: ["not", "a", "dict"]):
        with pytest.raises(ImproperlyConfigured):
            resolve_manifest_descriptors(FakeParent("p"))


def test_resolve_descriptors_unknown_key_raises():
    with override_settings(IIIF_MANIFEST_DESCRIPTORS={"bogus": 1}):
        with pytest.raises(ImproperlyConfigured):
            resolve_manifest_descriptors(FakeParent("p"))


# --- Piece 2: multi-image manifests ------------------------------------------

def test_multi_manifest_indexed_canvases_and_labels():
    manifest = build_multi_manifest(
        "http://server/obj",
        [
            ("http://server/recto", 100, 200),
            {"id": "http://server/verso", "width": 300, "height": 400, "label": "Verso"},
        ],
        label="An object",
    )
    canvases = manifest["items"]
    assert len(canvases) == 2
    assert canvases[0]["id"] == "http://server/obj/canvas/1"
    assert canvases[1]["id"] == "http://server/obj/canvas/2"
    assert "label" not in canvases[0]
    assert canvases[1]["label"] == {"none": ["Verso"]}
    # Each canvas's image body points at its own service.
    assert canvases[1]["items"][0]["items"][0]["body"]["service"][0]["id"] == "http://server/verso"


def test_multi_manifest_v2_service_variant():
    manifest = build_multi_manifest(
        "http://server/obj", [("http://server/a", 1, 1)], label="x", version=2, level="level1"
    )
    service = manifest["items"][0]["items"][0]["items"][0]["body"]["service"][0]
    assert service["@type"] == "ImageService2"
    assert service["profile"] == "http://iiif.io/api/image/2/level1.json"


def test_multi_manifest_auth_on_every_body():
    auth = {"id": "http://server/probe", "type": "AuthProbeService2"}
    manifest = build_multi_manifest(
        "http://server/obj",
        [("http://server/a", 1, 1), ("http://server/b", 1, 1)],
        label="x",
        auth=auth,
    )
    for canvas in manifest["items"]:
        assert canvas["items"][0]["items"][0]["body"]["service"][-1] == auth


def test_single_image_wrapper_equivalence():
    # build_manifest must equal the one-item build_multi_manifest.
    wrapped = build_manifest("http://server/pic.jpg", 100, 200, label="pic.jpg")
    direct = build_multi_manifest(
        "http://server/pic.jpg", [("http://server/pic.jpg", 100, 200)], label="pic.jpg"
    )
    assert wrapped == direct


# --- Piece 3: collections ----------------------------------------------------

def test_build_collection_reference_items():
    collection = build_collection(
        "http://server/iiif/collection",
        [
            ("http://server/a/manifest", "Item A"),
            ("http://server/b/manifest", "Item B", "http://server/b/thumb.jpg"),
        ],
        label="Album",
        summary="An album",
    )
    assert collection["type"] == "Collection"
    assert collection["label"] == {"none": ["Album"]}
    assert collection["summary"] == {"none": ["An album"]}
    assert collection["items"][0] == {
        "id": "http://server/a/manifest",
        "type": "Manifest",
        "label": {"none": ["Item A"]},
    }
    assert collection["items"][1]["thumbnail"] == [
        {"id": "http://server/b/thumb.jpg", "type": "Image"}
    ]


def test_build_collection_dict_item_passthrough():
    preformed = {"id": "http://server/a/manifest", "type": "Manifest", "label": {"en": ["A"]}}
    collection = build_collection("http://c", [preformed], label="Album")
    assert collection["items"][0] is preformed


# --- serve_collection view ---------------------------------------------------

@pytest.fixture
def rf():
    return RequestFactory()


def _collection_source():
    return [("http://server/a/manifest", "Item A")]


@override_settings(IIIF_COLLECTION_SOURCE=_collection_source, IIIF_COLLECTION_LABEL="My Album")
def test_serve_collection_happy_path(rf):
    response = views.serve_collection(rf.get("/iiif/collection"))
    assert response["Content-Type"] == "application/ld+json"
    assert response["Access-Control-Allow-Origin"] == "*"
    body = json.loads(response.content)
    assert body["type"] == "Collection"
    assert body["id"] == "http://testserver/iiif/collection"
    assert body["label"] == {"none": ["My Album"]}
    assert body["items"][0]["id"] == "http://server/a/manifest"


def test_serve_collection_404_when_unset(rf):
    with pytest.raises(Http404):
        views.serve_collection(rf.get("/iiif/collection"))


@override_settings(IIIF_COLLECTION_SOURCE=lambda: [])
def test_serve_collection_empty_source_valid(rf):
    body = json.loads(views.serve_collection(rf.get("/iiif/collection")).content)
    assert body["type"] == "Collection"
    assert body["items"] == []
