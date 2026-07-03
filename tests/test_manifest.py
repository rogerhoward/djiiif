"""Tests for the Presentation API manifest builder and .iiif.manifest property."""

from django.test import override_settings

from djiiif import IIIFObject, build_manifest


class FakeParent:
    def __init__(self, name, width=None, height=None):
        self.name = name
        self.width = width
        self.height = height


DICT_PROFILES = {
    "thumbnail": {"host": "http://server/", "region": "full", "size": "150,",
                  "rotation": "0", "quality": "default", "format": "jpg"},
}


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_manifest_top_level_shape():
    obj = IIIFObject(FakeParent("uploads/pic.jpg", width=4000, height=3000))
    manifest = obj.manifest
    assert manifest["@context"] == "http://iiif.io/api/presentation/3/context.json"
    assert manifest["type"] == "Manifest"
    assert manifest["id"] == "http://server/uploads%2Fpic.jpg/manifest"
    # Label defaults to the file's base name.
    assert manifest["label"] == {"none": ["pic.jpg"]}


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_manifest_canvas_and_image_body():
    obj = IIIFObject(FakeParent("uploads/pic.jpg", width=4000, height=3000))
    canvas = obj.manifest["items"][0]
    assert canvas["type"] == "Canvas"
    assert (canvas["width"], canvas["height"]) == (4000, 3000)

    body = canvas["items"][0]["items"][0]["body"]
    assert body["id"] == "http://server/uploads%2Fpic.jpg/full/max/0/default.jpg"
    assert body["service"][0] == {
        "id": "http://server/uploads%2Fpic.jpg",
        "type": "ImageService3",
        "profile": "level2",
    }


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_manifest_none_for_empty_field():
    assert IIIFObject(FakeParent("")).manifest is None


def test_build_manifest_v2_service_and_image():
    manifest = build_manifest(
        "http://server/pic.jpg", 100, 200, label="pic.jpg", version=2, level="level1"
    )
    body = manifest["items"][0]["items"][0]["items"][0]["body"]
    assert body["id"] == "http://server/pic.jpg/full/full/0/default.jpg"
    assert body["service"][0] == {
        "@id": "http://server/pic.jpg",
        "@type": "ImageService2",
        "profile": "http://iiif.io/api/image/2/level1.json",
    }
