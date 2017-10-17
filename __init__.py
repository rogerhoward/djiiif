
from django.db.models import ImageField
from django.db.models.fields.files import ImageFieldFile
from django.conf import settings

from .util import urljoin


class IIIFObject(object):
    def __init__(self, parent):

        for name in settings.IIIF_PROFILES:

            profile = settings.IIIF_PROFILES[name]

            if type(profile) is dict:
                iiif = profile
            elif callable(profile):
                iiif = profile(parent)

            url = urljoin([iiif['host'], parent.name, iiif['region'], iiif['size'], iiif['rotation'], '{}.{}'.format(iiif['quality'], iiif['format'])])
            setattr(self, name, url)


class IIIFFieldFile(ImageFieldFile):
    @property
    def iiif(self):
        return IIIFObject(self)

    def __init__(self, *args, **kwargs):
        super(IIIFFieldFile, self).__init__(*args, **kwargs)


class IIIFField(ImageField):

    attr_class = IIIFFieldFile

    def __init__(self, *args, **kwargs):
        super(IIIFField, self).__init__(*args, **kwargs)
