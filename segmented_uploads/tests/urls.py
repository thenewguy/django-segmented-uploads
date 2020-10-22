import re

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve


urlpatterns = [
    path('admin/', admin.site.urls),
    path('uploads/', include('segmented_uploads.urls')),
    path('', include('segmented_uploads.tests.testapp.urls')),
] + [
    re_path(r'^%s(?P<path>.*)$' % re.escape(prefix.lstrip('/')), serve, kwargs={'document_root': document_root})
    for prefix, document_root in (
        (settings.STATIC_URL, settings.STATIC_ROOT),
        (settings.MEDIA_URL, settings.MEDIA_ROOT),
    )
]
