# ───────────────────────────────────────────────────────────
# ThermVate Orchestrator — Docker Image
# ───────────────────────────────────────────────────────────
# Multi-stage build: slim runtime image for the orchestrator.
# Includes BAC0 (BACnet), paho-mqtt, InfluxDB client, etc.
# ───────────────────────────────────────────────────────────

FROM python:3.12-slim-bookworm AS builder

RUN apt-get update -qq && apt-get install -y -qq \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY orchestrator/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        --requirement requirements.txt \
        BAC0>=21.12.0 \
        bacpypes>=0.18.0 \
        minimalmodbus>=2.1.0 \
        fastapi>=0.100.0 \
        uvicorn>=0.22.0 \
        pydantic>=2.0.0 \
        psutil>=5.9.0 \
        aiofiles>=23.2.0

# ── Runtime Stage ─────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

RUN apt-get update -qq && apt-get install -y -qq \
    netcat-openbsd \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create thermvate user (non-root)
RUN groupadd -r thermvate && \
    useradd -r -g thermvate -d /home/thermvate -s /usr/sbin/nologin thermvate && \
    mkdir -p /home/thermvate /etc/thermvate /var/lib/thermvate /var/log/thermvate && \
    chown -R thermvate:thermvate /home/thermvate /var/lib/thermvate /var/log/thermvate

# Copy Python + deps from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy orchestrator code
WORKDIR /app
COPY orchestrator/ ./orchestrator/

# Copy default config
COPY docker/config.dev.yaml /etc/thermvate/config.yaml

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

USER thermvate

# Default command — orchestrator main
ENTRYPOINT ["python", "-m", "orchestrator.src.main"]
