# Design briefs

Proposals and records for djiiif features. Each brief follows the same shape:
Problem → Background → Scope → Design → Non-goals → Decisions → Testing →
Docs & compatibility → References. Status is tracked in each brief's header.

## Implemented

- [AUTH-API](AUTH-API.md) — IIIF Authorization Flow 2.0, metadata-only
  (`IIIF_AUTH`). Shipped in 1.0.0.
- [CONTENT-STATE](CONTENT-STATE.md) — Content State API 1.0 encode/decode
  helpers + `iiif.content_state` + `{% iiif_content_state %}` tag for viewer
  deep links. Implemented on `iiif-api-briefs` (unreleased).
- [PRESENTATION-ENRICHMENT](PRESENTATION-ENRICHMENT.md) — manifest descriptive
  metadata (`IIIF_MANIFEST_DESCRIPTORS`), multi-image manifests
  (`build_multi_manifest`), and Collections (`build_collection` +
  `serve_collection`). Implemented on `presentation-enrichment` (unreleased).
- [CHANGE-DISCOVERY](CHANGE-DISCOVERY.md) — Change Discovery API 1.0 activity
  stream (`IIIF_ACTIVITY_SOURCE` + `serve_activity_collection` /
  `serve_activity_page`); makes a Django site harvestable by aggregators.
  Implemented on `change-discovery` (unreleased).
- [WEB-ANNOTATIONS](WEB-ANNOTATIONS.md) + [CONTENT-SEARCH](CONTENT-SEARCH.md) —
  the shared `Annotation` dataclass, `IIIF_ANNOTATIONS_BACKEND` +
  `serve_annotation_page`, and `IIIF_SEARCH_BACKEND` + `serve_search` (with the
  substring fallback over the annotations backend). Co-landed on
  `annotations-search` (unreleased).
- [INFO-JSON-ENRICHMENT](INFO-JSON-ENRICHMENT.md) — declarative `sizes` /
  `tiles` / limits / `rights` in the generated `info.json` (`IIIF_INFO` +
  `InfoExtras`). Implemented on `info-json-enrichment` (unreleased).
- [NAVPLACE-GEO](NAVPLACE-GEO.md) — navPlace extension with GeoDjango geometry
  pass-through (`IIIF_NAVPLACE` + the optional `djiiif.geo` module). Implemented
  on `navplace-geo` (unreleased).

## Proposed — IIIF API expansion (2026-07)

All seven briefs are now implemented (unreleased). Nothing remains proposed.

Cross-cutting conventions settled across the briefs:

- **Dual-shape settings values** — spec-shaped objects are accepted as either
  a plain dict or a frozen dataclass (`Activity`, the shared `Annotation`),
  normalized by a `resolve_*` function, following the `Profile`/`ProbeService`
  precedent. Pure kwarg bags (the descriptor hook in 2, `IIIF_INFO` in 7) stay
  plain dicts with unknown/conflicting keys rejected loudly.
- **Per-image callables on view paths** — callables receive the
  `IIIFFieldFile` on model paths and the decoded storage name (`str`) on
  view-served paths (`parent: IIIFFieldFile | str`); settled in 7, Decision 2.
- **Fail loud on impossible configuration** — version mismatches, wrong SRIDs,
  unknown keys raise `ImproperlyConfigured`, never silently drop (matches the
  existing `IIIF_AUTH`-at-v2 posture).
