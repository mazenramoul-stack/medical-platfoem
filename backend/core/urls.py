from django.contrib import admin
from django.urls import include, path, re_path

from .media import serve_signed_media

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.authentication.urls')),
    path('api/', include('apps.patients.urls')),
    path('api/mri/', include('apps.mri.urls')),
    path('api/ecg/', include('apps.ecg.urls')),
    path('api/echo/', include('apps.echo.urls')),
    path('api/eeg/', include('apps.eeg.urls')),
    path('api/reports/', include('apps.reports.urls')),
    # Patient media (PHI) is served ONLY through the signature-checking view —
    # never via Django's public static() helper or a bare nginx alias. The API
    # mints short-lived signed URLs (core.media.signed_media_url) in its *_url
    # fields. In production, proxy /media/ to this view (or use nginx
    # auth_request) instead of serving MEDIA_ROOT directly.
    re_path(r'^media/(?P<path>.+)$', serve_signed_media, name='signed-media'),
]
