# Installation

## Requirements

- **Python** 3.10+
- **Django** (installed automatically as a dependency)
- A running **IIIF Image API server** to serve the actual image pixels (djiiif
  builds URLs and documents that point at it; see {doc}`index`).

## Install

```console
$ pip install djiiif
```

### Optional extras

| Extra | Install | Adds |
| ----- | ------- | ---- |
| Django REST Framework | `pip install "djiiif[drf]"` | The {doc}`serializer field <drf>` |
| Documentation toolchain | `pip install "djiiif[docs]"` | Sphinx + theme for building these docs |
| Full dev toolchain | `pip install -e ".[dev]"` | Tests, build, docs (for contributors) |

The core package never imports DRF, so installing without the `drf` extra keeps
your dependency tree minimal.

## Add djiiif to your project

Add it to `INSTALLED_APPS` — this enables the {ref}`system check <settings-check>`
that validates your configuration, and is required to use the
{ref}`template tags <template-tag>`:

```{code-block} python
:caption: settings.py
INSTALLED_APPS = [
    # ...
    "djiiif",
]
```

To use the optional {doc}`drop-in views <serving>`, include the URLconf:

```{code-block} python
:caption: urls.py
from django.urls import include, path

urlpatterns = [
    path("iiif/", include("djiiif.urls")),
]
```

Continue with the {doc}`quickstart`.
