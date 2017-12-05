
from django.db.models import ImageField
from django.db.models.fields.files import ImageFieldFile
from django.conf import settings
from django import template 
register = template.Library()


@register.simple_tag
def iiif(imagefield, profile):
    return(getattr(imagefield, profile))

