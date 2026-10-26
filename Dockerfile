# Production image: migrations run on start, then uvicorn behind the cluster's TLS proxy.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY noisebins ./noisebins
RUN pip install .

COPY alembic.ini ./
COPY alembic ./alembic

RUN useradd --system --uid 10001 noisebins && mkdir -p /app/data/blobs && chown -R noisebins /app/data
USER noisebins

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn noisebins.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
