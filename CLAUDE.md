# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`djiiif` is a small Django package that extends `ImageField` to expose IIIF Image API URLs. It is published to PyPI as `djiiif`; the package itself has no runtime application — it is consumed by Django projects that depend on it.

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

The whole library is two files; the second is a thin wrapper around the first.

- `djiiif/__init__.py` — defines `IIIFField` (subclass of `ImageField`) whose `attr_class` is `IIIFFieldFile` (subclass of `ImageFieldFile`). Accessing `.iiif` on a field file returns a freshly constructed `IIIFObject`, which reads `settings.IIIF_PROFILES` and sets one attribute per profile name holding the assembled IIIF URL, plus an `info` attribute for the IIIF `info.json` URL. Empty/unset fields produce empty-string URLs (this is the behavior referenced by the "safe for empty fields" / "return empty string for unpopulated fields" commits).
- `djiiif/templatetags/iiiftags.py` — registers the `{% iiif imagefield 'profile' %}` template tag. The tag just does `getattr(imagefield.iiif, profile)`, so it delegates to the real `IIIFObject` via `IIIFFieldFile.iiif`.
- `djiiif/templatetags/__init__.py` — **dead code**: contains an out-of-sync duplicate of `IIIFObject` / `IIIFField` / `urljoin` (no empty-name guard, no `info` URL, sets a stray `url` attribute). Nothing imports it. Treat `djiiif/__init__.py` as the source of truth; this file should be emptied as part of cleanup.

Profiles in `settings.IIIF_PROFILES` may be either a `dict` with keys `host, region, size, rotation, quality, format`, or a callable receiving the `IIIFFieldFile` and returning that same dict shape — callables enable per-image logic (e.g. square crop using `parent.width`/`parent.height`). The identifier segment of the URL is the field's `name` with `/` percent-encoded to `%2F`.

## Keeping docs in sync

Documentation in this repo must stay current with the code. When you change behavior, config, commands, or layout, update the affected docs in the **same commit** — not as a follow-up.

- `README.md` and `README.rst` are both checked in and must stay in sync with each other. When you update one, update the other.
- `CLAUDE.md` (this file) is the contract for future Claude sessions — if you change build/test commands, the public API surface, the testing setup, the coverage gate, or the file layout, update CLAUDE.md so the description matches reality. Stale guidance here is worse than no guidance.
- `docs/` (Sphinx) is currently a skeleton; if it grows real content, treat it the same way.

## Python conventions

- Target Python 3.10+ (`python_requires='>=3.10'` in `setup.py`; `Pipfile` pins 3.10). Keep these and the trove classifiers in sync when bumping the floor.
- Use `from __future__ import annotations` is unnecessary on 3.10+; prefer native PEP 604 (`X | None`) and PEP 585 (`list[str]`) syntax.
- Add type hints to all new/edited public functions, methods, and class attributes. Keep them precise — `Any` is a code smell, not a default.
- Prefer f-strings over `.format()` / `%`. The existing `'{}.{}'.format(...)` calls in `djiiif/__init__.py` and `iiiftags.py` are fine to leave alone but should be migrated when touched.
- Keep `IIIFField` / `IIIFFieldFile` / `IIIFObject` import paths stable — they are part of the public API consumed by downstream Django projects.

## Required test coverage

Every change to `djiiif/` must keep the suite green and the coverage gate satisfied. When adding behavior, add tests alongside it. The suite must always cover:

- Both `IIIF_PROFILES` shapes: plain `dict` profile and callable profile.
- The empty-/`None`-`name` path (must return `""` for every profile attr and for `info`) — this is the regression guarded by the 0.19 / 0.20 commits.
- Identifier encoding: a field name containing `/` must appear as `%2F` in the URL.
- The `{% iiif %}` template tag's happy path and its `NotAnIIIFField` error path.

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
