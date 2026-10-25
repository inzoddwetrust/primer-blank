# Backend image, three stages; the last one is the default target.
#
#   builder  runtime dependencies from requirements.lock, hashes required
#   test     runtime + dev dependencies + tests/: primer.yaml test.target
#   runtime  what runs on a box: no tests, no dev tools, no documents
#
# PRIMER_RELEASE and PRIMER_COMMIT are build arguments the machine passes to
# every build (contract 3 rule 19); /health and every log line carry them.
# A build without either stops at the first RUN of `base` with its name.

FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.lock ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r requirements.lock

FROM python:3.12-slim AS base
ARG PRIMER_RELEASE
ARG PRIMER_COMMIT
RUN : "${PRIMER_RELEASE:?PRIMER_RELEASE build argument is not set}" \
 && : "${PRIMER_COMMIT:?PRIMER_COMMIT build argument is not set}"
RUN groupadd --gid 1000 blank && useradd --uid 1000 --gid blank --shell /bin/sh blank
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini logging.json ./
COPY migrations/ ./migrations/
COPY primer_report/ ./primer_report/
COPY app/ ./app/
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PRIMER_RELEASE="${PRIMER_RELEASE}" \
    PRIMER_COMMIT="${PRIMER_COMMIT}"

FROM base AS test
COPY requirements-dev.lock pyproject.toml ./
RUN pip install --no-cache-dir --require-hashes -r requirements-dev.lock
COPY tests/ ./tests/
USER blank

FROM base AS runtime
USER blank
EXPOSE 8000
CMD ["uvicorn", "--factory", "app.main:create_app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--log-config", "logging.json", "--proxy-headers"]
