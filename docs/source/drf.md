# Django REST Framework

An optional serializer field is available for
[DRF](https://www.django-rest-framework.org/) projects. Install the extra:

```console
$ pip install "djiiif[drf]"
```

Then serialize an `IIIFField` to its profile URLs (the `as_dict()` mapping):

```{code-block} python
:caption: serializers.py
from rest_framework import serializers
from djiiif.serializers import IIIFSerializerField

class PhotoSerializer(serializers.ModelSerializer):
    image = IIIFSerializerField()          # or IIIFSerializerField(include_meta=True)

    class Meta:
        model = Photo
        fields = ["id", "image"]
```

The field is read-only and emits the profile mapping:

```json
{
  "id": 1,
  "image": {
    "thumbnail": "https://images.example.org/uploads%2Fsunset.jpg/full/150,/0/default.jpg",
    "preview":   "https://images.example.org/uploads%2Fsunset.jpg/full/600,/0/default.jpg"
  }
}
```

Pass `include_meta=True` to also include the `info` and `identifier` URLs.

:::{note}
Importing `djiiif` itself never imports DRF — the core package stays
dependency-free. The serializer lives in `djiiif.serializers`, which you import
only when you use it.
:::
