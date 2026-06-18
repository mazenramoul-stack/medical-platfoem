---
title: Medical AI Platform API
emoji: 🧠
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Medical AI Platform — Backend API

Django + DRF backend for the multimodal medical AI platform (MRI / ECG / Echo / EEG).
Built from a Docker SDK Space; the API listens on port 7860.

This text and the YAML block above must be the contents of the **`README.md`**
file at the root of the Hugging Face Space. The `app_port: 7860` line is what
tells HF which port to route to — do not remove it.

## Required Space secrets / variables

Set these under **Settings → Variables and secrets** in the Space:

| Name | Example value | Notes |
|---|---|---|
| `SECRET_KEY` | (random 50-char string) | Generate one; keep it secret |
| `DEBUG` | `False` | Never `True` on a public site |
| `ALLOWED_HOSTS` | `your-space.hf.space,.hf.space` | Your Space's hostname |
| `MONGO_URI` | `mongodb+srv://user:pass@cluster0.xxxx.mongodb.net/?appName=Cluster0` | From MongoDB Atlas |
| `DB_NAME` | `medical_platform` | |
| `CORS_ALLOWED_ORIGINS` | `https://your-project.vercel.app` | Your Vercel frontend URL |
| `SECURE_SSL_REDIRECT` | `False` | HF already terminates HTTPS |
