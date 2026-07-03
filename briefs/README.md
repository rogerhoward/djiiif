# Design briefs

Proposals and records for djiiif features. Each brief follows the same shape:
Problem → Background → Scope → Design → Non-goals → Open questions → Testing →
Docs & compatibility → References. Status is tracked in each brief's header.

## Implemented

- [AUTH-API](AUTH-API.md) — IIIF Authorization Flow 2.0, metadata-only
  (`IIIF_AUTH`). Shipped in 1.0.0.

## Proposed — IIIF API expansion (2026-07)

All seven are opt-in and backwards-compatible (no MAJOR bump). Suggested
sequencing, smallest/highest-leverage first:

1. [CONTENT-STATE](CONTENT-STATE.md) — Content State API 1.0 encode/decode
   helpers + template tag for viewer deep links. Smallest; zero new settings.
2. [PRESENTATION-ENRICHMENT](PRESENTATION-ENRICHMENT.md) — manifest descriptive
   metadata, multi-image manifests, Collections. Deepens the spec already
   implemented.
3. [CHANGE-DISCOVERY](CHANGE-DISCOVERY.md) — Change Discovery API 1.0 activity
   stream; makes a Django site harvestable by aggregators.
4. [CONTENT-SEARCH](CONTENT-SEARCH.md) — Content Search API 2.0 endpoint over a
   pluggable backend. Pairs with WEB-ANNOTATIONS; decide their shared
   annotation contract together.
5. [WEB-ANNOTATIONS](WEB-ANNOTATIONS.md) — serve W3C AnnotationPages
   (transcriptions/OCR/commentary) referenced from manifests.
6. [NAVPLACE-GEO](NAVPLACE-GEO.md) — navPlace extension with GeoDjango
   geometry pass-through. Niche but distinctive.
7. [INFO-JSON-ENRICHMENT](INFO-JSON-ENRICHMENT.md) — declarative `sizes` /
   `tiles` / limits / rights in the generated `info.json`.

Cross-cutting decisions to settle once (flagged in the individual briefs):
the dict-vs-dataclass normalization pattern for new settings (4, 5, and the
descriptor hook in 2 share it), and what per-image callables receive on the
view-served path where no `IIIFFieldFile` exists (7's Open question 2).
