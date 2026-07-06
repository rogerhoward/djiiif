"""Optional GeoDjango bridge for the IIIF navPlace extension.

Resolves ``settings.IIIF_NAVPLACE`` into the GeoJSON ``FeatureCollection`` that
:func:`djiiif.build_manifest` emits as a manifest's ``navPlace`` (see the
`navPlace extension <https://iiif.io/api/extension/navplace/>`_).

This module is **never imported by** :mod:`djiiif` at module load (it is imported
lazily by ``IIIFObject.manifest`` and explicitly by :mod:`djiiif.views`), and it
**never imports** ``django.contrib.gis``: a GEOS geometry is recognized by
duck-typing its ``.geojson`` / ``.srid`` attributes, so projects without the
GDAL/GEOS system libraries are unaffected and plain GeoJSON dicts work everywhere.
"""

import json

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from djiiif import _language_map

# GeoJSON geometry ``type`` values (RFC 7946) — anything else at the top level is
# a Feature or FeatureCollection.
_GEOMETRY_TYPES = frozenset(
    {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    }
)


def _geometry_to_dict(value) -> dict:
    """Coerce a navPlace value into a GeoJSON ``dict``.

    A plain ``dict`` passes through; a GEOS geometry (duck-typed via ``.geojson``)
    is converted with a WGS84 guard.

    Args:
        value: A GeoJSON ``dict`` or a GEOS geometry.

    Returns:
        A GeoJSON ``dict`` (geometry, Feature, or FeatureCollection).

    Raises:
        ImproperlyConfigured: If ``value`` is neither a dict nor a GEOS geometry,
            or a GEOS geometry's SRID is set and is not 4326 (WGS84).
    """
    if isinstance(value, dict):
        return value
    if hasattr(value, "geojson"):  # a GEOS geometry, without importing gis
        srid = getattr(value, "srid", None)
        if srid is not None and srid != 4326:
            raise ImproperlyConfigured(
                f"IIIF_NAVPLACE geometry has SRID {srid}; navPlace requires WGS84 "
                "(EPSG:4326). Reproject first, e.g. geom.transform(4326, clone=True)."
            )
        return json.loads(value.geojson)
    raise ImproperlyConfigured(
        "IIIF_NAVPLACE must resolve to a GeoJSON dict or a GEOS geometry, got "
        f"{type(value).__name__}."
    )


def _to_feature_collection(value: dict, label=None) -> dict:
    """Normalize a GeoJSON ``dict`` to a ``FeatureCollection``.

    A bare geometry is wrapped in a Feature; a Feature is wrapped in a
    FeatureCollection; a FeatureCollection is copied. When ``label`` is given (the
    ``(geometry, label)`` shortcut), it is coerced into the single Feature's
    ``properties`` — it is ignored for a FeatureCollection input, which should
    carry its own per-Feature properties.

    Args:
        value: A GeoJSON geometry, Feature, or FeatureCollection dict.
        label: An optional label for the ``(geometry, label)`` shortcut.

    Returns:
        A fresh ``FeatureCollection`` dict.
    """
    gtype = value.get("type")
    if gtype == "FeatureCollection":
        features = [dict(f) for f in value.get("features", [])]
        return {"type": "FeatureCollection", "features": features}

    if gtype == "Feature":
        feature = dict(value)
    elif gtype in _GEOMETRY_TYPES:
        feature = {"type": "Feature", "geometry": value}
    else:
        raise ImproperlyConfigured(
            f"IIIF_NAVPLACE GeoJSON has unexpected type {gtype!r}; expected a geometry, "
            "Feature, or FeatureCollection."
        )

    if label is not None:
        properties = dict(feature.get("properties") or {})
        properties["label"] = _language_map(label)
        feature["properties"] = properties
    return {"type": "FeatureCollection", "features": [feature]}


def resolve_navplace(parent) -> dict | None:
    """Resolve ``settings.IIIF_NAVPLACE`` to a navPlace ``FeatureCollection``.

    Mirrors :func:`djiiif.resolve_auth`. The setting may be a dotted-path string
    (imported), a callable, or a direct value; a callable is invoked with
    ``parent``. The resolved value may be:

    - ``None`` — no navPlace,
    - a GeoJSON ``dict`` (bare geometry, Feature, or FeatureCollection),
    - a GEOS geometry (converted via ``.geojson``; must be WGS84),
    - a ``(geometry_or_dict, label)`` pair — ``label`` coerced into the Feature's
      ``properties`` (a language map).

    Args:
        parent: The value passed to a callable config. On model paths this is the
            :class:`~djiiif.IIIFFieldFile`; on view paths it is the decoded
            storage name (``str``) — the ``parent: IIIFFieldFile | str`` convention.

    Returns:
        A normalized ``FeatureCollection`` dict, or ``None`` when unset/``None``.

    Raises:
        ImproperlyConfigured: If the resolved value is not an accepted shape, or a
            GEOS geometry is not WGS84.
    """
    nav = getattr(settings, "IIIF_NAVPLACE", None)
    if nav is None:
        return None
    if isinstance(nav, str):
        nav = import_string(nav)
    if callable(nav):
        nav = nav(parent)
    if nav is None:
        return None

    label = None
    if isinstance(nav, tuple):
        nav, label = nav

    return _to_feature_collection(_geometry_to_dict(nav), label)
