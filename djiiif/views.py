"""Drop-in views that serve IIIF documents for stored images.

Mounting :data:`djiiif.urls.urlpatterns` turns a Django instance into a minimal
provider of two documents built from a stored image: an Image API ``info.json``
(:func:`serve_info_json`) and a Presentation API ``manifest``
(:func:`serve_manifest`). Each maps an identifier back to a stored image, reads
its dimensions, and returns the document built by the corresponding
:mod:`djiiif` builder. Neither serves derivative pixels — only the JSON
documents.
"""

from urllib.parse import unquote

from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.core.files.images import get_image_dimensions
from django.core.files.storage import default_storage
from django.http import Http404, JsonResponse

from djiiif import build_collection, build_info_document, build_manifest


def _load_dimensions(identifier: str) -> tuple[str, int, int]:
    """Resolve an encoded identifier to its storage name and pixel dimensions.

    Args:
        identifier: The encoded identifier segment captured by the URLconf.

    Returns:
        A ``(name, width, height)`` tuple, where ``name`` is the decoded storage
        name.

    Raises:
        Http404: If the file is missing, outside storage, or not a readable
            image.
    """
    name = unquote(identifier)

    try:
        image = default_storage.open(name)
    except (FileNotFoundError, SuspiciousOperation, ValueError) as exc:
        raise Http404("No IIIF image for that identifier.") from exc

    try:
        width, height = get_image_dimensions(image)
    finally:
        image.close()

    if not width or not height:
        raise Http404("Identifier does not resolve to a readable image.")

    return name, width, height


def _ld_json(document: dict) -> JsonResponse:
    """Wrap a document in a JSON-LD response with the IIIF CORS header.

    Args:
        document: The IIIF document to serialize.

    Returns:
        A ``JsonResponse`` with the ``application/ld+json`` content type and a
        permissive ``Access-Control-Allow-Origin`` header that IIIF clients
        require.
    """
    response = JsonResponse(document, content_type="application/ld+json")
    response["Access-Control-Allow-Origin"] = "*"
    return response


def serve_info_json(request, identifier):
    """Serve the ``info.json`` document for a stored image.

    The document's ``id`` is taken from the request URL (minus the
    ``/info.json`` suffix) so it always matches the URL the document is served
    from, as the spec requires.

    Args:
        request: The incoming ``HttpRequest``.
        identifier: The encoded identifier segment captured by the URLconf.

    Returns:
        A JSON-LD ``JsonResponse`` carrying the ``info.json`` document.

    Raises:
        Http404: If the identifier does not resolve to a readable image.
    """
    _name, width, height = _load_dimensions(identifier)
    id_url = request.build_absolute_uri(request.path).rsplit("/info.json", 1)[0]
    return _ld_json(build_info_document(id_url, width, height))


def serve_manifest(request, identifier):
    """Serve a single-image Presentation API manifest for a stored image.

    The image service base URI is the request URL minus the ``/manifest``
    suffix, matching the identifier the ``info.json`` view serves. The manifest
    label defaults to the file's base name.

    Args:
        request: The incoming ``HttpRequest``.
        identifier: The encoded identifier segment captured by the URLconf.

    Returns:
        A JSON-LD ``JsonResponse`` carrying the manifest document.

    Raises:
        Http404: If the identifier does not resolve to a readable image.
    """
    name, width, height = _load_dimensions(identifier)
    id_url = request.build_absolute_uri(request.path).rsplit("/manifest", 1)[0]
    label = name.rsplit("/", 1)[-1]
    return _ld_json(build_manifest(id_url, width, height, label=label))


def serve_collection(request):
    """Serve a IIIF Collection of manifest references.

    Driven by the ``IIIF_COLLECTION_SOURCE`` setting — a callable returning an
    iterable of member entries (``(manifest_url, label[, thumbnail])`` tuples or
    preformed member dicts, per :func:`djiiif.build_collection`) and, optionally,
    a ``label`` for the collection itself. When the setting is unset the endpoint
    does not exist, so it returns ``404``.

    The collection's ``id`` is the request URL, so it always matches where it is
    served from. The response reads no image storage — it references manifests by
    URL only.

    Args:
        request: The incoming ``HttpRequest``.

    Returns:
        A JSON-LD ``JsonResponse`` carrying the Collection document.

    Raises:
        Http404: If ``IIIF_COLLECTION_SOURCE`` is unset.
    """
    source = getattr(settings, "IIIF_COLLECTION_SOURCE", None)
    if source is None:
        raise Http404("No IIIF collection is configured.")
    label = getattr(settings, "IIIF_COLLECTION_LABEL", "Collection")
    id_url = request.build_absolute_uri(request.path).rstrip("/")
    items = source() if callable(source) else source
    return _ld_json(build_collection(id_url, list(items), label=label))
