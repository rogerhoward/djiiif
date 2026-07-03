# PRESENTATION-ENRICHMENT — richer Presentation 3.0: descriptive metadata, multi-image manifests, Collections

**Status:** Proposed
**Branch:** _none yet (implementation branch TBD)_
**Date:** 2026-07-03

## Problem

djiiif's `build_manifest` / `IIIFObject.manifest` produce a deliberately minimal
manifest: one image, one canvas, a filename label, nothing else. That is enough
to open a viewer, but real-world use immediately wants three more things:

1. **Descriptive properties** — `metadata` (label/value pairs), `rights`,
   `requiredStatement` (attribution), `summary`, `thumbnail`, `navDate`. Without
   these a manifest is a bare image; with them it is a catalog record viewers
   actually render.
2. **Multi-image manifests** — a model with several images (recto/verso, a
   paged object, detail shots) should be presentable as *one* manifest with
   multiple canvases, not N disconnected manifests.
3. **Collections** — a IIIF `Collection` groups manifests for browsing and is
   the natural rendering of a Django queryset ("all photos in this album"). It
   is also the anchor a Change Discovery stream and aggregators point at.

All three deepen the spec djiiif already implements — no new IIIF API, just more
of Presentation 3.0.

## Background

- All descriptive text fields are IIIF **language maps**; the existing
  `_language_map` helper already coerces `str | list | dict` correctly.
- `metadata` is a list of `{"label": <lang-map>, "value": <lang-map>}` pairs.
- `rights` is a single URI string (Creative Commons / RightsStatements.org);
  `requiredStatement` is one label/value pair.
- A multi-image manifest is simply more `Canvas` items — the existing
  single-canvas structure repeated, with per-canvas ids
  (`.../canvas/1`, `/2`, …).
- A `Collection` is `{"type": "Collection", "label": ..., "items": [{"id":
  <manifest url>, "type": "Manifest", "label": ..., "thumbnail": ...}, ...]}` —
  references only, no embedded manifests.

## Scope

Three additive pieces, shippable independently (in this order):

1. Descriptive-property kwargs on `build_manifest` + a defaults hook.
2. A `build_multi_manifest(...)` builder (module-level; no ORM coupling).
3. A `build_collection(...)` builder + optional drop-in view.

`IIIFObject.manifest` keeps its exact current output when nothing new is
configured.

## Design

### 1. Descriptive properties

- `build_manifest(...)` gains keyword-only, `None`-defaulted parameters:
  `metadata`, `rights`, `required_statement`, `summary`, `thumbnail`,
  `nav_date`. Each is emitted only when non-`None`, so existing output is
  byte-identical by default.
  - `metadata`: `list[tuple[label, value]]` or preformed list of dicts; both
    coerced through `_language_map`.
  - `required_statement`: a `(label, value)` pair, same coercion.
  - `thumbnail`: a URL string (wrapped into the `[{"id": ..., "type":
    "Image"}]` shape) or a preformed list.
  - `nav_date`: an aware `datetime`, serialized ISO 8601.
- **New optional setting `IIIF_MANIFEST_DESCRIPTORS`** — a callable receiving
  the `IIIFFieldFile` and returning a dict of the kwargs above (or `None`).
  `IIIFObject.manifest` resolves it (mirroring `resolve_auth`) and threads the
  values into `build_manifest`. This is how per-image metadata flows from the
  model without djiiif knowing the model:

  ```python
  def manifest_descriptors(parent):
      photo = parent.instance
      return {
          "metadata": [("Title", photo.title), ("Date", str(photo.year))],
          "rights": "http://creativecommons.org/licenses/by/4.0/",
          "required_statement": ("Attribution", "Example Institution"),
          "thumbnail": photo.image.iiif.thumb,   # an existing profile URL
      }

  IIIF_MANIFEST_DESCRIPTORS = manifest_descriptors
  ```

### 2. Multi-image manifests

