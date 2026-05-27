import pytest

from djiiif import urljoin


def test_strips_internal_slashes_and_preserves_trailing():
    assert urljoin(["http://a/", "/b/", "c.jpg"]) == "http://a/b/c.jpg"


def test_preserves_trailing_slash_on_last_segment():
    assert urljoin(["http://a/", "/b/"]) == "http://a/b/"


def test_single_segment():
    assert urljoin(["x"]) == "x"


def test_empty_list_raises():
    with pytest.raises(ValueError):
        urljoin([])
