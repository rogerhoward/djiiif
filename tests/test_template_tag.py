from types import SimpleNamespace

import pytest
from django.template import Context, Template
from django.test import override_settings

from djiiif.templatetags.iiiftags import NotAnIIIFField, iiif as iiif_tag


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


def test_tag_returns_profile_url_from_iiif_attr():
    obj = SimpleNamespace(iiif=SimpleNamespace(thumbnail="http://example/url"))
    assert iiif_tag(obj, "thumbnail") == "http://example/url"


def test_tag_raises_when_input_has_no_iiif():
    with pytest.raises(NotAnIIIFField):
        iiif_tag(SimpleNamespace(), "thumbnail")


def test_tag_raises_when_profile_missing():
    obj = SimpleNamespace(iiif=SimpleNamespace())
    with pytest.raises(NotAnIIIFField):
        iiif_tag(obj, "thumbnail")


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_tag_renders_in_template():
    parent = SimpleNamespace(
        iiif=SimpleNamespace(thumbnail="http://server/uploads%2Ff.jpg/full/150,/0/default.jpg")
    )
    template = Template("{% load iiiftags %}{% iiif asset 'thumbnail' %}")
    rendered = template.render(Context({"asset": parent}))
    assert rendered == "http://server/uploads%2Ff.jpg/full/150,/0/default.jpg"
