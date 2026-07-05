# Harvestable streams (Change Discovery)

To let aggregators, portals, and search indexes discover *what changed since they
last looked*, djiiif can serve a
[IIIF Change Discovery 1.0](https://iiif.io/api/discovery/1.0/) activity stream —
the IIIF equivalent of a sitemap + RSS for your manifests. It's a natural fit for
Django: the stream is just a queryset ordered by a modified timestamp, paginated.

## Configure the source

Point `IIIF_ACTIVITY_SOURCE` at a callable (or a dotted-path string) that yields
one entry per resource, **in ascending `end_time` order**:

```{code-block} python
:caption: settings.py
IIIF_ACTIVITY_SOURCE = "myapp.iiif.activities"
```

```{code-block} python
:caption: myapp/iiif.py
def activities():
    for photo in Photo.objects.exclude(image="").order_by("modified"):
        yield {
            "object_id": f"https://example.org/iiif/{photo.slug}/manifest",
            "end_time": photo.modified,          # an aware datetime
        }
```

Each entry is a plain dict (or an {class}`~djiiif.Activity` dataclass) with:

```{list-table}
:header-rows: 1

* - Field
  - Default
  - Meaning
* - `object_id`
  - —
  - the manifest (or collection) URL
* - `end_time`
  - —
  - the modification timestamp (aware `datetime` or ISO 8601 string)
* - `type`
  - `"Update"`
  - the activity type (`"Update"` or `"Create"`)
* - `object_type`
  - `"Manifest"`
  - `"Manifest"` or `"Collection"`
```

## The endpoints

With the {doc}`URLconf <serving>` mounted, the stream is served at:

- `/iiif/activity/collection` — the `OrderedCollection` entry point. Harvesters
  start here and follow the `first`/`last`/`next` links.
- `/iiif/activity/page/<n>` — the `OrderedCollectionPage`s.

Page size comes from `IIIF_ACTIVITY_PAGE_SIZE` (default 100). Unset
`IIIF_ACTIVITY_SOURCE` ⇒ the activity URLs 404.

## Performance & ordering

Returning a **queryset** (rather than a generator) lets pages slice lazily in the
database — the recommended shape for large collections. A generator source is
materialized per request, which is fine for thousands of images.

:::{important}
Ordering is **trusted, not re-sorted** — your source must yield ascending by
`end_time`. (Re-sorting would defeat lazy queryset slicing.)
:::

## Conformance level

This is **level 1** (`Update`/`Create` activities with timestamps — enough for
incremental harvest). `Delete` tracking (level 2) would require a persisted
tombstone log and is future work.