- New builder `build_multi_manifest(id_url, images, *, label, version=None,
  level=None, auth=None, **descriptors)` where `images` is a sequence of
  per-canvas specs: `(service_id_url, width, height)` tuples or dicts adding
  optional per-canvas `label`. Canvas/annotation ids derive from `id_url` with
  a 1-based index, exactly extending the current synthetic-URI scheme.
- The single-image `build_manifest` becomes a thin wrapper over it (one-item
  list) — one canvas-assembly code path, zero behavior change.
- No `IIIFObject` surface for this: an `IIIFFieldFile` *is* one image. The
  multi-image case belongs to the model level; the builder is the reusable
  piece, and the README shows the ~5-line model method/property that assembles
  one from `photo.images.all()`.

### 3. Collections

- New builder `build_collection(id_url, items, *, label, **descriptors)` where
  `items` is a sequence of `(manifest_url, label)` (optionally `thumbnail`)
  entries — plain data, so any queryset maps in with a comprehension.
- **Optional drop-in view** `serve_collection` at `/iiif/collection`, driven by
  a new setting `IIIF_COLLECTION_SOURCE` (callable → iterable of item entries,
  same pattern as the Change Discovery brief's `IIIF_ACTIVITY_SOURCE`). Unset ⇒
  404. Reuses `_ld_json`.

## Non-goals

- Ranges / tables of contents (`structures`) — valuable for book-like objects,
  but needs an opinionated input shape; separate follow-up if wanted.
- `placeholderCanvas` / `accompanyingCanvas`, AV content (Canvas `duration`),
  `provider` logos, nested Collections-of-Collections.
- Presentation 4.0 shapes (release candidate expected 2026; viewer support will
  lag — v3 remains the interoperable baseline).
- Any ORM coupling in builders — they stay pure functions over plain data.

## Open questions

1. **Descriptor hook shape** — one `IIIF_MANIFEST_DESCRIPTORS` callable
   returning a kwargs dict (proposed) vs a typed `ManifestDescriptors`
   dataclass. Dict-of-kwargs is looser but matches "callable returning a dict"
   precedent from `IIIF_PROFILES`; a dataclass could be added later without
   breakage (accepted via `resolve_*` normalization like `Profile`).
2. **Auth on multi-image manifests** — apply the single resolved `IIIF_AUTH`
   block to every image body (proposed, matches current semantics) vs
   per-canvas resolution. Per-canvas needs the field files, which the builder
   deliberately doesn't see; revisit only if a real mixed-access use case shows
   up.
3. **`serve_collection` pagination** — IIIF Collections may be paged via
   `first`/`next` Collection pages; start unpaged (collections of references
   are small) and note the limit in docs?

## Testing (per repo conventions — 90% coverage gate)

- Descriptors: each property emitted correctly (language-map coercion, metadata
  pair shapes, thumbnail wrapping, ISO `navDate`); **all-absent ⇒ output
  byte-identical to today** (regression pin); `IIIF_MANIFEST_DESCRIPTORS`
  resolved for `IIIFObject.manifest` (callable and unset paths).
- `build_multi_manifest`: N canvases with correct indexed ids, per-canvas
  labels, v2 (`ImageService2`) variant, auth block on every body; single-image
  wrapper equivalence (old `build_manifest` output unchanged).
- `build_collection`: reference-only items, labels/thumbnails, descriptor
  passthrough.
- `serve_collection`: happy path (content type, CORS), source unset → 404,
  empty source → valid empty collection.

## Docs & compatibility

- **Purely additive** — existing signatures gain keyword-only optional params;
  default output unchanged. No MAJOR bump; `Added` CHANGELOG entry per piece.
- `README.md`: "Describing your images" (descriptors), "Multi-image objects",
  and "Collections" sections with the model-method recipe; `CLAUDE.md`
  architecture + required-coverage updated in the same commits.

## References

- [IIIF Presentation API 3.0](https://iiif.io/api/presentation/3.0/)
- [Descriptive properties (§3.1)](https://iiif.io/api/presentation/3.0/#31-descriptive-properties)
- [Collection (§5.1)](https://iiif.io/api/presentation/3.0/#51-collection)
