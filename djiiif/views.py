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
so aggregators can harvest what changed. :func:`serve_annotation_page` serves a
W3C AnnotationPage (transcriptions/OCR/commentary) and :func:`serve_search`
answers IIIF Content Search 2.0 queries; both draw from project-owned backend
callables, and :func:`serve_manifest` advertises them when configured.
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
    build_annotation_page,
    build_collection,
    build_collection_page,
    build_info_document,
    build_manifest,
    build_ordered_collection,
    build_search_response,
    build_search_service,
    resolve_activity,
    resolve_annotation,
    resolve_info,
    urljoin,
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
    from, as the spec requires. When ``settings.IIIF_INFO`` is configured, its
    declarative extras are threaded in; a per-image ``IIIF_INFO`` callable
    receives the **decoded storage name** here (there is no field file on the
    view path — see :func:`djiiif.resolve_info`).

    Args:
        request: The incoming ``HttpRequest``.
        identifier: The encoded identifier segment captured by the URLconf.

    Returns:
        A JSON-LD ``JsonResponse`` carrying the ``info.json`` document.

    Raises:
        Http404: If the identifier does not resolve to a readable image.
    """
    name, width, height = _load_dimensions(identifier)
    id_url = request.build_absolute_uri(request.path).rsplit("/info.json", 1)[0]
    return _ld_json(build_info_document(id_url, width, height, extras=resolve_info(name)))


def serve_manifest(request, identifier):
    """Serve a single-image Presentation API manifest for a stored image.

    The image service base URI is the request URL minus the ``/manifest``
    suffix, matching the identifier the ``info.json`` view serves. The manifest
    label defaults to the file's base name.

    When ``IIIF_ANNOTATIONS_BACKEND`` is configured, the canvas gains an
    ``annotations`` reference to this image's AnnotationPage; when a search
    backend is available (a dedicated ``IIIF_SEARCH_BACKEND`` or the annotations
    fallback), the manifest advertises a ``SearchService2``. Both are view-only —
    ``IIIFObject.manifest`` (no request in scope) emits neither.

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
    manifest = build_manifest(id_url, width, height, label=label)

    if _resolve_backend("IIIF_ANNOTATIONS_BACKEND") is not None:
        manifest["items"][0]["annotations"] = [
            {"id": urljoin([id_url, "annotations", "1"]), "type": "AnnotationPage"}
        ]
    if _search_available():
        manifest["service"] = [build_search_service(urljoin([id_url, "search"]))]

    return _ld_json(manifest)


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


def _resolve_backend(setting_name: str):
    """Resolve a backend setting to a callable, or ``None`` when unset.

    Args:
        setting_name: The setting to read (``IIIF_ANNOTATIONS_BACKEND`` /
            ``IIIF_SEARCH_BACKEND``).

    Returns:
        The backend callable (importing a dotted-path string), or ``None`` if the
        setting is unset.
    """
    backend = getattr(settings, setting_name, None)
    if backend is None:
        return None
    if isinstance(backend, str):
        backend = import_string(backend)
    return backend


def _search_available() -> bool:
    """Return whether search can be answered (a dedicated backend or the fallback)."""
    return (
        _resolve_backend("IIIF_SEARCH_BACKEND") is not None
        or _resolve_backend("IIIF_ANNOTATIONS_BACKEND") is not None
    )


def _canvas_id_for(request, suffix: str) -> tuple[str, str]:
    """Return ``(id_url, canvas_id)`` for an annotation/search request.

    Args:
        request: The incoming ``HttpRequest``.
        suffix: The trailing route segment to strip (``"/annotations/1"`` or
            ``"/search"``) to recover the image service base URI.

    Returns:
        The image service base URI and the ``{id_url}/canvas/1`` URI that a
        served manifest targets.
    """
    id_url = request.build_absolute_uri(request.path).rsplit(suffix, 1)[0]
    return id_url, urljoin([id_url, "canvas", "1"])


