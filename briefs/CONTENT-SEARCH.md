# CONTENT-SEARCH — IIIF Content Search API 2.0 (search within a resource)

**Status:** Proposed — all questions resolved, ready to implement (after WEB-ANNOTATIONS)
**Branch:** _none yet (implementation branch TBD)_
**Date:** 2026-07-03

## Problem

Viewers like Mirador and the Universal Viewer can search *within* an object —
highlighting matching regions on the image — when the manifest advertises a
[IIIF Content Search API 2.0](https://iiif.io/api/search/2.0/) service. This is
the feature that makes digitized text (OCR'd pages, transcribed letters,
catalog cards) actually usable. Django is an unusually good host for the server
side: the API is "filter annotations by a `q` parameter and return them as an
AnnotationPage", which maps directly onto the ORM or Postgres full-text search.

djiiif currently has no notion of annotations at all, so this brief has a larger
footprint than the others: it introduces the first *content* (as opposed to
image-derived) data flow. It pairs with the WEB-ANNOTATIONS brief, which defines
where the searchable annotations come from and how they are served outside of
search.

## Background — the shapes involved

- **Service advertisement:** the Manifest (or Canvas) carries
  `"service": [{"id": ".../search", "type": "SearchService2"}]`, optionally with
  a nested `AutoCompleteService2`.
- **Request:** `GET {search}?q=term` (the spec also defines optional
  `motivation`, `date`, `user` parameters; only `q` is required at level 0/1).
- **Response** (shapes verified against the spec, 2026-07-03): an
  `AnnotationPage` with `@context: "http://iiif.io/api/search/2/context.json"`.
  - `items`: the matching W3C Web Annotations, **fully embedded** — each with a
    `body` (typically a `TextualBody` holding the matched text) and a `target`
    (the canvas, usually with an `#xywh=` fragment locating the hit).
  - Hit snippets: an `annotations` array containing an `AnnotationPage` of
    match annotations with `motivation: "contextualizing"`, each targeting a
    `SpecificResource` whose `source` is the matched annotation and whose
    `selector` is a `TextQuoteSelector` with `prefix` / `exact` / `suffix`.
  - Unimplemented request parameters are echoed in an `ignored` list.
- Paging via `partOf` (an `AnnotationCollection` with `total`/`first`/`last`),
  `next`/`prev` page refs, and `startIndex`.

## Scope

**Server-side search over user-provided annotations, with a pluggable backend —
djiiif ships no database models.** The project owns storage (its own annotation
model, an OCR store, an external index); djiiif owns the spec-compliant HTTP
surface and document shapes:

- a search view + URL per identifier,
- the `SearchService2` advertisement in generated manifests,
- response/annotation builders.

Autocomplete (`AutoCompleteService2`) is explicitly phase 2. This keeps the
package model-free (consistent with its identity) while still making a
compliant search endpoint a ~20-line integration.

## Design

- **New optional setting `IIIF_SEARCH_BACKEND`** — a callable
  `(identifier: str, q: str, request) -> iterable` of hits. A hit is a plain
  dict or an instance of the shared frozen **`Annotation` dataclass** defined
  by the WEB-ANNOTATIONS brief (a search hit *is* an annotation plus snippet
  context; one type serves both, normalized by one `resolve_annotation`).
  Fields:
  - `text` — the matched text (annotation body),
  - `canvas_id` — target canvas URI (for djiiif-served manifests:
    `{id_url}/canvas/1`),
  - `xywh` — optional region string locating the hit,
  - `exact` / `before` / `after` — optional snippet context, mapped to the
    match block's `TextQuoteSelector` `exact`/`prefix`/`suffix` (`exact`
    defaults to `q`),
  - `id` — optional stable id (else synthesized from the search URL + index).
- **Fallback backend** (decided with WEB-ANNOTATIONS): when
  `IIIF_SEARCH_BACKEND` is unset but `IIIF_ANNOTATIONS_BACKEND` is set,
  `serve_search` filters that backend's annotations with a case-insensitive
  substring match in Python. One integration point gives small deployments
  search for free; a dedicated backend overrides it for real FTS.

  Example over a project's own OCR model with Postgres FTS:

  ```python
  # settings.py
  IIIF_SEARCH_BACKEND = "myapp.iiif.search_ocr"

  # myapp/iiif.py
  def search_ocr(identifier, q, request):
      name = unquote(identifier)
      for word in OcrWord.objects.filter(page__image=name, text__search=q):
          yield {
              "text": word.text,
              "canvas_id": f"{request.build_absolute_uri('/iiif/')}{identifier}/canvas/1",
              "xywh": f"{word.x},{word.y},{word.w},{word.h}",
          }
  ```

