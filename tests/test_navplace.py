"""Tests for the navPlace extension (djiiif.geo + manifest emission)."""

import json

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, override_settings

from djiiif import IIIFObject, build_manifest
from djiiif import views
from djiiif.geo import resolve_navplace


class FakeParent:
    def __init__(self, name, width=None, height=None):
        self.name = name
        self.width = width
        self.height = height


class FakeGeom:
    """Duck-typed stand-in for a GEOS geometry (``.geojson`` / ``.srid``)."""

    def __init__(self, geojson, srid=4326):
        self.geojson = geojson
        self.srid = srid


DICT_PROFILES = {
    "thumbnail": {"host": "http://server/", "region": "full", "size": "150,",
                  "rotation": "0", "quality": "default", "format": "jpg"},
}

POINT = {"type": "Point", "coordinates": [2.35, 48.85]}
FEATURE = {"type": "Feature", "geometry": POINT, "properties": {"name": "Paris"}}
FEATURE_COLLECTION = {"type": "FeatureCollection", "features": [FEATURE]}

NAVPLACE_CONTEXT = [
    "http://iiif.io/api/extension/navplace/context.json",
    "http://iiif.io/api/presentation/3/context.json",
]


# --- resolve_navplace --------------------------------------------------------

def test_resolve_unset_and_none():
    assert resolve_navplace(FakeParent("p")) is None
    with override_settings(IIIF_NAVPLACE=lambda parent: None):
        assert resolve_navplace(FakeParent("p")) is None


def test_resolve_bare_geometry_wraps_to_feature_collection():
    with override_settings(IIIF_NAVPLACE=lambda parent: POINT):
        fc = resolve_navplace(FakeParent("p"))
    assert fc["type"] == "FeatureCollection"
    assert fc["features"][0] == {"type": "Feature", "geometry": POINT}


def test_resolve_feature_wraps_to_feature_collection():
    with override_settings(IIIF_NAVPLACE=lambda parent: FEATURE):
        fc = resolve_navplace(FakeParent("p"))
    assert fc["features"] == [FEATURE]


def test_resolve_feature_collection_passthrough_copied():
    with override_settings(IIIF_NAVPLACE=lambda parent: FEATURE_COLLECTION):
        fc = resolve_navplace(FakeParent("p"))
    assert fc == FEATURE_COLLECTION
    assert fc is not FEATURE_COLLECTION  # a fresh copy, safe to mutate


def test_resolve_tuple_with_label():
    with override_settings(IIIF_NAVPLACE=lambda parent: (POINT, "Paris")):
        fc = resolve_navplace(FakeParent("p"))
    assert fc["features"][0]["properties"]["label"] == {"none": ["Paris"]}


def test_resolve_geos_duck_typed():
    with override_settings(IIIF_NAVPLACE=lambda parent: FakeGeom(json.dumps(POINT))):
        fc = resolve_navplace(FakeParent("p"))
    assert fc["features"][0]["geometry"] == POINT


def test_resolve_geos_srid_unset_trusted():
    with override_settings(IIIF_NAVPLACE=lambda parent: FakeGeom(json.dumps(POINT), srid=None)):
        assert resolve_navplace(FakeParent("p"))["features"][0]["geometry"] == POINT


def test_resolve_geos_wrong_srid_rejected():
    with override_settings(IIIF_NAVPLACE=lambda parent: FakeGeom(json.dumps(POINT), srid=3857)):
        with pytest.raises(ImproperlyConfigured):
            resolve_navplace(FakeParent("p"))


def test_resolve_bad_type_rejected():
    with override_settings(IIIF_NAVPLACE=lambda parent: 42):
        with pytest.raises(ImproperlyConfigured):
            resolve_navplace(FakeParent("p"))


def test_resolve_unexpected_geojson_type_rejected():
    with override_settings(IIIF_NAVPLACE=lambda parent: {"type": "Nonsense"}):
        with pytest.raises(ImproperlyConfigured):
            resolve_navplace(FakeParent("p"))


def test_resolve_dotted_path_string():
    with override_settings(IIIF_NAVPLACE="tests.test_navplace.point_source"):
        fc = resolve_navplace(FakeParent("p"))
    assert fc["features"][0]["geometry"] == POINT


def point_source(parent):
    return POINT


