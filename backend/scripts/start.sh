#!/bin/sh
# Apply migrations to BOTH databases, then start the API.
set -e
alembic -n core upgrade head
alembic -n vault upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 ${UVICORN_EXTRA_ARGS}
