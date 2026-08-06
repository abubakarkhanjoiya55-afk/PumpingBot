# Base image for Cursor cloud agents working on PumpingBot.
# Do not COPY the project — Cursor checks out the repo into the workspace.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    build-essential \
    python3 \
    python3-pip \
    python3-venv \
    python3.12-venv \
    libjpeg-turbo8 \
    zlib1g \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --break-system-packages --upgrade pip

WORKDIR /workspace