def test_resolve_direct_value_not_callable():
    # A direct (static) FeatureCollection value, not a callable — consistent with
    # how resolve_info / resolve_auth accept a direct value.
    with override_settings(IIIF_NAVPLACE=FEATURE_COLLECTION):
        assert resolve_navplace(FakeParent("p")) == FEATURE_COLLECTION


def test_resolve_real_geos_geometry():
    try:
        from django.contrib.gis.geos import Point

        point = Point(2.35, 48.85, srid=4326)
        point.geojson  # exercises GDAL; skip when the native libraries are absent
    except (ImportError, ImproperlyConfigured, OSError) as exc:
        pytest.skip(f"GEOS/GDAL native libraries not available: {exc}")
    with override_settings(IIIF_NAVPLACE=lambda parent: point):
        fc = resolve_navplace(FakeParent("p"))
    assert fc["features"][0]["geometry"]["type"] == "Point"


# --- manifest emission -------------------------------------------------------

def test_build_manifest_navplace_and_context():
    manifest = build_manifest(
        "http://s/pic.jpg", 100, 200, label="pic.jpg", nav_place=FEATURE_COLLECTION
    )
    assert manifest["@context"] == NAVPLACE_CONTEXT
    assert manifest["navPlace"]["type"] == "FeatureCollection"


def test_build_manifest_synthesizes_feature_ids():
    fc = {"type": "FeatureCollection", "features": [dict(FEATURE), dict(FEATURE)]}
    manifest = build_manifest("http://s/pic.jpg", 1, 1, label="x", nav_place=fc)
    ids = [f["id"] for f in manifest["navPlace"]["features"]]
    assert ids == [
        "http://s/pic.jpg/manifest/navplace/feature/1",
        "http://s/pic.jpg/manifest/navplace/feature/2",
    ]


def test_build_manifest_preserves_supplied_feature_id():
    fc = {"type": "FeatureCollection", "features": [{**FEATURE, "id": "http://s/f/9"}]}
    manifest = build_manifest("http://s/pic.jpg", 1, 1, label="x", nav_place=fc)
    assert manifest["navPlace"]["features"][0]["id"] == "http://s/f/9"


def test_build_manifest_does_not_mutate_caller_navplace():
    fc = {"type": "FeatureCollection", "features": [dict(FEATURE)]}
    build_manifest("http://s/pic.jpg", 1, 1, label="x", nav_place=fc)
    assert "id" not in fc["features"][0]  # caller's dict untouched


def test_build_manifest_no_navplace_string_context():
    manifest = build_manifest("http://s/pic.jpg", 1, 1, label="x")
    assert manifest["@context"] == "http://iiif.io/api/presentation/3/context.json"
    assert "navPlace" not in manifest


# --- IIIFObject.manifest threading -------------------------------------------

@override_settings(IIIF_PROFILES=DICT_PROFILES, IIIF_NAVPLACE=lambda parent: (POINT, "Paris"))
def test_iiifobject_manifest_threads_navplace():
    manifest = IIIFObject(FakeParent("uploads/pic.jpg", 4000, 3000)).manifest
    assert manifest["@context"] == NAVPLACE_CONTEXT
    assert manifest["navPlace"]["features"][0]["properties"]["label"] == {"none": ["Paris"]}


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_iiifobject_manifest_unset_unchanged():
    manifest = IIIFObject(FakeParent("uploads/pic.jpg", 4000, 3000)).manifest
    assert manifest["@context"] == "http://iiif.io/api/presentation/3/context.json"
    assert "navPlace" not in manifest


# --- serve_manifest threading ------------------------------------------------

class FakeFile:
    def close(self):
        pass


@pytest.fixture
def rf():
    return RequestFactory()


def _navplace_by_name(parent):
    # On the view path, parent is the decoded storage name (a str).
    assert isinstance(parent, str)
    return POINT


@override_settings(IIIF_NAVPLACE=_navplace_by_name)
def test_serve_manifest_threads_navplace(monkeypatch, rf):
    monkeypatch.setattr(views.default_storage, "open", lambda name: FakeFile())
    monkeypatch.setattr(views, "get_image_dimensions", lambda image: (4000, 3000))
    body = json.loads(views.serve_manifest(rf.get("/iiif/photo.jpg/manifest"), "photo.jpg").content)
    assert body["@context"] == NAVPLACE_CONTEXT
    assert body["navPlace"]["features"][0]["geometry"] == POINT
