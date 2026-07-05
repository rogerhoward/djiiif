"""URL patterns for the built-in IIIF document views.

Include this in a project's URLconf to expose ``info.json`` and ``manifest`` for
stored images::

    path("iiif/", include("djiiif.urls")),

An image stored as ``uploads/photo.jpg`` is then served at
``/iiif/uploads%2Fphoto.jpg/info.json`` and
``/iiif/uploads%2Fphoto.jpg/manifest``. Serving identifiers that contain encoded
slashes requires the web server to allow encoded slashes in the path (e.g.
Apache's ``AllowEncodedSlashes``); flat identifiers need no such config.

A Collection of manifest references is served at ``/iiif/collection`` when
``settings.IIIF_COLLECTION_SOURCE`` is configured (otherwise ``404``). A IIIF
Change Discovery activity stream is served at ``/iiif/activity/collection`` and
``/iiif/activity/page/<n>`` when ``settings.IIIF_ACTIVITY_SOURCE`` is configured
(otherwise ``404``).
"""

from django.urls import path, re_path

from djiiif.views import (
    serve_activity_collection,
    serve_activity_page,
    serve_collection,
    serve_info_json,
    serve_manifest,
)

app_name = "djiiif"

urlpatterns = [
    # Fixed routes first, so the greedy identifier patterns below cannot shadow them.
    path("collection", serve_collection, name="collection"),
    path("activity/collection", serve_activity_collection, name="activity-collection"),
    path("activity/page/<int:page>", serve_activity_page, name="activity-page"),
    re_path(r"^(?P<identifier>.+)/info\.json$", serve_info_json, name="info-json"),
    re_path(r"^(?P<identifier>.+)/manifest$", serve_manifest, name="manifest"),
]
