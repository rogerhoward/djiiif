# CONTENT-SEARCH — IIIF Content Search API 2.0 (search within a resource)

**Status:** Proposed
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
- **Response:** an `AnnotationPage` (context: search 2 + presentation 3) whose
  `items` are W3C Web Annotations — each with a `body` (the matched text) and a
  `target` (the canvas, usually with an `#xywh=` fragment locating the hit) —
  plus an `annotations` block of `TextQuoteSelector` "match" hints
  (`ignored`/`before`/`after`) that viewers use for hit snippets.
- Paging via `partOf`/`next` when result sets are large.

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
  `(identifier: str, q: str, request) -> iterable` of **hit dicts** (or typed
  `SearchHit` dataclasses, mirroring the `Profile` dual-shape pattern), each
  providing:
  - `text` — the matched text (annotation body),
  - `canvas_id` — target canvas URI (for djiiif-served manifests:
    `{id_url}/canvas/1`),
  - `xywh` — optional region string locating the hit,
  - `before` / `after` — optional snippet context for the match block,
  - `annotation_id` — optional stable id (else synthesized from the search URL
    + index).

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
  - `build_search_response(search_url, q, hits) -> dict` — the AnnotationPage
    with correct dual `@context`, `ignored` params, per-hit annotations
    (`motivation: painting`… actually `highlighting` is v1; **2.0 uses
    `motivation` from the source annotation, default none**) and the match
    `annotations` block. Exact motivations to be pinned against the spec during
    implementation (see Open questions).
  - `build_search_service(search_url) -> dict` — the `SearchService2` block.
- **View + URL**: `GET /iiif/<identifier>/search?q=...` → `serve_search` in
  `djiiif/views.py`, reusing `_ld_json`. Missing `q` ⇒ empty result page (spec:
  empty query returns all / implementation-defined — pin during
  implementation). `IIIF_SEARCH_BACKEND` unset ⇒ 404.
- **Advertisement**: when `IIIF_SEARCH_BACKEND` is configured **and** a search
  URL can be derived, `build_manifest`/`serve_manifest` attach the
  `SearchService2` block at the Manifest level. For `IIIFObject.manifest`
  (which has no request), the search URL comes from an optional
  `IIIF_SEARCH_URL` callable/format setting — or the service is only attached
  by the view, where the URL is known. Leaning: **view-only advertisement** to
  start (zero new URL-derivation config).

## Non-goals

- Shipping an annotation/OCR model or ingestion pipeline (see WEB-ANNOTATIONS
  brief for the serving side; storage stays project-owned).
- `AutoCompleteService2` (phase 2, additive).
- The optional `motivation` / `date` / `user` request parameters (level > 1);
  they arrive as ignored parameters, correctly reported in the response's
  `ignored` list.
- Cross-resource search (the API is explicitly within-resource).
- Search API 1.0 compatibility.

## Open questions

1. **Result paging** — return everything in one AnnotationPage (fine for
   within-object hit counts) vs `Paginator`-backed `next`/`partOf` pages from
   day one. Leaning: single page + documented limit, matching the spec's
   allowance.
2. **Exact motivation/context details** in 2.0 responses (differences from 1.0
   are subtle — e.g. `TextQuoteSelector` replacing 1.0's `hits`). Pin against
   the spec + a Mirador smoke test during implementation.
3. **Hit contract** — dicts only, or dict + frozen `SearchHit` dataclass with
   `resolve_hit(...)` normalization (consistent with `Profile`/`ProbeService`)?
   Leaning: both, it is ~15 lines.
4. **Advertisement placement** — manifest-level only, or also on the Canvas?
   Manifest-level is what viewers key on; start there.
5. Interaction with the paused Content Search TSG / Presentation 4: none
   expected — 2.0 is stable and is what viewers implement today.

## Testing (per repo conventions — 90% coverage gate)

- `build_search_response`: contexts, `ignored` parameters, hit annotation shape
  (body/target/xywh fragment), match-block snippets, empty-hit response.
- `build_search_service` shape.
- `serve_search`: happy path (content type, CORS, hits from a stub backend),
  missing `q`, backend unset → 404, backend yielding dataclasses and dicts.
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
