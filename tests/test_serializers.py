"""Tests for the optional DRF serializer field.

Skipped entirely when djangorestframework is not installed; CI installs the
``drf`` extra so these run there.
"""

import pytest
from django.test import override_settings

pytest.importorskip("rest_framework")

from djiiif import IIIFField, IIIFFieldFile  # noqa: E402
from djiiif.serializers import IIIFSerializerField  # noqa: E402

DICT_PROFILES = {
    "thumbnail": {"host": "http://server/", "region": "full", "size": "150,",
                  "rotation": "0", "quality": "default", "format": "jpg"},
}


def _field_file(name):
    return IIIFFieldFile(instance=None, field=IIIFField(), name=name)


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_field_serializes_profile_urls():
    field = IIIFSerializerField()
    assert field.to_representation(_field_file("uploads/x.jpg")) == {
        "thumbnail": "http://server/uploads%2Fx.jpg/full/150,/0/default.jpg",
    }


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_field_include_meta_adds_info_and_identifier():
    field = IIIFSerializerField(include_meta=True)
    data = field.to_representation(_field_file("uploads/x.jpg"))
    assert data["info"] == "http://server/uploads%2Fx.jpg/info.json"
    assert data["identifier"] == "http://server/uploads%2Fx.jpg"


def test_field_is_read_only_by_default():
    assert IIIFSerializerField().read_only is True
