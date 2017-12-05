
from django.db.models import ImageField
from django.db.models.fields.files import ImageFieldFile
from django.conf import settings
from django import template 
from djiiif import IIIFObject

register = template.Library()


@register.simple_tag
def iiif(imagefield, profile):
    if isinstance(imagefield, IIIFObject):
        return(getattr(imagefield.iiif, profile))
    else:
        return None