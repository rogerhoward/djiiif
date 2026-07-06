# INFO-JSON-ENRICHMENT — richer generated `info.json` (sizes, tiles, limits, rights)

**Status:** Implemented (unreleased) — on `info-json-enrichment`
**Branch:** `info-json-enrichment`
**Date:** 2026-07-03

## Problem

`build_info_document` emits the minimal spec-valid `info.json`: context, id,
protocol, profile, width, height. That is enough for a viewer to *start*, but
the Image API defines optional properties that materially improve client
behavior, and real deployments (djiiif fronting iiiris or a
static tile pyramid) often need to advertise them:

- **`sizes`** — preferred complete-image sizes; viewers use these for
  thumbnails and low-res previews instead of guessing.
- **`tiles`** — tile width/height and scale factors; without it, deep-zoom
  clients fall back to ad-hoc region requests that may miss the server's tile
  cache entirely.
- **`maxWidth` / `maxHeight` / `maxArea`** — server-enforced size limits;
  clients that don't know them get 4xx responses on large requests.
- **`rights`** (v3) — a license/rights URI surfaced in viewer UI.
- **`preferredFormats`**, **`extraQualities` / `extraFormats` /
  `extraFeatures`** (v3) — capabilities beyond the compliance level.

This is not a new IIIF API — it deepens the one djiiif already implements, and
it matters precisely because djiiif's `info.json` *describes another server*:
the document should be able to tell the truth about that server's tiles and
limits.

## Background — version differences

