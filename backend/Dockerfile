FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir ".[dev]"

COPY alembic.ini ./
COPY migrations ./migrations
COPY tests ./tests
COPY scripts ./scripts

EXPOSE 8000
CMD ["sh", "scripts/start.sh"]
