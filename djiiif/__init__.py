"""IIIF integration for Django's ``ImageField``.

Defines :class:`IIIFField` (an ``ImageField`` subclass) whose field files expose
an ``.iiif`` accessor. That accessor returns an :class:`IIIFObject` carrying one
IIIF Image API URL per configured profile, plus the ``info``/``identifier`` URLs
and the generated ``info_document`` / ``manifest`` documents.

Profiles are configured in ``settings.IIIF_PROFILES`` and may be a plain ``dict``,
a :class:`Profile` instance, or a callable returning either (see
:func:`resolve_profile`).

Optionally, ``settings.IIIF_AUTH`` describes an IIIF Authorization Flow 2.0 probe
service (a :class:`ProbeService`, a ``dict``, or a callable returning either or
``None``); when set, its ``service`` block is embedded in the generated
``info_document`` / ``manifest`` for access-controlled images (see
:func:`resolve_auth`).

The module also provides IIIF Content State API 1.0 helpers
(:func:`encode_content_state` / :func:`decode_content_state` /
:func:`build_content_state`, plus :meth:`IIIFObject.content_state`) for building
the shareable ``iiif-content=`` deep links that open an image — optionally zoomed
to a region — in a manifest-aware viewer.
"""

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from urllib.parse import quote, unquote

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import ImageField
from django.db.models.fields.files import ImageFieldFile

# @context URI advertised in a generated info.json, keyed by Image API version.
IIIF_CONTEXTS: dict[int, str] = {
    2: "http://iiif.io/api/image/2/context.json",
    3: "http://iiif.io/api/image/3/context.json",
}

# @context URI for a generated Presentation API manifest (always version 3).
PRESENTATION_CONTEXT = "http://iiif.io/api/presentation/3/context.json"

# Keys every fully-resolved profile spec must provide.
PROFILE_KEYS = ("host", "region", "size", "rotation", "quality", "format")


def urljoin(parts):
    """Join URL parts with single slashes, preserving a trailing slash.

    Args:
        parts: A non-empty list of URL fragments. Interior fragments are
            stripped of surrounding slashes; the final fragment keeps any
            trailing slash so callers can build directory-style URLs.

    Returns:
        The joined URL string.

    Raises:
        ValueError: If ``parts`` is empty.
    """
    if len(parts) == 0:
        raise ValueError("urljoin needs a list of at least length 1")
    return "/".join([x.strip("/") for x in parts[0:-1]] + [parts[-1].lstrip("/")])


def encode_identifier(name: str) -> str:
    """Percent-encode a field-file name into a IIIF identifier segment.

    The IIIF Image API treats the identifier as a single path segment, so every
    character in the reserved to-encode set (``/ ? # [ ] @ %`` and friends) must
    be percent-encoded — not just ``/``. ``quote(safe="")`` encodes everything
    outside the unreserved set, which is a superset of the required behavior and
    keeps ordinary filenames (``foo.jpg``) untouched while correctly encoding
    ``a/b.jpg`` → ``a%2Fb.jpg`` and names containing spaces, ``?``, ``#``, etc.

    Args:
        name: The stored file name (e.g. ``"uploads/photo.jpg"``).

    Returns:
        The encoded identifier segment.
    """
    return quote(name, safe="")


@dataclass(frozen=True)
class Profile:
    """A typed, IIIF Image API 3.0-aware image profile.

    A structured alternative to the raw ``dict`` profile shape, with 3.0-friendly
    defaults (``size="max"``) and helpers for the two 3.0 features that are easy
    to get wrong as hand-written strings: mirroring (``!`` rotation prefix) and
    upscaling (``^`` size prefix). Existing ``dict`` and callable profiles keep
    working unchanged; this is purely an additive, opt-in convenience.

    Attributes:
        host: Base URL of the IIIF image server.
        region: IIIF region parameter (``"full"``, ``"square"``, ``x,y,w,h``…).
        size: IIIF size parameter (``"max"``, ``"w,"``, ``"w,h"``…). If
            ``upscale`` is set and this does not already start with ``^``, a
            ``^`` prefix is added when the spec is built.
        rotation: IIIF rotation in degrees as a string. If ``mirror`` is set and
            this does not already start with ``!``, a ``!`` prefix is added.
        quality: IIIF quality (``"default"``, ``"color"``, ``"gray"``…).
        format: IIIF output format extension (``"jpg"``, ``"png"``, ``"webp"``…).
        mirror: When true, mirror the image (adds the ``!`` rotation prefix).
        upscale: When true, permit upscaling beyond the region (adds the ``^``
            size prefix).
    """

    host: str
    region: str = "full"
    size: str = "max"
    rotation: str = "0"
    quality: str = "default"
    format: str = "jpg"
    mirror: bool = False
    upscale: bool = False

    def as_spec(self) -> dict[str, str]:
        """Resolve this profile to the plain ``dict`` spec the builders consume.

        Folds :attr:`mirror` and :attr:`upscale` into the ``rotation`` and
        ``size`` strings, guarding against double-prefixing when the caller
        already supplied a ``!``/``^`` prefix.

        Returns:
            A dict with the keys in :data:`PROFILE_KEYS`.
        """
        rotation = self.rotation
        if self.mirror and not rotation.startswith("!"):
            rotation = f"!{rotation}"

        size = self.size
        if self.upscale and not size.startswith("^"):
            size = f"^{size}"

        return {
            "host": self.host,
            "region": self.region,
            "size": size,
            "rotation": rotation,
            "quality": self.quality,
            "format": self.format,
        }


