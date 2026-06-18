#!/usr/bin/env bash
# Startup for the Hugging Face Space (Docker) deployment.
#
# Why the three-step migrate: djongo 1.3.6 cannot translate SimpleJWT's
# token_blacklist BigAutoField migrations (0008/0010/0012 do
# `ALTER COLUMN "id" TYPE long`) into MongoDB, so a plain `migrate` aborts with
# `SQLDecodeError: Unknown token: TYPE`. MongoDB is schemaless, so those column
# retypes are no-ops — we apply everything we can, then FAKE the rest of
# token_blacklist (records them as applied without running the SQL). This is
# idempotent: on later restarts everything is already applied and migrate is a
# no-op. The first run prints a token_blacklist traceback — that is expected.

set -u

echo "[start-space] migrate (pass 1: apply everything possible)..."
python manage.py migrate --noinput || true

echo "[start-space] migrate (pass 2: fake token_blacklist BigAutoField steps)..."
python manage.py migrate token_blacklist --fake --noinput || true

echo "[start-space] migrate (pass 3: finish any remainder)..."
python manage.py migrate --noinput || true

echo "[start-space] dropping stale djongo jti_hex index if present..."
# djongo can't apply SimpleJWT's later token_blacklist migrations on MongoDB,
# leaving a stale UNIQUE index on jti_hex (always null) that makes the 2nd token
# insert collide (E11000) and 500s login/register. Drop it. Idempotent.
python fix_mongo_indexes.py || true

echo "[start-space] starting gunicorn on :7860 ..."
exec gunicorn core.wsgi:application \
    --bind 0.0.0.0:7860 \
    --workers 1 \
    --timeout 600
