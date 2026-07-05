# Serving IIIF documents from Django

djiiif ships an optional URLconf and a set of drop-in views so a Django instance
can serve IIIF documents itself — no separate image server needed for the
metadata. Each returns `application/ld+json` with the permissive
`Access-Control-Allow-Origin: *` header that IIIF clients require, and derives
the document `id` from the request URL so it always matches where it is served.

## Mount the URLconf

```{code-block} python
:caption: urls.py
from django.urls import include, path

urlpatterns = [
    path("iiif/", include("djiiif.urls")),
]
```

## Endpoints

```{list-table}
:header-rows: 1

* - URL (under `/iiif/`)
  - View
  - Requires
* - `<identifier>/info.json`
  - `serve_info_json`
  - a stored image
* - `<identifier>/manifest`
  - `serve_manifest`
  - a stored image
* - `collection`
  - `serve_collection`
  - `IIIF_COLLECTION_SOURCE` ({doc}`presentation`)
* - `activity/collection`, `activity/page/<n>`
  - `serve_activity_collection` / `serve_activity_page`
  - `IIIF_ACTIVITY_SOURCE` ({doc}`discovery`)
* - `<identifier>/annotations/1`
  - `serve_annotation_page`
  - `IIIF_ANNOTATIONS_BACKEND` ({doc}`annotations-search`)
* - `<identifier>/search?q=`
  - `serve_search`
  - a search or annotations backend ({doc}`annotations-search`)
```

The `info.json` and `manifest` views map an identifier back to a stored image via
Django's default storage and read its dimensions on demand. The other endpoints
read no image storage — they render project-supplied data.

An image stored as `uploads/photo.jpg` is served at:

```
/iiif/uploads%2Fphoto.jpg/info.json
/iiif/uploads%2Fphoto.jpg/manifest
```

## 404 behavior

Every settings-driven endpoint is **invisible until configured** — if its
setting is unset, the URL returns `404`. The `info.json` and `manifest` views
`404` when the identifier does not resolve to a readable image.

:::{tip}
Serving identifiers that contain encoded slashes requires your web server to
allow encoded slashes in the path (e.g. Apache's `AllowEncodedSlashes On`); flat
identifiers need no such configuration.
:::

## Storage

The built-in views use Django's **default storage** backend. If your media lives
elsewhere, either configure default storage accordingly or write thin views that
call the {doc}`builders <api>` directly with your own storage.