def resolve_profile(profile, parent) -> dict[str, str]:
    """Normalize any supported profile shape into a plain spec ``dict``.

    Accepts the three configured shapes — a :class:`Profile`, a callable
    receiving ``parent`` and returning a ``Profile`` or ``dict``, or a plain
    ``dict`` — and returns a uniform ``dict`` for URL assembly.

    Args:
        profile: The value from ``settings.IIIF_PROFILES`` for one profile name.
        parent: The :class:`IIIFFieldFile` passed to callable profiles.

    Returns:
        A resolved spec dict containing the keys in :data:`PROFILE_KEYS`.

    Raises:
        ImproperlyConfigured: If ``profile`` (or a callable's return value) is
            not a ``Profile``, callable, or ``dict``.
    """
    if isinstance(profile, Profile):
        return profile.as_spec()
    if isinstance(profile, dict):
        return profile
    if callable(profile):
        resolved = profile(parent)
        if isinstance(resolved, Profile):
            return resolved.as_spec()
        if isinstance(resolved, dict):
            return resolved
        raise ImproperlyConfigured(
            "An IIIF_PROFILES callable must return a dict or Profile, got "
            f"{type(resolved).__name__}."
        )
    raise ImproperlyConfigured(
        "Each IIIF_PROFILES entry must be a dict, Profile, or callable, got "
        f"{type(profile).__name__}."
    )


