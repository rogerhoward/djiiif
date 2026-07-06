API reference
=============

The public API of the ``djiiif`` package. Everything below is generated from the
source docstrings, so it always matches the installed version.

.. currentmodule:: djiiif

Fields and accessor
-------------------

.. autoclass:: IIIFField
   :members:

.. autoclass:: IIIFFieldFile
   :members:

.. autoclass:: IIIFObject
   :members:

Profiles
--------

.. autoclass:: Profile
   :members:

.. autofunction:: resolve_profile
.. autofunction:: image_url
.. autofunction:: encode_identifier

Image & Presentation documents
------------------------------

.. autofunction:: build_info_document
.. autofunction:: build_manifest
.. autofunction:: build_multi_manifest
.. autofunction:: build_collection

.. autoclass:: InfoExtras
   :members:

.. autofunction:: resolve_info

Geolocation (navPlace)
----------------------

.. autofunction:: djiiif.geo.resolve_navplace

Content State
-------------

.. autofunction:: build_content_state
.. autofunction:: encode_content_state
.. autofunction:: decode_content_state

Change Discovery
----------------

.. autoclass:: Activity
   :members:

.. autofunction:: resolve_activity
.. autofunction:: build_activity
.. autofunction:: build_ordered_collection
.. autofunction:: build_collection_page

Annotations and search
-----------------------

.. autoclass:: Annotation
   :members:

.. autofunction:: resolve_annotation
.. autofunction:: build_annotation
.. autofunction:: build_annotation_page
.. autofunction:: build_search_service
.. autofunction:: build_search_response

Authorization Flow 2.0
----------------------

.. autoclass:: ProbeService
   :members:

.. autoclass:: AccessService
   :members:

.. autoclass:: TokenService
   :members:

.. autoclass:: LogoutService
   :members:

.. autofunction:: resolve_auth

Views and serializer
--------------------

.. automodule:: djiiif.views
   :members:
   :undoc-members:

.. autoclass:: djiiif.serializers.IIIFSerializerField
   :members:
