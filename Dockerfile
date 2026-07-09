FROM python:3.11-slim-bookworm AS base

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY src ./src
COPY scripts ./scripts
# Seed SQL used by scripts/import_item_base_templates.py (and related imports).
# Without this, `docker compose exec api python -m scripts.import_item_base_templates`
# fails with FileNotFoundError: /app/info/item_base_templates_import.sql.
COPY info ./info
# Committed game art (nav icons, monsters, bosses, ...) served at /static
# (see main.py static mount). Runtime-generated files (waifu portraits etc.)
# are also written here; they re-sync from DB blobs after container recreate.
COPY static ./static

RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "waifu_bot.main:app", "--host", "0.0.0.0", "--port", "8000"]
