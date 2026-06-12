"""Signed, time-limited serving of patient media (PHI).

Why this exists
---------------
MRI/ECG/Echo/EEG uploads, generated masks/overlays/plots, and combined PDF
reports all live under ``MEDIA_ROOT``. Serving that tree from a public path
(Django's ``static()`` helper in DEBUG, or a bare ``nginx alias`` in production)
means anyone who learns or guesses a ``/media/...`` URL can read another doctor's
patient data — a direct breach of the project's doctor-isolation contract.

Approach
--------
The API never hands back a raw ``/media/`` URL. Serializers call
:func:`signed_media_url`, which appends a short-lived HMAC signature (``exp`` +
``sig``). :func:`serve_signed_media` validates that signature before streaming the
file, and rejects expired/forged/traversal requests. Because the signature lives
in the query string (not an ``Authorization`` header), plain ``<img src=...>``
tags keep working with no frontend change.

Trade-off (documented honestly): a signed URL grants access to anyone who holds
it until it expires — it is time-scoped, not per-identity. That is a large
improvement over permanent public access and is the standard pattern, but it is
not a substitute for a full per-request authorization check. In production, point
nginx at this view (or use ``auth_request``) rather than serving MEDIA_ROOT
directly.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.utils.crypto import constant_time_compare


def _secret() -> bytes:
    secret = getattr(settings, 'MEDIA_URL_SIGNING_SECRET', None) or settings.SECRET_KEY
    return secret.encode('utf-8')


def _ttl() -> int:
    return int(getattr(settings, 'MEDIA_SIGNED_URL_TTL_SECONDS', 3600))


def _normalise_rel(url: str) -> str:
    """Reduce a media URL or path to the MEDIA_ROOT-relative, slash-separated path."""
    rel = str(url)
    media_url = settings.MEDIA_URL
    if rel.startswith(media_url):
        rel = rel[len(media_url):]
    return rel.replace('\\', '/').lstrip('/')


def _sign(rel_path: str, exp: int) -> str:
    msg = f'{rel_path}:{exp}'.encode('utf-8')
    return hmac.new(_secret(), msg, hashlib.sha256).hexdigest()


def signed_media_url(request, url, ttl: int | None = None):
    """Return an absolute, signed, time-limited URL for a media file.

    ``url`` may be a full media URL (``/media/mri/uploads/x.png``), a
    ``FieldFile.url``, or a MEDIA_ROOT-relative path (``mri/uploads/x.png``).
    Returns ``None`` for a falsy input.
    """
    if not url:
        return None
    rel = _normalise_rel(url)
    exp = int(time.time()) + int(ttl if ttl is not None else _ttl())
    signed = f'{settings.MEDIA_URL}{rel}?exp={exp}&sig={_sign(rel, exp)}'
    return request.build_absolute_uri(signed) if request is not None else signed


def serve_signed_media(request, path: str):
    """Validate the HMAC signature and stream the file, else 403/404.

    Mounted at ``MEDIA_URL`` (see core/urls.py). ``path`` is the MEDIA_ROOT-
    relative path captured from the URL.
    """
    exp = request.GET.get('exp')
    sig = request.GET.get('sig')
    if not exp or not sig:
        return HttpResponseForbidden('Missing media signature.')
    try:
        exp_int = int(exp)
    except (TypeError, ValueError):
        return HttpResponseForbidden('Malformed media signature.')
    if exp_int < int(time.time()):
        return HttpResponseForbidden('Media link expired.')

    rel = _normalise_rel(path)
    if not constant_time_compare(_sign(rel, exp_int), sig):
        return HttpResponseForbidden('Invalid media signature.')

    # Resolve under MEDIA_ROOT and refuse any path-traversal escape.
    root = os.path.realpath(str(settings.MEDIA_ROOT))
    full = os.path.realpath(os.path.join(root, rel))
    if full != root and not full.startswith(root + os.sep):
        raise Http404('Not found.')
    if not os.path.isfile(full):
        raise Http404('Not found.')
    return FileResponse(open(full, 'rb'))
