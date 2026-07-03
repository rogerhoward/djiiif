# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`djiiif` is a small Django package that extends `ImageField` to expose IIIF Image API URLs. It is published to PyPI as `djiiif`; the package itself has no runtime application — it is consumed by Django projects that depend on it.

## Backwards compatibility

**Preserve backwards compatibility by default.** Because `djiiif` is a published library consumed by downstream Django projects, treat its public surface — the `IIIFField` / `IIIFFieldFile` / `IIIFObject` import paths, the `.iiif` attribute and its profile/`info`/`identifier` attributes, the `IIIF_PROFILES` config shapes (plain `dict` and callable), and the `{% iiif %}` template tag — as a contract that must not break without approval.

- **Do not introduce a breaking change unless the operator has explicitly called it out and approved the breakage.** If a task's cleanest implementation would break compatibility, stop and surface it rather than shipping the break silently — offer a backwards-compatible path first.
- **Any approved breakage must be documented for users** — a `CHANGELOG` / release-notes entry stating what changed, why, and the migration path — and updated in `README.md`/`README.rst` and this file in the same commit.
- **Any approved breakage causes a MAJOR version bump** (semver: `X.0` → `(X+1).0`), never a minor/patch release. Bug fixes and new backwards-compatible features stay within the current major.

## Changelog

**Maintain `CHANGELOG.md` automatically.** It is the canonical, user-facing record of what changed — keep it current as part of the work, never as a follow-up.

