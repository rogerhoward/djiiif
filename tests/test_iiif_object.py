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
def test_empty_name_returns_empty_strings():
    obj = IIIFObject(FakeParent(""))
    assert obj.thumbnail == ""
    assert obj.info == ""


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_none_name_returns_empty_strings():
    obj = IIIFObject(FakeParent(None))
    assert obj.thumbnail == ""
    assert obj.info == ""


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
