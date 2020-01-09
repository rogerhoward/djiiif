# django-iiif

django-iiif is a package designed to make integrating the [IIIF Image API](http://iiif.io/api/image/2.1/) easier by extending Django's ImageField. By defining one or more named "profiles", your ImageFields expose IIIF-compatible URLs for each profile.

## Why Django-IIIF and not ImageKit

I love ImageKit, but I recently worked on a project where we already had IIIF handling image derivative generation and serving, and Django ImageKit just got in the way. I wanted to still register my source images with Django, but serve them through an [IIIF server](https://github.com/loris-imageserver/loris), and this is what I came up with. I have lots of ideas for improvements here, but the initial release is just a santized version of what I used on my most recent project.

## Installation

`pip install django-iiif`

## Examples

First, let's setup a new field (or convert an existing ImageField):


`models.py`
```python
from django_iiif import IIIFField

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

As of version 0.15, we can also generate a IIIF info.json URL:

```
print(instance.original.iiif.info)
> http://server/uploads/filename.jpg/info.json
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