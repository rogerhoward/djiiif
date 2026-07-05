"""Tests for W3C Web Annotation serving (builders + view + manifest wiring)."""

import json

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.test import RequestFactory, override_settings

from djiiif import (
    Annotation,
    build_annotation,
    build_annotation_page,
    resolve_annotation,
)
from djiiif import views


ANNOTATION_CONTEXT = [
    "http://www.w3.org/ns/anno.jsonld",
    "http://iiif.io/api/presentation/3/context.json",
]


# --- builders ----------------------------------------------------------------

def test_build_annotation_defaults_and_target():
    anno = build_annotation("http://s/page", 1, "http://s/canvas/1", {"text": "hello"})
    assert anno == {
        "id": "http://s/page/anno/1",
        "type": "Annotation",
        "motivation": "supplementing",
        "body": {"type": "TextualBody", "value": "hello", "format": "text/plain"},
        "target": "http://s/canvas/1",
    }


def test_build_annotation_xywh_language_and_supplied_id():
    anno = build_annotation(
        "http://s/page", 2, "http://s/canvas/1",
        {"text": "bonjour", "xywh": "1,2,3,4", "language": "fr", "id": "http://s/a/9",
         "motivation": "commenting"},
    )
    assert anno["id"] == "http://s/a/9"
    assert anno["motivation"] == "commenting"
    assert anno["target"] == "http://s/canvas/1#xywh=1,2,3,4"
    assert anno["body"]["language"] == "fr"


def test_build_annotation_preformed_body_passthrough():
    body = {"type": "Image", "id": "http://s/img.png", "format": "image/png"}
    anno = build_annotation("http://s/page", 1, "http://s/canvas/1", {"text": body})
    assert anno["body"] is body


def test_build_annotation_page_shape_and_empty():
    page = build_annotation_page(
        "http://s/page", "http://s/canvas/1", [{"text": "a"}, {"text": "b"}]
    )
    assert page["@context"] == ANNOTATION_CONTEXT
    assert page["type"] == "AnnotationPage"
    assert page["id"] == "http://s/page"
    assert [a["id"] for a in page["items"]] == ["http://s/page/anno/1", "http://s/page/anno/2"]

    empty = build_annotation_page("http://s/page", "http://s/canvas/1", [])
    assert empty["items"] == []


# --- resolve_annotation ------------------------------------------------------

def test_resolve_annotation_dict_defaults():
    resolved = resolve_annotation({"text": "hi"})
    assert resolved["motivation"] == "supplementing"
    assert resolved["format"] == "text/plain"
    assert resolved["canvas_id"] is None


def test_resolve_annotation_dataclass():
    resolved = resolve_annotation(Annotation(text="hi", xywh="1,2,3,4", motivation="tagging"))
    assert resolved["xywh"] == "1,2,3,4"
    assert resolved["motivation"] == "tagging"


def test_resolve_annotation_bad_type_raises():
    with pytest.raises(ImproperlyConfigured):
        resolve_annotation(["not", "an", "annotation"])


# --- serve_annotation_page ---------------------------------------------------

@pytest.fixture
def rf():
    return RequestFactory()


def _annotations_backend(identifier, request):
    return [
        {"text": "a transcription", "xywh": "10,10,50,20"},
        Annotation(text="another", motivation="commenting"),
    ]


@override_settings(IIIF_ANNOTATIONS_BACKEND=_annotations_backend)
def test_serve_annotation_page_happy(rf):
    response = views.serve_annotation_page(rf.get("/iiif/photo.jpg/annotations/1"), "photo.jpg")
    assert response["Content-Type"] == "application/ld+json"
    assert response["Access-Control-Allow-Origin"] == "*"
    body = json.loads(response.content)
    assert body["id"] == "http://testserver/iiif/photo.jpg/annotations/1"
    target = "http://testserver/iiif/photo.jpg/canvas/1#xywh=10,10,50,20"
    assert body["items"][0]["target"] == target
    assert body["items"][1]["motivation"] == "commenting"


def test_serve_annotation_page_404_when_unset(rf):
    with pytest.raises(Http404):
        views.serve_annotation_page(rf.get("/iiif/photo.jpg/annotations/1"), "photo.jpg")


# --- manifest wiring ---------------------------------------------------------

class FakeFile:
    def close(self):
        pass


def _patch_dimensions(monkeypatch):
    monkeypatch.setattr(views.default_storage, "open", lambda name: FakeFile())
    monkeypatch.setattr(views, "get_image_dimensions", lambda image: (4000, 3000))


def test_manifest_no_backends_has_no_annotations_or_service(monkeypatch, rf):
    _patch_dimensions(monkeypatch)
    body = json.loads(views.serve_manifest(rf.get("/iiif/photo.jpg/manifest"), "photo.jpg").content)
    assert "annotations" not in body["items"][0]
    assert "service" not in body


@override_settings(IIIF_ANNOTATIONS_BACKEND=_annotations_backend)
def test_manifest_annotations_backend_adds_reference_and_search(monkeypatch, rf):
    _patch_dimensions(monkeypatch)
    body = json.loads(views.serve_manifest(rf.get("/iiif/photo.jpg/manifest"), "photo.jpg").content)
    assert body["items"][0]["annotations"] == [
        {"id": "http://testserver/iiif/photo.jpg/annotations/1", "type": "AnnotationPage"}
    ]
    # Configuring annotations makes substring search available, so the manifest
    # also advertises a SearchService2 (the "annotations => free search" contract).
    assert body["service"] == [
        {"id": "http://testserver/iiif/photo.jpg/search", "type": "SearchService2"}
    ]
