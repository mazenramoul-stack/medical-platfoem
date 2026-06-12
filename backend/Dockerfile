# syntax=docker/dockerfile:1
#
# Backend image for the Multimodal Medical AI Platform.
# Heavy because torch + ecglib + transformers + matplotlib weigh in at ~3 GB.

FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System deps for nibabel/pydicom/scipy + curl for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better Docker layer caching).
COPY requirements.txt /app/
# torch wheels for Linux ship as CUDA builds via PyPI; for a CPU-only container
# use the dedicated PyTorch index. Comment this line out if you have a GPU and
# want CUDA support inside the container.
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
    torch==2.2.0 torchvision==0.17.0 \
 && pip install -r requirements.txt

# Then copy the source.
COPY . /app/

EXPOSE 8000

# `runserver` is for development. For production, swap in:
#   gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 4
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
