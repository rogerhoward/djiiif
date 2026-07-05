# Profiles

A **profile** is a named recipe for a IIIF Image API URL. `IIIF_PROFILES` maps
each profile name to one of three shapes — a plain `dict`, a typed
{class}`~djiiif.Profile`, or a **callable** for per-image logic. Every profile
name becomes an attribute on `.iiif`.

The assembled URL follows the IIIF Image API pattern:

```
{host}/{identifier}/{region}/{size}/{rotation}/{quality}.{format}
```

## Dict profiles

The most explicit shape — every IIIF parameter spelled out:

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

The required keys are `host`, `region`, `size`, `rotation`, `quality`, and
`format`.

## Typed profiles

{class}`~djiiif.Profile` is a frozen dataclass with IIIF Image API 3.0-friendly
defaults, so you only specify what differs:

```{code-block} python
:caption: settings.py
from djiiif import Profile

IIIF_PROFILES = {
    "thumbnail": Profile(host=IIIF_HOST, size="150,"),
    "square":    Profile(host=IIIF_HOST, region="square", size="256,256"),
    "full":      Profile(host=IIIF_HOST),   # region=full, size=max, ...
}
```

The defaults are `region="full"`, `size="max"`, `rotation="0"`,
`quality="default"`, `format="jpg"`.

`Profile` also handles the two 3.0 features that are easy to get wrong as
hand-written strings:

```{list-table}
:header-rows: 1

* - Flag
  - Effect
* - `mirror=True`
  - Prefixes the rotation with `!` (a mirrored image)
* - `upscale=True`
  - Prefixes the size with `^` (permits upscaling beyond the region)
```

```pycon
>>> Profile(host=IIIF_HOST, size="2000,", upscale=True).as_spec()["size"]
'^2000,'
```

:::{note}
The IIIF 3.0 `square` region replaces the hand-rolled square-crop math that the
callable example below shows — prefer it when your image server supports 3.0.
:::

## Callable profiles

For logic that depends on the individual image, use a callable. It receives the
parent `IIIFFieldFile` (an `ImageFieldFile` subclass, so `.name`, `.width`, and
`.height` are available) and returns a `dict` **or** a `Profile`:

```{code-block} python
:caption: settings.py
def square_profile(parent):
    width, height = parent.width, parent.height
    if width > height:
        region = f"{(width - height) // 2},0,{height},{height}"
    elif height > width:
        region = f"0,{(height - width) // 2},{width},{width}"
    else:
        region = "full"
    return {"host": IIIF_HOST, "region": region, "size": "256,256",
            "rotation": "0", "quality": "default", "format": "jpg"}

IIIF_PROFILES = {
    "thumbnail": {"host": IIIF_HOST, "region": "full", "size": "150,",
                  "rotation": "0", "quality": "default", "format": "jpg"},
    "square": square_profile,
}
```

Callables let you compute the region, pick a format per image, or vary the host —
anything you can derive from the field file.

## Identifier encoding

The identifier segment is the field's stored `name`, fully percent-encoded so it
occupies exactly one IIIF path segment:

```pycon
>>> # name == "uploads/sunset final.jpg"
>>> photo.image.iiif.thumbnail
'https://images.example.org/uploads%2Fsunset%20final.jpg/full/150,/0/default.jpg'
```

`/` becomes `%2F`, and spaces, `?`, `#`, `%`, and the rest of the reserved set
are encoded too.

:::{tip}
Serving identifiers that contain encoded slashes from the {doc}`built-in views
<serving>` requires your web server to allow encoded slashes in the path (e.g.
Apache's `AllowEncodedSlashes On`). Flat identifiers need no such configuration.
:::

(template-tag)=
## The `{% iiif %}` template tag

An alternative to `{{ photo.image.iiif.thumbnail }}` for templates. With
`djiiif` in `INSTALLED_APPS`, load the library and pass the field plus a profile
name:

```{code-block} html+django
{% load iiiftags %}

<img src="{% iiif photo.image 'thumbnail' %}">
```

The first argument is an `IIIFField` instance; the second is a profile name.
Passing something that isn't an `IIIFField` raises `NotAnIIIFField`. This is
exactly equivalent to `{{ photo.image.iiif.thumbnail }}`.

## All profiles at once

`iiif.as_dict()` returns every profile URL keyed by name — handy for iterating
in a template or building a JSON response:

```pycon
>>> photo.image.iiif.as_dict()
{'thumbnail': 'https://images.example.org/uploads%2Fsunset.jpg/full/150,/0/default.jpg',
 'square':    'https://images.example.org/uploads%2Fsunset.jpg/256,0,768,768/256,256/0/default.jpg'}
```

Pass `include_meta=True` to also include the `info` and `identifier` URLs (see
{doc}`documents`). For an empty field every value is `""`.
