# Deployment Guide (single VM)

How to deploy the **Multimodal Medical AI Platform** on one server, beyond the
two-dev-server setup in the README. This is a **documented path, not a
battle-tested one** - validate every step in your own environment before
trusting it with real traffic. The repo's `docker-compose.yml` is likewise
**untested end-to-end** (see its own header comment); local dev only.

Target topology: MongoDB, the Django backend under gunicorn, and nginx as the
front door (TLS, built frontend, `/media/`, `/api/` reverse proxy) - all on one
VM. Windows works too; swap gunicorn for waitress (section 4).

---

## 1. Prerequisites

- Python **3.10 or 3.11** (djongo 1.3.6 + Django 3.2.25 do not run on 3.12+).
- Node.js 18+ (build the frontend once; not needed at runtime).
- MongoDB Community 6/7 as a managed service.
- A domain pointing at the VM and a TLS certificate (e.g. via certbot).
- ~3 GB free disk for cached model weights; ~8 GB RAM resident during inference.

---

## 2. Production `.env`

Copy `backend/.env.example` to `backend/.env` and harden it:

```ini
# Generate a fresh key (DO NOT reuse the dev one):
#   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY=<paste-the-50-char-random-key>

DEBUG=False
ALLOWED_HOSTS=medical.example.com

DB_NAME=medical_platform
DB_HOST=localhost
DB_PORT=27017

# Real frontend origin (https, no trailing slash). CORS is strict.
CORS_ALLOWED_ORIGINS=https://medical.example.com
```

With `DEBUG=False`, Django stops serving `/static/` and `/media/` itself, so
nginx must serve them (section 5). A missing domain in `ALLOWED_HOSTS` or
`CORS_ALLOWED_ORIGINS` will reject requests.

---

## 3. MongoDB as a service

Run MongoDB as a managed service, not a foreground `mongod`:

```bash
sudo systemctl enable --now mongod
sudo systemctl status mongod        # confirm it listens on 27017
```

The app connects unauthenticated to `localhost:27017`. Keep the Mongo port
firewalled to localhost. If you enable Mongo auth, note the `CLIENT` dict in
`core/settings.py` only passes `host`/`port` - extend it with credentials.

---

## 4. Backend under gunicorn (Linux)

From `backend/` with the venv active and `pip install -r requirements.txt` done:

```bash
python manage.py migrate
python manage.py collectstatic --noinput   # gathers admin/DRF assets into staticfiles/
pip install gunicorn
gunicorn core.wsgi:application --bind 127.0.0.1:8000 --workers 2 --timeout 180
```

`core.wsgi:application` is the WSGI entry point (`WSGI_APPLICATION` in settings).
Run it under systemd so it restarts on boot/crash.

**Why 2+ workers and a long timeout:** inference is **synchronous in the request
thread** - there is no Celery/RQ. A single MRI/ECG/Echo/EEG request can occupy a
worker for many seconds (longer on first call while weights download, or for EEG
over many segments on CPU). With one worker, a slow upload blocks every other
request. Use **2+ workers** to keep the UI responsive and a **generous timeout**
(120-300 s) so long inferences are not killed mid-request. Each worker holds the
loaded models in memory (~3 GB), so size workers against available RAM.

**Windows alternative - waitress.** No gunicorn on Windows; waitress serves the
same `core.wsgi` app:

```powershell
pip install waitress
waitress-serve --listen=127.0.0.1:8000 --threads=4 core.wsgi:application
```

waitress is threaded, not multi-process; raise `--threads` and accept that the
GIL serialises CPU-bound inference.

---

## 5. Frontend build + nginx

The API base URL is baked in **at build time**: `npm run build` reads
`VITE_API_URL` (`frontend/src/services/api.js`). `frontend/.env` is gitignored,
so a fresh checkout has none and `api.js` falls back to its hardcoded
`http://localhost:8000/api` - built as-is, the deployed app would call
localhost. Create a `frontend/.env.production` (Vite prefers it over `.env`
during builds) with the same-origin path, so nginx proxies everything and CORS
never triggers:

```ini
# frontend/.env.production
VITE_API_URL=/api
```

Then build once (on the VM or in CI, then copy `dist/` over):

```bash
cd frontend && npm install && npm run build   # emits frontend/dist/
```

nginx serves `dist/`, serves Django's `/media/` (uploads + generated
overlays/plots/PDFs) and `/static/` (admin/DRF assets), and reverse-proxies
`/api/` to gunicorn. Sample server block:

```nginx
server {
    listen 443 ssl;
    server_name medical.example.com;

    ssl_certificate     /etc/letsencrypt/live/medical.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/medical.example.com/privkey.pem;

    client_max_body_size 500M;   # echo videos up to 500 MB; MRI 100, EEG 200,
                                 # ECG 50 (caps live in apps/*/views.py)

    root /srv/medical-platform/frontend/dist;
    index index.html;

    location / {
        try_files $uri /index.html;   # SPA fallback for client-side routes
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;      # match the backend timeout
    }

    location /media/  { alias /srv/medical-platform/backend/media/; }
    location /static/ { alias /srv/medical-platform/backend/staticfiles/; }
}
```

Point the `root`/`alias` paths at your checkout, and redirect `:80` to `:443` in
a separate server block.

One wrinkle: the API builds absolute `file_url`/`plot_url`/`overlay_url` values
via `request.build_absolute_uri()`. Django 3.2 ignores `X-Forwarded-Proto`
unless you add `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`
to `core/settings.py` - without it those URLs come back as `http://` behind TLS.

---

## 6. Model weights

The MRI/ECG weights (~700 MB) download into the backend user's cache
(`~/.cache/torch/hub/`, `~/.cache/huggingface/`) on the **first** request. Two
sets are **not** auto-downloaded and must be on disk first, or those endpoints
return a clear `FileNotFoundError` (by design):

- **EchoNet** - `backend/models_weights/echonet/echonet_seg.pt` and
  `echonet_ef.pt` (override via `ECHONET_SEG_WEIGHTS` / `ECHONET_EF_WEIGHTS`).
- **BIOT IIIC head** - `backend/models_weights/biot/biot_iiic.pt` (override via
  `BIOT_IIIC_WEIGHTS`). The encoder ckpt is bundled; the head comes from
  `tools/train_eeg_head.py`.

Pre-warm the MRI/ECG caches once after deploy to avoid a slow/timed-out first
request: `python apps/inference/test_pipelines.py`.

---

## 7. Known constraints

- **Synchronous inference.** No task queue; plan for 2+ workers and a 120-300 s
  timeout (section 4).
- **Version pins are load-bearing.** djongo 1.3.6 forces **Django 3.2.25** and
  **Python 3.10/3.11**. Do not upgrade without replacing djongo.
- **Strict host/CORS.** With `DEBUG=False`, a missing domain breaks the app.
- **Not battle-tested.** This guide and `docker-compose.yml` are documented
  paths, not validated production deployments. Never put real patient data on an
  unhardened VM.
