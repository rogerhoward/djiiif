# Settings reference

Every djiiif setting is **optional** except `IIIF_PROFILES` (needed for profile
URLs). Anything unset simply leaves the corresponding feature off — no output
changes until you configure it.

## Core

```{list-table}
:header-rows: 1
:widths: 30 15 55

* - Setting
  - Default
  - Purpose
* - `IIIF_PROFILES`
  - —
  - Maps profile name → `dict` / {class}`~djiiif.Profile` / callable. Drives the `.iiif.<name>` URLs. See {doc}`profiles`.
* - `IIIF_IMAGE_API_VERSION`
  - `3`
  - Generated document shape: `3` (ImageService3) or `2` (ImageService2). See {doc}`documents`.
* - `IIIF_COMPLIANCE_LEVEL`
  - `"level2"`
  - Compliance level advertised in `info_document` / manifest image service.
```

## Presentation & collections

```{list-table}
:header-rows: 1
:widths: 30 15 55

* - Setting
  - Default
  - Purpose
* - `IIIF_MANIFEST_DESCRIPTORS`
  - unset
  - Callable (or dict) supplying manifest descriptive metadata. See {doc}`presentation`.
* - `IIIF_COLLECTION_SOURCE`
  - unset
  - Callable/iterable of `(manifest_url, label[, thumbnail])` items for `/iiif/collection`. Unset ⇒ 404.
* - `IIIF_COLLECTION_LABEL`
  - `"Collection"`
  - Label for the served collection.
```

## Change Discovery

```{list-table}
:header-rows: 1
:widths: 30 15 55

* - Setting
  - Default
  - Purpose
* - `IIIF_ACTIVITY_SOURCE`
  - unset
  - Callable / dotted-path / iterable of activity entries (ascending `end_time`). Unset ⇒ 404. See {doc}`discovery`.
* - `IIIF_ACTIVITY_PAGE_SIZE`
  - `100`
  - Activities per `OrderedCollectionPage`.
```

## Annotations & search

```{list-table}
:header-rows: 1
:widths: 30 15 55

* - Setting
  - Default
  - Purpose
* - `IIIF_ANNOTATIONS_BACKEND`
  - unset
  - Callable / dotted-path `(identifier, request) -> iterable` of annotations. Powers `/annotations/1` and the search fallback. See {doc}`annotations-search`.
* - `IIIF_SEARCH_BACKEND`
  - unset
  - Callable / dotted-path `(identifier, q, request) -> iterable` of hits. Powers `/search`. Overrides the annotations fallback.
```

## Authorization

```{list-table}
:header-rows: 1
:widths: 30 15 55

* - Setting
  - Default
  - Purpose
* - `IIIF_AUTH`
  - unset
  - {class}`~djiiif.ProbeService` / dict / callable describing an Auth Flow 2.0 probe service. Requires `IIIF_IMAGE_API_VERSION = 3`. See {doc}`auth`.
```

(settings-check)=
## Startup validation

With `djiiif` in `INSTALLED_APPS`, `manage.py check` validates `IIIF_PROFILES` at
startup — flagging a non-`dict` setting, an unsupported profile value, or a
`dict` profile missing required keys before it can produce a broken URL. Callable
and `Profile` entries are accepted as-is (a callable's shape can only be verified
when it runs).
