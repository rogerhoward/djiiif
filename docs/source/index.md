# djiiif

**djiiif** makes it easy to expose your Django images through the
[IIIF](https://iiif.io/) (International Image Interoperability Framework) family
of APIs. It extends Django's `ImageField` so that, by defining one or more named
**profiles**, every image field gains ready-made IIIF URLs — and, optionally,
spec-compliant `info.json`, Presentation manifests, collections, activity
streams, annotations, and search, served straight from Django.

```{code-block} python
:caption: models.py
from djiiif import IIIFField

class Photo(models.Model):
    image = IIIFField(upload_to="uploads/")
```

```{code-block} python
:caption: settings.py
IIIF_HOST = "https://images.example.org/"

IIIF_PROFILES = {
    "thumbnail": {"host": IIIF_HOST, "region": "full", "size": "150,",
                  "rotation": "0", "quality": "default", "format": "jpg"},
}
```

```pycon
>>> photo.image.iiif.thumbnail
'https://images.example.org/uploads%2Fsunset.jpg/full/150,/0/default.jpg'
```

That's the whole idea: your image server does the pixel work; djiiif builds the
correct IIIF URLs and documents for it.

## What djiiif gives you

- **Profile URLs** — one IIIF Image API URL per named profile, as attributes on
  `.iiif` ({doc}`profiles`).
- **Documents** — build a spec-valid `info.json` and a Presentation 3.0
  `manifest` from an image's own dimensions ({doc}`documents`).
- **Drop-in views** — serve `info.json`, manifests, and collections from Django
  with the correct content type and CORS ({doc}`serving`).
- **Share links** — Content State deep links that open an image, zoomed to a
  region, in a viewer ({doc}`content-state`).
- **Richer manifests** — descriptive metadata, multi-image objects, and
  collections ({doc}`presentation`).
- **Harvestable streams** — a Change Discovery activity stream so aggregators
  can find what changed ({doc}`discovery`).
- **Annotations & search** — serve transcriptions/OCR and search within an
  object ({doc}`annotations-search`).
- **Authorization** — advertise IIIF Authorization Flow 2.0 services
  ({doc}`auth`).
- **DRF & templates** — a serializer field ({doc}`drf`) and a template tag
  ({doc}`profiles`).

Every feature beyond the core profile URLs is **opt-in** and
**backwards-compatible** — nothing changes in your output until you configure it.

## Where djiiif fits

djiiif does **not** process or serve image pixels. You pair it with a real IIIF
image server — [iiiris](https://gitlab.com/iiiris-org/iiiris) is the recommended
one (IIIF Image API 3.0 + Authorization Flow 2.0), though any IIIF-compliant
server or cloud IIIF service works.
djiiif registers your source images with Django and produces the IIIF URLs and
JSON documents that point at that server — plus, if you want, the Presentation,
Discovery, Annotation, and Search documents the image server itself doesn't
provide.

```{toctree}
:maxdepth: 2
:caption: Getting started

installation
quickstart
```

```{toctree}
:maxdepth: 2
:caption: Guides

profiles
documents
serving
content-state
presentation
discovery
annotations-search
auth
drf
```

```{toctree}
:maxdepth: 2
:caption: Reference

settings
api
changelog
```