def _language_map(value: str | list[str] | dict | None) -> dict | None:
    """Coerce a label-ish value into a IIIF language map.

    Accepts a plain string or list of strings (wrapped under the ``"none"``
    language key) or an already-formed language map (returned unchanged).

    Args:
        value: A string, list of strings, language-map ``dict``, or ``None``.

    Returns:
        A language map ``dict``, or ``None`` if ``value`` is ``None``.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return {"none": [value]}
    return {"none": list(value)}


@dataclass(frozen=True)
class LogoutService:
    """An Authorization Flow 2.0 logout service (``AuthLogoutService2``)."""

    id: str
    label: str | list[str] | dict | None = None

    def as_dict(self) -> dict:
        """Serialize to the nested Auth 2.0 service ``dict``."""
        service = {"id": self.id, "type": "AuthLogoutService2"}
        label = _language_map(self.label)
        if label is not None:
            service["label"] = label
        return service


@dataclass(frozen=True)
class TokenService:
    """An Authorization Flow 2.0 access token service (``AuthAccessTokenService2``)."""

    id: str

    def as_dict(self) -> dict:
        """Serialize to the nested Auth 2.0 service ``dict``."""
        return {"id": self.id, "type": "AuthAccessTokenService2"}


@dataclass(frozen=True)
class AccessService:
    """An Authorization Flow 2.0 access service (``AuthAccessService2``).

    Attributes:
        id: The access service URI.
        profile: The interaction pattern — ``"active"`` (interactive login),
            ``"kiosk"`` (automatic), or ``"external"`` (ambient/IP).
        label / heading / note / confirm_label: ``active``-pattern UI text; each
            accepts a plain string, list of strings, or a IIIF language map.
        token: The nested :class:`TokenService`.
        logout: The optional nested :class:`LogoutService`.
    """

    id: str
    profile: str = "active"
    label: str | list[str] | dict | None = None
    heading: str | list[str] | dict | None = None
    note: str | list[str] | dict | None = None
    confirm_label: str | list[str] | dict | None = None
    token: TokenService | None = None
    logout: LogoutService | None = None

    def as_dict(self) -> dict:
        """Serialize to the nested Auth 2.0 service ``dict``."""
        service = {"id": self.id, "type": "AuthAccessService2", "profile": self.profile}
        for key, value in (
            ("label", self.label),
            ("heading", self.heading),
            ("note", self.note),
            ("confirmLabel", self.confirm_label),
        ):
            language_map = _language_map(value)
            if language_map is not None:
                service[key] = language_map

        nested = [s.as_dict() for s in (self.token, self.logout) if s is not None]
        if nested:
            service["service"] = nested
        return service


@dataclass(frozen=True)
class ProbeService:
    """An Authorization Flow 2.0 probe service (``AuthProbeService2``).

    The top of the nested auth service block and the value clients look for in an
    ``info.json`` / manifest. Use as an ``IIIF_AUTH`` value or return it from an
    ``IIIF_AUTH`` callable.

    Attributes:
        id: The probe service URI.
        access: The nested :class:`AccessService`.
    """

    id: str
    access: AccessService | None = None

    def as_dict(self) -> dict:
        """Serialize to the nested Auth 2.0 service ``dict``."""
        service = {"id": self.id, "type": "AuthProbeService2"}
        if self.access is not None:
            service["service"] = [self.access.as_dict()]
        return service


def resolve_auth(parent) -> dict | None:
    """Resolve ``settings.IIIF_AUTH`` to a probe-service ``dict`` for an image.

    Mirrors :func:`resolve_profile`: the setting may be a :class:`ProbeService`,
    a raw ``dict``, a callable receiving the field file and returning either (or
    ``None`` for a public image), or unset. Empty/public cases resolve to
    ``None`` so no auth block is emitted.

    Args:
        parent: The :class:`IIIFFieldFile` passed to callable configs.

    Returns:
        The nested probe-service ``dict``, or ``None`` when there is no auth.

    Raises:
        ImproperlyConfigured: If the (resolved) value is not a ``ProbeService``,
            ``dict``, or ``None``.
    """
    auth = getattr(settings, "IIIF_AUTH", None)
    if auth is None:
        return None
    if callable(auth):
        auth = auth(parent)
    if auth is None:
        return None
    if isinstance(auth, ProbeService):
        return auth.as_dict()
    if isinstance(auth, dict):
        return auth
    raise ImproperlyConfigured(
        "IIIF_AUTH must be a ProbeService, dict, callable, or None, got "
        f"{type(auth).__name__}."
    )


def image_url(spec: dict[str, str], identifier: str) -> str:
    """Assemble a full IIIF Image API request URL from a resolved spec.

    Args:
        spec: A resolved profile spec (keys in :data:`PROFILE_KEYS`).
        identifier: An already-encoded identifier segment (see
            :func:`encode_identifier`).

    Returns:
        The ``{host}/{identifier}/{region}/{size}/{rotation}/{quality}.{format}``
        URL.
    """
    return urljoin(
        [
            spec["host"],
            identifier,
            spec["region"],
            spec["size"],
            spec["rotation"],
            f"{spec['quality']}.{spec['format']}",
        ]
    )


def _api_version(version: int | None) -> int:
    """Return the effective Image API version, validated against known contexts.

    Args:
        version: An explicit version, or ``None`` to read
            ``settings.IIIF_IMAGE_API_VERSION`` (default ``3``).

    Returns:
        The resolved version (``2`` or ``3``).

    Raises:
        ImproperlyConfigured: If the resolved version is not a known context.
    """
    if version is None:
        version = getattr(settings, "IIIF_IMAGE_API_VERSION", 3)
    if version not in IIIF_CONTEXTS:
        raise ImproperlyConfigured(
            f"IIIF_IMAGE_API_VERSION must be one of {sorted(IIIF_CONTEXTS)}, got {version!r}."
        )
    return version


def _compliance_level(level: str | None) -> str:
    """Return the advertised compliance level.

    Args:
        level: An explicit level, or ``None`` to read
            ``settings.IIIF_COMPLIANCE_LEVEL`` (default ``"level2"``).

    Returns:
        The compliance level string (e.g. ``"level2"``).
    """
    if level is None:
        level = getattr(settings, "IIIF_COMPLIANCE_LEVEL", "level2")
    return level


def _require_auth_v3(auth: dict | None, version: int) -> None:
    """Guard: an Auth 2.0 block may only be emitted at Image API version 3.

    Args:
        auth: The resolved auth block, or ``None``.
        version: The resolved Image API version.

    Raises:
        ImproperlyConfigured: If ``auth`` is set while ``version`` is not 3
            (Authorization Flow 2.0 pairs with Image/Presentation API 3).
    """
    if auth is not None and version != 3:
        raise ImproperlyConfigured(
            "IIIF_AUTH (Authorization Flow 2.0) requires IIIF_IMAGE_API_VERSION = 3; "
            f"got version {version}."
        )


def build_info_document(
    id_url: str,
    width: int,
    height: int,
    *,
    version: int | None = None,
    level: str | None = None,
    auth: dict | None = None,
) -> dict:
    """Build a spec-conformant IIIF Image API ``info.json`` document.

    Args:
        id_url: The image service base URI (``{host}/{identifier}``).
        width: Image width in pixels.
        height: Image height in pixels.
        version: Image API version (``2`` or ``3``); defaults to
            ``settings.IIIF_IMAGE_API_VERSION`` (``3``).
        level: Advertised compliance level; defaults to
            ``settings.IIIF_COMPLIANCE_LEVEL`` (``"level2"``).
        auth: An optional resolved Authorization Flow 2.0 probe-service ``dict``
            (see :func:`resolve_auth`). When present it is added to the document's
            ``service`` array; only valid at version 3.

    Returns:
        The ``info.json`` document as a dict, ready for ``JsonResponse``.

    Raises:
        ImproperlyConfigured: If ``version`` is unknown, or ``auth`` is set while
            not on version 3.
    """
    version = _api_version(version)
    level = _compliance_level(level)
    _require_auth_v3(auth, version)

    if version == 2:
        return {
            "@context": IIIF_CONTEXTS[2],
            "@id": id_url,
            "protocol": "http://iiif.io/api/image",
            "profile": [f"http://iiif.io/api/image/2/{level}.json"],
            "width": width,
            "height": height,
        }

    document = {
        "@context": IIIF_CONTEXTS[3],
        "id": id_url,
        "type": "ImageService3",
        "protocol": "http://iiif.io/api/image",
        "profile": level,
        "width": width,
        "height": height,
    }
    if auth is not None:
        document["service"] = [auth]
    return document


def _manifest_uri(id_url: str) -> str:
    """Return the synthetic Manifest URI derived from an image service base URI.

    The single derivation point shared by :func:`build_manifest` and
    :func:`build_content_state` (via :meth:`IIIFObject.content_state`) so the two
    can never drift.

    Args:
        id_url: The image service base URI (``{host}/{identifier}``).

    Returns:
        The ``{id_url}/manifest`` URI.
    """
    return urljoin([id_url, "manifest"])


def _canvas_uri(id_url: str, index: int = 1) -> str:
    """Return the synthetic Canvas URI derived from an image service base URI.

    Shared derivation point (see :func:`_manifest_uri`); the 1-based ``index``
    matches the single-image manifest's ``{id_url}/canvas/1``.

    Args:
        id_url: The image service base URI (``{host}/{identifier}``).
        index: The 1-based canvas index.

    Returns:
        The ``{id_url}/canvas/{index}`` URI.
    """
    return urljoin([id_url, "canvas", str(index)])


# The descriptive-property kwargs the manifest/collection builders accept, mapped
# to their IIIF (camelCase) property names. Used both to validate a descriptor
# bag (reject typos loudly) and to build the property fragment.
DESCRIPTOR_KEYS = ("metadata", "rights", "required_statement", "summary", "thumbnail", "nav_date")


def _reject_unknown_descriptors(descriptors: dict) -> None:
    """Reject a descriptor bag carrying keys the builders do not understand.

    The descriptor bag is a plain kwarg dict (not a fixed-shape spec object), so
    an unrecognized key is almost always a typo (``metdata``, ``rght``). Failing
    loudly here mirrors the ``IIIF_AUTH``-at-v2 posture.

    Args:
        descriptors: The descriptor kwargs (e.g. from ``IIIF_MANIFEST_DESCRIPTORS``
            or a direct builder call).

    Raises:
        ImproperlyConfigured: If any key is not in :data:`DESCRIPTOR_KEYS`.
    """
    unknown = set(descriptors) - set(DESCRIPTOR_KEYS)
    if unknown:
        raise ImproperlyConfigured(
            f"Unknown manifest descriptor key(s): {', '.join(sorted(unknown))}. "
            f"Allowed keys are: {', '.join(DESCRIPTOR_KEYS)}."
        )


def _metadata_pairs(metadata: list) -> list[dict]:
    """Coerce descriptive ``metadata`` into IIIF ``{label, value}`` pairs.

    Args:
        metadata: A list whose items are either ``(label, value)`` pairs (each
            side coerced via :func:`_language_map`) or already-formed
            ``{"label": …, "value": …}`` dicts (passed through unchanged).

    Returns:
        The list of language-mapped metadata pair dicts.
    """
    pairs = []
    for item in metadata:
        if isinstance(item, dict):
            pairs.append(item)
        else:
            label, value = item
            pairs.append({"label": _language_map(label), "value": _language_map(value)})
    return pairs


def _label_value(pair) -> dict:
    """Coerce a ``(label, value)`` pair into a IIIF label/value dict.

    Args:
        pair: A ``(label, value)`` tuple (each side coerced via
            :func:`_language_map`) or an already-formed dict (passed through).

    Returns:
        A ``{"label": …, "value": …}`` dict.
    """
    if isinstance(pair, dict):
        return pair
    label, value = pair
    return {"label": _language_map(label), "value": _language_map(value)}


def _thumbnail(thumbnail: str | list) -> list:
    """Coerce a ``thumbnail`` into the IIIF thumbnail list shape.

    Args:
        thumbnail: A single URL string (wrapped as ``[{"id": …, "type":
            "Image"}]``) or an already-formed list of thumbnail dicts.

    Returns:
        The thumbnail list.
    """
    if isinstance(thumbnail, str):
        return [{"id": thumbnail, "type": "Image"}]
    return thumbnail


def _descriptive_properties(descriptors: dict) -> dict:
    """Build the IIIF descriptive-property fragment from a descriptor bag.

    Every property is emitted only when its key is present and non-``None``, so an
    empty (or all-``None``) bag contributes nothing and leaves the surrounding
    document byte-identical to one built without descriptors.

    Args:
        descriptors: A validated descriptor bag (keys in :data:`DESCRIPTOR_KEYS`).

    Returns:
        A dict of IIIF descriptive properties (``metadata``, ``summary``,
        ``requiredStatement``, ``rights``, ``navDate``, ``thumbnail``) in spec
        property order, ready to merge into a Manifest or Collection.
    """
    props: dict = {}
    metadata = descriptors.get("metadata")
    if metadata is not None:
        props["metadata"] = _metadata_pairs(metadata)
    summary = descriptors.get("summary")
    if summary is not None:
        props["summary"] = _language_map(summary)
    required_statement = descriptors.get("required_statement")
    if required_statement is not None:
        props["requiredStatement"] = _label_value(required_statement)
    rights = descriptors.get("rights")
    if rights is not None:
        props["rights"] = rights
    nav_date = descriptors.get("nav_date")
    if nav_date is not None:
        props["navDate"] = nav_date.isoformat() if isinstance(nav_date, datetime) else nav_date
    thumbnail = descriptors.get("thumbnail")
    if thumbnail is not None:
        props["thumbnail"] = _thumbnail(thumbnail)
    return props


def resolve_manifest_descriptors(parent) -> dict:
    """Resolve ``settings.IIIF_MANIFEST_DESCRIPTORS`` to a descriptor bag.

    Mirrors :func:`resolve_auth`: the setting may be a plain ``dict`` of
    descriptor kwargs, a callable receiving the field file and returning such a
    ``dict`` (or ``None`` for no descriptors), or unset. This is how per-image
    descriptive metadata flows into :attr:`IIIFObject.manifest` without djiiif
    knowing the model.

    Args:
        parent: The :class:`IIIFFieldFile` passed to a callable config.

    Returns:
        A validated descriptor bag (empty when unset or resolved to ``None``).

    Raises:
        ImproperlyConfigured: If the (resolved) value is neither a ``dict`` nor
            ``None``, or carries an unknown descriptor key.
    """
    hook = getattr(settings, "IIIF_MANIFEST_DESCRIPTORS", None)
    if hook is None:
        return {}
    descriptors = hook(parent) if callable(hook) else hook
    if descriptors is None:
        return {}
    if not isinstance(descriptors, dict):
        raise ImproperlyConfigured(
            "IIIF_MANIFEST_DESCRIPTORS must be a dict, a callable returning a dict "
            f"or None, or unset; got {type(descriptors).__name__}."
        )
    _reject_unknown_descriptors(descriptors)
    return descriptors


def _normalize_image_spec(image) -> tuple[str, int, int, object]:
    """Normalize one :func:`build_multi_manifest` image spec.

    Args:
        image: Either a ``(service_id_url, width, height)`` tuple or a dict with
            ``id`` / ``width`` / ``height`` keys and an optional per-canvas
            ``label``.

    Returns:
        A ``(service_id_url, width, height, label)`` tuple, where ``label`` is
        ``None`` when unspecified.
    """
    if isinstance(image, dict):
        return image["id"], image["width"], image["height"], image.get("label")
    service_id_url, width, height = image
    return service_id_url, width, height, None


def _build_canvas(
    manifest_id_url: str,
    index: int,
    service_id_url: str,
    width: int,
    height: int,
    *,
    label,
    version: int,
    level: str,
    auth: dict | None,
) -> dict:
    """Assemble one Canvas (with its painting annotation) for a manifest.

    The single canvas-assembly code path shared by every manifest — the
    single-image :func:`build_manifest` is just this called once. Canvas,
    annotation-page, and annotation ``id`` URIs derive from ``manifest_id_url``
    with the 1-based ``index``; the image body and its service derive from this
    image's own ``service_id_url`` (which equals ``manifest_id_url`` in the
    single-image case).

    Args:
        manifest_id_url: The manifest's image service base URI, the stem for the
            synthetic canvas/annotation URIs.
        index: The 1-based canvas index.
        service_id_url: This image's own service base URI.
        width: Image width in pixels.
        height: Image height in pixels.
        label: Optional per-canvas label (coerced via :func:`_language_map`);
            omitted from the canvas when ``None``.
        version: The resolved Image API version (``2`` or ``3``).
        level: The resolved compliance level.
        auth: The resolved probe-service ``dict`` applied to the image body, or
            ``None``.

    Returns:
        The Canvas dict.
    """
    # v3 uses the "max" size keyword; v2 uses "full" for a full-resolution image.
    full_size = "max" if version == 3 else "full"
    image_id = urljoin([service_id_url, "full", full_size, "0", "default.jpg"])

    if version == 2:
        service = {
            "@id": service_id_url,
            "@type": "ImageService2",
            "profile": f"http://iiif.io/api/image/2/{level}.json",
        }
    else:
        service = {"id": service_id_url, "type": "ImageService3", "profile": level}

    # The probe service is declared on the access-controlled resource — here the
    # image annotation body — alongside its image service.
    body_services = [service] if auth is None else [service, auth]

    canvas_id = _canvas_uri(manifest_id_url, index)
    canvas: dict = {"id": canvas_id, "type": "Canvas"}
    if label is not None:
        canvas["label"] = _language_map(label)
    canvas["width"] = width
    canvas["height"] = height
    canvas["items"] = [
        {
            "id": urljoin([canvas_id, "page", "1"]),
            "type": "AnnotationPage",
            "items": [
                {
                    "id": urljoin([canvas_id, "annotation", "1"]),
                    "type": "Annotation",
                    "motivation": "painting",
                    "target": canvas_id,
                    "body": {
                        "id": image_id,
                        "type": "Image",
                        "format": "image/jpeg",
                        "width": width,
                        "height": height,
                        "service": body_services,
                    },
                }
            ],
        }
    ]
    return canvas


def build_multi_manifest(
    id_url: str,
    images,
    *,
    label,
    version: int | None = None,
    level: str | None = None,
    auth: dict | None = None,
    **descriptors,
) -> dict:
    """Build a multi-canvas IIIF Presentation API 3.0 Manifest.

    Presents several images as one manifest — recto/verso, a paged object, detail
    shots — by repeating the single-canvas structure with per-canvas indexed
    ``id`` URIs. The document is always Presentation 3.0; each embedded image
    service reflects the Image API ``version``.

    Args:
        id_url: The manifest's image service base URI (``{host}/{identifier}``),
            the stem for the synthetic manifest/canvas URIs.
        images: A sequence of per-canvas specs — ``(service_id_url, width,
            height)`` tuples, or dicts with ``id`` / ``width`` / ``height`` and an
            optional ``label`` (see :func:`_normalize_image_spec`).
        label: Manifest label (coerced via :func:`_language_map`).
        version: Image API version of the embedded image services (``2`` or
            ``3``); defaults to ``settings.IIIF_IMAGE_API_VERSION`` (``3``).
        level: Advertised compliance level; defaults to
            ``settings.IIIF_COMPLIANCE_LEVEL`` (``"level2"``).
        auth: An optional resolved Authorization Flow 2.0 probe-service ``dict``
            applied to **every** image body; only valid at version 3.
        **descriptors: Optional descriptive properties (keys in
            :data:`DESCRIPTOR_KEYS`) emitted at the manifest top level.

    Returns:
        The manifest as a dict, ready for ``JsonResponse``.

    Raises:
        ImproperlyConfigured: If ``version`` is unknown, ``auth`` is set while not
            on version 3, or a descriptor key is unknown.
    """
    version = _api_version(version)
    level = _compliance_level(level)
    _require_auth_v3(auth, version)
    _reject_unknown_descriptors(descriptors)

    canvases = []
    for index, image in enumerate(images, start=1):
        service_id_url, width, height, canvas_label = _normalize_image_spec(image)
        canvases.append(
            _build_canvas(
                id_url,
                index,
                service_id_url,
                width,
                height,
                label=canvas_label,
                version=version,
                level=level,
                auth=auth,
            )
        )

    manifest = {
        "@context": PRESENTATION_CONTEXT,
        "id": _manifest_uri(id_url),
        "type": "Manifest",
        "label": _language_map(label),
    }
    manifest.update(_descriptive_properties(descriptors))
    manifest["items"] = canvases
    return manifest


def build_manifest(
    id_url: str,
    width: int,
    height: int,
    *,
    label,
    version: int | None = None,
    level: str | None = None,
    auth: dict | None = None,
    **descriptors,
) -> dict:
    """Build a minimal single-image IIIF Presentation API 3.0 Manifest.

    A thin wrapper over :func:`build_multi_manifest` for the common one-image
    case: the manifest wraps one image on one canvas so it opens directly in
    viewers like Mirador or OpenSeadragon. With no ``descriptors`` its output is
    identical to the historical single-image manifest.

    Args:
        id_url: The image service base URI (``{host}/{identifier}``), reused as
            the image service ``id`` and as the stem for the synthetic URIs.
        width: Image width in pixels.
        height: Image height in pixels.
        label: Human-readable label for the manifest (coerced via
            :func:`_language_map`).
        version: Image API version of the embedded image service (``2`` or
            ``3``); defaults to ``settings.IIIF_IMAGE_API_VERSION`` (``3``).
        level: Advertised compliance level; defaults to
            ``settings.IIIF_COMPLIANCE_LEVEL`` (``"level2"``).
        auth: An optional resolved Authorization Flow 2.0 probe-service ``dict``
            (see :func:`resolve_auth`). When present it is added to the
            access-controlled image body's ``service`` array; only valid at
            version 3.
        **descriptors: Optional descriptive properties (keys in
            :data:`DESCRIPTOR_KEYS`) emitted at the manifest top level.

    Returns:
        The manifest as a dict, ready for ``JsonResponse``.

    Raises:
        ImproperlyConfigured: If ``version`` is unknown, ``auth`` is set while not
            on version 3, or a descriptor key is unknown.
    """
    return build_multi_manifest(
        id_url,
        [(id_url, width, height)],
        label=label,
        version=version,
        level=level,
        auth=auth,
        **descriptors,
    )


def build_collection(id_url: str, items, *, label, **descriptors) -> dict:
    """Build a IIIF Presentation API 3.0 Collection of manifest references.

    A Collection groups manifests for browsing — the natural rendering of a
    Django queryset ("all photos in this album"). It embeds only *references* to
    each manifest (id/type/label/thumbnail), never the manifests themselves, so
    even a large collection stays a small response.

    Args:
        id_url: The Collection's own ``id`` URI.
        items: A sequence of member entries — ``(manifest_url, label)`` or
            ``(manifest_url, label, thumbnail)`` tuples, or already-formed member
            dicts (passed through). ``label`` is coerced via
            :func:`_language_map`; ``thumbnail`` via :func:`_thumbnail`.
        label: Collection label (coerced via :func:`_language_map`).
        **descriptors: Optional descriptive properties (keys in
            :data:`DESCRIPTOR_KEYS`) emitted at the collection top level.

    Returns:
        The Collection as a dict, ready for ``JsonResponse``.

    Raises:
        ImproperlyConfigured: If a descriptor key is unknown.
    """
    _reject_unknown_descriptors(descriptors)
    collection = {
        "@context": PRESENTATION_CONTEXT,
        "id": id_url,
        "type": "Collection",
        "label": _language_map(label),
    }
    collection.update(_descriptive_properties(descriptors))
    collection["items"] = [_collection_item(item) for item in items]
    return collection


def _collection_item(item) -> dict:
    """Build one Collection member reference.

    Args:
        item: A ``(manifest_url, label)`` or ``(manifest_url, label, thumbnail)``
            tuple, or an already-formed member dict (passed through).

    Returns:
        A ``{"id", "type": "Manifest", "label"[, "thumbnail"]}`` reference dict.
    """
    if isinstance(item, dict):
        return item
    manifest_url, label, *rest = item
    entry = {"id": manifest_url, "type": "Manifest", "label": _language_map(label)}
    if rest:
        entry["thumbnail"] = _thumbnail(rest[0])
    return entry


def encode_content_state(state: dict | str) -> str:
    """Encode a content state for use as an ``iiif-content`` query parameter.

    Implements the IIIF Content State API 1.0 §6 encoding: serialize to JSON
    (when given a ``dict``), percent-encode the UTF-8 string exactly as
    JavaScript's ``encodeURIComponent`` does, base64url-encode that, and strip the
    ``=`` padding. The percent-encoding step is part of the spec — the resulting
    string round-trips through any viewer's ``decodeURIComponent``.

    Args:
        state: A content-state ``dict`` (e.g. from :func:`build_content_state`)
            or a bare resource-URI ``str`` (the spec's trivial form).

    Returns:
        The URL-safe, unpadded encoded string.
    """
    text = state if isinstance(state, str) else json.dumps(state, separators=(",", ":"))
    # encodeURIComponent leaves A-Z a-z 0-9 - _ . ! ~ * ' ( ) unescaped; quote
    # already treats the alphanumerics and -_.~ as safe, so only the punctuation
    # differs from quote's default reserved set.
    percent_encoded = quote(text, safe="!~*'()")
    encoded = base64.urlsafe_b64encode(percent_encoded.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def decode_content_state(encoded: str) -> dict | str:
    """Decode an ``iiif-content`` value back into a content state.

    The inverse of :func:`encode_content_state`: restore the stripped base64url
    padding, base64url-decode, reverse the percent-encoding, and ``json.loads``
    the result. A payload that is not JSON (a bare resource-URI string) is
    returned verbatim.

    Args:
        encoded: The encoded string from an ``iiif-content`` parameter.

    Returns:
        The decoded content-state ``dict``, or the bare URI ``str`` for a
        non-JSON payload.
    """
    padding = "=" * (-len(encoded) % 4)
    percent_encoded = base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
    text = unquote(percent_encoded)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _format_xywh(xywh: str | tuple[int, int, int, int]) -> str:
    """Normalize an ``xywh`` region into the ``x,y,w,h`` media-fragment string.

    Args:
        xywh: A preformatted ``"x,y,w,h"`` string (used verbatim) or a 4-tuple
            of ints (formatted to ``x,y,w,h``).

    Returns:
        The ``x,y,w,h`` string.
    """
    if isinstance(xywh, str):
        return xywh
    return ",".join(str(v) for v in xywh)


def build_content_state(
    manifest_id: str,
    *,
    canvas_id: str | None = None,
    xywh: str | tuple[int, int, int, int] | None = None,
) -> dict:
    """Build a IIIF Content State API 1.0 annotation targeting a resource.

    Produces the spec's simplified target forms (Content State API 1.0 §3.2):
    with only ``manifest_id`` the state targets the Manifest; with ``canvas_id``
    it targets that Canvas and carries a ``partOf`` back to the Manifest; ``xywh``
    appends an ``#xywh=`` media-fragment to the canvas id to select a region.

    Args:
        manifest_id: The Manifest URI (e.g. ``{host}/{identifier}/manifest``).
        canvas_id: The Canvas URI to target within the manifest; omit to target
            the whole Manifest.
        xywh: An optional region as an ``x,y,w,h`` string or 4-tuple of ints.
            Ignored when ``canvas_id`` is ``None``.

    Returns:
        The content-state ``dict``, ready for :func:`encode_content_state`.
    """
    if canvas_id is None:
        return {"id": manifest_id, "type": "Manifest"}

    target_id = canvas_id if xywh is None else f"{canvas_id}#xywh={_format_xywh(xywh)}"
    return {
        "id": target_id,
        "type": "Canvas",
        "partOf": [{"id": manifest_id, "type": "Manifest"}],
    }


class IIIFObject(object):
    """The ``.iiif`` accessor for a field file: profile URLs and documents.

    Constructed fresh on each ``IIIFFieldFile.iiif`` access. For a populated
    field it eagerly sets one attribute per ``settings.IIIF_PROFILES`` name (the
    assembled Image API URL) plus ``info`` (the external ``info.json`` URL) and
    ``identifier`` (the plain ``{host}/{identifier}`` base URI). For an empty or
    unset field every URL attribute is the empty string.

    The generated documents — :attr:`info_document` and :attr:`manifest` — are
    lazy ``cached_property`` values because, unlike the URL attributes, they read
    the image's pixel dimensions from storage. Constructing an ``IIIFObject``
    therefore never touches the file.
    """

    def __init__(self, parent):
        """Assemble the profile/``info``/``identifier`` URLs for ``parent``.

        Args:
            parent: The :class:`IIIFFieldFile` this accessor belongs to. Stored
                as ``self._parent`` so the lazy document properties can read its
                ``width``/``height``.
        """
        self._parent = parent

        # Remember the configured profile names (in order) so as_dict() can
        # collect their URLs without re-reading settings.
        self._profile_names = list(settings.IIIF_PROFILES)

        # Encode the identifier once; it is shared by every URL below. Empty for
        # an unset field, which drives the empty-string branch throughout.
        identifier = encode_identifier(parent.name) if parent.name else ""

        # Track the host from the last resolved profile so the info/identifier
        # URLs can reuse it. Starts as None so an empty IIIF_PROFILES (or an
        # unset field) yields empty strings instead of raising.
        host: str | None = None
        for name, profile in settings.IIIF_PROFILES.items():
            if identifier:
                spec = resolve_profile(profile, parent)
                host = spec["host"]
                setattr(self, name, image_url(spec, identifier))
            else:
                setattr(self, name, "")

        if identifier and host:
            self.info = urljoin([host, identifier, "info.json"])
            self.identifier = urljoin([host, identifier])
        else:
            self.info = ""
            self.identifier = ""

    def as_dict(self, *, include_meta: bool = False) -> dict[str, str]:
        """Return the profile URLs as a plain ``dict``, keyed by profile name.

        Handy for JSON APIs (see :mod:`djiiif.serializers`) and for iterating
        profiles in a template. For an empty/unset field every value is ``""``.

        Args:
            include_meta: When true, also include the ``info`` and ``identifier``
                URLs under those keys.

        Returns:
            A ``{profile_name: url}`` mapping, optionally with ``info`` and
            ``identifier`` entries appended.
        """
        data = {name: getattr(self, name) for name in self._profile_names}
        if include_meta:
            data["info"] = self.info
            data["identifier"] = self.identifier
        return data

    @cached_property
    def info_document(self) -> dict | None:
        """The IIIF Image API ``info.json`` **document** (not its URL).

        Distinct from :attr:`info`, which returns the *URL* of an external
        ``info.json`` served by an image server. This builds the document here
        from the image's own ``width``/``height`` and the :attr:`identifier`
        base URI, so a view can serve a minimal ``info.json`` without a separate
        image server (e.g. ``JsonResponse(field.iiif.info_document)``).

        Accessing this reads the image from storage; the eager URL attributes
        never do. Shape is controlled by ``settings.IIIF_IMAGE_API_VERSION``
        (default ``3``) and ``settings.IIIF_COMPLIANCE_LEVEL`` (default
        ``"level2"``). When ``settings.IIIF_AUTH`` resolves to a probe service
        for this image, its Authorization Flow 2.0 ``service`` block is included.

        Returns:
            The ``info.json`` document, or ``None`` for an empty/unset field.
        """
        if not self.identifier:
            return None
        return build_info_document(
            self.identifier,
            self._parent.width,
            self._parent.height,
            auth=resolve_auth(self._parent),
        )

    @cached_property
    def manifest(self) -> dict | None:
        """A minimal single-image IIIF Presentation API 3.0 Manifest.

        Wraps this image in a one-canvas manifest suitable for Mirador or
        OpenSeadragon. The label defaults to the file's base name. Like
        :attr:`info_document`, accessing this reads the image dimensions from
        storage. When ``settings.IIIF_AUTH`` resolves to a probe service for this
        image, its Authorization Flow 2.0 ``service`` block is attached to the
        image body. When ``settings.IIIF_MANIFEST_DESCRIPTORS`` resolves to a
        descriptor bag for this image (see :func:`resolve_manifest_descriptors`),
        its descriptive properties (``metadata``, ``rights``, …) are emitted at
        the manifest top level.

        Returns:
            The manifest document, or ``None`` for an empty/unset field.
        """
        if not self.identifier:
            return None
        label = self._parent.name.rsplit("/", 1)[-1]
        return build_manifest(
            self.identifier,
            self._parent.width,
            self._parent.height,
            label=label,
            auth=resolve_auth(self._parent),
            **resolve_manifest_descriptors(self._parent),
        )

    def content_state(
        self,
        *,
        xywh: str | tuple[int, int, int, int] | None = None,
        encoded: bool = True,
    ) -> str | dict | None:
        """Build a IIIF Content State for a shareable deep link to this image.

        Targets this image's own Canvas (with a ``partOf`` back to its Manifest),
        deriving both URIs the same way :attr:`manifest` does — so the state opens
        the exact image the manifest describes. Pass ``xywh`` to open zoomed to a
        region. Unlike :attr:`manifest`, this reads nothing from storage.

        Args:
            xywh: An optional region as an ``x,y,w,h`` string or 4-tuple of ints;
                omit for a whole-image state.
            encoded: When true (default), return the URL-safe encoded string
                ready to drop into ``?iiif-content=``; when false, return the raw
                content-state ``dict``.

        Returns:
            The encoded string (``""`` for an empty/unset field), or the raw
            ``dict`` (``None`` for an empty/unset field) when ``encoded`` is
            false.
        """
        if not self.identifier:
            return "" if encoded else None
        state = build_content_state(
            _manifest_uri(self.identifier),
            canvas_id=_canvas_uri(self.identifier),
            xywh=xywh,
        )
        return encode_content_state(state) if encoded else state


class IIIFFieldFile(ImageFieldFile):
    """An ``ImageFieldFile`` that exposes an ``.iiif`` accessor."""

    @property
    def iiif(self) -> IIIFObject:
        """Return a freshly built :class:`IIIFObject` for this field file."""
        return IIIFObject(self)


class IIIFField(ImageField):
    """An ``ImageField`` whose field files carry IIIF URLs via ``.iiif``."""

    attr_class = IIIFFieldFile
