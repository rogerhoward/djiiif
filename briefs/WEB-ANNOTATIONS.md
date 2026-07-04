# WEB-ANNOTATIONS — serving W3C Web Annotations (transcriptions, OCR, commentary)

**Status:** Proposed — all questions resolved, ready to implement (first of the annotation pair)
**Branch:** _none yet (implementation branch TBD)_
**Date:** 2026-07-03

## Problem

Presentation 3.0 manifests can reference external `AnnotationPage`s via the
Canvas-level `annotations` property — this is how transcriptions, translations,
OCR text, and scholarly commentary get overlaid on images in Mirador et al.
djiiif generates manifests but has no way to (a) serve an AnnotationPage for an
image or (b) reference one from the generated manifest. Adding both turns
djiiif from "expose my images" into "expose my annotated corpus" — and it is
the prerequisite for the CONTENT-SEARCH brief, which searches the same
annotation data.

## Background — the shapes involved

- A Canvas may carry:
  `"annotations": [{"id": ".../annotations/1", "type": "AnnotationPage"}]` — a
  *reference* (id + type only); the page itself is fetched separately.
- The fetched **`AnnotationPage`** (`@context`: W3C anno + Presentation 3) has
  `items`: a list of **`Annotation`** objects, each with:
  - `motivation` — `"supplementing"` (transcription/OCR — the common case for
    non-painting content), `"commenting"`, `"tagging"`, …
  - `body` — typically a `TextualBody` (`{"type": "TextualBody", "value": ...,
    "format": "text/plain", "language": ...}`),
  - `target` — the canvas URI, optionally with `#xywh=` for a region.
- Painting annotations (the image itself) stay in `items`; **non-painting
  content must be in `annotations`** — viewers enforce this split.

## Scope

Same architecture as CONTENT-SEARCH, deliberately symmetric: **a pluggable
backend callable, spec-shape builders, a drop-in view, and opt-in manifest
wiring. djiiif ships no annotation model** — storage stays project-owned (a
Django model, an OCR sidecar file, an external annotation server). Creation/
editing (the W3C Annotation *Protocol*'s write side) is out of scope.

## Design

- **New optional setting `IIIF_ANNOTATIONS_BACKEND`** — a callable
  `(identifier: str, request) -> iterable` of annotations, each a plain dict
  or a frozen **`Annotation` dataclass** (dual-shape like `Profile`,
  normalized by `resolve_annotation`). This is the single annotation type for
  the package — CONTENT-SEARCH reuses it as its hit type. Fields:
  - `text` — the body value (or a preformed `body` dict for non-textual
    bodies),
  - `motivation` — default `"supplementing"`,
  - `xywh` — optional region on the canvas,
  - `language` / `format` — optional body attributes,
  - `id` — optional stable id (else synthesized `{page_url}/anno/{n}`),
  - `exact` / `before` / `after` — optional search-snippet context; unused
    when serving plain annotation pages, consumed by the search response
    builder.

  ```python
  # settings.py
  IIIF_ANNOTATIONS_BACKEND = "myapp.iiif.annotations"

  # myapp/iiif.py
  def annotations(identifier, request):
      name = unquote(identifier)
      for t in Transcription.objects.filter(photo__image=name):
          yield {"text": t.text, "xywh": t.region, "language": t.lang}
  ```

- **Builders** (module-level, pure):
  - `build_annotation(page_url, index, canvas_id, item) -> dict`
  - `build_annotation_page(page_url, canvas_id, items) -> dict`
- **View + URL**: `GET /iiif/<identifier>/annotations/1` →
  `serve_annotation_page` in `djiiif/views.py`, reusing `_ld_json`. Backend
  unset ⇒ 404. A single page per image to start (`/annotations/1` keeps the URL
  scheme ready for paging later without breakage).
- **Manifest wiring**: when `IIIF_ANNOTATIONS_BACKEND` is configured, the
  canvas in documents produced by `serve_manifest` gains the `annotations`
  reference (the view knows the absolute page URL). As with search,
  `IIIFObject.manifest` (no request in scope) starts **without** the reference
  unless a future `IIIF_ANNOTATIONS_URL` setting supplies one — view-first
  keeps configuration at zero.
  - The reference is **always emitted** when the backend is configured; an
    empty AnnotationPage is spec-valid, and conditional emission would cost a
    backend call on every manifest render (see Decisions).

## Non-goals

- **Write side** (W3C Web Annotation Protocol POST/PUT/DELETE, LDP containers)
  — djiiif is read-only metadata; an annotation *server* is a different
  project.
- Shipping an annotation model, admin, or ingestion tooling.
- AnnotationCollection paging (multi-page annotation sets) — the `/1` URL
  scheme leaves room.
- Non-text bodies beyond pass-through (a preformed `body` dict is accepted but
  not assisted).

## Decisions

1. **Backend unification with search** — **yes.** When `IIIF_SEARCH_BACKEND`
   is unset but this brief's `IIIF_ANNOTATIONS_BACKEND` is set, `serve_search`
   falls back to a case-insensitive substring filter over these annotations in
   Python. One integration point gives small deployments (a few thousand
   annotations per object) working search for free; a dedicated search backend
   overrides it for real FTS. The fallback is documented, not magical: "if you
   serve annotations, you get search."
2. **Reference emission** — **always emit** the `annotations` reference when
   the backend is configured. An empty page is spec-valid; only-when-nonempty
   would add a backend round-trip to every manifest render. No template tag
   for the page URL — no known use case.
3. **Dataclass shape** — **one shared `Annotation` dataclass** (defined here,
   reused by CONTENT-SEARCH as its hit type) with optional
   `exact`/`before`/`after` snippet fields, and one `resolve_annotation`
   normalizer. No separate `SearchHit` type.
4. **Sequencing** — **implement this brief first, CONTENT-SEARCH immediately
   after**, sharing `Annotation`/`resolve_annotation` and the annotation-shape
   builder. Co-landing both in one minor release is preferred (the search
   fallback makes them feel like one feature), but each remains independently
   shippable.

## Testing (per repo conventions — 90% coverage gate)

- Builders: AnnotationPage/Annotation shapes (contexts, motivation default,
  TextualBody attributes, xywh-fragment targets, synthesized vs supplied ids),
  preformed-`body` pass-through, empty page.
- `serve_annotation_page`: happy path (content type, CORS), backend unset →
  404, dict and dataclass items.
- Manifest wiring: `annotations` reference present in `serve_manifest` output
  when the backend is configured, absent otherwise (regression pin);
  `IIIFObject.manifest` unchanged.

## Docs & compatibility

- **Purely additive** — new setting + URL; manifests gain a block only when
  opted in. No MAJOR bump; `Added` CHANGELOG entry.
- `README.md` gains a "Transcriptions & annotations" section with the model
  recipe; cross-link with the search section. `CLAUDE.md` architecture +
  required-coverage updated in the same commit.

## References

- [W3C Web Annotation Data Model](https://www.w3.org/TR/annotation-model/)
- [Presentation 3.0 `annotations` (§3.4 / Canvas)](https://iiif.io/api/presentation/3.0/#annotations)
- [IIIF Cookbook — simplest annotation recipes](https://iiif.io/api/cookbook/recipe/0266-full-canvas-annotation/)
