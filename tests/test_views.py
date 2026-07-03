"""Tests for the info.json serving view.

Storage and image measurement are monkeypatched so the tests need neither a
real MEDIA_ROOT nor Pillow, matching the DB-free style of the rest of the suite.
"""

import json

import pytest
from django.http import Http404
from django.test import RequestFactory

from djiiif import views


class FakeFile:
    def close(self):
        pass


@pytest.fixture
def rf():
    return RequestFactory()


def _patch(monkeypatch, *, dimensions, open_raises=None):
    def fake_open(name):
        if open_raises is not None:
            raise open_raises
        return FakeFile()

    monkeypatch.setattr(views.default_storage, "open", fake_open)
    monkeypatch.setattr(views, "get_image_dimensions", lambda image: dimensions)


def test_serve_info_json_returns_document(monkeypatch, rf):
    _patch(monkeypatch, dimensions=(400, 300))
    request = rf.get("/iiif/photo.jpg/info.json")

    response = views.serve_info_json(request, "photo.jpg")

    assert response["Content-Type"] == "application/ld+json"
    assert response["Access-Control-Allow-Origin"] == "*"
    body = json.loads(response.content)
    assert body["id"] == "http://testserver/iiif/photo.jpg"
    assert body["type"] == "ImageService3"
    assert (body["width"], body["height"]) == (400, 300)


def test_serve_info_json_404_when_missing(monkeypatch, rf):
    _patch(monkeypatch, dimensions=(1, 1), open_raises=FileNotFoundError())
    with pytest.raises(Http404):
        views.serve_info_json(rf.get("/iiif/x.jpg/info.json"), "x.jpg")


def test_serve_info_json_404_when_not_an_image(monkeypatch, rf):
    _patch(monkeypatch, dimensions=(None, None))
    with pytest.raises(Http404):
        views.serve_info_json(rf.get("/iiif/x.txt/info.json"), "x.txt")


def test_serve_manifest_returns_document(monkeypatch, rf):
    _patch(monkeypatch, dimensions=(4000, 3000))
    request = rf.get("/iiif/photo.jpg/manifest")

    response = views.serve_manifest(request, "photo.jpg")

    assert response["Content-Type"] == "application/ld+json"
    assert response["Access-Control-Allow-Origin"] == "*"
    body = json.loads(response.content)
    assert body["type"] == "Manifest"
    assert body["id"] == "http://testserver/iiif/photo.jpg/manifest"
    assert body["label"] == {"none": ["photo.jpg"]}
    canvas = body["items"][0]
    assert (canvas["width"], canvas["height"]) == (4000, 3000)


def test_serve_manifest_404_when_missing(monkeypatch, rf):
    _patch(monkeypatch, dimensions=(1, 1), open_raises=FileNotFoundError())
    with pytest.raises(Http404):
        views.serve_manifest(rf.get("/iiif/x.jpg/manifest"), "x.jpg")
