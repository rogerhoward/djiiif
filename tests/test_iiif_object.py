import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from djiiif import IIIFObject


class FakeParent:
    def __init__(self, name, width=None, height=None):
        self.name = name
        self.width = width
        self.height = height


DICT_PROFILES = {
    "thumbnail": {
        "host": "http://server/",
        "region": "full",
        "size": "150,",
        "rotation": "0",
        "quality": "default",
        "format": "jpg",
    },
}


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_dict_profile_builds_url():
    obj = IIIFObject(FakeParent("uploads/file.jpg"))
    assert obj.thumbnail == "http://server/uploads%2Ffile.jpg/full/150,/0/default.jpg"


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_info_url_present():
    obj = IIIFObject(FakeParent("uploads/file.jpg"))
    assert obj.info == "http://server/uploads%2Ffile.jpg/info.json"


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_identifier_url_present():
    obj = IIIFObject(FakeParent("uploads/file.jpg"))
    assert obj.identifier == "http://server/uploads%2Ffile.jpg"


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_empty_name_returns_empty_strings():
    obj = IIIFObject(FakeParent(""))
    assert obj.thumbnail == ""
    assert obj.info == ""
    assert obj.identifier == ""


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_none_name_returns_empty_strings():
    obj = IIIFObject(FakeParent(None))
    assert obj.thumbnail == ""
    assert obj.info == ""
    assert obj.identifier == ""


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_identifier_percent_encodes_slashes():
    obj = IIIFObject(FakeParent("a/b/c.jpg"))
    assert "a%2Fb%2Fc.jpg" in obj.thumbnail
    assert "/" not in obj.thumbnail.split("http://server/")[1].split("/")[0]


def _square_profile(parent):
    return {
        "host": "http://server/",
        "region": f"0,0,{parent.width},{parent.height}",
        "size": "256,256",
        "rotation": "0",
        "quality": "default",
        "format": "jpg",
    }


@override_settings(IIIF_PROFILES={"square": _square_profile})
def test_callable_profile_receives_parent_and_builds_url():
    obj = IIIFObject(FakeParent("file.jpg", width=400, height=300))
    assert obj.square == "http://server/file.jpg/0,0,400,300/256,256/0/default.jpg"


@override_settings(
    IIIF_PROFILES={
        "thumb": DICT_PROFILES["thumbnail"],
        "square": _square_profile,
    }
)
def test_multiple_profiles_coexist():
    obj = IIIFObject(FakeParent("pic.jpg", width=100, height=200))
    assert obj.thumb.endswith("/full/150,/0/default.jpg")
    assert obj.square.endswith("/0,0,100,200/256,256/0/default.jpg")


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_info_document_defaults_to_v3():
    obj = IIIFObject(FakeParent("uploads/file.jpg", width=400, height=300))
    assert obj.info_document == {
        "@context": "http://iiif.io/api/image/3/context.json",
        "id": "http://server/uploads%2Ffile.jpg",
        "type": "ImageService3",
        "protocol": "http://iiif.io/api/image",
        "profile": "level2",
        "width": 400,
        "height": 300,
    }


@override_settings(IIIF_PROFILES=DICT_PROFILES, IIIF_IMAGE_API_VERSION=2)
def test_info_document_v2_shape():
    obj = IIIFObject(FakeParent("uploads/file.jpg", width=400, height=300))
    assert obj.info_document == {
        "@context": "http://iiif.io/api/image/2/context.json",
        "@id": "http://server/uploads%2Ffile.jpg",
        "protocol": "http://iiif.io/api/image",
        "profile": ["http://iiif.io/api/image/2/level2.json"],
        "width": 400,
        "height": 300,
    }


@override_settings(IIIF_PROFILES=DICT_PROFILES, IIIF_COMPLIANCE_LEVEL="level1")
def test_info_document_honors_compliance_level():
    obj = IIIFObject(FakeParent("file.jpg", width=10, height=10))
    assert obj.info_document["profile"] == "level1"


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_info_document_none_for_empty_field():
    assert IIIFObject(FakeParent("")).info_document is None
    assert IIIFObject(FakeParent(None)).info_document is None


@override_settings(IIIF_PROFILES=DICT_PROFILES, IIIF_IMAGE_API_VERSION=99)
def test_info_document_rejects_unknown_version():
    obj = IIIFObject(FakeParent("file.jpg", width=10, height=10))
    with pytest.raises(ImproperlyConfigured):
        obj.info_document


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_info_url_unchanged_alongside_document():
    # .info remains the external info.json URL, independent of .info_document.
    obj = IIIFObject(FakeParent("uploads/file.jpg", width=400, height=300))
    assert obj.info == "http://server/uploads%2Ffile.jpg/info.json"
