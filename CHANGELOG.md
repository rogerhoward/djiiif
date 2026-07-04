# Changelog

All notable changes to `djiiif` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/). Per
the backwards-compatibility policy in `CLAUDE.md`, any breaking change to the
public API is called out under a **Breaking** heading and triggers a MAJOR
version bump.

Entries older than 0.24 were backfilled from git history and may be approximate;
dates are the commit dates of the corresponding version bump.

## [Unreleased]

### Added
- **Richer Presentation 3.0 manifests — descriptive properties.** `build_manifest`
  now accepts optional keyword descriptors `metadata`, `rights`,
  `required_statement`, `summary`, `thumbnail`, and `nav_date` (each emitted only
  when given, so default output is byte-identical). A new opt-in
  `IIIF_MANIFEST_DESCRIPTORS` setting — a `dict` of those kwargs or a callable
  receiving the field file and returning one (or `None`) — flows per-image
  descriptive metadata into `iiif.manifest` without djiiif knowing your model. An
  unknown descriptor key raises `ImproperlyConfigured`.
- **Multi-image manifests.** New `build_multi_manifest(id_url, images, *, label,
  …)` builder presents several images as one manifest with indexed canvases;
  `build_manifest` is now a thin single-image wrapper over it (output unchanged).
  A resolved `IIIF_AUTH` block applies to every image body.
- **Collections.** New `build_collection(id_url, items, *, label, **descriptors)`
  builder emits a Presentation 3.0 `Collection` of manifest *references*, plus an
  optional drop-in `serve_collection` view (mounted at `/iiif/collection` by
  `djiiif.urls`) driven by the `IIIF_COLLECTION_SOURCE` setting (unset ⇒ 404;
  `IIIF_COLLECTION_LABEL` sets the collection label). See
  `briefs/PRESENTATION-ENRICHMENT.md`. All three pieces are purely additive.
- **IIIF Content State API 1.0 helpers** for shareable viewer deep links. New
  module-level functions `encode_content_state` / `decode_content_state`
  (spec §6 base64url encoding, incl. the `encodeURIComponent` percent-encoding
  step) and `build_content_state` (targets a Manifest, a Canvas with `partOf`,
  or a Canvas region via `xywh`), plus `iiif.content_state(xywh=..., encoded=...)`
  which derives this image's own manifest/canvas URIs (the same ones
  `iiif.manifest` emits) with no file I/O, and a `{% iiif_content_state image %}`
  /`{% iiif_content_state image xywh='x,y,w,h' %}` template tag. Drop the result
  into `?iiif-content=` to open an image — optionally zoomed to a region — in
  Mirador, Theseus, or any content-state-aware viewer. Purely additive; no new
  settings, views, or dependencies, and no change to existing output. See
  `briefs/CONTENT-STATE.md`.

## [1.0.0] - 2026-07-03

First stable release. Marks the public API — `IIIFField` / `IIIFFieldFile` /
`IIIFObject`, the `.iiif` attributes and generated documents, the `IIIF_PROFILES`
/ `IIIF_AUTH` config shapes, the typed helpers, the serving views, and the DRF
field — as stable and covered by the backwards-compatibility policy. No breaking
changes from 0.24; the bump to 1.0 signals maturity, not a break.

### Added
- **Optional IIIF Authorization Flow 2.0 support (metadata-only).** A new opt-in
  `IIIF_AUTH` setting (a `ProbeService`, a `dict`, or a callable returning either
  or `None`, mirroring `IIIF_PROFILES`) embeds an Auth 2.0 `service` block in the
  generated `info_document` and `manifest`, so viewers can authenticate against an
  image server that implements Auth 2.0 (e.g. iiiris). New typed helpers
  `ProbeService` / `AccessService` / `TokenService` / `LogoutService` build the
  nested block. djiiif only describes the services; the image server implements
  and enforces them. Auth 2.0 requires `IIIF_IMAGE_API_VERSION = 3` (raises
  `ImproperlyConfigured` on v2). Documents are unchanged when `IIIF_AUTH` is unset.
  See `briefs/AUTH-API.md`.

## [0.24] - 2026-07-03

### Added
- `iiif.info_document`: returns the IIIF `info.json` **document** itself (a
  `dict`, or `None` for an empty field), assembled from the image's own
  `width`/`height`, so a Django view can serve a minimal, spec-valid `info.json`
  without a separate image server. Distinct from `iiif.info`, which is unchanged
  and still returns the *URL* of an external `info.json`. It is the only `iiif`
  attribute that reads the file from storage.
- `iiif.manifest`: returns a minimal single-image IIIF Presentation API 3.0
  Manifest (a `dict`, or `None` for an empty field) wrapping the image on one
  canvas, ready for viewers like Mirador or OpenSeadragon. The embedded image
  service follows `IIIF_IMAGE_API_VERSION`.
