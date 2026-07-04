
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


@register.simple_tag
def iiif_content_state(imagefield, xywh=None):
    """Returns an encoded IIIF Content State for an IIIFField deep link.

    Drop the result into ``?iiif-content=`` to open the image — optionally zoomed
    to the ``xywh`` region — in a manifest-aware viewer.

    Args:
        imagefield: An ``IIIFField`` instance (its ``.iiif`` accessor is used).
        xywh: An optional ``"x,y,w,h"`` region string.

    Raises:
        NotAnIIIFField: If ``imagefield`` is not an ``IIIFField`` instance.
    """
    try:
        iiif = imagefield.iiif
    except AttributeError:
        raise NotAnIIIFField(
            'The iiif_content_state template tag expects an instance of a IIIFField '
            'as its first parameter.'
        )
    return iiif.content_state(xywh=xywh)