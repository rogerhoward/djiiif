
from django.db.models import ImageField
from django.db.models.fields.files import ImageFieldFile
from django.conf import settings
from django import template 
from djiiif import IIIFObject


class NotAnIIIFField(AttributeError):
    def __init__(self, *args, **kwargs):
        AttributeError.__init__(self, *args, **kwargs)

register = template.Library()


@register.simple_tag
def iiif(imagefield, profile):
    """
    Returns an IIIF URL based on an IIIFField and a profile stored in IIIF_PROFILES.
    """
    try:
        return getattr(imagefield.iiif, profile)
    except AttributeError:
        raise NotAnIIIFField('The iiif template tag expects an instance of a IIIFField as its first parameter.')