"""A drop-in view that serves a IIIF Image API ``info.json`` from storage.

Mounting :data:`djiiif.urls.urlpatterns` turns a Django instance into a minimal
level-0 ``info.json`` provider: the view maps an identifier back to a stored
image, reads its dimensions, and returns the document built by
:func:`djiiif.build_info_document`. It does not serve derivative pixels — only
the ``info.json`` metadata document.
"""

from urllib.parse import unquote

from django.core.exceptions import SuspiciousOperation
from django.core.files.images import get_image_dimensions
from django.core.files.storage import default_storage
from django.http import Http404, JsonResponse

from djiiif import build_info_document


def serve_info_json(request, identifier):
    """Serve the ``info.json`` document for a stored image.

    The ``identifier`` captured from the URL is percent-decoded back into the
    storage name, opened via ``default_storage``, and measured. The document's
    ``id`` is taken from the request URL (minus the ``/info.json`` suffix) so it
    always matches the URL the document is served from, as the spec requires.

    Args:
        request: The incoming ``HttpRequest``.
        identifier: The encoded identifier segment captured by the URLconf.

    Returns:
        A ``JsonResponse`` carrying the ``info.json`` document, with the
        ``application/ld+json`` content type and a permissive CORS header that
        IIIF clients require.

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

    # The document id must equal the base URI it is served from (the request URL
    # without the trailing "/info.json").
    id_url = request.build_absolute_uri(request.path).rsplit("/info.json", 1)[0]

    response = JsonResponse(
        build_info_document(id_url, width, height),
        content_type="application/ld+json",
    )
    response["Access-Control-Allow-Origin"] = "*"
    return response
