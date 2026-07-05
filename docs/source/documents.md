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

Rather than writing these views yourself, you can mount djiiif's
{doc}`drop-in views <serving>`.
