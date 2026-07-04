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

## Proposed — IIIF API expansion (2026-07)

The six remaining are opt-in and backwards-compatible (no MAJOR bump). All open
questions were resolved 2026-07-03; each brief carries a Decisions section and
is ready to implement. Suggested sequencing, smallest/highest-leverage first:

1. [PRESENTATION-ENRICHMENT](PRESENTATION-ENRICHMENT.md) — manifest descriptive
   metadata, multi-image manifests, Collections. Deepens the spec already
   implemented.
2. [CHANGE-DISCOVERY](CHANGE-DISCOVERY.md) — Change Discovery API 1.0 activity
   stream; makes a Django site harvestable by aggregators.
3. [WEB-ANNOTATIONS](WEB-ANNOTATIONS.md) — serve W3C AnnotationPages
   (transcriptions/OCR/commentary) referenced from manifests. Defines the
   shared `Annotation` dataclass; implement before CONTENT-SEARCH.
4. [CONTENT-SEARCH](CONTENT-SEARCH.md) — Content Search API 2.0 endpoint over a
   pluggable backend, with a free substring-search fallback over the
   WEB-ANNOTATIONS backend. Prefer co-landing with WEB-ANNOTATIONS in one
   release.
5. [NAVPLACE-GEO](NAVPLACE-GEO.md) — navPlace extension with GeoDjango
   geometry pass-through. Niche but distinctive.
6. [INFO-JSON-ENRICHMENT](INFO-JSON-ENRICHMENT.md) — declarative `sizes` /
   `tiles` / limits / rights in the generated `info.json`.

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
