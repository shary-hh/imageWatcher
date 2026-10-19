# Arena de pruebas reproducible para imageWatcher (pytest).
#   docker build -f arena/Dockerfile -t imagewatcher-arena .
#   docker run --rm imagewatcher-arena
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then \
        sed -i 's/^Components: main.*/Components: main restricted universe multiverse/' /etc/apt/sources.list.d/ubuntu.sources; \
    fi \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
        python3-pil python3-xlib python3-pip \
        ffmpeg xvfb x11-utils ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN python3 -m pip install --break-system-packages --no-cache-dir -r requirements-dev.txt \
 && chmod +x arena/run_arena.sh run.sh packaging/*.sh

CMD ["arena/run_arena.sh"]
