# =============================================================================
# Hugging Face Space (Docker SDK) — backend + AI for the Medical AI Platform.
#
# This file lives in the HF SPACE repo (not strictly in your GitHub repo). It
# pulls your code from GitHub at build time, installs the ML stack, and serves
# the Django API on port 7860 (the port HF Spaces expects).
#
# >>> EDIT ONE LINE: replace the GitHub URL + branch in the `git clone` below.
# =============================================================================
FROM python:3.11-slim

# ---- System libraries needed by torch / pillow / matplotlib / opencv --------
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential \
        libglib2.0-0 libgl1 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces run the container as user id 1000. Give it a writable home so model
# weight caches (~700 MB, downloaded on first inference) have somewhere to live.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    TORCH_HOME=/home/user/.cache/torch \
    HF_HOME=/home/user/.cache/huggingface \
    PYTHONUNBUFFERED=1

WORKDIR /home/user/app

# ---- Pull your code from GitHub --------------------------------------------
# Your public GitHub repo URL and branch.
RUN git clone --depth 1 --branch main \
    https://github.com/mazenramoul-stack/medical-platfoem.git .

WORKDIR /home/user/app/backend

# ---- Python dependencies ----------------------------------------------------
# dnspython is required for pymongo to resolve Atlas `mongodb+srv://` URIs.
# gunicorn is the production WSGI server.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn dnspython

EXPOSE 7860

# Apply migrations, then serve. A single worker keeps memory in check (the ML
# models are big); the 600 s timeout covers slow synchronous inference + the
# one-time weight download on the first request after a cold start.
CMD python manage.py migrate --noinput && \
    gunicorn core.wsgi:application \
        --bind 0.0.0.0:7860 \
        --workers 1 \
        --timeout 600