| Property | v3 | v2 |
| --- | --- | --- |
| `sizes`, `tiles` | ✓ | ✓ (same shape) |
| `maxWidth`/`maxHeight`/`maxArea` | ✓ top-level | ✓ (inside `profile` list's feature object) |
| `rights` | ✓ (single URI) | `license` (list) |
| `preferredFormats` | ✓ | — |
| `extraQualities`/`extraFormats`/`extraFeatures` | ✓ | `qualities`/`formats`/`supports` in the profile object |

Supporting the v3 column fully and a pragmatic v2 subset (`sizes`, `tiles`)
covers real usage without reimplementing v2's profile-object gymnastics.

## Scope

**A declarative, opt-in settings surface that passes these properties through
into the generated `info.json`.** djiiif does not probe the image server, does
not compute tile pyramids, and does not validate that the advertisement matches
server reality — the operator declares what their server supports, djiiif
emits it in the right place for the configured API version.

## Design

- **New optional setting `IIIF_INFO`** — dict-or-callable (the established
  pattern), resolved by a `resolve_info(parent)` mirroring `resolve_auth`.
  Keys (all optional): `sizes`, `tiles`, `max_width`, `max_height`,
  `max_area`, `rights`, `preferred_formats`, `extra_qualities`,
  `extra_formats`, `extra_features`. A callable enables per-image values
  (e.g. `sizes` computed from the image's own dimensions).

  ```python
  IIIF_INFO = {
      "tiles": [{"width": 512, "scaleFactors": [1, 2, 4, 8]}],
      "max_width": 5000,
      "rights": "http://creativecommons.org/licenses/by/4.0/",
      "preferred_formats": ["webp", "jpg"],
  }

  # Or per-image, deriving sizes from the stored dimensions:
  def info_extras(parent):
      w, h = parent.width, parent.height
      return {"sizes": [{"width": w // f, "height": h // f} for f in (8, 4, 2, 1)]}
  IIIF_INFO = info_extras
  ```

- **Optional typed helper `InfoExtras`** (frozen dataclass, dual-shape like
  `Profile`) for discoverability/typo-safety; raw dicts accepted.
- **Emission in `build_info_document`** via a keyword-only
  `extras: dict | None = None` parameter:
  - **v3**: emit each present key at top level with spec casing
    (`maxWidth`, `preferredFormats`, …); `rights` as given.
  - **v2**: emit `sizes`/`tiles`; **raise `ImproperlyConfigured`** for
    v3-only keys (consistent fail-loud posture, same as `IIIF_AUTH` at v2 —
    see Decisions).
  - Key order: keep spec-conventional grouping (dimensions, then `sizes`/
    `tiles`, then limits, then rights/extras) for human readability; JSON
    consumers don't care.
- `IIIFObject.info_document` and `serve_info_json` thread
  `resolve_info(...)` through, exactly like `auth`. On the view path there is
  no field file: per the repo-wide convention settled here (Decision 2),
  **per-image callables receive the `IIIFFieldFile` on model paths and the
  decoded storage name (`str`) on view paths** — both expose the identity a
  callable actually branches on (the name), and the documented signature is
  `parent: IIIFFieldFile | str`.
- **Unset ⇒ byte-identical output to today.**

## Non-goals

- Probing/validating against the actual image server, computing scale factors
  from stored images, or generating tile pyramids.
- Full v2 profile-object emission (`supports`/`qualities`/`formats`, embedded
  max limits) — v2 is legacy; `sizes`/`tiles` is the pragmatic subset.
- `attribution`/`logo` (v2 descriptive properties) and v3 `partOf`/`seeAlso`/
  `service` beyond what `IIIF_AUTH` already handles — deferrable, and
  `service` composition with auth needs care if ever added.
- The `sizeUpscaling` feature-name minutiae of compliance levels — the
  operator's declared `extra_features` is passed through verbatim.

## Decisions

1. **v3-only keys at v2** — **raise `ImproperlyConfigured`.** Consistent with
   `IIIF_AUTH` at v2 and the unknown-version check: configuration that cannot
   mean what it says fails loud. A mixed-version transition can branch in a
   callable (`version` is a settings read away); silent dropping would mask
   typos forever.
2. **Callable argument for the view path** — **repo-wide convention:**
   per-image setting callables (`IIIF_INFO`, and any future ones used by the
   drop-in views) receive the `IIIFFieldFile` on model paths and the
   **decoded storage name (`str`)** on view paths; documented signature
   `parent: IIIFFieldFile | str`. Rationale: the name is the identity both
   paths share, `None` would force every callable to handle a no-information
   case, and dict-only-for-views would silently fork the feature set. A
   callable needing model data looks it up by name — which is exactly what
   the view path's information really is. (`IIIF_AUTH` today is unaffected:
   the existing views never resolve it; if they ever do, this convention
   applies.)
3. **Key casing** — **accept both** snake_case (Pythonic, matches dataclass
   field names) and spec-literal camelCase (copy-paste from spec examples
   works), normalized once in `resolve_info`. Conflicting duplicates
   (`max_width` and `maxWidth` both present) raise `ImproperlyConfigured`.
4. **`"sizes": "auto"`** — **no.** It would read pixel dimensions from
   storage inside an otherwise declaration-only code path, hiding I/O. The
   documented callable recipe derives sizes explicitly in three lines.

## Testing (per repo conventions — 90% coverage gate)

- Each key emitted with correct spec casing/placement at v3; `sizes`/`tiles`
  at v2; v3-only key at v2 raises `ImproperlyConfigured`; camelCase and
  snake_case keys both accepted, conflicting duplicates rejected.
- Dict, callable, and (if adopted) `InfoExtras` dataclass shapes through
  `resolve_info`, plus its bad-type `ImproperlyConfigured` path.
- **Unset ⇒ byte-identical documents** (regression pin for both versions).
- `serve_info_json` threading, including the no-field-file callable contract.
- Composition with `IIIF_AUTH`: both `service` (auth) and extras present in
  one document.

## Docs & compatibility

- **Purely additive** — unset means unchanged output. No MAJOR bump; `Added`
  CHANGELOG entry.
- `README.md`: extend the info.json section with the tiles/limits recipe and
  a note that the advertisement must match the real image server's behavior;
  `CLAUDE.md` architecture + required-coverage updated in the same commit.

## References

- [IIIF Image API 3.0 — technical properties (§5.3–5.5)](https://iiif.io/api/image/3.0/#53-sizes)
- [IIIF Image API 2.1 — `sizes`/`tiles`](https://iiif.io/api/image/2.1/#image-information)
- [Image API compliance levels](https://iiif.io/api/image/3.0/compliance/)
