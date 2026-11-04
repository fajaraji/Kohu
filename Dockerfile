# Kohu API + UI. Ubuntu 24.04 ships Python 3.12; FFmpeg is needed for
# video frames and audio.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /app
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

COPY api api
COPY ui ui
COPY corpus corpus
COPY seed.sh docker-entrypoint.sh ./
RUN chmod +x seed.sh docker-entrypoint.sh \
 && useradd --create-home kohu && chown -R kohu /app
USER kohu

ENV PYTHON=python PORT=8000
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
