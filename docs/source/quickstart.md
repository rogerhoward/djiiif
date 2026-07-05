# Quickstart

This walks through the smallest useful setup: a model with an IIIF image field,
one profile, and the URLs you get back.

## 1. Use `IIIFField` on your model

`IIIFField` is a drop-in subclass of Django's `ImageField` — swap it in on a new
field, or convert an existing `ImageField`:

```{code-block} python
:caption: models.py
from django.db import models
from djiiif import IIIFField

class Photo(models.Model):
    title = models.CharField(max_length=200)
    image = IIIFField(upload_to="uploads/")
```

Because it *is* an `ImageField`, uploads, storage, `width`/`height`, and
migrations all behave exactly as you already expect.

## 2. Define profiles

A **profile** is a named recipe for a IIIF Image API URL. Configure one or more
in `settings.py`:

```{code-block} python
:caption: settings.py
IIIF_HOST = "https://images.example.org/"

IIIF_PROFILES = {
    "thumbnail": {"host": IIIF_HOST, "region": "full", "size": "150,",
                  "rotation": "0", "quality": "default", "format": "jpg"},
    "preview":   {"host": IIIF_HOST, "region": "full", "size": "600,",
                  "rotation": "0", "quality": "default", "format": "jpg"},
}
```

Each key becomes an attribute on `.iiif`. See {doc}`profiles` for the typed
`Profile` shape and per-image callables.

## 3. Read the URLs

Every profile is available as an attribute of the field's `.iiif` accessor:

```pycon
>>> photo.image.name
'uploads/sunset.jpg'

>>> photo.image.iiif.thumbnail
'https://images.example.org/uploads%2Fsunset.jpg/full/150,/0/default.jpg'

>>> photo.image.iiif.preview
'https://images.example.org/uploads%2Fsunset.jpg/full/600,/0/default.jpg'
```

The identifier segment (`uploads%2Fsunset.jpg`) is fully percent-encoded so the
field name occupies a single IIIF path segment — slashes become `%2F`, and other
reserved characters are encoded too.

In a template:

```{code-block} html+django
<img src="{{ photo.image.iiif.thumbnail }}">
```

Or with the {ref}`template tag <template-tag>`:

```{code-block} html+django
{% load iiiftags %}
<img src="{% iiif photo.image 'thumbnail' %}">
```

## 4. Safe on empty fields

Accessing `.iiif` on an empty/unset field never raises — every profile attribute
returns the empty string `""`, so templates stay clean:

```pycon
>>> blank.image.iiif.thumbnail
''
```

## Next steps

- {doc}`profiles` — typed profiles, per-image callables, the template tag.
- {doc}`documents` — build `info.json` and Presentation manifests.
- {doc}`serving` — serve those documents straight from Django.