- **Builders** (module-level, pure):
  - `build_search_response(search_url, q, hits, *, ignored=()) -> dict` — the
    AnnotationPage with the search/2 `@context`, the `ignored` list, fully
    embedded hit annotations in `items`, and the match `annotations` block
    (`motivation: "contextualizing"`, `SpecificResource` +
    `TextQuoteSelector`) per the verified shapes above.
  - `build_search_service(search_url) -> dict` — the `SearchService2` block.
- **View + URL**: `GET /iiif/<identifier>/search?q=...` → `serve_search` in
  `djiiif/views.py`, reusing `_ld_json`. Missing or empty `q` ⇒ a valid empty
  AnnotationPage (conservative; returning the full corpus for an empty query
  is a surprise, not a feature). Unrecognized spec parameters
  (`motivation`/`date`/`user`) ⇒ echoed in `ignored`. Neither
  `IIIF_SEARCH_BACKEND` nor `IIIF_ANNOTATIONS_BACKEND` set ⇒ 404.
- **Advertisement**: **view-only** (per Decision 4). When a search backend is
  configured (dedicated or fallback), `serve_manifest` attaches the
  `SearchService2` block at the Manifest level — the view knows the absolute
  search URL, so no URL-derivation setting is needed. `IIIFObject.manifest`
  (no request in scope) emits no search service.

## Non-goals

- Shipping an annotation/OCR model or ingestion pipeline (see WEB-ANNOTATIONS
  brief for the serving side; storage stays project-owned).
- `AutoCompleteService2` (phase 2, additive).
- The optional `motivation` / `date` / `user` request parameters (level > 1);
  they arrive as ignored parameters, correctly reported in the response's
  `ignored` list.
- Cross-resource search (the API is explicitly within-resource).
- Search API 1.0 compatibility.

## Decisions

1. **Result paging** — **single AnnotationPage**, no `partOf`/`next` paging.
   Within-one-object hit counts are small; the spec permits a complete single
   page. Documented; paging is additive later if a real corpus needs it.
2. **Response shapes** — **pinned against the 2.0 spec (2026-07-03)**: single
   search/2 `@context`; embedded annotations in `items`; match block as an
   `annotations` AnnotationPage of `contextualizing` annotations targeting a
   `SpecificResource` with a `TextQuoteSelector` (`prefix`/`exact`/`suffix`).
   A Mirador smoke test still gates the implementation PR (belt and braces —
   viewer tolerance is the real conformance test).
3. **Hit contract** — **dict or the shared `Annotation` dataclass** (defined
   in WEB-ANNOTATIONS, with the `exact`/`before`/`after` snippet fields), one
   `resolve_annotation` normalizer. No separate `SearchHit` type — a hit is an
   annotation.
4. **Advertisement placement** — **Manifest-level only**, attached by
   `serve_manifest` (which knows the absolute search URL). No Canvas-level
   service, no `IIIF_SEARCH_URL` setting for `IIIFObject.manifest` — view-only
   advertisement keeps new configuration at zero; revisit only if someone
   needs search advertised in model-generated manifests.
5. **Empty/missing `q`** — **valid empty AnnotationPage**, never the full
   corpus.
6. **Presentation 4 / paused Search TSG** — no interaction: 2.0 is stable and
   is what viewers implement; nothing here couples to Presentation-version
   specifics.

## Testing (per repo conventions — 90% coverage gate)

- `build_search_response`: contexts, `ignored` parameters, hit annotation shape
  (body/target/xywh fragment), match-block snippets, empty-hit response.
- `build_search_service` shape.
- `serve_search`: happy path (content type, CORS, hits from a stub backend),
  missing/empty `q` → empty page, ignored-parameter echo, neither backend set
  → 404, backend yielding dataclasses and dicts, and the substring-fallback
  path over `IIIF_ANNOTATIONS_BACKEND` (including the dedicated backend taking
  precedence).
- Manifest advertisement: service present when configured (view path), absent
  otherwise (regression pin on current output).

## Docs & compatibility

- **Purely additive** — new setting, new URL, opt-in advertisement; existing
  documents unchanged when unconfigured. No MAJOR bump; `Added` CHANGELOG
  entry.
- `README.md` gains a "Search inside your objects" section with the OCR-model
  recipe; `CLAUDE.md` architecture + required-coverage updated in the same
  commit. Note the pairing with WEB-ANNOTATIONS in both.

## References

- [IIIF Content Search API 2.0](https://iiif.io/api/search/2.0/)
- [Search 2.0 response structure (§4)](https://iiif.io/api/search/2.0/#40-response-structures)
- [W3C Web Annotation Data Model](https://www.w3.org/TR/annotation-model/)
