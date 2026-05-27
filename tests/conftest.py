import django
from django.conf import settings


def pytest_configure():
    settings.configure(
        DEBUG=False,
        DATABASES={},
        INSTALLED_APPS=["djiiif"],
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": [],
                "APP_DIRS": True,
                "OPTIONS": {},
            },
        ],
        IIIF_HOST="http://server/",
        IIIF_PROFILES={
            "thumbnail": {
                "host": "http://server/",
                "region": "full",
                "size": "150,",
                "rotation": "0",
                "quality": "default",
                "format": "jpg",
            },
        },
        USE_TZ=True,
    )
    django.setup()
