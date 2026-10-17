# API image. Build from the repository root:  docker build -f apps/api/Dockerfile .
# The layout mirrors the repo (/app/apps/api and /app/packages/contracts) because the API serves the OpenAPI
# contract from a path relative to the repo root.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app/apps/api

COPY apps/api/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY apps/api/ ./
COPY packages/contracts/ /app/packages/contracts/

# Cloud Run sets PORT. The job worker and scheduler run inside this process, so run exactly one instance
# with CPU always allocated (see deploy/gcp/README.md).
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn asgi:app --host 0.0.0.0 --port ${PORT}"]
