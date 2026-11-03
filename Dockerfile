# Kohu API + UI. FFmpeg is needed for video frames and audio.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

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
