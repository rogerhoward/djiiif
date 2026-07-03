"""IIIF integration for Django's ``ImageField``.

Defines :class:`IIIFField` (an ``ImageField`` subclass) whose field files expose
an ``.iiif`` accessor. That accessor returns an :class:`IIIFObject` carrying one
IIIF Image API URL per configured profile, plus the ``info``/``identifier`` URLs
and the generated ``info_document`` / ``manifest`` documents.

Profiles are configured in ``settings.IIIF_PROFILES`` and may be a plain ``dict``,
a :class:`Profile` instance, or a callable returning either (see
:func:`resolve_profile`).
"""

from dataclasses import dataclass
from functools import cached_property
from urllib.parse import quote

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


def build_info_document(
    id_url: str,
    width: int,
    height: int,
    *,
    version: int | None = None,
    level: str | None = None,
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

    Returns:
        The ``info.json`` document as a dict, ready for ``JsonResponse``.

    Raises:
        ImproperlyConfigured: If ``version`` is unknown.
    """
    version = _api_version(version)
    level = _compliance_level(level)

    if version == 2:
        return {
            "@context": IIIF_CONTEXTS[2],
            "@id": id_url,
            "protocol": "http://iiif.io/api/image",
            "profile": [f"http://iiif.io/api/image/2/{level}.json"],
            "width": width,
            "height": height,
        }

    return {
        "@context": IIIF_CONTEXTS[3],
        "id": id_url,
        "type": "ImageService3",
        "protocol": "http://iiif.io/api/image",
        "profile": level,
        "width": width,
        "height": height,
    }


def build_manifest(
    id_url: str,
    width: int,
    height: int,
    *,
    label: str,
    version: int | None = None,
    level: str | None = None,
) -> dict:
    """Build a minimal single-image IIIF Presentation API 3.0 Manifest.

    The manifest wraps one image on one canvas so it opens directly in viewers
    like Mirador or OpenSeadragon. The document itself is always Presentation
    3.0; the embedded image service reflects the Image API ``version`` so a 2.x
    deployment advertises ``ImageService2`` and a matching full-size image URL.

    Synthetic ``id`` URIs for the manifest, canvas, annotation page, and
    annotation are derived from ``id_url`` (e.g. ``{id_url}/manifest``); they
    only need to be stable and unique, which these are.

    Args:
        id_url: The image service base URI (``{host}/{identifier}``), reused as
            the image service ``id`` and as the stem for the synthetic URIs.
        width: Image width in pixels.
        height: Image height in pixels.
        label: Human-readable label for the manifest/canvas.
        version: Image API version of the embedded image service (``2`` or
            ``3``); defaults to ``settings.IIIF_IMAGE_API_VERSION`` (``3``).
        level: Advertised compliance level; defaults to
            ``settings.IIIF_COMPLIANCE_LEVEL`` (``"level2"``).

    Returns:
        The manifest as a dict, ready for ``JsonResponse``.

    Raises:
        ImproperlyConfigured: If ``version`` is unknown.
    """
    version = _api_version(version)
    level = _compliance_level(level)

    # v3 uses the "max" size keyword; v2 uses "full" for a full-resolution image.
    full_size = "max" if version == 3 else "full"
    image_id = urljoin([id_url, "full", full_size, "0", "default.jpg"])

    if version == 2:
        service = {
            "@id": id_url,
            "@type": "ImageService2",
            "profile": f"http://iiif.io/api/image/2/{level}.json",
        }
    else:
        service = {"id": id_url, "type": "ImageService3", "profile": level}

    canvas_id = urljoin([id_url, "canvas", "1"])
    return {
        "@context": PRESENTATION_CONTEXT,
        "id": urljoin([id_url, "manifest"]),
        "type": "Manifest",
        "label": {"none": [label]},
        "items": [
            {
                "id": canvas_id,
                "type": "Canvas",
                "width": width,
                "height": height,
                "items": [
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
                                    "service": [service],
                                },
                            }
                        ],
                    }
                ],
            }
        ],
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
        ``"level2"``).

        Returns:
            The ``info.json`` document, or ``None`` for an empty/unset field.
        """
        if not self.identifier:
            return None
        return build_info_document(self.identifier, self._parent.width, self._parent.height)

    @cached_property
    def manifest(self) -> dict | None:
        """A minimal single-image IIIF Presentation API 3.0 Manifest.

        Wraps this image in a one-canvas manifest suitable for Mirador or
        OpenSeadragon. The label defaults to the file's base name. Like
        :attr:`info_document`, accessing this reads the image dimensions from
        storage.

        Returns:
            The manifest document, or ``None`` for an empty/unset field.
        """
        if not self.identifier:
            return None
        label = self._parent.name.rsplit("/", 1)[-1]
        return build_manifest(
            self.identifier, self._parent.width, self._parent.height, label=label
        )


class IIIFFieldFile(ImageFieldFile):
    """An ``ImageFieldFile`` that exposes an ``.iiif`` accessor."""

    @property
    def iiif(self) -> IIIFObject:
        """Return a freshly built :class:`IIIFObject` for this field file."""
        return IIIFObject(self)


class IIIFField(ImageField):
    """An ``ImageField`` whose field files carry IIIF URLs via ``.iiif``."""

    attr_class = IIIFFieldFile
