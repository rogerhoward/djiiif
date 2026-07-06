# Info and manifest documents

Beyond profile URLs, djiiif can build the two JSON documents that IIIF viewers
consume: an Image API **`info.json`** and a Presentation API **`manifest`**.
Unlike the profile URLs, these read the image's real pixel dimensions from
storage.

:::{admonition} URL vs. document
:class: important

`iiif.info` returns the **URL** of an external `info.json` (served by your image
server). `iiif.info_document` returns the **document itself** (a `dict`), built
locally. They are complementary — `.info` is unchanged and always available.
:::

## Metadata URLs

Two lightweight, I/O-free URL attributes:

```pycon
>>> photo.image.iiif.info
'https://images.example.org/uploads%2Fsunset.jpg/info.json'

>>> photo.image.iiif.identifier      # host + identifier, no IIIF suffix
'https://images.example.org/uploads%2Fsunset.jpg'
```

`iiif.identifier` is the plain `{host}/{identifier}` base URL — handy for handing
an image to a viewer like OpenSeadragon that takes just the IIIF identifier.

## `info.json` document

`iiif.info_document` assembles a spec-valid Image API document from the image's
own dimensions, so a Django view can serve `info.json` without a separate image
server:

```{code-block} python
:caption: views.py
from django.http import JsonResponse

def image_info(request, pk):
    photo = Photo.objects.get(pk=pk)
    return JsonResponse(photo.image.iiif.info_document)
```

```pycon
>>> photo.image.iiif.info_document
{'@context': 'http://iiif.io/api/image/3/context.json',
 'id': 'https://images.example.org/uploads%2Fsunset.jpg',
 'type': 'ImageService3',
 'protocol': 'http://iiif.io/api/image',
 'profile': 'level2',
 'width': 4000,
 'height': 3000}
```

Because it needs real dimensions, accessing `.info_document` reads the image from
storage. For an empty/unset field it returns `None`.

## Manifest document

`iiif.manifest` returns a minimal single-image
[Presentation 3.0](https://iiif.io/api/presentation/3.0/) manifest — one image on
one canvas — ready to hand to Mirador, the Universal Viewer, or OpenSeadragon:

```{code-block} python
:caption: views.py
def image_manifest(request, pk):
    photo = Photo.objects.get(pk=pk)
    return JsonResponse(photo.image.iiif.manifest)
```

The label defaults to the file's base name; like `info_document` it reads
dimensions from storage and returns `None` for an empty field. To enrich the
manifest with descriptive metadata, multiple images, or collections, see
{doc}`presentation`.

## Choosing the API version and compliance level

Two settings control the generated document shapes:

```{list-table}
:header-rows: 1

* - Setting
  - Default
  - Effect
* - `IIIF_IMAGE_API_VERSION`
  - `3`
  - `3` → Image API 3.0 (`id` / `type: ImageService3`); `2` → the 2.x shape (`@id` / `profile` array, `ImageService2`)
* - `IIIF_COMPLIANCE_LEVEL`
  - `"level2"`
  - The compliance level advertised in `info_document` and the manifest's image service
```

The manifest is always Presentation 3.0; only its **embedded image service**
follows `IIIF_IMAGE_API_VERSION`. An unknown version raises
`ImproperlyConfigured`.

```{code-block} python
:caption: settings.py
IIIF_IMAGE_API_VERSION = 2
IIIF_COMPLIANCE_LEVEL = "level1"
```

## Enriching info.json

The default `info.json` is deliberately minimal. Set **`IIIF_INFO`** to advertise
the optional Image API properties your image server actually supports — preferred
`sizes`, `tiles` for deep-zoom clients, server size limits, a `rights` URI, and
v3 capability lists:

```{code-block} python
:caption: settings.py
IIIF_INFO = {
    "tiles": [{"width": 512, "scaleFactors": [1, 2, 4, 8]}],
    "max_width": 5000,
    "rights": "http://creativecommons.org/licenses/by/4.0/",
    "preferred_formats": ["webp", "jpg"],
}
```

Keys may be snake_case (above) or spec camelCase (`maxWidth`,
`preferredFormats`, …) — supply each property once; giving both spellings raises
`ImproperlyConfigured`. For per-image values, use a callable — it receives the
`IIIFFieldFile` on the model path and the decoded storage **name** (a `str`) on
the view path:

```{code-block} python
:caption: settings.py
def info_extras(parent):
    w, h = parent.width, parent.height
    return {"sizes": [{"width": w // f, "height": h // f} for f in (8, 4, 2, 1)]}

IIIF_INFO = info_extras
```

The `InfoExtras` dataclass is a typed alternative to the dict. At
`IIIF_IMAGE_API_VERSION = 2` only `sizes`/`tiles` are accepted (v3-only keys
raise `ImproperlyConfigured`). Unset ⇒ output unchanged.

:::{important}
These are **declarations, not measurements**. djiiif emits exactly what you
configure and never probes the image server, so the values must match what that
server really does (its tile size, its maximum request dimensions, …).
:::

Rather than writing these views yourself, you can mount djiiif's
{doc}`drop-in views <serving>`.