- **Every change that affects users** — new features, behavior changes, bug fixes, deprecations, and (approved) breaks — gets an entry in `CHANGELOG.md` **in the same commit** as the code/doc change. Internal-only churn (refactors, test-only or CI-only changes, formatting) does not need an entry.
- Follow the existing format: [Keep a Changelog](https://keepachangelog.com/) headings (`Added` / `Changed` / `Fixed` / `Deprecated` / `Removed` / `Security`), newest first. Accumulate entries under a top **`## [Unreleased]`** section as you work.
- **Breaking changes** go under a **`Breaking`** heading in the entry and must state the migration path — this is the same entry the backwards-compatibility policy above requires, and it pairs with the MAJOR version bump.
- **At release time**, rename `## [Unreleased]` to the new version with the release date (`## [X.Y] - YYYY-MM-DD`), add a fresh empty `## [Unreleased]` above it, and update the compare/link references at the bottom. Keep the version in `CHANGELOG.md` consistent with the `setup.py` version and the release tag.

## Build & release

**Releases are automated.** Do not run `./build.sh` or `twine upload` from a workstation.

To cut a release:

1. Bump `version=` in `setup.py` and commit on `master` (or merge to it).
2. Create a GitHub Release with tag `vX.Y` (e.g. `v0.21`) targeting that commit. The tag — minus the leading `v` — **must** match the `setup.py` version; the release workflow asserts this and fails the build otherwise.
3. `.github/workflows/release.yml` then: installs deps, runs the test suite, builds sdist + wheel via `python -m build`, runs `twine check`, and publishes to PyPI via OIDC trusted publishing (no API token in secrets).

`build.sh` is legacy from before CI — it still works for local sanity checks but is not the release path.

**One-time PyPI setup required:** the project must have a Trusted Publisher configured at https://pypi.org/manage/project/djiiif/settings/publishing/ pointing at `rogerhoward/djiiif`, workflow `release.yml`, environment `pypi`. The matching GitHub Environment `pypi` can also gate the publish job with manual approval / branch restrictions.

Pipenv pins the build/docs/test toolchain (`twine`, `sphinx`, `pytest`, `pytest-django`, `pytest-cov`, `django`) — see `Pipfile`. Runtime dependency is `Django` (declared in `setup.py`).

## Tests

```bash
pip install -e . django pytest pytest-django pytest-cov   # one-time setup (or via Pipenv)
pytest                                                    # runs all tests + coverage gate
pytest tests/test_iiif_object.py::test_dict_profile_builds_url   # single test
```

Tests live in `tests/`. `tests/conftest.py` configures a minimal in-memory Django (no DB) via `settings.configure(...)` — there is no `manage.py` and no `DJANGO_SETTINGS_MODULE`. Pytest config (testpaths, coverage flags, fail-under threshold) is in `pyproject.toml`.

CI runs the same `pytest` invocation across Python 3.10–3.13 via `.github/workflows/test.yml`.

**Coverage gate: 90% (`--cov-fail-under=90` in `pyproject.toml`).** Any change that drops coverage below the gate must either add tests or — if the line is genuinely defensive/unreachable — raise the gate intentionally rather than silently lowering it.

## Architecture

The core is `djiiif/__init__.py`; the other modules are thin, optional add-ons around it.

- `djiiif/__init__.py` — defines `IIIFField` (subclass of `ImageField`) whose `attr_class` is `IIIFFieldFile` (subclass of `ImageFieldFile`). Accessing `.iiif` on a field file returns a freshly constructed `IIIFObject`, which reads `settings.IIIF_PROFILES` and sets one attribute per profile name holding the assembled IIIF URL, plus an `info` attribute for the IIIF `info.json` **URL** and an `identifier` attribute for the plain `host/identifier` URL (used for openseadragon-style integrations). Empty/unset fields — **and an empty `IIIF_PROFILES`** — produce empty-string URLs without raising (the "safe for empty fields" behavior, extended in 0.24 to the no-profiles case).
  - **Module-level builders** (all public, all reused by the serving view): `encode_identifier(name)` percent-encodes the identifier segment; `resolve_profile(profile, parent)` normalizes any profile shape to a spec `dict`; `image_url(spec, identifier)` assembles the Image API URL; `build_info_document(...)` and `build_manifest(...)` construct the two JSON documents; `_api_version`/`_compliance_level` resolve the version/level settings. `IIIF_CONTEXTS` maps Image API version → `@context` URI; `PRESENTATION_CONTEXT` is the Presentation 3.0 context; `PROFILE_KEYS` is the required-key tuple.
  - `Profile` (frozen dataclass, added 0.24) is the typed, opt-in profile shape with 3.0 defaults (`size="max"`) and `mirror`/`upscale` flags that fold into the `!`-rotation / `^`-size prefixes via `.as_spec()`.
  - `IIIFObject.info_document` and `IIIFObject.manifest` (both `cached_property`, 0.24) are distinct from the eager URL attributes: they return **documents** (`dict`, or `None` for an empty field) built from the image's own `width`/`height`. They are the *only* attributes that read the file from storage, so constructing an `IIIFObject` stays I/O-free (the constructor stores `self._parent` for them). Both honor `IIIF_IMAGE_API_VERSION` (default `3`; `2` switches to 2.x shapes) and `IIIF_COMPLIANCE_LEVEL` (default `"level2"`); an unknown version raises `ImproperlyConfigured`.
- `djiiif/views.py` + `djiiif/urls.py` (0.24) — optional drop-in `serve_info_json` view and its URLconf. Maps an encoded identifier back to a stored image via `default_storage`, reads dimensions with `get_image_dimensions`, and returns `build_info_document(...)` as `application/ld+json` with a `*` CORS header; the document `id` comes from the request URL. Included via `path("iiif/", include("djiiif.urls"))`; uses default storage only.
- `djiiif/checks.py` + `djiiif/apps.py` (0.24) — `DjiiifConfig.ready()` registers `check_iiif_profiles`, a system check that validates `IIIF_PROFILES` at startup (ids `djiiif.W001`/`E001`/`E002`/`E003`). Callable and `Profile` entries pass unchecked (a callable's shape is only knowable at call time).
- `djiiif/templatetags/iiiftags.py` — registers the `{% iiif imagefield 'profile' %}` template tag. The tag just does `getattr(imagefield.iiif, profile)`, so it delegates to the real `IIIFObject` via `IIIFFieldFile.iiif`.
- `djiiif/templatetags/__init__.py` — **dead code**: contains an out-of-sync duplicate of `IIIFObject` / `IIIFField` / `urljoin`. Nothing imports it. Treat `djiiif/__init__.py` as the source of truth; this file should be emptied as part of cleanup.

Profiles in `settings.IIIF_PROFILES` may be a `dict` with keys `host, region, size, rotation, quality, format`, a `Profile` instance, or a callable receiving the `IIIFFieldFile` and returning either a `dict` or a `Profile` — callables enable per-image logic (e.g. square crop using `parent.width`/`parent.height`). The identifier segment is the field's `name` fully percent-encoded via `encode_identifier` (`/` → `%2F`, plus the rest of the reserved set); as of 0.24 this replaces the old `/`-only `str.replace`, so names containing spaces/`?`/`#`/etc. now encode correctly (a URL change only for such names).

## Keeping docs in sync

Documentation in this repo must stay current with the code. When you change behavior, config, commands, or layout, update the affected docs in the **same commit** — not as a follow-up.

- `README.md` is the **single source of truth** for the readme — there is no `README.rst` (it was removed to eliminate the two-file drift). Do not recreate a second readme file; if a reStructuredText copy is ever needed (e.g. for a tool that requires it), generate it from `README.md` rather than hand-maintaining a duplicate.
- `CLAUDE.md` (this file) is the contract for future Claude sessions — if you change build/test commands, the public API surface, the testing setup, the coverage gate, or the file layout, update CLAUDE.md so the description matches reality. Stale guidance here is worse than no guidance.
- `docs/` (Sphinx) is currently a skeleton; if it grows real content, treat it the same way.

## Python conventions

- Target Python 3.10+ (`python_requires='>=3.10'` in `setup.py`; `Pipfile` pins 3.10). Keep these and the trove classifiers in sync when bumping the floor.
- Use `from __future__ import annotations` is unnecessary on 3.10+; prefer native PEP 604 (`X | None`) and PEP 585 (`list[str]`) syntax.
- Add type hints to all new/edited public functions, methods, and class attributes. Keep them precise — `Any` is a code smell, not a default.
- Prefer f-strings over `.format()` / `%`. The existing `'{}.{}'.format(...)` calls in `djiiif/__init__.py` and `iiiftags.py` are fine to leave alone but should be migrated when touched.
- **Docstrings & comments use [Google style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)** (`Args:` / `Returns:` / `Raises:` sections, one-line summary first). Every public module, class, and function gets a docstring; comments explain *why*, not *what*. **Whenever you touch a function, method, class, or module, create or update its docstring and any nearby comments so they match the new behavior in the same edit** — stale or missing docs on code you changed is not acceptable. Don't leave a wall of prose: keep summaries tight and only add `Args:`/`Returns:`/`Raises:` sections where they carry real information.
- Keep `IIIFField` / `IIIFFieldFile` / `IIIFObject` import paths stable — they are part of the public API consumed by downstream Django projects.

## Required test coverage

Every change to `djiiif/` must keep the suite green and the coverage gate satisfied. When adding behavior, add tests alongside it. The suite must always cover:

- Both `IIIF_PROFILES` shapes: plain `dict` profile and callable profile.
- The empty-/`None`-`name` path (must return `""` for every profile attr, for `info`, and for `identifier`) — this is the regression guarded by the 0.19 / 0.20 commits.
- Identifier encoding: a field name containing `/` must appear as `%2F`, and other reserved characters (space, `?`, `#`, …) must be percent-encoded too.
- The `{% iiif %}` template tag's happy path and its `NotAnIIIFField` error path.
- `info_document`: the default (v3) and `IIIF_IMAGE_API_VERSION=2` document shapes, the `IIIF_COMPLIANCE_LEVEL` override, `None` for an empty field, the `ImproperlyConfigured` unknown-version path, and that `.info` (the URL) is unchanged alongside it.
- `Profile`: the 3.0 defaults, the `mirror`/`upscale` prefix folding (including the no-double-prefix guards), and that a `Profile` works as an `IIIF_PROFILES` entry; `resolve_profile` for dict/`Profile`/callable inputs plus its two `ImproperlyConfigured` rejection paths.
- `manifest`: the Presentation-3.0 top-level shape, the nested canvas/image body, the `ImageService2` (v2) variant, and `None` for an empty field.
- The `serve_info_json` view: the happy path (document body, `application/ld+json`, CORS header) and its `Http404` paths (missing file, non-image).
- `check_iiif_profiles`: valid profiles pass; the `W001` (unset), `E001` (non-dict), `E002` (bad type), and `E003` (missing keys) paths each fire.
- The empty-`IIIF_PROFILES` path must not raise (`info`/`identifier` are `""`, documents are `None`).

## Formatting & linting

- Use `ruff` for both linting and formatting (`ruff check .` and `ruff format .`). No separate `black` / `flake8` / `isort` — `ruff` covers all three.
- Line length 100. Double quotes. `pyproject.toml` already exists (for pytest/coverage); add a `[tool.ruff]` block there rather than introducing a separate config file.
- Run `ruff check --fix` before committing; never silence a lint with `# noqa` without a comment explaining why.

## Packaging modernization notes

The repo still uses legacy `setup.py` + `build.sh` + `MANIFEST.in`. When modernizing:

- Migrate `setup.py` metadata into the existing `pyproject.toml` (PEP 621). `pyproject.toml` already declares the `[build-system]` (setuptools backend) and holds pytest/coverage config; the migration moves `name`/`version`/`install_requires`/classifiers/etc. there too and can then delete `setup.py`.
- Consider `setuptools-scm` so the package version is derived from the git tag instead of being hand-bumped in `setup.py` — this would let us drop the tag-vs-version assertion in `release.yml`.
- Replace `python3 setup.py sdist bdist` with `python -m build`; replace the egg-info / `build/` / `dist/` clutter accordingly (and add them to `.gitignore` if not already).
- Drop `Pipfile` in favor of optional dependency groups in `pyproject.toml` (e.g. `[project.optional-dependencies] dev = [...]`), unless the user explicitly wants to keep Pipenv.
