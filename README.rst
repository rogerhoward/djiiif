
# djiiif

djiiif is a package designed to make integrating the [IIIF Image API](http://iiif.io/api/image/2.1/) easier by extending Django's ImageField. By defining one or more named "profiles", your ImageFields expose IIIF-compatible URLs for each profile.

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
> http://server/uploads/filename.jpg/full/150,/0/default.jpg
```


In a Django template:

```
<img src="{{ instance.original.iiif.thumbnail }}">
```

As of version 0.15, there's a IIIF info.json URL in the info property:

```
print(instance.original.iiif.info)
> http://server/uploads/filename.jpg/info.json
```

As of version 0.21, there's a IIIF URL with just the identifier, great for OpenSeadragon use:

```
print(instance.original.iiif.identifier)
> http://server/uploads/filename.jpg
```

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
