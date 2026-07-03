"""URL patterns for the built-in IIIF document views.

Include this in a project's URLconf to expose ``info.json`` and ``manifest`` for
stored images::

    path("iiif/", include("djiiif.urls")),

An image stored as ``uploads/photo.jpg`` is then served at
``/iiif/uploads%2Fphoto.jpg/info.json`` and
``/iiif/uploads%2Fphoto.jpg/manifest``. Serving identifiers that contain encoded
slashes requires the web server to allow encoded slashes in the path (e.g.
Apache's ``AllowEncodedSlashes``); flat identifiers need no such config.
"""

from django.urls import re_path

from djiiif.views import serve_info_json, serve_manifest

app_name = "djiiif"

urlpatterns = [
    re_path(r"^(?P<identifier>.+)/info\.json$", serve_info_json, name="info-json"),
    re_path(r"^(?P<identifier>.+)/manifest$", serve_manifest, name="manifest"),
]