- `Profile` dataclass: a typed, opt-in alternative to raw `dict` profiles, with
  IIIF 3.0 defaults (`size="max"`) and `mirror` / `upscale` flags that fold into
  the `!`-rotation and `^`-size prefixes. Callable profiles may now return a
  `Profile` as well as a `dict`.
- Drop-in serving views (`djiiif.views.serve_info_json` / `serve_manifest`) and
  URLconf (`djiiif.urls`): `path("iiif/", include("djiiif.urls"))` serves both
  `info.json` and `manifest` for stored images with the correct content type and
  CORS header — no separate image server required for the metadata documents.
- `iiif.as_dict()`: returns every profile URL keyed by profile name (with an
  `include_meta=True` option to add the `info`/`identifier` URLs) — convenient for
  templates and JSON responses.
- Optional Django REST Framework support: `djiiif.serializers.IIIFSerializerField`
  serializes an `IIIFField` to its `as_dict()` mapping. Install via the new `drf`
  extra (`pip install djiiif[drf]`); importing `djiiif` never imports DRF.
- System check `check_iiif_profiles` (registered by the new `DjiiifConfig` app
  config): `manage.py check` now validates `IIIF_PROFILES` at startup, flagging a
  non-`dict` setting or a `dict` profile missing required keys.
- `IIIF_IMAGE_API_VERSION` setting (default `3`) selects the generated
  `info_document` / `manifest` shapes — `3` for Image API 3.0 (`id` /
  `type: ImageService3`), `2` for the 2.x `@id` / array-`profile` shape. An
  unknown value raises `ImproperlyConfigured`.
- `IIIF_COMPLIANCE_LEVEL` setting (default `"level2"`) sets the compliance level
  advertised in `info_document` and the manifest's image service.

### Changed
- Identifier encoding now percent-encodes the full IIIF reserved set via
  `urllib.parse.quote`, not just `/` → `%2F`. **This changes emitted URLs only
  for field names that contain characters beyond `/`** (spaces, `?`, `#`, `%`,
  etc.), which previously produced malformed URLs; plain names and names whose
  only special character is `/` are unaffected. Not a breaking change under the
  compatibility policy (it corrects previously-broken output), but noted here for
  anyone who stored such names.
- An empty `IIIF_PROFILES` no longer raises when a field has a value; `info` and
  `identifier` return `""` (and the documents `None`), matching the empty-field
  behavior.
- **Packaging modernized (PEP 621 + setuptools-scm).** All metadata moved to
  `pyproject.toml`; the package version is now derived from the git tag instead
  of a hand-bumped `setup.py`. Removed `setup.py`, `Pipfile`, `Pipfile.lock`,
  `MANIFEST.in`, `requirements.txt`, and `build.sh`. No change to the installed
  package or its runtime dependency (`Django`). **Contributors:** install the dev
  toolchain with `pip install -e ".[dev]"` (Pipenv is no longer used).

## [0.23] - 2026-05-27
### Added
- `iiif.identifier`: a plain `host/identifier` URL (no
  `/region/size/rotation/quality.format` suffix) for handing an image to viewers
  like OpenSeadragon.
### Changed
- Reconciled `master` with the published 0.22 release.
- Added a test suite, CI across Python 3.10–3.13, and a trusted-publishing
  release workflow.

## [0.22] - 2023-09-05
### Fixed
- Corrected an error in URL assembly.

## [0.21] - 2023-09-05
### Added
- Plain, identifier-only URL for easy OpenSeadragon integration (later reconciled
  under 0.23).

## [0.20] - 2020-01-09
### Fixed
- Made `iiif` attribute access safe for empty fields.

## [0.19] - 2020-01-09
### Changed
- Return an empty string for unpopulated (empty/`None`-name) fields instead of
  building a broken URL.

## [0.15]
### Added
- `iiif.info`: the IIIF `info.json` URL for a field.

## [0.1]
### Added
- Initial implementation: `IIIFField` / `IIIFFieldFile` / `IIIFObject`,
  `IIIF_PROFILES`-driven profile URLs (dict and callable shapes), and the
  `{% iiif %}` template tag.

[Unreleased]: https://github.com/rogerhoward/djiiif/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/rogerhoward/djiiif/compare/v0.24...v1.0.0
[0.24]: https://github.com/rogerhoward/djiiif/compare/v0.23...v0.24
[0.23]: https://github.com/rogerhoward/djiiif/compare/0.14...v0.23
[0.22]: https://github.com/rogerhoward/djiiif/releases/tag/0.22
[0.21]: https://github.com/rogerhoward/djiiif/releases/tag/0.21
[0.20]: https://github.com/rogerhoward/djiiif/releases/tag/0.20
[0.19]: https://github.com/rogerhoward/djiiif/releases/tag/0.19
[0.15]: https://github.com/rogerhoward/djiiif/releases/tag/0.15
[0.1]: https://github.com/rogerhoward/djiiif/releases/tag/0.1
