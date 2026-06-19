from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from .health import health
from .media import serve_signed_media

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health, name='health'),
    path('api/auth/', include('apps.authentication.urls')),
    path('api/', include('apps.patients.urls')),
    path('api/mri/', include('apps.mri.urls')),
    path('api/ecg/', include('apps.ecg.urls')),
    path('api/echo/', include('apps.echo.urls')),
    path('api/eeg/', include('apps.eeg.urls')),
    path('api/convert/', include('apps.conversion.urls')),
    path('api/reports/', include('apps.reports.urls')),
    # OpenAPI schema + interactive docs (drf-spectacular).
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    # Patient media (PHI) is served ONLY through the signature-checking view —
    # never via Django's public static() helper or a bare nginx alias. The API
    # mints short-lived signed URLs (core.media.signed_media_url) in its *_url
    # fields. In production, proxy /media/ to this view (or use nginx
    # auth_request) instead of serving MEDIA_ROOT directly.
    re_path(r'^media/(?P<path>.+)$', serve_signed_media, name='signed-media'),
]
