# AUTH-API — Optional IIIF Authorization Flow API 2.0 integration

**Status:** Implemented on branch `auth-api` (metadata-only, per this brief)
**Branch:** `auth-api`
**Date:** 2026-07-03

## Problem

djiiif generates IIIF Image API URLs and metadata documents — `info.json` (via
`iiif.info_document`) and a Presentation manifest (via `iiif.manifest`) — for
images stored by a Django app and served by an external IIIF image server. Some
deployments serve **access-controlled** images through servers that implement the
[IIIF Authorization Flow API 2.0](https://iiif.io/api/auth/2.0/) — notably
**iiiris**, a IIIF Image API 3.0 + Authorization Flow 2.0 image server.

For a viewer (Mirador / OpenSeadragon) to authenticate against such a server, the
**auth service descriptions** must be embedded in the IIIF metadata the viewer
consumes. Today djiiif emits no auth services, so its generated
`info_document` / `manifest` cannot drive an authenticated viewer flow.

This brief evaluates an **optional, opt-in** integration whose goal is to make
**IIIF Auth easy from a Django app**, across two different server situations:

- **Mode A — server implements Auth 2.0 (iiiris).** The probe/access/token
  endpoints already exist on the image server. djiiif only needs to *describe*
  them in the `info.json`/manifest it generates, pointing at the server's
  endpoints. The server enforces access.
- **Mode B — server does NOT implement Auth 2.0 (Cantaloupe).** The endpoints
  don't exist, so something must provide them. That "something" could be
  **djiiif-provided Django views** (probe/access/token/logout), with the metadata
  pointing at those Django endpoints. **Caveat:** the image bytes are still served
  by Cantaloupe, which won't validate tokens by itself — so Mode B also needs an
  **enforcement point** on the image path (Cantaloupe's own delegate/pre-authorize
  hooks, or a Django-proxied image route). Describing + issuing tokens is
  necessary but not sufficient to actually restrict access.
  **Scoped out of this brief — see [Future work](#future-work--ideas).**

**This brief covers Mode A only.** The integration must stay opt-in, with no
effect (and no new hard dependency) when unconfigured.

## Background — how Auth 2.0 splits responsibilities

The Authorization Flow API 2.0 is a *pattern*, not a protocol like OAuth2. Its
work is divided across three parties:

- **Content / image server (iiiris):** implements the probe, access, token, and
  (optional) logout endpoints; validates bearer tokens; serves protected pixels.
  **Not djiiif's job.**
- **Client / viewer:** orchestrates the flow — probe → open access (login) tab →
  load token service in a hidden iframe → re-probe with `Authorization: Bearer` →
  load content. **Not djiiif's job.**
- **The metadata:** the nested `service` block that *describes* the auth services
  (`AuthProbeService2` → `AuthAccessService2` → `AuthAccessTokenService2` /
  `AuthLogoutService2`). Per the spec, the **probe service MUST appear in the
  Image API `info.json`** and MAY also appear in the Presentation manifest.
  **This is the djiiif surface.**

Service block shape (nested):

```
access-controlled resource
  service: [ AuthProbeService2 (id, type)
             service: [ AuthAccessService2 (id, type, profile: active|kiosk|external, label/heading/note/confirmLabel)
                        service: [ AuthAccessTokenService2 (id, type),
                                   AuthLogoutService2 (id, type, label) ] ] ]
```

So the likely scope is **metadata-only**: djiiif describes the services so a
compliant viewer can run the flow against the server that actually enforces auth.

## Scope (settled)

**Mode A only, metadata-only.** djiiif embeds an Authorization Flow 2.0 `service`
block into the documents it already generates (`info_document`, and `manifest`),
describing the probe → access → token/logout services and pointing at the image
server's own endpoints (e.g. iiiris). The server implements and enforces
everything; djiiif only *describes*.

Because djiiif is pure metadata pass-through here, it supports all three access
patterns (`active` / `kiosk` / `external`) for free — it serializes whatever the
configured service block says.

## Design

- **New optional setting `IIIF_AUTH`**, mirroring the existing `IIIF_PROFILES`
  dict-or-callable pattern — giving both granularities from one design:
  - a **`dict`** (or a `ProbeService` helper, below) → applied to every image
    (uniform), **or**
  - a **callable** receiving the `IIIFFieldFile` and returning that value **or
    `None`** → per-image control (public images return `None` and get no auth
    block; restricted images return the block). Same ergonomics as callable
    profiles; `resolve_auth(parent)` normalizes all shapes to a `dict` or `None`,
    parallel to `resolve_profile`.
- **Full typed helpers** (parallel to the `Profile` dataclass), the recommended
  way to build the block: `ProbeService`, `AccessService`, `TokenService`,
  `LogoutService`. Each carries the correct Auth 2.0 `type` (`AuthProbeService2`,
  `AuthAccessService2`, `AuthAccessTokenService2`, `AuthLogoutService2`) and the
  `active`-pattern UI fields (`label` / `heading` / `note` / `confirm_label`, as
  IIIF language maps). `.as_dict()` emits the correctly nested block. Raw dicts
  are still accepted for full control.
- **Emission:** when `IIIF_AUTH` resolves to a non-`None` value for an image, the
  probe service (with nested access → token/logout) is attached to
  `info_document`'s top-level `service` array (spec-required location) **and** to
  the access-controlled image resource's `service` in `manifest` (alongside the
  `ImageService3`).
- **Optionality / back-compat:** no `IIIF_AUTH` (or a callable returning `None`)
  ⇒ documents are byte-identical to today. No new hard dependency. Purely
  additive, opt-in — non-breaking, no MAJOR bump.
- **Version coupling:** Auth 2.0 service types pair with Image/Presentation API 3,
  so the block is emitted only at `IIIF_IMAGE_API_VERSION = 3`. If `IIIF_AUTH` is
  set while `= 2`, **raise `ImproperlyConfigured`** (fail loud on the mismatch,
  consistent with the existing unknown-version behavior). Auth 1.0's different
  service shape is out of scope.

### Configuration example

```python
from djiiif import ProbeService, AccessService, TokenService, LogoutService

# Uniform: every image is access-controlled by the iiiris server.
IIIF_AUTH = ProbeService(
    id="https://iiiris.example/auth/probe",
    access=AccessService(
        id="https://iiiris.example/auth/login",
        profile="active",
        label={"en": ["Log in to Example Institution"]},
        heading={"en": ["Restricted material"]},
        note={"en": ["Please log in with your institutional account."]},
        confirm_label={"en": ["Log in"]},
        token=TokenService(id="https://iiiris.example/auth/token"),
        logout=LogoutService(
            id="https://iiiris.example/auth/logout",
            label={"en": ["Log out"]},
        ),
    ),
)

# Per-image: return None for public images, the ProbeService for restricted ones.
def image_auth(parent):
    if parent.instance.is_public:
        return None
    return ProbeService(id="https://iiiris.example/auth/probe", access=...)

IIIF_AUTH = image_auth
```

### Rough implementation outline

- `djiiif/__init__.py`: `ProbeService` / `AccessService` / `TokenService` /
  `LogoutService` dataclasses + `resolve_auth(parent) -> dict | None`; a
  `build_auth_service(...)` (or the helpers' `.as_dict()`) producing the nested
  block; `IIIFObject` gains the resolved block and threads it into
  `info_document` / `manifest` (guarded by the v3 check).
- No new modules or dependencies; no views, URLs, or settings beyond `IIIF_AUTH`.

## Non-goals

- **Mode B** — supporting servers that don't implement Auth 2.0 (e.g. Cantaloupe):
  no djiiif-provided probe/access/token/logout endpoints, no token issuance/
  validation, no image-byte enforcement/proxy. Explicitly out of scope here; see
  **Future work** for a concrete path.
- Implementing or orchestrating the viewer-side flow.
- Auth API **1.0**.
- Any change to how access is enforced — that stays entirely on the image server.

## Future work / ideas

- **Mode B via a Cantaloupe JRuby auth delegate (bridge Django ↔ Cantaloupe).**
  For servers that lack native Auth 2.0 (Cantaloupe), djiiif could ship a
  **Cantaloupe delegate script** (Ruby, run under JRuby) implementing Cantaloupe's
  `authorize` / `pre_authorize` hooks. The delegate would validate the request
  against Django/djiiif before Cantaloupe serves pixels — e.g. verify a signed
  token or call back to a Django verify/probe endpoint — while djiiif provides the
  Django-side probe/access/token services (ideally backed by
  `django.contrib.auth`). This closes the enforcement gap that makes Mode B unsafe
  today (Cantaloupe otherwise serves raw image URLs to anyone), turning djiiif +
  the delegate into a drop-in Auth 2.0 layer in front of a non-supporting server.
  Larger scope (security-sensitive token handling, a shipped non-Python artifact,
  Cantaloupe version/delegate-API coupling) — deferred to a separate brief.

## Decisions

1. **Granularity** — support **both** (dict = uniform, callable = per-image),
   for free from the `IIIF_PROFILES`-style dict-or-callable design.
2. **Documents** — emit in **`info_document` + `manifest`**.
3. **Typed helpers** — **ship full** `ProbeService` / `AccessService` /
   `TokenService` / `LogoutService` dataclasses (raw dicts still accepted).
4. **Version at `= 2`** — **raise `ImproperlyConfigured`**.
5. **Service URLs** — **configured** by the user in `IIIF_AUTH`; not derived.

## Testing (per repo conventions — 90% coverage gate)

- Auth block present in `info_document` and `manifest` when `IIIF_AUTH` is set,
  with correct Auth 2.0 nesting/`type`s, via both a `dict`/`ProbeService`
  (uniform) and a callable (per-image).
- Callable returning `None` (public image) ⇒ **no** `service` block; documents
  unchanged.
- `IIIF_AUTH` unset ⇒ documents byte-identical to current output (regression).
- `ImproperlyConfigured` raised when `IIIF_AUTH` is set and
  `IIIF_IMAGE_API_VERSION = 2`.
- Typed helpers: `.as_dict()` shape, defaults, and that a `ProbeService` works as
  an `IIIF_AUTH` value.

## Docs & compatibility

- **Backwards-compatible / additive** — public API and existing document output
  unchanged when `IIIF_AUTH` is unset. No MAJOR bump; a normal `Added` CHANGELOG
  entry.
- Update `README.md` (new "IIIF authorization" section), `CLAUDE.md`
  (architecture + required-coverage), and `CHANGELOG.md` in the same change, per
  the docs-in-sync policy.

## Remaining unknowns / to verify during implementation

- **Exact manifest placement** of the probe service for an access-controlled
  image body in Presentation 3.0 (on the annotation body's `service` array
  alongside `ImageService3`) — confirm against the spec's manifest examples.
- **iiiris service-URL conventions** — confirmed as user-configured for this
  scope; worth a quick look at iiiris docs in case a future convenience default is
  warranted (non-blocking).
- **Language-map ergonomics** — whether the helpers accept plain strings and wrap
  them into `{"none": [...]}` / `{"en": [...]}`, or require language maps. Minor
  API-polish decision for implementation time.

## References

- [IIIF Authorization Flow API 2.0](https://iiif.io/api/auth/2.0/)
- [Auth 2.0 change log](https://iiif.io/api/auth/2.0/change-log/)
- iiiris — IIIF Image API 3.0 + Authorization Flow 2.0 image server _(add canonical URL)_
