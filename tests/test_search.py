"""Tests for IIIF Content Search 2.0 (builders + view + fallback + advertisement)."""

import json

import pytest
from django.http import Http404
from django.test import RequestFactory, override_settings

from djiiif import Annotation, build_search_response, build_search_service
from djiiif import views


# --- builders ----------------------------------------------------------------

def test_build_search_service_shape():
    assert build_search_service("http://s/search") == {
        "id": "http://s/search",
        "type": "SearchService2",
    }


def test_build_search_response_hit_and_match_block():
    hits = [{"text": "a bird", "canvas_id": "http://s/canvas/1", "xywh": "1,2,3,4",
             "before": "saw ", "exact": "bird", "after": " today"}]
    resp = build_search_response("http://s/search", "bird", hits)
    assert resp["@context"] == "http://iiif.io/api/search/2/context.json"
    assert resp["id"] == "http://s/search?q=bird"
    assert resp["type"] == "AnnotationPage"

    item = resp["items"][0]
    assert item["type"] == "Annotation"
    assert item["body"] == {"type": "TextualBody", "value": "a bird", "format": "text/plain"}
    assert item["target"] == "http://s/canvas/1#xywh=1,2,3,4"

    match = resp["annotations"][0]
    assert match["type"] == "AnnotationPage"
    selector = match["items"][0]["target"]
    assert match["items"][0]["motivation"] == "contextualizing"
    assert selector["type"] == "SpecificResource"
    assert selector["source"] == item["id"]
    assert selector["selector"] == {
        "type": "TextQuoteSelector",
        "prefix": "saw ",
        "exact": "bird",
        "suffix": " today",
    }


def test_build_search_response_exact_defaults_to_query():
    hits = [{"text": "cat", "canvas_id": "http://s/c/1"}]
    resp = build_search_response("http://s/search", "cat", hits)
    selector = resp["annotations"][0]["items"][0]["target"]["selector"]
    assert selector["exact"] == "cat"
    assert selector["prefix"] == "" and selector["suffix"] == ""


def test_build_search_response_ignored_and_empty():
    resp = build_search_response("http://s/search", "x", [], ignored=["user", "date"])
    assert resp["ignored"] == ["user", "date"]
    assert resp["items"] == []
    assert "annotations" not in resp


# --- serve_search ------------------------------------------------------------

@pytest.fixture
def rf():
    return RequestFactory()


def _search(rf, q_suffix="?q=bird"):
    """Run serve_search for photo.jpg and return the decoded JSON body."""
    request = rf.get(f"/iiif/photo.jpg/search{q_suffix}")
    return json.loads(views.serve_search(request, "photo.jpg").content)


def _search_backend(identifier, q, request):
    return [
        {"text": f"match for {q}", "canvas_id": "http://testserver/iiif/photo.jpg/canvas/1",
         "xywh": "5,5,10,10"},
        Annotation(text="second", canvas_id="http://testserver/iiif/photo.jpg/canvas/1"),
    ]


@override_settings(IIIF_SEARCH_BACKEND=_search_backend)
def test_serve_search_happy(rf):
    response = views.serve_search(rf.get("/iiif/photo.jpg/search?q=bird"), "photo.jpg")
    assert response["Content-Type"] == "application/ld+json"
    assert response["Access-Control-Allow-Origin"] == "*"
    body = json.loads(response.content)
    assert body["id"] == "http://testserver/iiif/photo.jpg/search?q=bird"
    assert body["items"][0]["body"]["value"] == "match for bird"
    assert body["items"][0]["target"].endswith("/canvas/1#xywh=5,5,10,10")
    assert len(body["items"]) == 2


@override_settings(IIIF_SEARCH_BACKEND=_search_backend)
def test_serve_search_empty_q_is_empty_page(rf):
    body = _search(rf, "")
    assert body["items"] == []
    assert "annotations" not in body


@override_settings(IIIF_SEARCH_BACKEND=_search_backend)
def test_serve_search_ignored_parameters(rf):
    request = rf.get("/iiif/photo.jpg/search?q=bird&user=alice&motivation=commenting")
    body = json.loads(views.serve_search(request, "photo.jpg").content)
    assert set(body["ignored"]) == {"user", "motivation"}


def test_serve_search_404_when_no_backend(rf):
    with pytest.raises(Http404):
        views.serve_search(rf.get("/iiif/photo.jpg/search?q=x"), "photo.jpg")


def _annotations_backend(identifier, request):
    return [
        {"text": "a transcription of birdsong", "xywh": "1,1,2,2"},
        {"text": "unrelated note"},
    ]


@override_settings(IIIF_ANNOTATIONS_BACKEND=_annotations_backend)
def test_serve_search_substring_fallback(rf):
    body = _search(rf, "?q=BIRD")
    # Case-insensitive substring match hits only the first annotation.
    assert len(body["items"]) == 1
    assert body["items"][0]["body"]["value"] == "a transcription of birdsong"
    # The fallback fills the canvas from the served-manifest canvas URI.
    assert body["items"][0]["target"] == "http://testserver/iiif/photo.jpg/canvas/1#xywh=1,1,2,2"


def _annotations_with_canvas(identifier, request):
    # An annotation that already carries its own canvas_id (the fallback keeps it).
    return [{"text": "a bird here", "canvas_id": "http://elsewhere/canvas/9", "xywh": "0,0,1,1"}]


@override_settings(IIIF_ANNOTATIONS_BACKEND=_annotations_with_canvas)
def test_fallback_preserves_existing_canvas_id(rf):
    body = _search(rf)
    assert body["items"][0]["target"] == "http://elsewhere/canvas/9#xywh=0,0,1,1"


@override_settings(IIIF_SEARCH_BACKEND="tests.test_search._search_backend")
def test_dotted_path_backend(rf):
    assert _search(rf)["items"][0]["body"]["value"] == "match for bird"


@override_settings(
    IIIF_SEARCH_BACKEND=_search_backend, IIIF_ANNOTATIONS_BACKEND=_annotations_backend
)
def test_dedicated_backend_takes_precedence_over_fallback(rf):
    # The dedicated backend's marker text, not the annotations fallback's.
    assert _search(rf)["items"][0]["body"]["value"] == "match for bird"


# --- manifest advertisement --------------------------------------------------

class FakeFile:
    def close(self):
        pass


def _patch_dimensions(monkeypatch):
    monkeypatch.setattr(views.default_storage, "open", lambda name: FakeFile())
    monkeypatch.setattr(views, "get_image_dimensions", lambda image: (4000, 3000))


@override_settings(IIIF_SEARCH_BACKEND=_search_backend)
def test_manifest_advertises_search_service(monkeypatch, rf):
    _patch_dimensions(monkeypatch)
    body = json.loads(views.serve_manifest(rf.get("/iiif/photo.jpg/manifest"), "photo.jpg").content)
    assert body["service"] == [
        {"id": "http://testserver/iiif/photo.jpg/search", "type": "SearchService2"}
    ]
    # A search-only backend adds no annotations reference.
    assert "annotations" not in body["items"][0]
