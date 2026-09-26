FROM python:3.11-slim

WORKDIR /opt/pihole-speedtest

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 speedtest \
    && mkdir -p /data \
    && chown speedtest:speedtest /data

USER speedtest
VOLUME ["/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=3).close()'

CMD ["pihole-speedtest", "serve", "--database", "/data/speedtest.db", "--host", "0.0.0.0", "--port", "8765", "--collection-binary", "/usr/local/bin/speedtest", "--collection-lock-file", "/data/speedtest.db.collect.lock"]
