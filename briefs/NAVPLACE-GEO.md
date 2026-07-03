# NAVPLACE-GEO — navPlace extension via GeoDjango (geolocated manifests)

**Status:** Proposed
**Branch:** _none yet (implementation branch TBD)_
**Date:** 2026-07-03

## Problem

Collections with a geographic dimension — photographs of places, maps,
architectural surveys — want their IIIF resources to carry location data that
map-aware viewers and aggregators can plot. The approved
[IIIF navPlace extension](https://iiif.io/api/extension/navplace/) does exactly
this: a `navPlace` property holding a GeoJSON `FeatureCollection` on a
Manifest, Canvas, Collection, or Range.

Django projects that care about geodata typically already model it with
**GeoDjango** (`django.contrib.gis`) — `PointField`, `PolygonField`, etc. —
and every GEOS geometry serializes to GeoJSON via its `.geojson` property. The
bridge from a GeoDjango model to a spec-conformant `navPlace` block is
therefore nearly free, and no Django IIIF package offers it. This is a niche
but genuinely distinctive integration.

## Background — the shapes involved

- `navPlace` value: a GeoJSON `FeatureCollection` whose `features` are
  `Feature` objects (`geometry` = Point/Polygon/…, `properties` may carry a
  `label` language map).
- The extension requires its context in the document's `@context` **array**:
  `["http://iiif.io/api/extension/navplace/context.json",
  "http://iiif.io/api/presentation/3/context.json"]` (extension context first,
  Presentation context last). Today djiiif emits a bare string context — the
  builder must switch to an array only when the extension is used.
- `navPlace` is for **navigation/discovery** ("where is this about"), not
  georeferencing pixels — the separate
  [Georeference extension](https://iiif.io/api/extension/georef/) handles
  warped-map overlays and is out of scope here.

## Scope

An **opt-in, per-image geometry hook folded into generated manifests** (and,
if the PRESENTATION-ENRICHMENT brief lands, collections). GeoDjango is used
when available but **must not become a dependency** — plain GeoJSON dicts work
without it, so projects without GDAL/GEOS system libraries are unaffected.
Mirrors the `drf` pattern: any GeoDjango-touching code lives in an optional
module never imported by `djiiif/__init__.py`.

## Design

- **New optional setting `IIIF_NAVPLACE`** — a callable receiving the
  `IIIFFieldFile` and returning one of:
  - `None` — no `navPlace` (the default for unset),
  - a **GeoJSON dict** — a `Feature`, `FeatureCollection`, or bare geometry
    (normalized: geometry → Feature → FeatureCollection),
  - a **GEOS geometry** (`django.contrib.gis.geos.GEOSGeometry`) — converted
    via `json.loads(geom.geojson)` and wrapped the same way; detected by
    duck-typing/`isinstance` inside the optional module so the core never
    imports `django.contrib.gis`,
  - optionally a `(geometry_or_dict, label)` pair — label coerced by
    `_language_map` into the Feature's `properties`.

  ```python
  # settings.py
  IIIF_NAVPLACE = "myapp.iiif.navplace"

  # myapp/iiif.py — Photo has location = models.PointField(null=True)
  def navplace(parent):
      photo = parent.instance
      if photo.location is None:
          return None
      return (photo.location, photo.place_name)
  ```

- **Normalization** `resolve_navplace(parent) -> dict | None` (mirroring
  `resolve_auth`), living in a new `djiiif/geo.py` so the GEOS import stays
  optional and lazy.
- **Emission**: `build_manifest` gains a keyword-only `nav_place: dict | None`
  parameter. When non-`None`:
  - the `navPlace` FeatureCollection is set on the **Manifest** (top level —
    the common single-image case; Canvas-level placement deferred),
  - `@context` becomes the required two-element array.
  `IIIFObject.manifest` and `serve_manifest` thread `resolve_navplace(...)`
  through, exactly like `auth`.
- **Feature ids**: the extension recommends ids on Features; synthesize
  `{manifest_id}/navplace/feature/{n}` in line with the existing synthetic-URI
  scheme.
- **Packaging**: no new pip dependency (GeoDjango ships with Django; its
  system libraries are the real requirement, and only projects whose callables
  return GEOS objects need them). No `geo` extra needed unless a future
  version wants `geojson`-lib validation.

## Non-goals

- The **Georeference extension** (ground control points, warped map overlays)
  — different spec, different data model; future brief if demand appears.
- Canvas-level or Range-level `navPlace` (Manifest-level covers the
  one-image-one-canvas reality of djiiif manifests; Collection-level arrives
  with PRESENTATION-ENRICHMENT).
- Any map UI, tile serving, or coordinate transformation (navPlace mandates
  WGS84; transforming from other SRIDs is the caller's one-liner:
  `geom.transform(4326, clone=True)` — documented, not performed).
- Validating user-supplied GeoJSON beyond basic shape normalization.

## Open questions

1. **SRID safety** — silently trust coordinates vs raise
   `ImproperlyConfigured` when a GEOS geometry's `srid` is set and ≠ 4326.
   Leaning: raise (fail loud matches the repo's existing configuration-error
   posture; wrong-datum coordinates are silent data corruption otherwise).
2. **Tuple-with-label** input shape vs requiring a full Feature dict for
   labeled features. The tuple is ergonomic; is it too cute?
3. Should `navPlace` also be emitted in `info.json`? No — it is a Presentation
   -family property; noted here to preempt the question.

## Testing (per repo conventions — 90% coverage gate)

- `resolve_navplace`: `None`/unset, bare geometry dict, Feature,
  FeatureCollection (pass-through), `(geom, label)` pair, GEOS geometry
  (skipped via `importorskip("django.contrib.gis.geos")` if GEOS libraries are
  absent — same pattern as the DRF serializer tests), bad-type
  `ImproperlyConfigured`, SRID rejection (per Open question 1).
- Manifest emission: `navPlace` present with array `@context` (extension
  context first) when configured; **absent, with today's string context, when
  unconfigured** (regression pin); feature id synthesis.
- View path: `serve_manifest` threading.

## Docs & compatibility

- **Purely additive** — string→array `@context` only occurs for opted-in
  documents (and is spec-mandated there). No MAJOR bump; `Added` CHANGELOG
  entry.
- `README.md` gains a "Geolocated images (navPlace)" section with the
  GeoDjango recipe; `CLAUDE.md` architecture + required-coverage updated in
  the same commit. Coverage config may need `djiiif/geo.py` handled like
  `serializers.py` if GEOS-dependent lines are unreachable in CI.

## References

- [IIIF navPlace extension 1.0](https://iiif.io/api/extension/navplace/)
- [GeoJSON (RFC 7946)](https://datatracker.ietf.org/doc/html/rfc7946)
- [GeoDjango / GEOS geometries](https://docs.djangoproject.com/en/stable/ref/contrib/gis/geos/)
- [IIIF Georeference extension](https://iiif.io/api/extension/georef/) (future work)
