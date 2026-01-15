FROM python:3.12-slim

WORKDIR /app

# system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
  && rm -rf /var/lib/apt/lists/*

# install uv
RUN pip install --no-cache-dir uv

# install deps (uv.lock появится после uv sync локально; в CI/сервере тоже можно сделать uv lock)
COPY pyproject.toml uv.lock* /app/
RUN uv sync --no-dev

# copy app
COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

ENV PYTHONUNBUFFERED=1

CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
