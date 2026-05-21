FROM python:3.13-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tmux \
        asciinema \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir \
    flask==3.1.0 \
    requests==2.32.3 \
    pytest==8.3.5 \
    pytest-json-ctrf==0.3.5

WORKDIR /app
