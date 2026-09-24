FROM python:3.11-slim

WORKDIR /opt/pihole-speedtest

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 speedtest

USER speedtest
VOLUME ["/data"]
EXPOSE 8765

CMD ["pihole-speedtest", "serve", "--database", "/data/speedtest.db", "--host", "0.0.0.0", "--port", "8765"]
