"""Liveness/readiness probe: GET /api/health/.

Reports DB connectivity and which model weights are present on disk (the same
info as `tools/download_weights.py --check-only`, but live over HTTP). Public and
auth-free so a load balancer / container HEALTHCHECK / uptime monitor can hit it.
Returns 200 when the database is reachable, 503 otherwise.
"""

import os

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WEIGHTS_DIR = os.path.join(_BACKEND_DIR, 'models_weights')


def _weights_status() -> dict:
    def has(*parts):
        return os.path.exists(os.path.join(_WEIGHTS_DIR, *parts))

    ecg_dir = os.path.join(_WEIGHTS_DIR, 'ecg_finetuned')
    ecg_finetuned = (
        len([f for f in os.listdir(ecg_dir) if f.endswith('.pt')])
        if os.path.isdir(ecg_dir) else 0
    )
    return {
        'mri_classifier': has('vit_brain_tumor', 'config.json'),
        'ecg_finetuned': ecg_finetuned,                       # 0–7 per-pathology checkpoints
        'echonet': has('echonet', 'echonet_seg.pt') and has('echonet', 'echonet_ef.pt'),
        'biot_encoder': has('biot', 'EEG-PREST-16-channels.ckpt'),
        'biot_iiic_head': has('biot', 'biot_iiic.pt'),
    }


@require_GET
def health(request):
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False
    payload = {
        'status': 'ok' if db_ok else 'degraded',
        'database': 'ok' if db_ok else 'unreachable',
        'weights': _weights_status(),
    }
    return JsonResponse(payload, status=200 if db_ok else 503)
