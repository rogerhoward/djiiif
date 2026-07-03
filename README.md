# djiiif

djiiif is a package designed to make integrating the [IIIF Image API](https://iiif.io/api/image/3.0/) easier by extending Django's ImageField. By defining one or more named "profiles", your ImageFields expose IIIF-compatible URLs for each profile.

## Why djiiif and not ImageKit

I love ImageKit, but I recently worked on a project where we already had IIIF handling image derivative generation and serving, and Django ImageKit just got in the way. I wanted to still register my source images with Django, but serve them through an [IIIF server](https://github.com/loris-imageserver/loris), and this is what I came up with. I have lots of ideas for improvements here, but the initial release is just a santized version of what I used on my most recent project.

## Installation

`pip install djiiif`

## Examples

First, let's setup a new field (or convert an existing ImageField):

`models.py`
```python
from djiiif import IIIFField

original = IIIFField()
```

Second, configure the relevant settings.

`settings.py`
```python

IIIF_HOST = 'http://server/'

IIIF_PROFILES = {
    'thumbnail':
        {'host': IIIF_HOST, 
        'region': 'full', 
        'size': '150,',
        'rotation': '0',
        'quality': 'default',
        'format': 'jpg'}
}
```


Finally, we can access profile(s) as attributes of the `iiif` attribute on an instance of `original`.

In Python:

```python
print(instance.original.name)
> uploads/filename.jpg

print(instance.original.iiif.thumbnail)
> http://server/uploads%2Ffilename.jpg/full/150,/0/default.jpg
```

(The identifier segment is percent-encoded — slashes become `%2F`, and other reserved characters are encoded too — so the field name occupies a single IIIF path segment.)


In a Django template:

```
<img src="{{ instance.original.iiif.thumbnail }}">
```

As of version 0.15, we can also generate a IIIF info.json URL:

```
print(instance.original.iiif.info)
> http://server/uploads%2Ffilename.jpg/info.json
```

As of version 0.21, we also expose a plain identifier-only URL (host + identifier, with no `/region/size/rotation/quality.format` suffix) — handy for handing the image off to viewers like OpenSeadragon that take just the IIIF identifier:

```
print(instance.original.iiif.identifier)
> http://server/uploads%2Ffilename.jpg
```

As of version 0.24, `iiif.info_document` returns the IIIF `info.json` **document** itself (a `dict`), assembled from the image's own dimensions — as opposed to `iiif.info`, which returns the *URL* of an external `info.json` served by an image server. Both remain available; `.info` is unchanged. This lets a Django view serve a minimal, spec-valid `info.json` without a separate image server:

```python
from django.http import JsonResponse

def image_info(request, pk):
    asset = MyModel.objects.get(pk=pk)
    return JsonResponse(asset.original.iiif.info_document)
```

```python
print(instance.original.iiif.info_document)
> {
>     "@context": "http://iiif.io/api/image/3/context.json",
>     "id": "http://server/uploads/filename.jpg",
>     "type": "ImageService3",
>     "protocol": "http://iiif.io/api/image",
>     "profile": "level2",
>     "width": 4000,
>     "height": 3000,
> }
```

Because it needs real pixel dimensions, accessing `.info_document` reads the image from storage (via `width`/`height`); the URL attributes above never do. For an empty/unset field it returns `None`. Two optional settings control the output:

- `IIIF_IMAGE_API_VERSION` — `3` (default) emits an Image API 3.0 document (`id` / `type: ImageService3`); `2` emits a 2.x document (`@id` / `profile` array).
- `IIIF_COMPLIANCE_LEVEL` — the advertised compliance level, default `"level2"`.

### Typed profiles

As of version 0.24, instead of a raw `dict` you can use the `Profile` dataclass, which carries IIIF Image API 3.0-friendly defaults (`size="max"`) and validates its fields:

```python
from djiiif import Profile

IIIF_PROFILES = {
    "thumbnail": Profile(host=IIIF_HOST, size="150,"),
    "square": Profile(host=IIIF_HOST, region="square", size="256,256"),
}
```

Note the `square` example: IIIF 3.0's `square` region replaces the hand-rolled crop math shown below. `Profile` also handles the two 3.0 features that are easy to get wrong as hand-written strings:

- `mirror=True` prefixes the rotation with `!` (mirrored image).
- `upscale=True` prefixes the size with `^` (permits upscaling beyond the extracted region).

Plain `dict` and callable profiles keep working exactly as before — `Profile` is opt-in, and a callable may return either a `dict` or a `Profile`.

### callable-based profiles

You can also use a callable to dynamically generate a URL. The callable will receive the parent `IIIFFieldFile` (a subclass of `ImageFieldFile`) as its sole parameter, `parent`, and must return a `dict` with the following keys: host, region, size, rotation, quality, and format. Using a callable allows you to implement more complex logic in your profile, including the ability to access the original file's name, width, and height.

An example of a callable-based profile named `square` is below, used to generate a square-cropped image.


```python
def squareProfile(original):
    width, height = original.width, original.height

    if width > height:
        x = int((width - height) / 2)
        y = 0
        w = height
        h = height
        region = '{},{},{},{}'.format(x,y,w,h)
    elif width < height:
        x = 0
        y = int((height - width) / 2)
        w = width
        h = width
        region = '{},{},{},{}'.format(x,y,w,h)
    else:
        region = 'full'

    spec = {'host': IIIF_HOST, 
        'region': region, 
        'size': '256,256',
        'rotation': '0',
        'quality': 'default',
        'format': 'jpg'}
    return spec
```

```python
IIIF_PROFILES = {
    'thumbnail':
        {'host': IIIF_HOST, 
        'region': 'full', 
        'size': '150,',
        'rotation': '0',
        'quality': 'default',
        'format': 'jpg'},
    'preview':
        {'host': IIIF_HOST, 
        'region': 'full', 
        'size': '600,',
        'rotation': '0',
        'quality': 'default',
        'format': 'jpg'},
    'square': squareProfile
}
 ```

### IIIF manifest (Presentation API)

As of version 0.24, `iiif.manifest` returns a minimal single-image [IIIF Presentation API 3.0](https://iiif.io/api/presentation/3.0/) Manifest (a `dict`) wrapping the image on one canvas — ready to hand to a viewer like Mirador or OpenSeadragon:

```python
return JsonResponse(asset.original.iiif.manifest)
```

Like `info_document`, it reads the image's dimensions from storage and returns `None` for an empty field. The manifest is always Presentation 3.0; its embedded image service follows `IIIF_IMAGE_API_VERSION` (`ImageService3` by default, `ImageService2` when set to `2`).

### Serving info.json and manifests from Django

djiiif can also serve the `info.json` and `manifest` documents itself — no separate image server is required for the metadata. Include its URLconf:

```python
from django.urls import include, path

urlpatterns = [
    path("iiif/", include("djiiif.urls")),
]
```

An image stored as `uploads/photo.jpg` is then served at `/iiif/uploads%2Fphoto.jpg/info.json` and `/iiif/uploads%2Fphoto.jpg/manifest`, each with the `application/ld+json` content type and the CORS header IIIF clients expect. Each document's `id` is derived from the request URL, so it always matches where it is served from. The views use the default storage backend and read image dimensions on demand.

> Serving identifiers that contain encoded slashes requires your web server to allow encoded slashes in the path (e.g. Apache's `AllowEncodedSlashes On`); flat identifiers need no such configuration.

### All profiles as a dict (`as_dict`)

`iiif.as_dict()` returns every profile URL keyed by profile name — handy for iterating in a template or building a JSON response:

```python
print(instance.original.iiif.as_dict())
> {"thumbnail": "http://server/uploads%2Ffilename.jpg/full/150,/0/default.jpg"}
```

Pass `include_meta=True` to also include the `info` and `identifier` URLs. For an empty field every value is `""`.

### Django REST Framework support

An optional serializer field is available for [DRF](https://www.django-rest-framework.org/) projects. Install the extra:

```
pip install djiiif[drf]
```

Then serialize an `IIIFField` to its profile URLs (the `as_dict()` mapping):

```python
from rest_framework import serializers
from djiiif.serializers import IIIFSerializerField

class AssetSerializer(serializers.ModelSerializer):
    original = IIIFSerializerField()          # or IIIFSerializerField(include_meta=True)

    class Meta:
        model = Asset
        fields = ["id", "original"]
```

The field is read-only and emits `{"thumbnail": "…", …}`. Importing `djiiif` itself never imports DRF, so the core package stays dependency-free.

### Validating your configuration

With `djiiif` in `INSTALLED_APPS`, `manage.py check` validates `IIIF_PROFILES` at startup — flagging a non-`dict` setting, an unsupported profile value, or a `dict` profile missing required keys before it can produce a broken URL. Callable and `Profile` entries are accepted as-is (a callable's shape can only be verified when it runs).

### IIIF authorization (Auth Flow 2.0)

For access-controlled images served by an image server that implements the [IIIF Authorization Flow API 2.0](https://iiif.io/api/auth/2.0/) (e.g. [iiiris](https://iiif.io/api/auth/2.0/)), djiiif can embed the auth **service description** in the `info_document` and `manifest` it generates, so a viewer (Mirador / OpenSeadragon) knows how to authenticate. djiiif only *describes* the services — the image server implements and enforces them.

Configure `IIIF_AUTH` with a `ProbeService` (or a raw `dict`), using the typed helpers to build the nested probe → access → token/logout block:

```python
from djiiif import ProbeService, AccessService, TokenService, LogoutService

IIIF_AUTH = ProbeService(
    id="https://iiiris.example/auth/probe",
    access=AccessService(
        id="https://iiiris.example/auth/login",
        profile="active",                      # or "kiosk" / "external"
        label="Log in to Example Institution",
        heading="Restricted material",
        note="Please log in with your institutional account.",
        confirm_label="Log in",
        token=TokenService(id="https://iiiris.example/auth/token"),
        logout=LogoutService(id="https://iiiris.example/auth/logout", label="Log out"),
    ),
)
```

Label-ish fields accept a plain string, a list of strings, or an already-formed IIIF language map (`{"en": ["…"]}`).

For a **mix of public and restricted** images, set `IIIF_AUTH` to a callable receiving the field file — return the `ProbeService` for restricted images and `None` for public ones:

```python
def image_auth(parent):
    if parent.instance.is_public:
        return None
    return ProbeService(id="https://iiiris.example/auth/probe", access=...)

IIIF_AUTH = image_auth
```

When `IIIF_AUTH` is unset (or the callable returns `None`), documents are unchanged. Authorization Flow 2.0 pairs with Image API 3, so setting `IIIF_AUTH` while `IIIF_IMAGE_API_VERSION = 2` raises `ImproperlyConfigured`.

### IIIF Template Tag

An alternate way to access IIIF URLs for your IIIFField is via the `iiif` template tag.

First, add `djiiif` to your `INSTALLED_APPS`:


```
INSTALLED_APPS = [
    ...
    'djiiif'
]
 ```


Next, load our template tag library `iiiftags` in your template:

```
{% load iiiftags %}
```

Finally, use it in a template:

```
{% iiif asset.original 'thumbnail' %}
```

The first parameter (asset.original) is a reference to an IIIFField instance.

The second parameter ('thumbnail') is the name of one of your IIIF profiles.

This tag syntax is effectively the same as:

```
{{ asset.original.iiif.thumbnail }}
```
