FROM python:3.12-slim AS builder

ARG PLAYWRIGHT_BROWSERS=firefox

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        python3-dev \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==1.8.2

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false && \
    poetry install --without dev --no-root --no-interaction --no-ansi --no-cache

COPY README.md ./
COPY src/ ./src/
COPY provider_configs/ ./provider_configs/
COPY config.example.yaml ./config.yaml

RUN poetry install --only-root --no-interaction --no-ansi

FROM python:3.12-slim AS runtime

ARG PLAYWRIGHT_BROWSERS=firefox

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    PYTHONPATH=/app:/app/src \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    POETRY_VERBOSITY=-1 \
    POETRY_NO_INTERACTION=1 \
    IN_DOCKER=1

WORKDIR /app

# Install runtime dependencies including Playwright system dependencies for Firefox
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        # Basic utilities
        xvfb \
        wget \
        unzip \
        socat \
        netcat-openbsd \
        curl \
        procps \
        inotify-tools \
        supervisor \
        # Playwright Firefox dependencies (complete set for headless operation)
        libnss3 \
        libnspr4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libdbus-1-3 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libpango-1.0-0 \
        libcairo2 \
        libasound2 \
        libatspi2.0-0 \
        libwayland-client0 \
        # GTK3 and additional dependencies for Firefox
        libgtk-3-0 \
        libgdk-pixbuf-2.0-0 \
        libpangocairo-1.0-0 \
        libcairo-gobject2 \
        libxcursor1 \
    && rm -rf /var/lib/apt/lists/*

# Install DuckDB CLI
ARG TARGETARCH
RUN case "${TARGETARCH}" in \
        amd64) DUCKDB_ARCH="linux-amd64" ;; \
        arm64) DUCKDB_ARCH="linux-arm64" ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    wget -q https://github.com/duckdb/duckdb/releases/download/v1.4.1/duckdb_cli-${DUCKDB_ARCH}.zip && \
    unzip -q duckdb_cli-${DUCKDB_ARCH}.zip -d /usr/local/bin/ && \
    chmod +x /usr/local/bin/duckdb && \
    rm duckdb_cli-${DUCKDB_ARCH}.zip

COPY --from=builder /usr/local /usr/local

# Install only Firefox browser (not Chromium or WebKit)
RUN playwright install ${PLAYWRIGHT_BROWSERS} && \
    # Clean up Playwright cache and unnecessary files
    rm -rf /ms-playwright/.links && \
    rm -rf /ms-playwright/*-driver && \
    # Remove any browsers that aren't Firefox (shouldn't exist but just in case)
    find /ms-playwright -type d -name "chromium-*" -exec rm -rf {} + 2>/dev/null || true && \
    find /ms-playwright -type d -name "webkit-*" -exec rm -rf {} + 2>/dev/null || true

COPY --from=builder /build/src ./src
COPY --from=builder /build/provider_configs ./provider_configs
COPY --from=builder /build/config.yaml ./config.yaml

COPY --from=builder /build/pyproject.toml ./pyproject.toml
COPY --from=builder /build/poetry.lock ./poetry.lock

# Suppress Poetry virtualenv warnings
RUN poetry config virtualenvs.create false && \
    poetry config warnings.export false

COPY docker/scripts/entrypoint.sh /entrypoint.sh
COPY docker/scripts/run_migrations.sh /run_migrations.sh
COPY docker/scripts/watch_and_sync.sh /watch_and_sync.sh
COPY docker/scripts/poetry_wrapper.sh /usr/local/bin/poetry-run
COPY docker/scripts/init_ui.sql /init_ui.sql
COPY docker/scripts/init_duckdb.py /init_duckdb.py
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

RUN chmod +x /entrypoint.sh /run_migrations.sh /watch_and_sync.sh /usr/local/bin/poetry-run

# Create dummy xdg-open to silence DuckDB browser open attempts (no GUI in Docker)
RUN echo '#!/bin/sh\nexit 0' > /usr/local/bin/xdg-open && chmod +x /usr/local/bin/xdg-open

RUN mkdir -p /app/data && ln -s /app/data /data

EXPOSE 4213

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:4213/ || exit 1

ENTRYPOINT ["/entrypoint.sh"]

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

LABEL maintainer="Robin Schulz <bulletinmybeard@gmail.com>"
LABEL version="1.0.0"
LABEL description="Self-hosted price tracker with local data storage"
LABEL org.opencontainers.image.source="https://github.com/bulletinmybeard/price-scout"
