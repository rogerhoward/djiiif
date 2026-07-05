# Richer manifests & collections

The single-image `iiif.manifest` ({doc}`documents`) is deliberately minimal. This
page covers three additive ways to go further with Presentation 3.0: descriptive
metadata, multi-image manifests, and collections. All are opt-in — nothing
changes in your output until you configure them.

## Descriptive metadata

By default a manifest is a bare image on a canvas. Set `IIIF_MANIFEST_DESCRIPTORS`
to a callable — receiving the field file, returning a dict of descriptive
properties (or `None`) — to turn it into a catalog record viewers actually
render:

```{code-block} python
:caption: settings.py
def manifest_descriptors(parent):
    photo = parent.instance
    return {
        "metadata": [("Title", photo.title), ("Date", str(photo.year))],
        "summary": photo.caption,
        "rights": "http://creativecommons.org/licenses/by/4.0/",
        "required_statement": ("Attribution", "Example Institution"),
        "thumbnail": photo.image.iiif.thumbnail,   # an existing profile URL
        "nav_date": photo.created,                 # an aware datetime
    }

IIIF_MANIFEST_DESCRIPTORS = manifest_descriptors
```

A plain dict works too (the same descriptors for every image). Each property is
emitted only when present, so an unset `IIIF_MANIFEST_DESCRIPTORS` leaves the
manifest byte-identical to before.

```{list-table}
:header-rows: 1

* - Descriptor
  - Accepts
* - `metadata`
  - a list of `(label, value)` pairs or preformed dicts
* - `summary`, `required_statement`
  - a string, list, or IIIF language map (`required_statement` is a `(label, value)` pair)
* - `rights`
  - a license/rights URI string
* - `thumbnail`
  - a URL string (wrapped as an Image) or a preformed list
* - `nav_date`
  - an aware `datetime` (serialized ISO 8601)
```

An unknown descriptor key raises `ImproperlyConfigured`. The same keyword
descriptors can be passed directly to `build_manifest(...)`.

## Multi-image objects

A model with several images (recto/verso, a paged object, detail shots) can be
one manifest with several canvases via `build_multi_manifest`:

```{code-block} python
:caption: models.py / a helper
from djiiif import build_multi_manifest

def object_manifest(obj):
    images = [
        (page.image.iiif.identifier, page.image.width, page.image.height)
        for page in obj.pages.all()
    ]
    return build_multi_manifest(obj.iiif_id, images, label=obj.title)
```

Each image spec is a `(service_id_url, width, height)` tuple, or a dict adding an
optional per-canvas `label`. Canvases are indexed (`.../canvas/1`, `/2`, …);
descriptor kwargs and `IIIF_AUTH` apply just as they do for a single-image
manifest. The single-image `build_manifest` is a thin wrapper over
`build_multi_manifest`, so its output is unchanged.

## Collections

A IIIF `Collection` groups manifests for browsing — the natural rendering of a
Django queryset ("all photos in this album"), and the anchor an aggregator points
at. `build_collection` emits **references** to each manifest (never embedded
manifests), so it stays small even for thousands of items:

```{code-block} python
:caption: a helper
from djiiif import build_collection

items = [(p.iiif_manifest_url, p.title) for p in album.photos.all()]
collection = build_collection(album.iiif_url, items, label=album.title)
```

Each item is `(manifest_url, label)` — optionally a third `thumbnail`.

### Serving a collection

To serve one directly, set `IIIF_COLLECTION_SOURCE` to a callable returning such
items; it is exposed at `/iiif/collection` by the {doc}`URLconf <serving>`
(`IIIF_COLLECTION_LABEL` sets the collection's own label; unset source ⇒ 404):

```{code-block} python
:caption: settings.py
def album_items():
    for p in Photo.objects.exclude(image=""):
        yield (p.manifest_url, p.title)

IIIF_COLLECTION_SOURCE = album_items
IIIF_COLLECTION_LABEL = "Example Album"
```
