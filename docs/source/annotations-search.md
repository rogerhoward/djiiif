# Annotations & search

These two paired features turn djiiif from "expose my images" into "expose my
annotated corpus": serve W3C Web Annotations (transcriptions, OCR, commentary)
and let viewers search *within* an object. They share one annotation type, and
configuring annotations gives you search for free.

djiiif ships **no annotation model** — storage stays yours (a Django model, an
OCR sidecar, an external annotation server). You provide a backend callable;
djiiif owns the spec-compliant HTTP surface.

## Transcriptions & annotations

Manifests can reference [W3C Web Annotations](https://www.w3.org/TR/annotation-model/)
that viewers like Mirador overlay on the image. Point `IIIF_ANNOTATIONS_BACKEND`
at a callable `(identifier, request)` yielding one annotation per item:

```{code-block} python
:caption: settings.py
IIIF_ANNOTATIONS_BACKEND = "myapp.iiif.annotations"
```

```{code-block} python
:caption: myapp/iiif.py
from urllib.parse import unquote

def annotations(identifier, request):
    name = unquote(identifier)
    for t in Transcription.objects.filter(photo__image=name):
        yield {"text": t.text, "xywh": t.region, "language": t.lang}
```

Each entry is a plain dict (or the {class}`~djiiif.Annotation` dataclass) with
`text` (a string, or a preformed `body` dict), and optional `motivation`
(default `"supplementing"`), `xywh`, `language`, `format`, and `id`.

With the {doc}`URLconf <serving>` mounted, the page is served at
`/iiif/<identifier>/annotations/1`, and the generated manifest's canvas gains an
`annotations` reference to it. Unset backend ⇒ 404.

## Search inside your objects

When a manifest advertises a
[Content Search 2.0](https://iiif.io/api/search/2.0/) service, viewers can search
within the object and highlight matching regions. Point `IIIF_SEARCH_BACKEND` at
a callable `(identifier, q, request)` yielding hits — each an annotation plus
optional snippet context:

```{code-block} python
:caption: settings.py
IIIF_SEARCH_BACKEND = "myapp.iiif.search_ocr"
```

```{code-block} python
:caption: myapp/iiif.py
from urllib.parse import unquote

def search_ocr(identifier, q, request):
    name = unquote(identifier)
    for word in OcrWord.objects.filter(page__image=name, text__search=q):
        yield {
            "text": word.text,
            "canvas_id": f"{request.build_absolute_uri('/iiif/')}{identifier}/canvas/1",
            "xywh": f"{word.x},{word.y},{word.w},{word.h}",
            "exact": word.text, "before": word.prefix, "after": word.suffix,  # optional snippet
        }
```

The endpoint is `/iiif/<identifier>/search?q=...`, and `serve_manifest`
advertises the `SearchService2` automatically. A missing or empty `q` returns a
valid empty page (never the whole corpus); unrecognized spec parameters
(`motivation`/`date`/`user`) are echoed in the response's `ignored` list.

## Free search from your annotations

If you set `IIIF_ANNOTATIONS_BACKEND` but no `IIIF_SEARCH_BACKEND`, `serve_search`
falls back to a **case-insensitive substring match** over your annotations — so
serving transcriptions gives you working search with no extra code:

```
IIIF_ANNOTATIONS_BACKEND set, IIIF_SEARCH_BACKEND unset
        └── /iiif/<id>/search?q=…  →  substring match over annotations
```

A dedicated `IIIF_SEARCH_BACKEND` (e.g. Postgres full-text search) overrides the
fallback. With neither set, the search URL 404s.

:::{note}
Response shapes are pinned against the Content Search 2.0 spec, but viewer
tolerance is the real conformance test — a quick Mirador smoke test is
recommended before you rely on search in production.
:::
