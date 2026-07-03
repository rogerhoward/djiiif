# CHANGE-DISCOVERY — IIIF Change Discovery API 1.0 activity stream (harvestable collections)

**Status:** Proposed
**Branch:** _none yet (implementation branch TBD)_
**Date:** 2026-07-03

## Problem

A Django project using djiiif can expose a manifest per image, but there is no
machine-readable way for an aggregator (a portal, a union catalog, a search
index) to discover *which* IIIF resources exist and *what changed since last
harvest*. The [IIIF Change Discovery API 1.0](https://iiif.io/api/discovery/1.0/)
solves this with a paged [ActivityStreams](https://www.w3.org/TR/activitystreams-core/)
feed of Create/Update/Delete activities over IIIF resources — the IIIF
equivalent of a sitemap + RSS for manifests.

This is an unusually good fit for Django: the stream is "a queryset ordered by
a modified timestamp, paginated" — which is exactly what the ORM and
`django.core.paginator` already do. No lightweight Django package offers this
today.

## Background — the shapes involved

Three JSON-LD documents, all `@context: ["http://iiif.io/api/discovery/1/context.json", "https://www.w3.org/ns/activitystreams"]`:

- **`OrderedCollection`** (the entry point): `totalItems` plus `first`/`last`
  references to pages.
- **`OrderedCollectionPage`**: `partOf` → the collection, `prev`/`next` page
  refs, and `orderedItems` — a list of activities **in ascending time order**.
- **Activity**: `{"type": "Update", "object": {"id": <manifest url>, "type":
  "Manifest"}, "endTime": <ISO 8601>}`. Types: `Create`, `Update`, `Delete`
  (plus `Move`/`Add`/`Remove`/`Refresh`, out of scope here).

The spec defines conformance levels: **level 0** (bare list of resources),
**level 1** (`Update` activities with timestamps — enables incremental harvest),
**level 2** (adds `Create`/`Delete`). Level 1 is the sweet spot: it needs only
a "last modified" timestamp per object, which most Django models already have.
Level 2 requires remembering deletions, which forces an activity-log table.

## Scope

An optional, settings-driven activity stream served by drop-in views, in the
same style as `djiiif/views.py` + `djiiif/urls.py`. **Level 1 conformance from
pure queryset data; no database models shipped by djiiif.** Level 2 (Delete
tracking) is future work — it is the first feature that would require djiiif to
ship a model, and deserves its own decision.

## Design

- **New optional setting `IIIF_ACTIVITY_SOURCE`** — a callable (dotted path or
  callable object, resolved like the rest of the settings) returning an
  **iterable of activity tuples/dicts**, each providing:
  - `object_id` — the manifest (or collection) URL,
  - `object_type` — `"Manifest"` (default) or `"Collection"`,
  - `end_time` — an aware `datetime` (the modified timestamp),
  - `type` — `"Update"` (default) or `"Create"` (level 1 allows Create too).

  The callable owns the ordering contract: **ascending by `end_time`**. In
  practice it is a thin generator over a queryset:

  ```python
  # settings.py
  IIIF_ACTIVITY_SOURCE = "myapp.iiif.activities"

  # myapp/iiif.py
  def activities():
      for photo in Photo.objects.exclude(image="").order_by("modified"):
          yield {
              "object_id": f"https://example.org/iiif/{photo.image.iiif_encoded_name}/manifest",
              "end_time": photo.modified,
          }
  ```

- **Builders** (module-level, pure, mirroring `build_info_document`):
  - `build_ordered_collection(id_url, total, first_url, last_url) -> dict`
  - `build_collection_page(id_url, collection_url, activities, *, prev_url,
    next_url) -> dict`
  - `build_activity(object_id, end_time, *, activity_type="Update",
    object_type="Manifest") -> dict`
- **Views + URLs** in `djiiif/views.py` / `djiiif/urls.py`:
  - `GET /iiif/activity/collection` → `serve_activity_collection`
  - `GET /iiif/activity/page/<int:page>` → `serve_activity_page`

  Both reuse the existing `_ld_json` helper (`application/ld+json` + CORS `*`).
  Page size from `IIIF_ACTIVITY_PAGE_SIZE` (default 100; spec guidance is
  10–100). Pagination via `django.core.paginator.Paginator` over the
  materialized source. Unknown page → `Http404`. `IIIF_ACTIVITY_SOURCE` unset →
  the activity URLs 404 (consistent with "opt-in ⇒ invisible when unconfigured").
- **Performance note:** `Paginator` needs a `count` and slicing; a generator
  source gets materialized per request. Fine for thousands of images; the
  setting accepts a *queryset-returning* callable too (querysets slice lazily in
  the DB), which is the documented recommendation for large collections.

## Non-goals

- **Level 2 / `Delete` activities** — requires persisting a tombstone log
  (djiiif's first model). Deferred to a follow-up brief if demand appears.
- `Move`, `Add`, `Remove`, `Refresh` activity types.
- Harvesting/consuming other providers' streams (client side).
- `seeAlso`/provenance enrichment of activities.

## Open questions

1. **URL naming** — `activity/collection` + `activity/page/<n>` vs the spec
   examples' `activity/all-changes` + `activity/page-<n>`. Cosmetic; the spec
   mandates no paths.
2. **Source contract** — dicts (extensible, stringly) vs a small frozen
   `Activity` dataclass (typed, consistent with `Profile`/`ProbeService`).
   Leaning: accept both, normalize via a `resolve_activity(...)` mirroring
   `resolve_profile`.
3. **Ordering enforcement** — trust the callable's ordering (documented
   contract) vs sorting defensively in the view (O(n log n) per request, breaks
   queryset laziness). Leaning: trust + document.
4. Should the collection also emit `partOf`/`seeAlso` links when the project
   serves a top-level IIIF Collection (see PRESENTATION-ENRICHMENT brief)?
   Nice-to-have, non-blocking.

## Testing (per repo conventions — 90% coverage gate)

- Builders: `OrderedCollection`, `OrderedCollectionPage`, and activity shapes
  match the spec (contexts, `partOf`, `prev`/`next` presence/absence at the
  boundaries, ISO 8601 `endTime` with timezone).
- Views: happy path (content type, CORS header, page contents in ascending
  order), multi-page pagination (`first`/`last`/`prev`/`next` correctness),
  empty source (valid empty collection), unknown page → 404, unset
  `IIIF_ACTIVITY_SOURCE` → 404.
- A queryset-shaped source and a generator source both work.
- `resolve_activity` (if adopted): dict, dataclass, and rejection paths.

## Docs & compatibility

- **Purely additive** — new setting + new URLs; nothing existing changes. No
  MAJOR bump; `Added` CHANGELOG entry.
- `README.md` gains a "Make your collection harvestable" section (this is the
  headline user-facing win); `CLAUDE.md` architecture + required-coverage
  updated in the same commit.

## References

- [IIIF Change Discovery API 1.0](https://iiif.io/api/discovery/1.0/)
- [Activity Streams 2.0](https://www.w3.org/TR/activitystreams-core/)
- [Discovery API conformance levels (§3.2)](https://iiif.io/api/discovery/1.0/#32-conformance-levels)
