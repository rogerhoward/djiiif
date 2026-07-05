"""Sphinx configuration for the djiiif documentation.

The docs are written in Markdown (via MyST) with a Furo theme, and the API
reference is generated from the package's Google-style docstrings by autodoc +
napoleon. The version is read from the installed package metadata (setuptools-scm
derives it from the git tag), so it never needs hand-bumping here.
"""

import os
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

# Make the package importable when building from a source checkout (Read the Docs
# installs it, but a local ``make html`` may run against the working tree).
sys.path.insert(0, os.path.abspath("../.."))

# Autodoc imports djiiif, which imports Django. Configure a minimal in-memory
# Django so the import succeeds without a real project (matching the test suite).
import django  # noqa: E402
from django.conf import settings  # noqa: E402

if not settings.configured:
    settings.configure(
        INSTALLED_APPS=["djiiif"],
        DATABASES={},
        IIIF_PROFILES={},
        USE_TZ=True,
    )
    django.setup()


# -- Project information ------------------------------------------------------

project = "djiiif"
author = "Roger Howard"
copyright = "2017–2026, Roger Howard"

try:
    release = _pkg_version("djiiif")
except PackageNotFoundError:  # not installed (e.g. a bare checkout)
    release = "0.0.0"
version = ".".join(release.split(".")[:2])


# -- General configuration ----------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_parser",
    "sphinx_copybutton",
]

templates_path = ["_templates"]
exclude_patterns = []

# MyST (Markdown) — enable the small set of extensions the docs actually use.
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

# Autodoc / napoleon.
autodoc_member_order = "bysource"
autodoc_typehints = "description"
add_module_names = False
napoleon_google_docstring = True
napoleon_numpy_docstring = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}


# -- HTML output --------------------------------------------------------------

html_theme = "furo"
html_title = f"djiiif {version}"
html_static_path = ["_static"]
