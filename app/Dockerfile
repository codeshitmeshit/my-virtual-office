FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir websockets "lark-oapi>=1.7,<2"

# Copy application files
COPY app/ .
COPY integrations/feishu-channel-worker/ /integrations/feishu-channel-worker/
RUN cd /integrations/feishu-channel-worker \
    && npm ci --omit=dev --ignore-scripts --no-audit --no-fund \
    && npm cache clean --force

# Create data directory
RUN mkdir -p /data

# Default environment
ENV VO_STATUS_DIR=/data \
    VO_OPENCLAW_PATH=/openclaw \
    VO_PORT=8090 \
    VO_WS_PORT=8091

EXPOSE 8090 8091

RUN chmod +x entrypoint.sh

CMD ["sh", "entrypoint.sh"]
