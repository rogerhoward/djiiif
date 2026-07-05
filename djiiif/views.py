"""Drop-in views that serve IIIF documents for stored images.

Mounting :data:`djiiif.urls.urlpatterns` turns a Django instance into a minimal
provider of two documents built from a stored image: an Image API ``info.json``
(:func:`serve_info_json`) and a Presentation API ``manifest``
(:func:`serve_manifest`). Each maps an identifier back to a stored image, reads
its dimensions, and returns the document built by the corresponding
:mod:`djiiif` builder. Neither serves derivative pixels — only the JSON
documents.

Two settings-driven views need no stored image: :func:`serve_collection` renders
a browsable Collection of manifest references, and :func:`serve_activity_collection`
/ :func:`serve_activity_page` render a paged IIIF Change Discovery activity stream
so aggregators can harvest what changed.
"""

from urllib.parse import unquote

from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.core.files.images import get_image_dimensions
from django.core.files.storage import default_storage
from django.core.paginator import InvalidPage, Paginator
from django.http import Http404, JsonResponse
from django.utils.module_loading import import_string

from djiiif import (
    build_activity,
    build_collection,
    build_collection_page,
    build_info_document,
    build_manifest,
    build_ordered_collection,
    resolve_activity,
)


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


def _activity_paginator() -> Paginator:
    """Resolve ``IIIF_ACTIVITY_SOURCE`` into a :class:`~django.core.paginator.Paginator`.

    The setting may be a dotted-path string (imported here), a callable object, or
    a direct iterable; a callable is invoked to obtain the iterable. A queryset or
    list is paginated in place (querysets slice lazily in the DB); a bare
    generator, which cannot be sliced, is materialized to a list first.

    Returns:
        A ``Paginator`` over the activity entries, page size from
        ``IIIF_ACTIVITY_PAGE_SIZE`` (default 100).

    Raises:
        Http404: If ``IIIF_ACTIVITY_SOURCE`` is unset (the stream is opt-in).
    """
    source = getattr(settings, "IIIF_ACTIVITY_SOURCE", None)
    if source is None:
        raise Http404("No IIIF activity stream is configured.")
    if isinstance(source, str):
        source = import_string(source)
    entries = source() if callable(source) else source
    if not hasattr(entries, "__getitem__"):
        entries = list(entries)
    page_size = getattr(settings, "IIIF_ACTIVITY_PAGE_SIZE", 100)
    return Paginator(entries, page_size)


def _activity_base_url(request, suffix: str) -> str:
    """Return the ``/iiif/activity`` base URL, stripping a route ``suffix``.

    Args:
        request: The incoming ``HttpRequest``.
        suffix: The trailing route segment to remove (``"/collection"`` or
            ``"/page/<n>"``).

    Returns:
        The absolute base URL shared by the collection and page routes.
    """
    return request.build_absolute_uri(request.path).rsplit(suffix, 1)[0]


def serve_activity_collection(request):
    """Serve the Change Discovery ``OrderedCollection`` entry point.

    Driven by ``IIIF_ACTIVITY_SOURCE`` (see :func:`_activity_paginator`). The
    collection's ``id`` is the request URL; ``first``/``last`` point at the page
    routes. Reads no image storage.

    Args:
        request: The incoming ``HttpRequest``.

    Returns:
        A JSON-LD ``JsonResponse`` carrying the ``OrderedCollection``.

    Raises:
        Http404: If ``IIIF_ACTIVITY_SOURCE`` is unset.
    """
    paginator = _activity_paginator()
    base = _activity_base_url(request, "/collection")
    id_url = request.build_absolute_uri(request.path)
    return _ld_json(
        build_ordered_collection(
            id_url,
            paginator.count,
            f"{base}/page/1",
            f"{base}/page/{paginator.num_pages}",
        )
    )


def serve_activity_page(request, page):
    """Serve one Change Discovery ``OrderedCollectionPage``.

    The page's activities are the source entries for this slice, resolved via
    :func:`djiiif.resolve_activity` and built with :func:`djiiif.build_activity`,
    kept in the source's ascending-``endTime`` order (the source owns that
    contract; djiiif does not re-sort). ``prev``/``next`` are emitted at the
    interior boundaries only.

    Args:
        request: The incoming ``HttpRequest``.
        page: The 1-based page number (captured by the ``<int:page>`` route).

    Returns:
        A JSON-LD ``JsonResponse`` carrying the ``OrderedCollectionPage``.

    Raises:
        Http404: If ``IIIF_ACTIVITY_SOURCE`` is unset or ``page`` is out of range.
    """
    paginator = _activity_paginator()
    try:
        page_obj = paginator.page(page)
    except InvalidPage as exc:
        raise Http404("No such activity page.") from exc

    base = _activity_base_url(request, f"/page/{page}")
    page_url = request.build_absolute_uri(request.path)
    prev_url = f"{base}/page/{page - 1}" if page_obj.has_previous() else None
    next_url = f"{base}/page/{page + 1}" if page_obj.has_next() else None

    activities = []
    for entry in page_obj.object_list:
        resolved = resolve_activity(entry)
        activities.append(
            build_activity(
                resolved["object_id"],
                resolved["end_time"],
                activity_type=resolved["type"],
                object_type=resolved["object_type"],
            )
        )

    return _ld_json(
        build_collection_page(
            page_url,
            f"{base}/collection",
            activities,
            prev_url=prev_url,
            next_url=next_url,
            start_index=paginator.per_page * (page - 1),
        )
    )
