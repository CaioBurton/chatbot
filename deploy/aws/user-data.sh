#!/bin/bash
# EC2 user-data (cloud-init) script — PROPESQI RAG Chatbot, AWS/Gemini mode.
#
# Installs Docker + the Compose plugin and starts the stack defined in
# docker-compose.aws.yml. This script does NOT create the .env file for you —
# copy it to the instance (e.g. via `scp` or AWS Systems Manager) BEFORE the
# stack starts, or the containers will fail on missing required variables.
#
# Intended flow:
#   1. Launch EC2 with this file as user-data.
#   2. Once the instance is running, scp the repo (or `git clone` it) and your
#      real `.env` (based on .env.aws.example) into /opt/propesqi.
#   3. Run: cd /opt/propesqi && docker compose -f docker-compose.aws.yml up -d
#
# This script only prepares the instance; it deliberately does NOT run
# `docker compose up` itself, since the .env file (secrets) must be placed
# first by whoever provisions the box.

set -euo pipefail

# ---- Docker Engine + Compose plugin ---------------------------------------
dnf update -y || apt-get update -y
if command -v dnf >/dev/null 2>&1; then
    dnf install -y docker
    systemctl enable --now docker
    dnf install -y docker-compose-plugin || true
else
    apt-get install -y ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable --now docker
fi

usermod -aG docker ec2-user 2>/dev/null || usermod -aG docker ubuntu 2>/dev/null || true

mkdir -p /opt/propesqi
echo "Docker installed. Copy the repo + .env into /opt/propesqi, then run:"
echo "  cd /opt/propesqi && docker compose -f docker-compose.aws.yml up -d"
