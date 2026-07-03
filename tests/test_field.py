"""End-to-end tests for the field classes and the URLconf module."""

from django.test import override_settings

from djiiif import IIIFField, IIIFFieldFile, IIIFObject

DICT_PROFILES = {
    "thumbnail": {"host": "http://server/", "region": "full", "size": "150,",
                  "rotation": "0", "quality": "default", "format": "jpg"},
}


@override_settings(IIIF_PROFILES=DICT_PROFILES)
def test_fieldfile_iiif_property_returns_object_with_urls():
    field = IIIFField()
    field_file = IIIFFieldFile(instance=None, field=field, name="uploads/x.jpg")

    iiif = field_file.iiif

    assert isinstance(iiif, IIIFObject)
    assert iiif.thumbnail == "http://server/uploads%2Fx.jpg/full/150,/0/default.jpg"
    assert iiif.identifier == "http://server/uploads%2Fx.jpg"


def test_iiiffield_uses_iiiffieldfile_attr_class():
    assert IIIFField.attr_class is IIIFFieldFile


def test_urlconf_exposes_info_json_pattern():
    from djiiif import urls

    assert urls.app_name == "djiiif"
    names = [p.name for p in urls.urlpatterns]
    assert "info-json" in names
