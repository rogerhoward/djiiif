# Share links (Content State)

Because djiiif can describe an image's manifest, it can also build a
[IIIF Content State 1.0](https://iiif.io/api/content-state/1.0/) deep link — a
shareable URL that opens the image, optionally zoomed to a region, in any
content-state-aware viewer such as [Mirador](https://projectmirador.org/) or
[Theseus](https://theseusviewer.org/). This powers "cite this detail", "share
this view", and cross-viewer handoff.

## From an image

`iiif.content_state()` returns the URL-safe encoded string, ready to drop into an
`?iiif-content=` query parameter. It derives this image's own manifest and canvas
URIs and reads nothing from storage:

```pycon
>>> photo.image.iiif.content_state(xywh="1000,2000,1000,2000")
'JTdCJTIyaWQlMjIlM0El…'   # URL-safe, unpadded

>>> photo.image.iiif.content_state()          # whole image, no region
'JTdCJTIyaWQlMjIlM0El…'
```

`xywh` accepts a preformatted `"x,y,w,h"` string or a 4-tuple of ints. For an
empty/unset field it returns `""`.

In a template, the `{% iiif_content_state %}` tag emits the encoded string
directly:

```{code-block} html+django
{% load iiiftags %}

<a href="https://theseusviewer.org/?iiif-content={% iiif_content_state photo.image xywh='1000,2000,1000,2000' %}">
  Open this detail in Theseus
</a>
```

Pass `encoded=False` to get the raw content-state `dict` instead of the encoded
string (`None` for an empty field).

## Lower-level builders

For custom needs the module-level helpers are public:

```pycon
>>> from djiiif import build_content_state, encode_content_state, decode_content_state
>>> state = build_content_state("https://ex.org/manifest",
...                             canvas_id="https://ex.org/canvas/1",
...                             xywh="10,20,30,40")
>>> encoded = encode_content_state(state)
>>> decode_content_state(encoded) == state
True
```

- `build_content_state(manifest_id, *, canvas_id=None, xywh=None)` — the
  annotation `dict` (targets a Manifest, or a Canvas with `partOf`, plus an
  optional region).
- `encode_content_state` / `decode_content_state` — the spec's base64url
  encode/decode pair (usable, for example, in a view that decodes an inbound
  `iiif-content` parameter).

:::{note}
The encoding percent-encodes the JSON (matching JavaScript's
`encodeURIComponent`) before base64url — as the spec requires — so the result
round-trips through any viewer's `decodeURIComponent`.
:::
