# CONTENT-STATE — IIIF Content State API 1.0 helpers (share/deep-link support)

**Status:** Proposed — all questions resolved, ready to implement
**Branch:** _none yet (implementation branch TBD)_
**Date:** 2026-07-03

## Problem

djiiif can generate a Presentation 3.0 manifest for any stored image
(`iiif.manifest`, or the drop-in `serve_manifest` view), which means the image is
one URL away from opening in Mirador, Theseus, or any manifest-aware viewer. But
there is no way to express *"open this image, zoomed to this region"* — the kind
of shareable deep link that powers "cite this detail", "share this view", and
cross-site handoff between viewers.

The [IIIF Content State API 1.0](https://iiif.io/api/content-state/1.0/) is the
standard for exactly this: a small JSON-LD annotation describing a view of a
Presentation resource, serialized and passed to a viewer (typically as an
`iiif-content=` query parameter, base64url-encoded). djiiif already knows every
value a content state needs — the manifest URI, the canvas URI, and the image
geometry — so this is a natural, tiny extension.

## Background — what a content state is

A content state is an `Annotation` with `motivation: "contentState"` whose
`target` is the resource to show. The simplest useful forms:

- **Whole manifest:** the target is the Manifest (in the trivial case the state
  can even be just the manifest URI string).
- **A canvas within a manifest:** target is the Canvas, with `partOf` pointing at
  the Manifest.
- **A region of a canvas:** the canvas `id` carries a media-fragment suffix,
  e.g. `.../canvas/1#xywh=1000,2000,1000,2000`.

For transfer in a URL, the JSON is UTF-8 encoded, base64url-encoded, and the
padding stripped (the spec defines this exact encoding). Viewers accept it as
`?iiif-content=<encoded>` (Mirador and Theseus both do).

djiiif's manifest builder already emits stable, derivable URIs:
`{identifier}/manifest` for the manifest and `{identifier}/canvas/1` for the
single canvas — so content states can be constructed without fetching anything.

## Scope

Pure helper functions + one template tag. **No new settings, no new views, no
new dependencies, no change to any existing output.** djiiif *produces* content
states; consuming them (e.g. a Django view that decodes an inbound
`iiif-content` parameter) is limited to a `decode` helper — no viewer-side
orchestration.

## Design

- **Encoding primitives** in `djiiif/__init__.py` (or a small
  `djiiif/contentstate.py` if `__init__` is getting long):
  - `encode_content_state(state: dict | str) -> str` — UTF-8 → base64url →
    strip `=` padding, per the spec's encoding algorithm.
  - `decode_content_state(encoded: str) -> dict | str` — the inverse (restore
    padding, decode, `json.loads` when the payload is JSON).
- **State builder** working from what djiiif already knows:
  - `build_content_state(manifest_id: str, *, canvas_id: str | None = None,
    xywh: str | tuple[int, int, int, int] | None = None) -> dict` — returns the
    annotation dict. With only `manifest_id` it targets the Manifest; with
    `canvas_id` it targets the Canvas with `partOf` → Manifest; `xywh` appends
    the fragment. A 4-tuple of ints is formatted to the `x,y,w,h` string; a
    string is used verbatim (spec-literal escape hatch).
- **`IIIFObject` convenience** (lazy, no I/O):
  - `IIIFObject.content_state(*, xywh: str | None = None, encoded: bool = True)`
    — builds the state for this image's own manifest/canvas URIs and returns the
    encoded string (or the raw dict with `encoded=False`). Empty/unset field →
    `""` (or `None` for the dict form), matching the safe-for-empty-fields
    contract.
- **Template tag** in `iiiftags`:
  - `{% iiif_content_state image %}` → the encoded state string, and
    `{% iiif_content_state image xywh="125,15,120,200" %}` for a region — ready
    to drop into `?iiif-content={{ ... }}` links. Raises `NotAnIIIFField` for
    non-IIIF fields, matching the existing `{% iiif %}` tag's error path.

### Usage example

```django
<a href="https://theseusviewer.org/?iiif-content={% iiif_content_state photo.image xywh='1000,2000,1000,2000' %}">
  Open this detail in Theseus
</a>
```

```python
state = photo.image.iiif.content_state(xywh="1000,2000,1000,2000")
# -> "JTdCJTIyaWQlMjIlM0El..." (URL-safe, no padding)
```

### Rough implementation outline

- Encoding pair + `build_content_state` as module-level builders (pure, tested
  in isolation, reusable by downstream projects).
- `IIIFObject.content_state(...)` method deriving `manifest_id` / `canvas_id`
  from `self.identifier` exactly as `build_manifest` does (`.../manifest`,
  `.../canvas/1`) — keep the two derivations in one place (small private helper)
  so they cannot drift.
- New tag in `djiiif/templatetags/iiiftags.py`.

## Non-goals

- No viewer embedding or redirect views (a "launch viewer" view is trivial for
  users to write with these helpers).
- No content-state *protocol* participation beyond encode/decode (no paste/drag
  -and-drop handling — that is viewer-side).
- No multi-target or multi-canvas states in v1 of this feature (the spec allows
  them; the builder can grow a list form later without breakage).

## Decisions

1. **Placement** — **`djiiif/__init__.py`**. It is ~60 lines of pure functions
   with no new imports beyond `base64`/`json`; keeping the core a single module
   preserves the "core is one file" story and matches where every other builder
   lives.
2. **Region ergonomics** — **accept both** a preformatted `xywh` string
   (spec-literal, copy-paste-safe) and a 4-tuple of ints (Pythonic). Tuple is
   formatted to `x,y,w,h`; anything else passes through verbatim.
3. **No `serve_content_state` redirect view** — a "launch viewer" redirect is a
   2-line user view once the helpers exist, and viewer choice is app policy,
   not djiiif's. Stays in Non-goals.

## Testing (per repo conventions — 90% coverage gate)

- Encode/decode round-trip; padding stripped on encode and restored on decode;
  non-JSON (bare URI string) payloads survive the round-trip.
- `build_content_state`: manifest-only, canvas + `partOf`, and `xywh` fragment
  shapes match the spec's examples; tuple and string `xywh` forms produce the
  same fragment.
- `IIIFObject.content_state`: derived URIs match the ones `manifest` emits;
  empty/unset field returns `""`; encoded output decodes back to the dict form.
- Template tag happy path + `NotAnIIIFField` error path.

## Docs & compatibility

- **Purely additive** — no existing attribute, document, or setting changes. No
  MAJOR bump; a normal `Added` CHANGELOG entry.
- `README.md` gains a "Share links / content state" section with the viewer
  example above; `CLAUDE.md` architecture + required-coverage updated in the
  same commit.

## References

- [IIIF Content State API 1.0](https://iiif.io/api/content-state/1.0/)
- [Content State encoding rules (§6)](https://iiif.io/api/content-state/1.0/#6-content-state-encoding)
