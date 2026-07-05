# Authorization (Auth Flow 2.0)

For access-controlled images served by an image server that implements the
[IIIF Authorization Flow 2.0](https://iiif.io/api/auth/2.0/) (e.g.
[iiiris](https://gitlab.com/iiiris-org/iiiris)), djiiif can embed the auth
**service description** in the `info_document` and `manifest` it generates, so a
viewer knows how to authenticate.

:::{important}
djiiif only **describes** the services. The image server **implements and
enforces** them — djiiif never checks credentials or gates pixels.
:::

## Configure `IIIF_AUTH`

Use the typed helpers to build the nested probe → access → token/logout block:

```{code-block} python
:caption: settings.py
from djiiif import ProbeService, AccessService, TokenService, LogoutService

IIIF_AUTH = ProbeService(
    id="https://iiiris.example/auth/probe",
    access=AccessService(
        id="https://iiiris.example/auth/login",
        profile="active",                      # or "kiosk" / "external"
        label="Log in to Example Institution",
        heading="Restricted material",
        note="Please log in with your institutional account.",
        confirm_label="Log in",
        token=TokenService(id="https://iiiris.example/auth/token"),
        logout=LogoutService(id="https://iiiris.example/auth/logout", label="Log out"),
    ),
)
```

Label-ish fields accept a plain string, a list of strings, or an already-formed
IIIF language map (`{"en": ["…"]}`). A raw `dict` works in place of
`ProbeService` too.

## Per-image (mixed public/restricted)

For a mix of public and restricted images, set `IIIF_AUTH` to a callable
receiving the field file — return the `ProbeService` for restricted images and
`None` for public ones:

```{code-block} python
:caption: settings.py
def image_auth(parent):
    if parent.instance.is_public:
        return None
    return ProbeService(id="https://iiiris.example/auth/probe", access=...)

IIIF_AUTH = image_auth
```

When `IIIF_AUTH` is unset (or the callable returns `None`), documents are
unchanged.

## Version requirement

Authorization Flow 2.0 pairs with Image API 3. Setting `IIIF_AUTH` while
`IIIF_IMAGE_API_VERSION = 2` raises `ImproperlyConfigured`.