def serve_annotation_page(request, identifier):
    """Serve a W3C ``AnnotationPage`` for a stored image.

    Draws its annotations from the ``IIIF_ANNOTATIONS_BACKEND`` callable
    ``(identifier, request) -> iterable`` of :class:`~djiiif.Annotation` /
    ``dict`` entries. The annotations target ``{id_url}/canvas/1``, matching the
    canvas :func:`serve_manifest` emits. Reads no image storage.

    Args:
        request: The incoming ``HttpRequest``.
        identifier: The encoded identifier segment captured by the URLconf.

    Returns:
        A JSON-LD ``JsonResponse`` carrying the ``AnnotationPage``.

    Raises:
        Http404: If ``IIIF_ANNOTATIONS_BACKEND`` is unset.
    """
    backend = _resolve_backend("IIIF_ANNOTATIONS_BACKEND")
    if backend is None:
        raise Http404("No IIIF annotations backend is configured.")
    _id_url, canvas_id = _canvas_id_for(request, "/annotations/1")
    page_url = request.build_absolute_uri(request.path)
    items = list(backend(identifier, request))
    return _ld_json(build_annotation_page(page_url, canvas_id, items))


def serve_search(request, identifier):
    """Answer a IIIF Content Search 2.0 query for a stored image.

    Uses ``IIIF_SEARCH_BACKEND`` ``(identifier, q, request) -> iterable`` of hits
    when configured; otherwise falls back to a case-insensitive substring match
    over ``IIIF_ANNOTATIONS_BACKEND`` (so serving annotations yields search for
    free). A missing or empty ``q`` returns a valid empty page — never the whole
    corpus. Unimplemented spec parameters (``motivation``/``date``/``user``) are
    echoed in ``ignored``. Reads no image storage.

    Args:
        request: The incoming ``HttpRequest``.
        identifier: The encoded identifier segment captured by the URLconf.

    Returns:
        A JSON-LD ``JsonResponse`` carrying the search ``AnnotationPage``.

    Raises:
        Http404: If neither a search nor an annotations backend is configured.
    """
    search_backend = _resolve_backend("IIIF_SEARCH_BACKEND")
    annotations_backend = _resolve_backend("IIIF_ANNOTATIONS_BACKEND")
    if search_backend is None and annotations_backend is None:
        raise Http404("No IIIF search backend is configured.")

    search_url = request.build_absolute_uri(request.path)
    q = request.GET.get("q", "")
    ignored = [p for p in ("motivation", "date", "user") if p in request.GET]

    if not q:
        hits = []
    elif search_backend is not None:
        hits = list(search_backend(identifier, q, request))
    else:
        _id_url, canvas_id = _canvas_id_for(request, "/search")
        hits = _substring_hits(annotations_backend, identifier, q, request, canvas_id)

    return _ld_json(build_search_response(search_url, q, hits, ignored=ignored))


def _substring_hits(backend, identifier, q, request, canvas_id: str) -> list[dict]:
    """Filter an annotations backend to a case-insensitive substring match on ``q``.

    The free-search fallback: annotations from ``IIIF_ANNOTATIONS_BACKEND`` carry
    no ``canvas_id`` (their canvas is implied by the page URL), so each match is
    given the served manifest's ``canvas_id`` to locate the hit.

    Args:
        backend: The resolved annotations backend callable.
        identifier: The encoded identifier passed to the backend.
        q: The query string (matched case-insensitively as a substring).
        request: The incoming ``HttpRequest`` passed to the backend.
        canvas_id: The canvas URI to attach to matching hits.

    Returns:
        The matching hits as resolved annotation dicts.
    """
    needle = q.lower()
    hits = []
    for entry in backend(identifier, request):
        ann = resolve_annotation(entry)
        text = ann["text"]
        if isinstance(text, str) and needle in text.lower():
            if ann["canvas_id"] is None:
                ann["canvas_id"] = canvas_id
            hits.append(ann)
    return hits
