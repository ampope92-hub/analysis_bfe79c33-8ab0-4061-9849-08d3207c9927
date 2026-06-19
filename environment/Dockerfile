FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

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

# Ship the half-finished, buggy project the agent must debug and complete.
COPY skeleton/ /app/
RUN chmod 644 /app/game.py
