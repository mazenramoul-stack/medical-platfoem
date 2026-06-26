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

# ---- Model weights baked into the image ------------------------------------
# The large *.pt / *.safetensors / *.ckpt files are gitignored, so the GitHub
# clone above does NOT include them. Without them Echo + EEG crash with
# "weights not found" and MRI has to download the stock model at request time
# (slow / fragile). We upload the real weights into THIS Space repo with
# tools/deploy_weights_to_space.py, then copy them over the cloned sidecar
# configs here so everything is on disk before the server starts.
#   * Echo  -> models_weights/echonet/{echonet_seg.pt, echonet_ef.pt}
#   * EEG   -> models_weights/biot/{EEG-PREST-16-channels.ckpt, biot_iiic.pt}
#   * MRI   -> models_weights/vit_brain_tumor/model.safetensors (the 95.4% Swin)
#   * ECG   -> models_weights/ecg_finetuned/*.pt (optional; ECG already works)
COPY --chown=user models_weights/ /home/user/app/backend/models_weights/

# ---- Python dependencies ----------------------------------------------------
# dnspython is required for pymongo to resolve Atlas `mongodb+srv://` URIs.
# gunicorn is the production WSGI server.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn dnspython

# ---- Pre-warm the small U-Net so MRI does not download at request time ------
# The Swin classifier is now baked in (above), but the segmentation U-Net still
# loads from torch.hub. Fetch it at build time so the first MRI request is fast
# and offline. Non-fatal: if the hub is unreachable at build it falls back to a
# runtime download (unchanged old behaviour).
RUN python -c "import torch; torch.hub.load('mateuszbuda/brain-segmentation-pytorch','unet',in_channels=3,out_channels=1,init_features=32,pretrained=True,trust_repo=True)" \
    || echo "U-Net prewarm skipped (will download at runtime)"

EXPOSE 7860

# Startup logic (migrations + djongo token_blacklist workaround + gunicorn,
# single worker to keep memory in check, 600s timeout for slow synchronous
# inference + one-time weight download) lives in the repo's start-space.sh so
# future tweaks need only a GitHub push + Factory rebuild — no Dockerfile edit.
CMD ["bash", "start-space.sh"]
