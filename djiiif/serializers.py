"""Optional Django REST Framework support for :class:`~djiiif.IIIFField`.

This module imports ``rest_framework``, which djiiif does not depend on at
runtime. Install the extra to use it::

    pip install djiiif[drf]

Importing :mod:`djiiif` itself never imports this module, so the core package
has no DRF dependency.
"""

from rest_framework import serializers


class IIIFSerializerField(serializers.Field):
    """A read-only DRF field that serializes an ``IIIFField`` to its profile URLs.

    Declare it on a serializer with the model's IIIF field as the source::

        class AssetSerializer(serializers.ModelSerializer):
            original = IIIFSerializerField()

            class Meta:
                model = Asset
                fields = ["id", "original"]

    The representation is :meth:`djiiif.IIIFObject.as_dict`, i.e. a
    ``{profile_name: url}`` mapping (with ``info``/``identifier`` included when
    ``include_meta`` is set).

    Attributes:
        include_meta: Passed through to ``as_dict`` to include the ``info`` and
            ``identifier`` URLs.
    """

    def __init__(self, *args, include_meta: bool = False, **kwargs):
        """Configure the field.

        Args:
            include_meta: Include the ``info``/``identifier`` URLs in the output.
            *args: Forwarded to ``serializers.Field``.
            **kwargs: Forwarded to ``serializers.Field``; ``read_only`` defaults
                to ``True`` since the representation is derived, not writable.
        """
        self.include_meta = include_meta
        kwargs.setdefault("read_only", True)
        super().__init__(*args, **kwargs)

    def to_representation(self, value) -> dict[str, str]:
        """Serialize an ``IIIFFieldFile`` to its profile URL mapping.

        Args:
            value: The ``IIIFFieldFile`` attribute value for the source field.

        Returns:
            The ``{profile_name: url}`` mapping from ``value.iiif.as_dict``.
        """
        return value.iiif.as_dict(include_meta=self.include_meta)
