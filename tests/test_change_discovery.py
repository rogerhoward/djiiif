"""Tests for the IIIF Change Discovery API 1.0 stream (builders + views)."""

import json
from datetime import datetime, timezone

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.test import RequestFactory, override_settings

from djiiif import (
    Activity,
    build_activity,
    build_collection_page,
    build_ordered_collection,
    resolve_activity,
)
from djiiif import views


DISCOVERY_CONTEXT = [
    "http://iiif.io/api/discovery/1/context.json",
    "https://www.w3.org/ns/activitystreams",
]


def _dt(day):
    return datetime(2020, 1, day, 12, 0, 0, tzinfo=timezone.utc)


# A module-level source reachable by dotted path (exercises import_string).
def sample_activities():
    return [
        {"object_id": f"http://server/iiif/{i}/manifest", "end_time": _dt(i)}
        for i in range(1, 6)
    ]


class FakeQuerySet:
    """A sliceable, count()-able stand-in for a Django queryset (no DB)."""

    def __init__(self, data):
        self._data = data

    def count(self):
        return len(self._data)

    def __getitem__(self, item):
        return self._data[item]


# --- builders ----------------------------------------------------------------

def test_build_activity_datetime_and_shape():
    activity = build_activity("http://server/m", _dt(2))
    assert activity == {
        "type": "Update",
        "object": {"id": "http://server/m", "type": "Manifest"},
        "endTime": "2020-01-02T12:00:00+00:00",
    }


def test_build_activity_string_time_and_overrides():
    activity = build_activity(
        "http://server/c", "2020-01-02T00:00:00Z", activity_type="Create", object_type="Collection"
    )
    assert activity["type"] == "Create"
    assert activity["object"] == {"id": "http://server/c", "type": "Collection"}
    assert activity["endTime"] == "2020-01-02T00:00:00Z"


def test_build_ordered_collection_shape():
    coll = build_ordered_collection(
        "http://server/act/collection", 21, "http://s/page/1", "http://s/page/3"
    )
    assert coll["@context"] == DISCOVERY_CONTEXT
    assert coll["type"] == "OrderedCollection"
    assert coll["totalItems"] == 21
    assert coll["first"] == {"id": "http://s/page/1", "type": "OrderedCollectionPage"}
    assert coll["last"] == {"id": "http://s/page/3", "type": "OrderedCollectionPage"}


def test_build_collection_page_boundaries():
    first = build_collection_page(
        "http://s/page/1", "http://s/collection", [], next_url="http://s/page/2"
    )
    assert first["partOf"] == {"id": "http://s/collection", "type": "OrderedCollection"}
    assert "prev" not in first
    assert first["next"] == {"id": "http://s/page/2", "type": "OrderedCollectionPage"}

    middle = build_collection_page(
        "http://s/page/2", "http://s/collection", [],
        prev_url="http://s/page/1", next_url="http://s/page/3", start_index=2,
    )
    assert middle["prev"]["id"] == "http://s/page/1"
    assert middle["next"]["id"] == "http://s/page/3"
    assert middle["startIndex"] == 2

    last = build_collection_page(
        "http://s/page/3", "http://s/collection", [], prev_url="http://s/page/2"
    )
    assert "next" not in last
    assert last["prev"]["id"] == "http://s/page/2"


# --- resolve_activity --------------------------------------------------------

def test_resolve_activity_dataclass():
    entry = Activity("http://server/m", _dt(1), type="Create", object_type="Collection")
    assert resolve_activity(entry) == {
        "object_id": "http://server/m",
        "end_time": _dt(1),
        "type": "Create",
        "object_type": "Collection",
    }


def test_resolve_activity_dict_defaults():
    resolved = resolve_activity({"object_id": "http://server/m", "end_time": _dt(1)})
    assert resolved["type"] == "Update"
    assert resolved["object_type"] == "Manifest"


def test_resolve_activity_bad_type_raises():
    with pytest.raises(ImproperlyConfigured):
        resolve_activity(("http://server/m", _dt(1)))


# --- views -------------------------------------------------------------------

@pytest.fixture
def rf():
    return RequestFactory()


def _five_dicts():
    return sample_activities()


@override_settings(IIIF_ACTIVITY_SOURCE=_five_dicts, IIIF_ACTIVITY_PAGE_SIZE=2)
def test_collection_entry_point(rf):
    response = views.serve_activity_collection(rf.get("/iiif/activity/collection"))
    assert response["Content-Type"] == "application/ld+json"
    assert response["Access-Control-Allow-Origin"] == "*"
    body = json.loads(response.content)
    assert body["type"] == "OrderedCollection"
    assert body["id"] == "http://testserver/iiif/activity/collection"
    assert body["totalItems"] == 5
    assert body["first"]["id"] == "http://testserver/iiif/activity/page/1"
    assert body["last"]["id"] == "http://testserver/iiif/activity/page/3"


@override_settings(IIIF_ACTIVITY_SOURCE=_five_dicts, IIIF_ACTIVITY_PAGE_SIZE=2)
def test_first_page_contents_ascending(rf):
    body = json.loads(views.serve_activity_page(rf.get("/iiif/activity/page/1"), 1).content)
    assert body["type"] == "OrderedCollectionPage"
    assert "prev" not in body
    assert body["next"]["id"] == "http://testserver/iiif/activity/page/2"
    assert body["startIndex"] == 0
    ids = [a["object"]["id"] for a in body["orderedItems"]]
    assert ids == ["http://server/iiif/1/manifest", "http://server/iiif/2/manifest"]
    times = [a["endTime"] for a in body["orderedItems"]]
    assert times == sorted(times)


@override_settings(IIIF_ACTIVITY_SOURCE=_five_dicts, IIIF_ACTIVITY_PAGE_SIZE=2)
def test_middle_and_last_page_links(rf):
    middle = json.loads(views.serve_activity_page(rf.get("/iiif/activity/page/2"), 2).content)
    assert middle["prev"]["id"] == "http://testserver/iiif/activity/page/1"
    assert middle["next"]["id"] == "http://testserver/iiif/activity/page/3"
    assert middle["startIndex"] == 2

    last = json.loads(views.serve_activity_page(rf.get("/iiif/activity/page/3"), 3).content)
    assert "next" not in last
    assert last["prev"]["id"] == "http://testserver/iiif/activity/page/2"
    assert len(last["orderedItems"]) == 1


@override_settings(IIIF_ACTIVITY_SOURCE=_five_dicts, IIIF_ACTIVITY_PAGE_SIZE=2)
def test_unknown_page_404(rf):
    with pytest.raises(Http404):
        views.serve_activity_page(rf.get("/iiif/activity/page/9"), 9)
    with pytest.raises(Http404):
        views.serve_activity_page(rf.get("/iiif/activity/page/0"), 0)


def test_activity_stream_404_when_unset(rf):
    with pytest.raises(Http404):
        views.serve_activity_collection(rf.get("/iiif/activity/collection"))
    with pytest.raises(Http404):
        views.serve_activity_page(rf.get("/iiif/activity/page/1"), 1)


@override_settings(IIIF_ACTIVITY_SOURCE=lambda: [])
def test_empty_source_valid_collection(rf):
    coll = json.loads(views.serve_activity_collection(rf.get("/iiif/activity/collection")).content)
    assert coll["totalItems"] == 0
    assert coll["first"]["id"] == "http://testserver/iiif/activity/page/1"
    assert coll["last"]["id"] == "http://testserver/iiif/activity/page/1"

    page = json.loads(views.serve_activity_page(rf.get("/iiif/activity/page/1"), 1).content)
    assert page["orderedItems"] == []
    assert "prev" not in page and "next" not in page


def _generator_source():
    yield from sample_activities()


@override_settings(IIIF_ACTIVITY_SOURCE=_generator_source, IIIF_ACTIVITY_PAGE_SIZE=10)
def test_generator_source_materialized(rf):
    body = json.loads(views.serve_activity_collection(rf.get("/iiif/activity/collection")).content)
    assert body["totalItems"] == 5


@override_settings(
    IIIF_ACTIVITY_SOURCE=lambda: FakeQuerySet(sample_activities()), IIIF_ACTIVITY_PAGE_SIZE=10
)
def test_queryset_shaped_source(rf):
    body = json.loads(views.serve_activity_page(rf.get("/iiif/activity/page/1"), 1).content)
    assert len(body["orderedItems"]) == 5


@override_settings(
    IIIF_ACTIVITY_SOURCE="tests.test_change_discovery.sample_activities", IIIF_ACTIVITY_PAGE_SIZE=10
)
def test_dotted_path_source(rf):
    body = json.loads(views.serve_activity_collection(rf.get("/iiif/activity/collection")).content)
    assert body["totalItems"] == 5


@override_settings(IIIF_ACTIVITY_SOURCE=lambda: [Activity("http://server/m", _dt(1))],
                   IIIF_ACTIVITY_PAGE_SIZE=10)
def test_activity_dataclass_entries(rf):
    body = json.loads(views.serve_activity_page(rf.get("/iiif/activity/page/1"), 1).content)
    assert body["orderedItems"][0]["object"]["id"] == "http://server/m"
    assert body["orderedItems"][0]["type"] == "Update"
